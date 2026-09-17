"""
Run from the `src` folder:  python -m unittest tests.test_vision_check -v
"""
import unittest

import cv2
import numpy as np

from utilities.vision_check import FOUND_BELOW, UI_TEMPLATES, score_template


def client_showing(template: np.ndarray, left: int, top: int) -> np.ndarray:
    """A noisy fake client screenshot with a UI template drawn at the given position."""
    client = np.random.default_rng(seed=1).integers(0, 255, size=(500, 800, 3), dtype=np.uint8)
    h, w = template.shape[:2]
    client[top : top + h, left : left + w] = template[:, :, :3]
    return client


class ScoreTemplateTests(unittest.TestCase):
    def setUp(self):
        self.minimap = cv2.imread(str(UI_TEMPLATES.joinpath("minimap.png")), cv2.IMREAD_UNCHANGED)

    def test_template_is_found_where_it_appears(self):
        score, x, y = score_template(self.minimap, client_showing(self.minimap, left=560, top=20))
        self.assertLess(score, FOUND_BELOW)
        self.assertEqual((x, y), (560, 20))

    def test_template_is_not_found_in_a_client_stretched_by_display_scaling(self):
        stretched = cv2.resize(client_showing(self.minimap, left=560, top=20), None, fx=2.5, fy=2.5, interpolation=cv2.INTER_LINEAR)
        self.assertGreater(score_template(self.minimap, stretched)[0], FOUND_BELOW)

    def test_template_is_found_again_once_the_display_scaling_is_undone(self):
        stretched = cv2.resize(client_showing(self.minimap, left=560, top=20), None, fx=2.5, fy=2.5, interpolation=cv2.INTER_LINEAR)
        self.assertLess(score_template(self.minimap, stretched, display_scale=2.5)[0], FOUND_BELOW)

    def test_template_larger_than_the_client_is_not_found(self):
        self.assertEqual(score_template(self.minimap, np.zeros((50, 50, 3), dtype=np.uint8))[0], 1.0)


if __name__ == "__main__":
    unittest.main()
