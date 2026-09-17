"""
RuneLite can enlarge the client by a whole number ("Scale" in RuneLite (configure)), drawing every game pixel as a
block of screen pixels. These tests cover the framework seeing through that: looking at the game in game pixels, and
moving the mouse in screen pixels.

Run from the `src` folder:  python -m unittest tests.test_display_scale -v
"""
import unittest
from unittest import mock

import cv2
import numpy as np

import utilities.geometry as geometry
import utilities.imagesearch as imsearch
from utilities.geometry import Point, Rectangle
from utilities.mouse import Mouse
from utilities.window import Window, WindowInitializationError

UI_TEMPLATES = imsearch.BOT_IMAGES.joinpath("ui_templates")


class FakeMonitor:
    """Stands in for `mss`: a monitor showing a game that RuneLite has enlarged by a whole number."""

    def __init__(self, game: np.ndarray, scale: int, game_left: int, game_top: int):
        enlarged = cv2.resize(game, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        self.pixels = np.zeros((game_top + enlarged.shape[0] + 100, game_left + enlarged.shape[1] + 100, 4), dtype=np.uint8)
        self.pixels[game_top : game_top + enlarged.shape[0], game_left : game_left + enlarged.shape[1], :3] = enlarged

    def grab(self, monitor: dict) -> np.ndarray:
        return self.pixels[monitor["top"] : monitor["top"] + monitor["height"], monitor["left"] : monitor["left"] + monitor["width"]]


class FakeCursor:
    """Stands in for `pyautogui`'s cursor functions."""

    def __init__(self, x: int = 0, y: int = 0):
        self.x, self.y = x, y

    def position(self):
        return Point(self.x, self.y)

    def moveTo(self, point):
        self.x, self.y = round(point[0]), round(point[1])


class DisplayScaleTestCase(unittest.TestCase):
    def setUp(self):
        self.addCleanup(geometry.set_display_scale, 1)

    def show(self, game: np.ndarray, scale: int, game_left: int, game_top: int) -> None:
        patcher = mock.patch.object(geometry, "sct", FakeMonitor(game, scale, game_left, game_top))
        patcher.start()
        self.addCleanup(patcher.stop)


class ScreenshotTests(DisplayScaleTestCase):
    def setUp(self):
        super().setUp()
        self.game = np.random.default_rng(seed=7).integers(0, 255, size=(120, 200, 3), dtype=np.uint8)

    def test_screenshot_of_an_unscaled_game_is_the_screen_as_is(self):
        self.show(self.game, scale=1, game_left=300, game_top=100)
        self.assertTrue(np.array_equal(Rectangle(300, 100, 200, 120).screenshot(), self.game))

    def test_screenshot_of_an_enlarged_game_is_in_game_pixels(self):
        self.show(self.game, scale=2, game_left=600, game_top=200)
        geometry.set_display_scale(2)
        self.assertTrue(np.array_equal(Rectangle(300, 100, 200, 120).screenshot(), self.game))

    def test_game_pixels_are_exact_even_when_the_window_sits_on_an_odd_screen_pixel(self):
        self.show(self.game, scale=3, game_left=601, game_top=203)
        geometry.set_display_scale(3)
        # Screen pixel 601 is inside game-pixel column 200 (600-602), so the game's own column 0 is first seen at 201.
        self.assertTrue(np.array_equal(Rectangle(201, 68, 199, 119).screenshot(), self.game[:119, :199]))


class CoordinateTests(DisplayScaleTestCase):
    def test_game_point_maps_to_a_screen_pixel_inside_its_enlarged_block(self):
        geometry.set_display_scale(3)
        for _ in range(50):
            x, y = geometry.to_screen(Point(100, 40))
            self.assertIn(x, (300, 301, 302))
            self.assertIn(y, (120, 121, 122))

    def test_every_screen_pixel_of_a_block_maps_back_to_its_game_point(self):
        geometry.set_display_scale(3)
        self.assertEqual({geometry.from_screen(x, 121) for x in (300, 301, 302)}, {Point(100, 40)})

    def test_coordinates_are_unchanged_when_the_game_is_not_enlarged(self):
        self.assertEqual(geometry.to_screen(Point(100, 40)), Point(100, 40))
        self.assertEqual(geometry.from_screen(100, 40), Point(100, 40))


class MouseTests(DisplayScaleTestCase):
    def setUp(self):
        super().setUp()
        self.cursor = FakeCursor(x=10, y=10)
        for name in ("position", "moveTo"):
            patcher = mock.patch(f"pyautogui.{name}", getattr(self.cursor, name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_moving_to_a_game_point_lands_on_its_enlarged_block_on_screen(self):
        geometry.set_display_scale(2)
        Mouse().move_to(Point(400, 300))
        self.assertIn(self.cursor.x, (800, 801))
        self.assertIn(self.cursor.y, (600, 601))

    def test_relative_moves_are_measured_in_game_pixels(self):
        geometry.set_display_scale(2)
        self.cursor.x, self.cursor.y = 800, 600
        Mouse().move_rel(10, -5)
        self.assertIn(self.cursor.x, (820, 821))
        self.assertIn(self.cursor.y, (590, 591))

    def test_cursor_position_is_reported_in_game_pixels(self):
        geometry.set_display_scale(2)
        self.cursor.x, self.cursor.y = 801, 600
        self.assertEqual(geometry.cursor_position(), Point(400, 300))


class FakeClientWindow:
    def __init__(self, left, top, width, height):
        self.left, self.top, self.width, self.height = left, top, width, height


class WindowTests(DisplayScaleTestCase):
    CLIENT_WIDTH, CLIENT_HEIGHT = 1000, 640

    def open_client(self, scale: int, left: int = 120, top: int = 60, game: np.ndarray = None) -> Window:
        """Shows a client (in resizable-classic layout unless another game image is given) enlarged by `scale`."""
        game = self.draw_game() if game is None else game
        self.show(game, scale, left, top)
        client = FakeClientWindow(left, top, game.shape[1] * scale, game.shape[0] * scale)
        patcher = mock.patch("utilities.window.pywinctl.getWindowsWithTitle", return_value=[client])
        patcher.start()
        self.addCleanup(patcher.stop)
        return Window("RuneLite", padding_top=26, padding_left=0)

    def draw_game(self) -> np.ndarray:
        game = np.random.default_rng(seed=3).integers(0, 255, size=(self.CLIENT_HEIGHT, self.CLIENT_WIDTH, 3), dtype=np.uint8)
        for filename, (x, y) in {"minimap.png": (780, 30), "chat.png": (0, 470), "inv.png": (755, 300)}.items():
            template = cv2.imread(str(UI_TEMPLATES.joinpath(filename)), cv2.IMREAD_UNCHANGED)
            h, w = template.shape[:2]
            opaque = template[:, :, 3] > 0 if template.shape[2] == 4 else np.ones((h, w), dtype=bool)
            game[y : y + h, x : x + w][opaque] = template[:, :, :3][opaque]
        return game

    def test_client_rectangle_is_in_game_pixels(self):
        window = self.open_client(scale=2, left=120, top=60)
        geometry.set_display_scale(2)
        rect = window.rectangle()
        self.assertEqual((rect.left, rect.top, rect.width, rect.height), (60, 30, self.CLIENT_WIDTH, self.CLIENT_HEIGHT))

    def test_initialize_finds_the_interface_of_an_unscaled_client(self):
        window = self.open_client(scale=1)
        self.assertTrue(window.initialize())
        self.assertEqual(geometry.display_scale, 1)

    def test_initialize_detects_a_client_enlarged_by_runelite(self):
        window = self.open_client(scale=2)
        self.assertTrue(window.initialize())
        self.assertEqual(geometry.display_scale, 2)

    def test_interface_regions_of_an_enlarged_client_are_in_game_pixels(self):
        window = self.open_client(scale=3, left=120, top=60)
        window.initialize()
        # The control panel was drawn at game pixel (755, 300) of a client whose corner is at game pixel (40, 20).
        self.assertEqual((window.control_panel.left, window.control_panel.top), (40 + 755, 20 + 300))
        self.assertEqual((window.inventory_slots[0].width, window.inventory_slots[0].height), (36, 32))

    def test_initialize_fails_and_assumes_no_enlargement_when_the_interface_cannot_be_found(self):
        window = self.open_client(scale=2, game=np.zeros((self.CLIENT_HEIGHT, self.CLIENT_WIDTH, 3), dtype=np.uint8))
        with self.assertRaises(WindowInitializationError):
            window.initialize()
        self.assertEqual(geometry.display_scale, 1)


if __name__ == "__main__":
    unittest.main()
