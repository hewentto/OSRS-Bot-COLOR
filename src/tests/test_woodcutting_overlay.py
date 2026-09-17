"""
RuneLite's Woodcutting plugin shows a status line at the top-left of the game view: a green "Woodcutting" while the
character is swinging an axe, and a red "NOT woodcutting" otherwise. It's a quicker and surer sign that a tree has
fallen than watching the character for movement.

Run from the `src` folder:  python -m unittest tests.test_woodcutting_overlay -v
"""
import unittest
from unittest import mock

import utilities.ocr as ocr
from model.osrs.WillowsDad.WDWoodcutting import OSRSWDWoodcutting
from tests.fake_client import FakeScreen, draw_text
from utilities.geometry import Rectangle

GREEN, RED, WHITE = (0, 255, 0), (0, 0, 255), (255, 255, 255)  # BGR
CHOPPING, NOT_CHOPPING, NO_OVERLAY = True, False, None


class WoodcuttingBotTestCase(unittest.TestCase):
    def setUp(self):
        self.bot = OSRSWDWoodcutting()
        self.bot.log_msg = lambda msg, overwrite=False: None
        self.bot.api_m = mock.Mock()
        self.bot.api_m.get_is_player_idle.return_value = False
        patcher = mock.patch("time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def overlay_shows(self, *statuses):
        """Makes the overlay report each status in turn; the last one repeats."""
        readings = list(statuses)
        self.bot.action_status = lambda action: readings.pop(0) if len(readings) > 1 else readings[0]


class ReadingTheOverlayTests(WoodcuttingBotTestCase):
    """The game view here starts at (4, 26), so an overlay in its usual spot has its status text at about (36, 54)."""

    def setUp(self):
        super().setUp()
        self.screen = FakeScreen()
        self.bot.win.game_view = Rectangle(4, 26, 512, 334)
        self.screenshots_taken = 0
        patcher = mock.patch.object(Rectangle, "screenshot", lambda rect: self.grab(rect))
        patcher.start()
        self.addCleanup(patcher.stop)

    def grab(self, rect):
        self.screenshots_taken += 1
        return self.screen.grab(rect)

    def test_green_status_means_the_character_is_chopping(self):
        draw_text(self.screen, 40, 54, "Woodcutting", ocr.PLAIN_12, GREEN)
        self.assertIs(self.bot.action_status("Woodcutting"), CHOPPING)

    def test_red_status_means_the_character_is_not_chopping(self):
        draw_text(self.screen, 30, 54, "NOT woodcutting", ocr.PLAIN_12, RED)
        self.assertIs(self.bot.action_status("Woodcutting"), NOT_CHOPPING)

    def test_no_status_when_the_overlay_is_not_showing(self):
        self.assertIs(self.bot.action_status("Woodcutting"), NO_OVERLAY)

    def test_other_text_near_the_overlay_is_not_mistaken_for_a_status(self):
        draw_text(self.screen, 8, 30, "Walk here", ocr.PLAIN_12, WHITE)
        draw_text(self.screen, 12, 72, "Logs cut:", ocr.PLAIN_12, WHITE)
        self.assertIs(self.bot.action_status("Woodcutting"), NO_OVERLAY)

    def test_status_is_read_wherever_the_overlay_sits_in_the_top_left_of_the_game_view(self):
        for x, y in [(8, 46), (60, 62), (20, 58)]:
            self.screen = FakeScreen()
            draw_text(self.screen, x, y, "NOT woodcutting", ocr.PLAIN_12, RED)
            self.assertIs(self.bot.action_status("Woodcutting"), NOT_CHOPPING, f"status text drawn at ({x}, {y})")

    def test_only_the_top_left_of_the_game_view_is_looked_at(self):
        draw_text(self.screen, 300, 200, "Woodcutting", ocr.PLAIN_12, GREEN)
        self.assertIs(self.bot.action_status("Woodcutting"), NO_OVERLAY)

    def test_status_is_read_from_a_single_screenshot(self):
        draw_text(self.screen, 30, 54, "NOT woodcutting", ocr.PLAIN_12, RED)
        self.bot.action_status("Woodcutting")
        self.assertEqual(self.screenshots_taken, 1)


class WaitingForChoppingToStartTests(WoodcuttingBotTestCase):
    """After a tree is clicked the status stays red for as long as the character is walking over to it."""

    def test_red_status_during_the_walk_is_waited_out_until_chopping_starts(self):
        self.overlay_shows(NOT_CHOPPING, NOT_CHOPPING, NOT_CHOPPING, CHOPPING)
        self.assertTrue(self.bot.wait_for_chopping_to_start(timeout=5))

    def test_gives_up_when_the_character_has_stopped_without_chopping(self):
        self.bot.WALK_START_GRACE = 0
        self.overlay_shows(NOT_CHOPPING)
        self.bot.api_m.get_is_player_idle.return_value = True  # Standing still: the tree fell before we got there
        self.assertFalse(self.bot.wait_for_chopping_to_start(timeout=5))

    def test_keeps_waiting_while_the_character_is_still_walking(self):
        self.overlay_shows(*[NOT_CHOPPING] * 40, CHOPPING)
        self.bot.api_m.get_is_player_idle.return_value = False
        self.assertTrue(self.bot.wait_for_chopping_to_start(timeout=5))

    def test_standing_still_right_after_the_click_is_not_giving_up(self):
        self.bot.WALK_START_GRACE = 60  # The character only sets off on the next game tick
        self.overlay_shows(*[NOT_CHOPPING] * 10, CHOPPING)
        self.bot.api_m.get_is_player_idle.return_value = True
        self.assertTrue(self.bot.wait_for_chopping_to_start(timeout=5))

    def test_gives_up_after_the_timeout_even_if_the_character_never_stops(self):
        self.overlay_shows(NOT_CHOPPING)
        self.assertFalse(self.bot.wait_for_chopping_to_start(timeout=0.05))

    def test_does_not_wait_when_there_is_no_overlay_to_watch(self):
        self.overlay_shows(NO_OVERLAY)
        self.assertFalse(self.bot.wait_for_chopping_to_start(timeout=5))
        self.bot.api_m.get_is_player_idle.assert_not_called()


class WaitingForChoppingToEndTests(WoodcuttingBotTestCase):
    def test_returns_as_soon_as_the_status_turns_red(self):
        self.overlay_shows(CHOPPING, CHOPPING, NOT_CHOPPING)
        self.bot.sleep_while_chopping()
        self.assertIs(self.bot.action_status("Woodcutting"), NOT_CHOPPING)

    def test_returns_if_the_overlay_disappears(self):
        self.overlay_shows(CHOPPING, NO_OVERLAY)
        self.bot.sleep_while_chopping()  # Must not hang

    def test_never_falls_back_to_watching_for_movement(self):
        self.overlay_shows(CHOPPING, CHOPPING, NOT_CHOPPING)
        self.bot.sleep_while_chopping()
        self.bot.api_m.get_is_player_idle.assert_not_called()


class DecidingWhenToClickATreeTests(WoodcuttingBotTestCase):
    def test_ready_for_a_tree_when_the_status_is_red(self):
        self.overlay_shows(NOT_CHOPPING)
        self.assertTrue(self.bot.is_ready_for_next_tree())
        self.bot.api_m.get_is_player_idle.assert_not_called()

    def test_not_ready_for_a_tree_while_chopping(self):
        self.overlay_shows(CHOPPING)
        self.assertFalse(self.bot.is_ready_for_next_tree())

    def test_falls_back_to_watching_for_movement_before_the_overlay_appears(self):
        self.overlay_shows(NO_OVERLAY)
        self.bot.api_m.get_is_player_idle.return_value = True
        self.assertTrue(self.bot.is_ready_for_next_tree())


if __name__ == "__main__":
    unittest.main()
