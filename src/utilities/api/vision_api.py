"""
Vision-based replacement for the MorgHTTPClient and StatusSocket plugin APIs.

RuneLite disabled both plugins on the Plugin Hub (2024-05-26), so nothing in here talks to the game client.
Everything is answered by looking at the screen: template matching, OCR and frame differencing. Method names and
return values mirror `MorgHTTPSocket`/`StatusSocket` so bots can swap `MorgHTTPSocket()` for `VisionAPI(self)`.

Item lookups need a sprite for each item in `src/images/bot/items/`, named after the constant in `item_ids.py`
(E.g., `ids.WILLOW_LOGS` -> `Willow_logs.png`). Sprites that are missing are treated as "item not found", logged to
the bot once, and recorded in `src/vision_missing_sprites.json`. Run `python -m utilities.vision_todo` from `src`
for the full checklist of sprites each bot still needs.
"""
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple, Union

import cv2
import numpy as np

import utilities.api.item_ids as item_ids
import utilities.color as clr
import utilities.imagesearch as imsearch
import utilities.ocr as ocr
from utilities.geometry import Rectangle

ITEM_SPRITES = imsearch.BOT_IMAGES.joinpath("items")
EMPTY_SLOT_IMG = imsearch.BOT_IMAGES.joinpath("ui_templates", "empty_slot.png")
MISSING_SPRITES_LOG = Path(__file__).parent.parent.parent.joinpath("vision_missing_sprites.json")

_ITEM_NAMES: Dict[int, str] = {value: name for name, value in vars(item_ids).items() if isinstance(value, int) and name.isupper()}


def sprite_filenames(item_id: int) -> List[str]:
    """
    Returns the sprite filenames that may represent an item, most specific first.
    Variants that RuneLite suffixes with their ID (E.g., BIRD_NEST_5071) fall back to the base item's sprite.
    """
    name = _ITEM_NAMES.get(item_id)
    if name is None:
        return []
    filenames = [f"{name.capitalize()}.png"]
    if base_name := re.fullmatch(rf"(.+)_{item_id}", name):
        filenames.append(f"{base_name[1].capitalize()}.png")
    return filenames


# The game draws items with each color (0-1) raised to the power of its brightness setting, from 0.9 (darkest) down to
# 0.6 (brightest). The interface isn't affected. OSRS Wiki sprites are drawn at the brightest setting.
WIKI_BRIGHTNESS = 0.6
_DARKEST_BRIGHTNESS = 0.9


def render_at_brightness(sprite: cv2.Mat, brightness: float) -> cv2.Mat:
    """
    Redraws an OSRS Wiki sprite the way the game draws that item at another brightness setting.
    """
    if brightness == WIKI_BRIGHTNESS:
        return sprite
    rendered = sprite.copy()
    rendered[:, :, :3] = np.round(255 * (sprite[:, :, :3] / 255) ** (brightness / WIKI_BRIGHTNESS))
    # Pure black means transparent to the game, so it bumps any color that darkens to black up to (0, 0, 1) RGB.
    # This is also why item outlines are that color rather than black.
    became_black = (sprite[:, :, :3].max(axis=2) > 0) & (rendered[:, :, :3].max(axis=2) == 0)
    rendered[became_black, 0] = 1
    return rendered


def estimate_brightness(sprite: cv2.Mat, seen: cv2.Mat) -> Union[float, None]:
    """
    Works out the game's brightness setting from how an item on screen compares to its OSRS Wiki sprite.
    Args:
        sprite: The item's BGRA Wiki sprite.
        seen: The BGR pixels on screen where the sprite was found (same size as the sprite).
    Returns:
        The brightness, or None if the two don't have enough comparable pixels.
    """
    expected = sprite[:, :, :3].astype(np.float64)
    seen = seen.astype(np.float64)
    # Mid-tones say the most: near-black and near-white barely move with brightness, and transparent pixels say nothing.
    comparable = (sprite[:, :, 3:] > 0) & (expected > 30) & (expected < 230) & (seen > 5) & (seen < 250)
    if comparable.sum() < 30:
        return None
    darkening = np.median(np.log(seen[comparable] / 255) / np.log(expected[comparable] / 255))
    return float(np.clip(darkening * WIKI_BRIGHTNESS, WIKI_BRIGHTNESS, _DARKEST_BRIGHTNESS))


# Stack counts are drawn over the top-left of an item in one of these exact colors (BGR), with a black drop shadow.
_STACK_NUMBER_COLORS = [(0, 255, 255), (255, 255, 255), (128, 255, 0)]
# A sprite scoring worse than this isn't the item, no matter what's drawn over it.
_STACK_NUMBER_RESCORE_LIMIT = 0.3


def sprite_match_score(sprite: cv2.Mat, img: cv2.Mat) -> float:
    """
    Scores how well a sprite matches its best position in an image. See `find_sprite()`.
    """
    return find_sprite(sprite, img)[0]


def find_sprite(sprite: cv2.Mat, img: cv2.Mat) -> Tuple[float, int, int]:
    """
    Finds the position in an image that a sprite matches best, ignoring any stack number drawn over it.
    Args:
        sprite: The BGRA sprite to look for.
        img: The BGR image to look in (E.g., a screenshot of one inventory slot).
    Returns:
        A Tuple(score, x, y). The score is the normalized squared difference, where 0 is a pixel-perfect match and 1 is
        no match at all. The position is the top-left corner of the match within the image.
    """
    h, w = sprite.shape[:2]
    if h > img.shape[0] or w > img.shape[1]:
        return 1.0, 0, 0
    base = sprite[:, :, :3]
    opaque = sprite[:, :, 3] > 0 if sprite.shape[2] == 4 else np.ones((h, w), dtype=bool)
    mask = cv2.merge([opaque.astype(np.uint8) * 255] * 3)
    scores = np.nan_to_num(cv2.matchTemplate(img, base, cv2.TM_SQDIFF_NORMED, mask=mask), nan=1.0, posinf=1.0)
    score, _, (x, y), _ = cv2.minMaxLoc(scores)
    if score == 0 or score > _STACK_NUMBER_RESCORE_LIMIT:
        return float(score), x, y

    # Rescore the best position without the pixels that a stack number (or its shadow) covers.
    number = np.zeros(img.shape[:2], dtype=bool)
    for color in _STACK_NUMBER_COLORS:
        number |= np.all(img == color, axis=2)
    shadow = np.zeros_like(number)
    shadow[1:, 1:] = number[:-1, :-1]
    compare = opaque & ~(number | shadow)[y : y + h, x : x + w]
    if not number.any() or compare.sum() < opaque.sum() / 2:
        return float(score), x, y
    seen = img[y : y + h, x : x + w][compare].astype(np.float64)
    expected = base[compare].astype(np.float64)
    denominator = np.sqrt((seen**2).sum() * (expected**2).sum())
    return (float(((seen - expected) ** 2).sum() / denominator) if denominator else 1.0), x, y


def frame_difference(previous_frame: cv2.Mat, current_frame: cv2.Mat) -> float:
    """
    Measures how much changed between two screenshots of the same area. Created by @Gang on the OSBC discord server.
    Returns:
        The changed area as a percentage of the frame's size.
    """
    difference = cv2.absdiff(cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY), cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY))
    _, threshold = cv2.threshold(difference, 30, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return sum(cv2.contourArea(contour) for contour in contours) / previous_frame.size * 100


# Plugin API calls that can't be answered by looking at the screen, and the "unknown" value each returns instead.
UNSUPPORTED_CALLS = {
    "get_animation": -1,
    "get_animation_id": -1,
    "get_animation_data": [],
    "get_skill_level": -1,
    "get_skill_xp": -1,
    "get_skill_xp_gained": -1,
    "get_real_level": -1,
    "get_boosted_level": -1,
    "get_is_boosted": False,
    "get_is_player_praying": False,
    "get_game_tick": -1,
    "get_player_position": (-1, -1, -1),
    "get_player_region_data": (-1, -1, -1),
    "get_camera_position": None,
    "get_mouse_position": (-1, -1),
    "get_interaction_code": None,
    "get_npc_hitpoints": None,
    "get_inv_item_stack_amount": 0,
    "get_equipped_item_quantity": 0,
    "get_player_equipment": [],
    "get_equipment_stats": [],
}


class VisionAPI:
    # Max normalized squared difference for a sprite to count as found (0 is a pixel-perfect match).
    # Similar items score surprisingly close to each other (Logs vs Oak logs: 0.011), so keep this tight.
    ITEM_MATCH_CONFIDENCE = 0.005
    # Max normalized squared difference for the middle of a slot to count as bare inventory background.
    EMPTY_SLOT_CONFIDENCE = 0.15
    # Pixels of slack around the inventory when screenshotting it, in case the control panel was located a pixel off.
    INVENTORY_PADDING = 2
    # The sliver of the game view that the player's character stands in: (scale_width, scale_height, anchor_x, anchor_y).
    PLAYER_REGION = (0.02, 0.04, 0.505, 0.495)
    # Percentage of the player region that must change between frames for the player to count as animating.
    IDLE_DIFFERENCE_THRESHOLD = 0.3
    # Seconds between the frames that get compared.
    IDLE_FRAME_INTERVAL = 0.3
    # The bottom portion of the chatbox that holds the latest message.
    LATEST_CHAT_MESSAGE_HEIGHT = 0.37
    EQUIPMENT_TAB, INVENTORY_TAB = 4, 3

    def __init__(
        self,
        bot,
        sprite_dir: Path = ITEM_SPRITES,
        missing_log_path: Path = MISSING_SPRITES_LOG,
    ):
        """
        Args:
            bot: The bot this API looks at the screen for. Its `win`, `mouse` and `log_msg` are used.
            sprite_dir: Folder containing the item sprites.
            missing_log_path: JSON file where sprites that were needed but not found get recorded.
        """
        self.bot = bot
        self.sprite_dir = Path(sprite_dir)
        self.missing_log_path = Path(missing_log_path)
        self.__reported_missing = set()
        self.__reported_unsupported = set()
        self.brightness = None  # The game's brightness setting. Detected the first time an item is recognised.
        self.__sprites_by_shape = None  # Loaded the first time look-alikes are needed
        self.__empty_slot_img = cv2.imread(str(EMPTY_SLOT_IMG), cv2.IMREAD_UNCHANGED)

    # --- Inventory (no sprites needed) ---
    def get_inv(self) -> List[dict]:
        """
        Gets the occupied inventory slots. Unlike the plugin APIs, the items themselves are unknown.
        Returns:
            A list of dicts, each containing the `index` of a slot that has an item in it.
        """
        inventory_img, left, top = self.__grab_inventory()
        slots = self.bot.win.inventory_slots
        return [{"index": i} for i, slot in enumerate(slots) if not self.__is_slot_empty(self.__slot_img(inventory_img, slot, left, top))]

    def get_is_inv_full(self) -> bool:
        """
        Checks if player's inventory is full. The inventory tab must be open.
        """
        return len(self.get_inv()) == len(self.bot.win.inventory_slots)

    def get_is_inv_empty(self) -> bool:
        """
        Checks if player's inventory is empty. The inventory tab must be open.
        """
        return not self.get_inv()

    def __is_slot_empty(self, slot_img: cv2.Mat) -> bool:
        h, w = slot_img.shape[:2]
        middle = slot_img[h // 4 : h - h // 4, w // 4 : w - w // 4]
        return sprite_match_score(self.__empty_slot_img, middle) <= self.EMPTY_SLOT_CONFIDENCE

    # --- Inventory (needs item sprites) ---
    def get_inv_item_indices(self, item_id: Union[List[int], int]) -> List[int]:
        """
        For the given item ID(s), returns a sorted list of inventory slot indexes that the item exists in.
        """
        return sorted(slot for slots in self.__slots_by_item(item_id).values() for slot in slots)

    def get_first_occurrence(self, item_id: Union[List[int], int]) -> Union[int, List[int]]:
        """
        For the given item ID(s), returns the first inventory slot index that the item exists in.
        Returns:
            If a single item ID is provided, returns an integer (or -1).
            If a list of item IDs is provided, returns the first slot of each item found, sorted (or empty list).
        """
        first_slots = sorted(min(slots) for slots in self.__slots_by_item(item_id).values() if slots)
        if isinstance(item_id, int):
            return first_slots[0] if first_slots else -1
        return first_slots

    # Older WillowsDad bots call this by its previous name.
    get_inv_item_first_indice = get_first_occurrence

    def get_if_item_in_inv(self, item_id: Union[List[int], int]) -> bool:
        """
        Checks if any of the given item ID(s) are in the inventory.
        """
        return any(self.__slots_by_item(item_id).values())

    def __slots_by_item(self, item_id: Union[List[int], int]) -> Dict[int, List[int]]:
        """
        Maps each requested item ID to the inventory slots it was seen in.
        """
        sprites = self.__load_sprites(item_id)
        if not sprites:
            return {}
        inventory_img, left, top = self.__grab_inventory()
        slot_imgs = [self.__slot_img(inventory_img, slot, left, top, self.INVENTORY_PADDING) for slot in self.bot.win.inventory_slots]
        return {id_: [i for i, slot_img in enumerate(slot_imgs) if self.__is_sprite_in(sprite, slot_img)] for id_, sprite in sprites.items()}

    def __is_sprite_in(self, sprite: cv2.Mat, img: cv2.Mat) -> bool:
        if self.brightness is None:
            self.__detect_brightness(sprite, img)
        brightness = self.brightness or WIKI_BRIGHTNESS
        score, x, y = find_sprite(render_at_brightness(sprite, brightness), img)
        if score > self.ITEM_MATCH_CONFIDENCE:
            return False
        # Recolors of one model can all pass the threshold (Compost vs Supercompost: 0.0014), so the closest sprite wins.
        # They're only compared where the sprite was found, as a look-alike may legitimately be elsewhere in the image.
        found_img = img[y : y + sprite.shape[0], x : x + sprite.shape[1]]
        return all(sprite_match_score(render_at_brightness(look_alike, brightness), found_img) >= score for look_alike in self.__look_alikes(sprite))

    def __detect_brightness(self, sprite: cv2.Mat, img: cv2.Mat) -> None:
        """
        Sets `self.brightness` if the sprite, or one of its look-alikes, can be recognised in the image at some brightness.
        Look-alikes are included so that brightness is never guessed by forcing the wrong item to fit.
        """
        best_score, best_brightness = self.ITEM_MATCH_CONFIDENCE, None
        for candidate in [sprite] + self.__look_alikes(sprite):
            score, x, y = find_sprite(candidate, img)
            if score > _STACK_NUMBER_RESCORE_LIMIT:
                continue  # Not even the same shape
            brightness = WIKI_BRIGHTNESS
            if score > self.ITEM_MATCH_CONFIDENCE:
                brightness = estimate_brightness(candidate, img[y : y + candidate.shape[0], x : x + candidate.shape[1]])
                if brightness is None:
                    continue
                score = sprite_match_score(render_at_brightness(candidate, brightness), img)
            if score <= best_score:
                best_score, best_brightness = score, brightness
        if best_brightness is None:
            return
        self.brightness = best_brightness
        if best_brightness != WIKI_BRIGHTNESS:
            self.bot.log_msg(f"[VisionAPI] Detected game brightness {best_brightness:.2f} (item sprites are {WIKI_BRIGHTNESS}). Darkening sprites to match.")

    def __look_alikes(self, sprite: cv2.Mat) -> List[cv2.Mat]:
        """
        Gets the other sprites in the sprite folder that an item could be mistaken for: same size, different pixels.
        """
        if self.__sprites_by_shape is None:
            self.__sprites_by_shape = {}
            for path in self.sprite_dir.glob("*.png"):
                other = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                if other is not None:
                    self.__sprites_by_shape.setdefault(other.shape, []).append(other)
        return [other for other in self.__sprites_by_shape.get(sprite.shape, []) if not np.array_equal(other, sprite)]

    def __grab_inventory(self):
        """
        Screenshots the inventory once so every slot is judged from the same frame.
        Returns:
            The image, and the screen position of its top-left corner.
        """
        slots = self.bot.win.inventory_slots
        pad = self.INVENTORY_PADDING
        left, top = slots[0].left - pad, slots[0].top - pad
        right, bottom = slots[-1].left + slots[-1].width + pad, slots[-1].top + slots[-1].height + pad
        return Rectangle(left, top, right - left, bottom - top).screenshot(), left, top

    def __slot_img(self, inventory_img: cv2.Mat, slot: Rectangle, inv_left: int, inv_top: int, pad: int = 0) -> cv2.Mat:
        x, y = slot.left - inv_left - pad, slot.top - inv_top - pad
        return inventory_img[y : y + slot.height + 2 * pad, x : x + slot.width + 2 * pad]

    # --- Equipment (needs item sprites) ---
    def get_is_item_equipped(self, item_id: Union[int, List[int]]) -> bool:
        """
        Checks if the player has any of the given item(s) equipped by looking for them in the worn equipment tab.
        This clicks over to the equipment tab and back to the inventory, so avoid calling it in a tight loop.
        """
        sprites = self.__load_sprites(item_id)
        if not sprites:
            return False
        self.__open_tab(self.EQUIPMENT_TAB)
        equipment_img = self.bot.win.control_panel.screenshot()
        self.__open_tab(self.INVENTORY_TAB)
        return any(self.__is_sprite_in(sprite, equipment_img) for sprite in sprites.values())

    def __open_tab(self, tab: int) -> None:
        self.bot.mouse.move_to(self.bot.win.cp_tabs[tab].random_point())
        self.bot.mouse.click()
        time.sleep(0.4)

    # --- Player ---
    def get_is_player_idle(self, poll_seconds=1) -> bool:
        """
        Checks if the player's character stays still for the whole polling period.
        Args:
            poll_seconds: The number of seconds to watch the character for.
        Returns:
            False as soon as the character is seen animating, True if it never was.
        """
        player_region = self.bot.win.game_view.scale(*self.PLAYER_REGION)
        previous_frame = player_region.screenshot()
        stop_time = time.time() + poll_seconds
        while True:
            time.sleep(self.IDLE_FRAME_INTERVAL)
            current_frame = player_region.screenshot()
            if frame_difference(previous_frame, current_frame) >= self.IDLE_DIFFERENCE_THRESHOLD:
                return False
            if time.time() >= stop_time:
                return True
            previous_frame = current_frame

    def get_is_in_combat(self) -> bool:
        """
        Checks if the player is in combat by looking for an opponent's name in RuneLite's Opponent Information overlay.
        """
        return bool(ocr.extract_text(self.bot.win.current_action, ocr.PLAIN_12, clr.WHITE))

    def get_hitpoints(self):
        """
        Reads the player's hitpoints from the HP orb.
        Returns:
            A Tuple(current_hitpoints, -1). Maximum hitpoints can't be seen on screen.
        """
        return self.bot.get_hp(), -1

    def get_run_energy(self) -> int:
        """
        Reads the player's run energy from the run orb, or -1 if it couldn't be read.
        """
        return self.bot.get_run_energy()

    def wait_til_gained_xp(self, skill: str, timeout: int = 10) -> int:
        """
        Waits until the player has gained xp. XP is read from the total XP counter, so this can't tell skills apart.
        Args:
            skill: Unused. Kept so calls written for the plugin API still work.
            timeout: The maximum amount of time to wait for xp gain (seconds).
        Returns:
            The new total xp, or -1 if no XP was gained during the timeout or total XP couldn't be read.
        """
        starting_xp = self.bot.get_total_xp()
        if starting_xp == -1:
            self.bot.log_msg("[VisionAPI] Couldn't read total XP. Make sure the XP counter is showing beside the minimap.")
            return -1
        stop_time = time.time() + timeout
        while time.time() < stop_time:
            if (xp := self.bot.get_total_xp()) > starting_xp:
                return xp
            time.sleep(0.2)
        return -1

    # --- Chat ---
    def get_latest_chat_message(self) -> str:
        """
        Reads the game messages at the bottom of the chatbox. The chatbox must be opaque.
        Returns:
            The text without spaces (E.g., "Ican'treachthat!"), so check it with `in` rather than `==`.
        """
        latest = self.bot.win.chat.scale(scale_width=1, scale_height=self.LATEST_CHAT_MESSAGE_HEIGHT, anchor_x=0, anchor_y=1)
        return ocr.extract_text(latest, ocr.PLAIN_12, clr.BLACK)

    # --- Calls with no vision-based equivalent ---
    def __getattr__(self, name: str):
        if name not in UNSUPPORTED_CALLS:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        def unsupported(*args, **kwargs):
            fallback = UNSUPPORTED_CALLS[name]
            if name not in self.__reported_unsupported:
                self.__reported_unsupported.add(name)
                self.bot.log_msg(f"[VisionAPI] TODO: {name}() can't be answered by looking at the screen. Returning {fallback!r}.")
            return fallback

        return unsupported

    # --- Sprites ---
    def __load_sprites(self, item_id: Union[int, List[int]]) -> Dict[int, cv2.Mat]:
        """
        Loads the sprite of each given item ID, leaving out (and reporting) the ones that don't exist yet.
        """
        item_ids_ = [item_id] if isinstance(item_id, int) else item_id
        return {id_: sprite for id_ in item_ids_ if (sprite := self.__load_sprite(id_)) is not None}

    def __load_sprite(self, item_id: int) -> Union[cv2.Mat, None]:
        filenames = sprite_filenames(item_id)
        for filename in filenames:
            path = self.sprite_dir.joinpath(filename)
            if path.exists():
                return cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        self.__report_missing_sprite(item_id, filenames)
        return None

    def __report_missing_sprite(self, item_id: int, filenames: List[str]) -> None:
        if item_id in self.__reported_missing:
            return
        self.__reported_missing.add(item_id)
        if not filenames:
            self.bot.log_msg(f"[VisionAPI] TODO: item ID {item_id} isn't in item_ids.py, so it has no sprite name.")
            return
        filename = filenames[0]
        self.bot.log_msg(f"[VisionAPI] TODO: missing sprite {filename} (item {item_id}). Treating it as not found. Add it to {self.sprite_dir}")
        try:
            tracked = json.loads(self.missing_log_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            tracked = {}
        entry = tracked.setdefault(filename, {"item_id": item_id, "requested_by": []})
        bot_name = type(self.bot).__name__
        if bot_name not in entry["requested_by"]:
            entry["requested_by"].append(bot_name)
        self.missing_log_path.write_text(json.dumps(tracked, indent=2, sort_keys=True))
