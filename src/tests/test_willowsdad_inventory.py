"""
The WillowsDad bots' own inventory helpers, which Mining, Motherload and Smithing are written against.

Run from the `src` folder:  python -m unittest tests.test_willowsdad_inventory -v
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from model.osrs.WillowsDad.WDWoodcutting import OSRSWDWoodcutting
from tests.fake_client import FakeScreen, FakeWindow, draw_inventory
from utilities.api.vision_api import VisionAPI
from utilities.geometry import Rectangle

GAME_DEFAULT_BRIGHTNESS = 0.8


class InventoryHelperTests(unittest.TestCase):
    def setUp(self):
        self.bot = OSRSWDWoodcutting()
        self.bot.log_msg = lambda msg, overwrite=False: None
        layout = FakeWindow()
        self.bot.win.inventory_slots, self.bot.win.control_panel = layout.inventory_slots, layout.control_panel
        self.bot.api_m = VisionAPI(self.bot, missing_log_path=Path(tempfile.mkdtemp()).joinpath("missing.json"))
        self.screen = FakeScreen()
        screen = self.screen
        patcher = mock.patch.object(Rectangle, "screenshot", lambda rect: screen.grab(rect))
        patcher.start()
        self.addCleanup(patcher.stop)

    def fill(self, slots):
        """Puts willow logs (which blend into the inventory background) in the given slots."""
        draw_inventory(self.screen, self.bot, {i: "Willow_logs.png" for i in slots}, GAME_DEFAULT_BRIGHTNESS)

    def test_inventory_of_28_dark_items_is_full(self):
        self.fill(range(28))
        self.assertTrue(self.bot.is_inv_full())

    def test_inventory_with_a_free_slot_is_not_full(self):
        self.fill(range(27))
        self.assertFalse(self.bot.is_inv_full())

    def test_inventory_holding_one_dark_item_is_not_empty(self):
        self.fill([13])
        self.assertFalse(self.bot.is_inv_empty())

    def test_inventory_holding_nothing_is_empty(self):
        self.fill([])
        self.assertTrue(self.bot.is_inv_empty())

    def test_last_slot_is_empty_until_something_is_in_it(self):
        self.fill(range(27))
        self.assertIs(self.bot.is_last_inv_slot_empty(), True)
        self.fill(range(28))
        self.assertIs(self.bot.is_last_inv_slot_empty(), False)

    def test_any_slot_can_be_checked(self):
        self.fill([0])
        self.assertIs(self.bot.is_inv_slot_empty(1), True)
        self.assertIs(self.bot.is_inv_slot_empty(0), False)


if __name__ == "__main__":
    unittest.main()
