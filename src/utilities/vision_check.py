"""
Diagnoses "Failed to initialize window". Screenshots the live RuneLite client and scores each UI template that
`Window.initialize()` relies on, so you can see which region wasn't found, how far off it was, and whether Windows
display scaling is the reason.

Run from the `src` folder while RuneLite is open and logged in:
    python -m utilities.vision_check
"""
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

import cv2
import numpy as np
import pywinctl

import utilities.imagesearch as imsearch
from utilities.geometry import Rectangle

# `imsearch.search_img_in_rect()` counts a template as found when its score is below this.
FOUND_BELOW = 0.15
UI_TEMPLATES = imsearch.BOT_IMAGES.joinpath("ui_templates")
# What each template locates. `Window.initialize()` needs the chatbox, the control panel, and either one of the minimaps.
TEMPLATES = {"chat.png": "chatbox", "inv.png": "control panel", "minimap.png": "minimap (resizable)", "minimap_fixed.png": "minimap (fixed)"}
SCREENSHOT = Path(__file__).parent.parent.joinpath("vision_check_client.png")


def score_template(template: cv2.Mat, client_img: cv2.Mat, display_scale: float = 1):
    """
    Finds the template's best position in the client, scored the same way `imagesearch` does.
    Args:
        template: The UI template to look for.
        client_img: A screenshot of the client.
        display_scale: If the client was stretched by display scaling (E.g., 2.5 for 250%), the screenshot is shrunk by
                       this much first to show whether the template would match at 100%.
    Returns:
        A Tuple(score, x, y), where a score of 0 is a pixel-perfect match.
    """
    if display_scale != 1:
        client_img = cv2.resize(client_img, None, fx=1 / display_scale, fy=1 / display_scale, interpolation=cv2.INTER_AREA)
    if template.ndim < 3 or template.shape[2] != 4:
        template = cv2.cvtColor(template, cv2.COLOR_BGR2BGRA)
    if template.shape[0] > client_img.shape[0] or template.shape[1] > client_img.shape[1]:
        return 1.0, 0, 0
    alpha = cv2.merge([template[:, :, 3]] * 3)
    scores = np.nan_to_num(cv2.matchTemplate(client_img, template[:, :, :3], cv2.TM_SQDIFF_NORMED, mask=alpha), nan=1.0, posinf=1.0)
    score, _, (x, y), _ = cv2.minMaxLoc(scores)
    return float(score), x, y


def display_scaling(window_handle: int):
    """
    Returns a Tuple(scale of the monitor the window is on, whether Windows is stretching the window to that scale).
    Windows stretches the picture of any program that doesn't declare itself DPI-aware, which RuneLite doesn't by default.
    """
    user32, shcore = ctypes.windll.user32, ctypes.windll.shcore
    dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
    shcore.GetDpiForMonitor(user32.MonitorFromWindow(window_handle, 2), 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
    is_dpi_unaware = user32.GetAwarenessFromDpiAwarenessContext(user32.GetWindowDpiAwarenessContext(window_handle)) == 0
    return dpi_x.value / 96, is_dpi_unaware


def main() -> None:
    windows = pywinctl.getWindowsWithTitle("RuneLite")
    if not windows:
        sys.exit("No window titled 'RuneLite' was found. Is the client open?")
    client = windows[0]
    # The bot focuses the client before looking at it, so do the same (a screenshot captures whatever is on top).
    client.activate()
    time.sleep(1)
    scale, is_stretched = display_scaling(client.getHandle())
    is_stretched = is_stretched and scale != 1
    print(f"Window '{client.title}': position ({client.left}, {client.top}), size {client.width}x{client.height}")
    print(f"Monitor display scaling: {scale:.0%}. Windows is {'STRETCHING' if is_stretched else 'not stretching'} the client.")
    client_img = Rectangle(client.left, client.top, client.width, client.height).screenshot()
    cv2.imwrite(str(SCREENSHOT), client_img)
    print(f"Screenshot saved to {SCREENSHOT}\n")

    for filename, region in TEMPLATES.items():
        template = cv2.imread(str(UI_TEMPLATES.joinpath(filename)), cv2.IMREAD_UNCHANGED)
        score, x, y = score_template(template, client_img)
        line = f"{'FOUND' if score < FOUND_BELOW else 'not found':>9}  {region:<20} score {score:.3f} (needs < {FOUND_BELOW}) at ({x}, {y})"
        if is_stretched and score >= FOUND_BELOW:
            unscaled_score = score_template(template, client_img, display_scale=scale)[0]
            line += f"  |  with the scaling undone: {unscaled_score:.3f} {'FOUND' if unscaled_score < FOUND_BELOW else 'not found'}"
        print(line)

    if is_stretched:
        print(
            f"\nThe client is drawn at {scale:.0%} size, but everything the bots look for (UI templates, fonts, item sprites) is"
            "\npixel-exact at 100%. Fix: close RuneLite, open 'RuneLite (configure)' from the Start menu, set Scale to 1, Save,"
            "\nthen launch RuneLite again. The game will look small on this monitor; that's what 1:1 pixels looks like."
        )


if __name__ == "__main__":
    main()
