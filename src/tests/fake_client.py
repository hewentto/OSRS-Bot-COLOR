"""
Test helpers that stand in for a live game client. A FakeScreen is a plain image that Rectangles are
"screenshotted" from (tests patch `Rectangle.screenshot` to read from it), so vision code can be exercised
without RuneLite running.
"""
from pathlib import Path
from typing import List

import cv2
import numpy as np

from utilities.api.vision_api import WIKI_BRIGHTNESS, render_at_brightness
from utilities.geometry import Rectangle

SRC = Path(__file__).parent.parent
ITEM_SPRITES = SRC.joinpath("images", "bot", "items")
EMPTY_SLOT_IMG = SRC.joinpath("model", "osrs", "WillowsDad", "WillowsDad_images", "emptyslot.png")

INVENTORY_BROWN_BGR = (41, 53, 62)


class FakeScreen:
    def __init__(self, width: int = 800, height: int = 600):
        self.img = np.zeros((height, width, 3), dtype=np.uint8)

    def grab(self, rect: Rectangle) -> np.ndarray:
        return self.img[rect.top : rect.top + rect.height, rect.left : rect.left + rect.width].copy()

    def fill(self, rect: Rectangle, bgr) -> None:
        self.img[rect.top : rect.top + rect.height, rect.left : rect.left + rect.width] = bgr

    def paste(self, image: np.ndarray, left: int, top: int) -> None:
        """Pastes an image onto the screen. Transparent pixels (if there's an alpha channel) are skipped."""
        h, w = image.shape[:2]
        region = self.img[top : top + h, left : left + w]
        if image.shape[2] == 4:
            opaque = image[:, :, 3] > 0
            region[opaque] = image[:, :, :3][opaque]
        else:
            region[:] = image

    def paste_centered(self, image: np.ndarray, rect: Rectangle) -> None:
        h, w = image.shape[:2]
        self.paste(image, rect.left + (rect.width - w) // 2, rect.top + (rect.height - h) // 2)


class FakeMouse:
    def __init__(self):
        self.events = []

    def move_to(self, point, **kwargs):
        self.events.append(("move", tuple(point)))

    def click(self, **kwargs):
        self.events.append(("click",))
        return True


class FakeWindow:
    """Mirrors the layout math in utilities.window.Window for a control panel at a fixed position."""

    def __init__(self):
        cp_left, cp_top = 500, 200
        self.control_panel = Rectangle(cp_left, cp_top, 241, 335)
        self.game_view = Rectangle(0, 0, 480, 334)
        self.current_action = Rectangle(10, 25, 128, 20)
        self.chat = Rectangle(0, 340, 480, 140)
        self.inventory_slots: List[Rectangle] = []
        y = 44 + cp_top
        for _ in range(7):
            x = 40 + cp_left
            for _ in range(4):
                self.inventory_slots.append(Rectangle(left=x, top=y, width=36, height=32))
                x += 36 + 6
            y += 32 + 4
        self.cp_tabs = [Rectangle(left=8 + cp_left + i * 33, top=4 + cp_top, width=29, height=26) for i in range(7)]


class FakeBot:
    def __init__(self):
        self.win = FakeWindow()
        self.mouse = FakeMouse()
        self.logs: List[str] = []
        self.total_xp_readings: List[int] = []
        self.hp = -1
        self.run_energy = -1

    def log_msg(self, msg: str, overwrite=False):
        self.logs.append(msg)

    def get_total_xp(self) -> int:
        """Pops queued readings; the final reading repeats forever."""
        if len(self.total_xp_readings) > 1:
            return self.total_xp_readings.pop(0)
        return self.total_xp_readings[0]

    def get_hp(self) -> int:
        return self.hp

    def get_run_energy(self) -> int:
        return self.run_energy


def load_sprite(name: str) -> np.ndarray:
    return cv2.imread(str(ITEM_SPRITES.joinpath(name)), cv2.IMREAD_UNCHANGED)


def draw_text(screen: FakeScreen, left: int, top: int, text: str, font: dict, bgr) -> None:
    """Draws text the way the game does: OCR font glyphs side by side in a solid color."""
    x = left
    for char in text:
        glyph = font[char]
        h, w = glyph.shape
        screen.img[top : top + h, x : x + w][glyph > 0] = bgr
        x += w


def draw_stack_number(screen: FakeScreen, slot: Rectangle, text: str) -> None:
    """Draws a yellow stack count with a black drop shadow in the top-left of a slot, like the game does."""
    for offset, bgr in ((1, (0, 0, 0)), (0, (0, 255, 255))):
        cv2.putText(screen.img, text, (slot.left + offset, slot.top + 9 + offset), cv2.FONT_HERSHEY_PLAIN, 0.8, bgr, 1, cv2.LINE_8)


def draw_inventory(screen: FakeScreen, bot: FakeBot, items: dict, brightness: float = WIKI_BRIGHTNESS) -> None:
    """
    Draws an inventory onto the screen.
    Args:
        items: Maps slot index -> sprite filename. Slots not listed are drawn empty.
        brightness: The game's brightness setting, which items (but not the interface) are drawn with.
    """
    screen.fill(bot.win.control_panel, INVENTORY_BROWN_BGR)
    empty_patch = cv2.imread(str(EMPTY_SLOT_IMG))
    for i, slot in enumerate(bot.win.inventory_slots):
        screen.paste_centered(empty_patch, slot)
        if i in items:
            screen.paste_centered(render_at_brightness(load_sprite(items[i]), brightness), slot)
