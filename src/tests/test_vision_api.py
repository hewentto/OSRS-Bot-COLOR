"""
Run from the `src` folder:  python -m unittest tests.test_vision_api -v
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import utilities.api.item_ids as ids
import utilities.ocr as ocr
from tests.fake_client import INVENTORY_BROWN_BGR, ITEM_SPRITES, FakeBot, FakeScreen, draw_inventory, draw_stack_number, draw_text, load_sprite
from utilities.api.vision_api import VisionAPI, render_at_brightness, sprite_filenames
from utilities.geometry import Rectangle


class SpriteFilenameTests(unittest.TestCase):
    def test_item_id_maps_to_wiki_style_filename(self):
        self.assertEqual(sprite_filenames(ids.WILLOW_LOGS), ["Willow_logs.png"])

    def test_variant_id_falls_back_to_base_item_name(self):
        self.assertEqual(sprite_filenames(ids.BIRD_NEST_5071), ["Bird_nest_5071.png", "Bird_nest.png"])

    def test_unknown_item_id_has_no_filename(self):
        self.assertEqual(sprite_filenames(-12345), [])


class VisionTestCase(unittest.TestCase):
    """Base class: a fake bot + screen, and a VisionAPI reading sprites from a temp folder."""

    SPRITES = ["Willow_logs.png", "Oak_logs.png"]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sprite_dir = self.tmp.joinpath("items")
        self.sprite_dir.mkdir()
        for name in self.SPRITES:
            shutil.copy(ITEM_SPRITES.joinpath(name), self.sprite_dir)
        self.missing_log = self.tmp.joinpath("missing.json")
        self.bot = FakeBot()
        self.screen = FakeScreen()
        self.api = VisionAPI(self.bot, sprite_dir=self.sprite_dir, missing_log_path=self.missing_log)
        # The fake screen stands in for the monitor, and waiting is skipped.
        screen = self.screen
        for patcher in (mock.patch.object(Rectangle, "screenshot", lambda rect: screen.grab(rect)), mock.patch("time.sleep")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class InventoryItemTests(VisionTestCase):
    def setUp(self):
        super().setUp()
        draw_inventory(self.screen, self.bot, {0: "Willow_logs.png", 3: "Oak_logs.png", 5: "Willow_logs.png", 27: "Willow_logs.png"})

    def test_finds_every_slot_holding_the_item(self):
        self.assertEqual(self.api.get_inv_item_indices(ids.WILLOW_LOGS), [0, 5, 27])

    def test_does_not_confuse_similar_looking_items(self):
        self.assertEqual(self.api.get_inv_item_indices(ids.OAK_LOGS), [3])

    def test_list_of_ids_returns_slots_of_all_of_them_in_order(self):
        self.assertEqual(self.api.get_inv_item_indices([ids.OAK_LOGS, ids.WILLOW_LOGS]), [0, 3, 5, 27])

    def test_first_occurrence_of_single_id_is_an_int(self):
        self.assertEqual(self.api.get_first_occurrence(ids.WILLOW_LOGS), 0)

    def test_first_occurrence_of_absent_single_id_is_minus_one(self):
        shutil.copy(ITEM_SPRITES.joinpath("Maple_logs.png"), self.sprite_dir)
        self.assertEqual(self.api.get_first_occurrence(ids.MAPLE_LOGS), -1)

    def test_first_occurrence_of_list_is_first_slot_per_item(self):
        self.assertEqual(self.api.get_first_occurrence([ids.OAK_LOGS, ids.WILLOW_LOGS]), [0, 3])

    def test_first_occurrence_of_absent_list_is_empty_list(self):
        shutil.copy(ITEM_SPRITES.joinpath("Maple_logs.png"), self.sprite_dir)
        self.assertEqual(self.api.get_first_occurrence([ids.MAPLE_LOGS]), [])

    def test_legacy_first_indice_name_still_works(self):
        self.assertEqual(self.api.get_inv_item_first_indice([ids.OAK_LOGS, ids.WILLOW_LOGS]), [0, 3])

    def test_item_in_inv(self):
        self.assertTrue(self.api.get_if_item_in_inv(ids.OAK_LOGS))

    def test_item_not_in_inv(self):
        shutil.copy(ITEM_SPRITES.joinpath("Maple_logs.png"), self.sprite_dir)
        self.assertFalse(self.api.get_if_item_in_inv([ids.MAPLE_LOGS]))


class LookAlikeTests(VisionTestCase):
    """Compost, Supercompost and Ultracompost are the same sprite in slightly different shades."""

    SPRITES = ["Compost.png", "Supercompost.png", "Ultracompost.png"]

    def setUp(self):
        super().setUp()
        draw_inventory(self.screen, self.bot, {0: "Ultracompost.png", 1: "Supercompost.png", 2: "Compost.png", 3: "Ultracompost.png"})

    def test_recolored_item_is_not_mistaken_for_the_one_searched_for(self):
        self.assertEqual(self.api.get_inv_item_indices(ids.SUPERCOMPOST), [1])

    def test_each_recolor_is_found_in_its_own_slots(self):
        self.assertEqual(self.api.get_inv_item_indices(ids.ULTRACOMPOST), [0, 3])
        self.assertEqual(self.api.get_inv_item_indices(ids.COMPOST), [2])

    def test_recolors_searched_for_together_are_all_found(self):
        self.assertEqual(self.api.get_inv_item_indices([ids.COMPOST, ids.SUPERCOMPOST, ids.ULTRACOMPOST]), [0, 1, 2, 3])


class RenderAtBrightnessTests(unittest.TestCase):
    """Expected colors were measured from a Rune axe in a live client at the game's default brightness (0.8)."""

    def sprite_of(self, *bgra_pixels):
        return np.array([list(bgra_pixels)], dtype=np.uint8)

    def test_wiki_brightness_leaves_the_sprite_unchanged(self):
        sprite = load_sprite("Willow_logs.png")
        self.assertTrue(np.array_equal(render_at_brightness(sprite, 0.6), sprite))

    def test_darker_brightness_gives_the_colors_the_game_draws(self):
        darker = render_at_brightness(self.sprite_of((92, 82, 61, 255), (17, 103, 139, 255), (98, 88, 66, 255)), 0.8)
        measured_in_game = [(65, 56, 38), (7, 76, 113), (71, 62, 42)]
        for drawn, measured in zip(darker[0, :, :3].astype(int), measured_in_game):
            self.assertLessEqual(max(abs(drawn - measured)), 1, f"{tuple(drawn)} isn't within 1 of {measured}")

    def test_outline_and_transparency_are_untouched(self):
        darker = render_at_brightness(self.sprite_of((1, 0, 0, 255), (0, 0, 0, 0)), 0.8)
        self.assertEqual(darker[0].tolist(), [[1, 0, 0, 255], [0, 0, 0, 0]])


class GameBrightnessTests(VisionTestCase):
    """The game draws items darker than the Wiki's sprites unless its brightness setting is at maximum."""

    SPRITES = ["Logs.png", "Oak_logs.png", "Willow_logs.png"]
    GAME_DEFAULT_BRIGHTNESS = 0.8

    def test_item_is_found_when_the_game_is_darker_than_the_wiki_sprites(self):
        draw_inventory(self.screen, self.bot, {4: "Willow_logs.png", 9: "Willow_logs.png"}, self.GAME_DEFAULT_BRIGHTNESS)
        self.assertEqual(self.api.get_inv_item_indices(ids.WILLOW_LOGS), [4, 9])

    def test_similar_items_are_still_told_apart_in_a_darker_game(self):
        draw_inventory(self.screen, self.bot, {0: "Logs.png", 1: "Oak_logs.png"}, self.GAME_DEFAULT_BRIGHTNESS)
        self.assertEqual(self.api.get_inv_item_indices(ids.LOGS), [0])
        self.assertEqual(self.api.get_inv_item_indices(ids.OAK_LOGS), [1])

    def test_brightness_is_not_guessed_from_a_look_alike_of_the_item_searched_for(self):
        draw_inventory(self.screen, self.bot, {0: "Oak_logs.png"}, self.GAME_DEFAULT_BRIGHTNESS)
        self.assertEqual(self.api.get_inv_item_indices(ids.LOGS), [])
        self.assertEqual(self.api.get_inv_item_indices(ids.OAK_LOGS), [0])

    def test_equipped_item_is_found_in_a_darker_game(self):
        cp = self.bot.win.control_panel
        self.screen.fill(cp, INVENTORY_BROWN_BGR)
        self.screen.paste(render_at_brightness(load_sprite("Willow_logs.png"), self.GAME_DEFAULT_BRIGHTNESS), cp.left + 30, cp.top + 120)
        self.assertTrue(self.api.get_is_item_equipped(ids.WILLOW_LOGS))

    def test_detected_brightness_is_logged_once(self):
        draw_inventory(self.screen, self.bot, {4: "Willow_logs.png"}, self.GAME_DEFAULT_BRIGHTNESS)
        self.api.get_inv_item_indices(ids.WILLOW_LOGS)
        self.api.get_inv_item_indices(ids.WILLOW_LOGS)
        self.assertEqual(len([msg for msg in self.bot.logs if "brightness" in msg.lower()]), 1)

    def test_nothing_is_logged_when_the_game_is_at_the_wiki_brightness(self):
        draw_inventory(self.screen, self.bot, {4: "Willow_logs.png"})
        self.api.get_inv_item_indices(ids.WILLOW_LOGS)
        self.assertEqual(self.bot.logs, [])


class StackNumberTests(VisionTestCase):
    def setUp(self):
        super().setUp()
        draw_inventory(self.screen, self.bot, {2: "Willow_logs.png", 9: "Oak_logs.png"})
        draw_stack_number(self.screen, self.bot.win.inventory_slots[2], "1337")
        draw_stack_number(self.screen, self.bot.win.inventory_slots[9], "28")

    def test_item_is_found_under_its_stack_number(self):
        self.assertEqual(self.api.get_inv_item_indices(ids.WILLOW_LOGS), [2])

    def test_stack_number_does_not_make_similar_items_match(self):
        shutil.copy(ITEM_SPRITES.joinpath("Logs.png"), self.sprite_dir)
        self.assertEqual(self.api.get_inv_item_indices(ids.LOGS), [])


class InventoryOccupancyTests(VisionTestCase):
    def test_inventory_with_a_free_slot_is_not_full(self):
        draw_inventory(self.screen, self.bot, {i: "Willow_logs.png" for i in range(27)})
        self.assertFalse(self.api.get_is_inv_full())

    def test_inventory_with_28_items_is_full(self):
        draw_inventory(self.screen, self.bot, {i: "Willow_logs.png" for i in range(28)})
        self.assertTrue(self.api.get_is_inv_full())

    def test_inventory_with_no_items_is_empty(self):
        draw_inventory(self.screen, self.bot, {})
        self.assertTrue(self.api.get_is_inv_empty())

    def test_inventory_with_one_item_is_not_empty(self):
        draw_inventory(self.screen, self.bot, {13: "Oak_logs.png"})
        self.assertFalse(self.api.get_is_inv_empty())

    def test_get_inv_lists_each_occupied_slot(self):
        draw_inventory(self.screen, self.bot, {1: "Oak_logs.png", 13: "Oak_logs.png", 27: "Willow_logs.png"})
        self.assertEqual([item["index"] for item in self.api.get_inv()], [1, 13, 27])

    def test_item_the_color_of_the_inventory_background_still_fills_its_slot(self):
        # Willow logs at the game's default brightness are close enough to the background to pass for an empty slot.
        draw_inventory(self.screen, self.bot, {i: "Willow_logs.png" for i in range(28)}, brightness=0.8)
        self.assertTrue(self.api.get_is_inv_full())

    def test_single_slot_holding_an_item_is_not_empty(self):
        draw_inventory(self.screen, self.bot, {27: "Willow_logs.png"}, brightness=0.8)
        self.assertFalse(self.api.get_is_inv_slot_empty(27))

    def test_single_slot_holding_nothing_is_empty(self):
        draw_inventory(self.screen, self.bot, {27: "Willow_logs.png"}, brightness=0.8)
        self.assertTrue(self.api.get_is_inv_slot_empty(26))

    def test_stack_number_alone_does_not_fill_a_slot(self):
        draw_inventory(self.screen, self.bot, {})
        draw_stack_number(self.screen, self.bot.win.inventory_slots[5], "1337")
        self.assertTrue(self.api.get_is_inv_empty())

    def test_occupancy_needs_no_item_sprites(self):
        shutil.rmtree(self.sprite_dir)
        draw_inventory(self.screen, self.bot, {4: "Oak_logs.png"})
        self.assertEqual(len(self.api.get_inv()), 1)
        self.assertEqual(self.bot.logs, [])


class MissingSpriteTests(VisionTestCase):
    def setUp(self):
        super().setUp()
        draw_inventory(self.screen, self.bot, {0: "Willow_logs.png"})

    def test_missing_sprite_is_treated_as_item_not_found(self):
        self.assertEqual(self.api.get_inv_item_indices(ids.RAW_SHARK), [])

    def test_missing_sprite_is_logged_to_the_bot_once(self):
        self.api.get_inv_item_indices(ids.RAW_SHARK)
        self.api.get_if_item_in_inv(ids.RAW_SHARK)
        mentions = [msg for msg in self.bot.logs if "Raw_shark.png" in msg]
        self.assertEqual(len(mentions), 1)

    def test_missing_sprite_is_recorded_in_the_tracking_file(self):
        self.api.get_inv_item_indices(ids.RAW_SHARK)
        tracked = json.loads(self.missing_log.read_text())
        self.assertEqual(tracked["Raw_shark.png"]["item_id"], ids.RAW_SHARK)
        self.assertEqual(tracked["Raw_shark.png"]["requested_by"], ["FakeBot"])

    def test_items_with_sprites_still_match_when_others_in_the_list_are_missing(self):
        self.assertEqual(self.api.get_inv_item_indices([ids.RAW_SHARK, ids.WILLOW_LOGS]), [0])


class IdleTests(VisionTestCase):
    def test_player_is_idle_when_the_game_view_stays_still(self):
        self.assertTrue(self.api.get_is_player_idle(poll_seconds=0.05))

    def test_player_is_not_idle_when_their_character_is_moving(self):
        center = self.bot.win.game_view.get_center()
        frames = iter(range(1, 10_000))

        def animated_grab(rect):
            shade = 255 if next(frames) % 2 else 0
            self.screen.img[center.y - 5 : center.y + 5, center.x - 5 : center.x + 5] = shade
            return self.screen.grab(rect)

        with mock.patch.object(Rectangle, "screenshot", animated_grab):
            self.assertFalse(self.api.get_is_player_idle(poll_seconds=0.05))


class XpTests(VisionTestCase):
    def test_returns_new_total_once_xp_is_gained(self):
        self.bot.total_xp_readings = [100, 100, 150]
        self.assertEqual(self.api.wait_til_gained_xp("Woodcutting", timeout=5), 150)

    def test_returns_minus_one_when_no_xp_is_gained_in_time(self):
        self.bot.total_xp_readings = [100]
        self.assertEqual(self.api.wait_til_gained_xp("Woodcutting", timeout=0.05), -1)

    def test_returns_minus_one_and_explains_when_total_xp_cannot_be_read(self):
        self.bot.total_xp_readings = [-1]
        self.assertEqual(self.api.wait_til_gained_xp("Woodcutting", timeout=0.05), -1)
        self.assertTrue(any("total XP" in msg for msg in self.bot.logs))


class EquipmentTests(VisionTestCase):
    EQUIPMENT_TAB, INVENTORY_TAB = 4, 3

    def setUp(self):
        super().setUp()
        self.screen.fill(self.bot.win.control_panel, INVENTORY_BROWN_BGR)

    def clicked_tabs(self):
        """The control panel tabs that were clicked, in order."""
        tabs = []
        for event, following in zip(self.bot.mouse.events, self.bot.mouse.events[1:]):
            if event[0] == "move" and following == ("click",):
                x, y = event[1]
                tabs += [i for i, tab in enumerate(self.bot.win.cp_tabs) if tab.left <= x <= tab.left + tab.width and tab.top <= y <= tab.top + tab.height]
        return tabs

    def test_item_showing_in_the_equipment_tab_is_equipped(self):
        cp = self.bot.win.control_panel
        self.screen.paste(load_sprite("Willow_logs.png"), cp.left + 30, cp.top + 120)
        self.assertTrue(self.api.get_is_item_equipped([ids.OAK_LOGS, ids.WILLOW_LOGS]))

    def test_item_not_showing_in_the_equipment_tab_is_not_equipped(self):
        self.assertFalse(self.api.get_is_item_equipped(ids.WILLOW_LOGS))

    def test_opens_the_equipment_tab_then_returns_to_the_inventory(self):
        self.api.get_is_item_equipped(ids.WILLOW_LOGS)
        self.assertEqual(self.clicked_tabs(), [self.EQUIPMENT_TAB, self.INVENTORY_TAB])

    def test_does_not_touch_the_mouse_when_no_sprite_exists_to_look_for(self):
        self.assertFalse(self.api.get_is_item_equipped(ids.DRAGON_AXE))
        self.assertEqual(self.bot.mouse.events, [])


class EquipmentLookAlikeTests(VisionTestCase):
    SPRITES = ["Supercompost.png", "Ultracompost.png"]

    def test_look_alike_worn_in_another_slot_does_not_hide_the_item_searched_for(self):
        cp = self.bot.win.control_panel
        self.screen.fill(cp, INVENTORY_BROWN_BGR)
        self.screen.paste(load_sprite("Supercompost.png"), cp.left + 30, cp.top + 120)
        self.screen.paste(load_sprite("Ultracompost.png"), cp.left + 130, cp.top + 200)
        # One pixel of rendering noise, so the item searched for isn't a pixel-perfect match but its look-alike is.
        self.screen.img[cp.top + 135, cp.left + 45] += 3
        self.assertTrue(self.api.get_is_item_equipped(ids.SUPERCOMPOST))


class OcrBackedTests(VisionTestCase):
    def test_in_combat_when_opponent_info_shows_a_name(self):
        action = self.bot.win.current_action
        draw_text(self.screen, action.left + 2, action.top + 2, "Goblin", ocr.PLAIN_12, (255, 255, 255))
        self.assertTrue(self.api.get_is_in_combat())

    def test_not_in_combat_when_opponent_info_is_absent(self):
        self.assertFalse(self.api.get_is_in_combat())

    def test_latest_chat_message_is_read_from_the_bottom_of_the_chatbox(self):
        chat = self.bot.win.chat
        self.screen.fill(chat, (150, 180, 200))
        draw_text(self.screen, chat.left + 10, chat.top + chat.height - 40, "I can't reach that!", ocr.PLAIN_12, (0, 0, 0))
        self.assertIn("reach", self.api.get_latest_chat_message())

    def test_old_messages_higher_up_the_chatbox_are_ignored(self):
        chat = self.bot.win.chat
        self.screen.fill(chat, (150, 180, 200))
        draw_text(self.screen, chat.left + 10, chat.top + 5, "I can't reach that!", ocr.PLAIN_12, (0, 0, 0))
        self.assertNotIn("reach", self.api.get_latest_chat_message())


class OrbTests(VisionTestCase):
    def test_hitpoints_come_from_the_hp_orb_and_max_is_unknown(self):
        self.bot.hp = 43
        self.assertEqual(self.api.get_hitpoints(), (43, -1))

    def test_run_energy_comes_from_the_run_orb(self):
        self.bot.run_energy = 77
        self.assertEqual(self.api.get_run_energy(), 77)


class UnsupportedTests(VisionTestCase):
    def test_animation_id_cannot_be_seen_so_it_is_unknown(self):
        self.assertEqual(self.api.get_animation_id(), -1)

    def test_calling_something_with_no_visual_equivalent_is_logged_once_as_a_todo(self):
        self.api.get_animation_id()
        self.api.get_animation_id()
        mentions = [msg for msg in self.bot.logs if "get_animation_id" in msg and "TODO" in msg]
        self.assertEqual(len(mentions), 1)

    def test_player_position_is_unknown(self):
        self.assertEqual(self.api.get_player_position(), (-1, -1, -1))


if __name__ == "__main__":
    unittest.main()
