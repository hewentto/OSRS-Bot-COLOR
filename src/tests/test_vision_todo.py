"""
Run from the `src` folder:  python -m unittest tests.test_vision_todo -v
"""
import shutil
import tempfile
import unittest
from pathlib import Path

import utilities.api.item_ids as ids
from tests.fake_client import ITEM_SPRITES
from utilities.vision_todo import render_markdown, scan_bot, wiki_override_url

BOT_SOURCE = '''
import utilities.api.item_ids as ids

class OSRSExample(WillowsDadBot):
    def main_loop(self):
        tools = [ids.WILLOW_LOGS, ids.RAW_SHARK]
        # old = ids.MAGIC_LOGS
        if self.api_m.get_if_item_in_inv(tools):
            # TODO(vision): check this overlay in game
            position = self.api_m.get_player_position()
        # frame = self.api_m.get_animation_id()
'''


class ScanBotTests(unittest.TestCase):
    def setUp(self):
        self.sprite_dir = Path(tempfile.mkdtemp())
        shutil.copy(ITEM_SPRITES.joinpath("Willow_logs.png"), self.sprite_dir)
        self.report = scan_bot("Example.py", BOT_SOURCE, self.sprite_dir)

    def tearDown(self):
        shutil.rmtree(self.sprite_dir, ignore_errors=True)

    def test_sprite_that_exists_is_marked_present(self):
        self.assertIn(("Willow_logs.png", ids.WILLOW_LOGS, True), self.report.sprites)

    def test_sprite_that_does_not_exist_is_marked_missing(self):
        self.assertIn(("Raw_shark.png", ids.RAW_SHARK, False), self.report.sprites)

    def test_items_only_mentioned_in_comments_are_ignored(self):
        self.assertNotIn("Magic_logs.png", [filename for filename, _, _ in self.report.sprites])

    def test_item_groups_expand_to_every_item_in_them(self):
        report = scan_bot("Example.py", "slots = api.get_inv_item_indices(item_ids.logs)", self.sprite_dir)
        self.assertEqual(sorted(item_id for _, item_id, _ in report.sprites), sorted(ids.logs))

    def test_variant_item_is_present_when_its_base_sprite_exists(self):
        shutil.copy(ITEM_SPRITES.joinpath("Willow_logs.png"), self.sprite_dir.joinpath("Bird_nest.png"))
        report = scan_bot("Example.py", "nest = ids.BIRD_NEST_5071", self.sprite_dir)
        self.assertEqual(report.sprites, [("Bird_nest_5071.png", ids.BIRD_NEST_5071, True)])

    def test_todo_markers_are_collected_with_their_line_number(self):
        self.assertEqual(self.report.todos, [(9, "check this overlay in game")])

    def test_live_calls_with_no_vision_equivalent_are_collected(self):
        self.assertEqual(self.report.unsupported_calls, [(10, "get_player_position")])


class BrokenBotTests(unittest.TestCase):
    def test_bot_with_a_syntax_error_is_reported_as_broken_instead_of_scanned(self):
        report = scan_bot("Broken.py", "<<<<<<< HEAD\ntools = [ids.WILLOW_LOGS]\n=======\n", ITEM_SPRITES)
        self.assertTrue(report.broken)
        self.assertEqual(report.sprites, [])

    def test_bot_that_parses_is_not_broken(self):
        self.assertFalse(scan_bot("Example.py", BOT_SOURCE, ITEM_SPRITES).broken)

    def test_broken_bot_is_called_out_in_the_checklist(self):
        markdown = render_markdown([scan_bot("Broken.py", "<<<<<<< HEAD\n", ITEM_SPRITES)], runtime_missing={})
        self.assertIn("## Broken.py (skipped: doesn't parse as Python)", markdown)


class WikiOverrideTests(unittest.TestCase):
    def test_sprite_named_differently_on_the_wiki_downloads_from_its_wiki_file(self):
        self.assertEqual(wiki_override_url("Paydirt.png"), "https://oldschool.runescape.wiki/images/Pay-dirt.png")

    def test_wiki_file_names_with_spaces_and_brackets_are_made_url_safe(self):
        self.assertEqual(wiki_override_url("Bird_nest_5071.png"), "https://oldschool.runescape.wiki/images/Bird_nest_%28green_egg%29.png")

    def test_sprite_with_a_regular_name_has_no_override(self):
        self.assertIsNone(wiki_override_url("Willow_logs.png"))


class RenderMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.sprite_dir = Path(tempfile.mkdtemp())
        shutil.copy(ITEM_SPRITES.joinpath("Willow_logs.png"), self.sprite_dir)
        self.markdown = render_markdown([scan_bot("Example.py", BOT_SOURCE, self.sprite_dir)], runtime_missing={})

    def tearDown(self):
        shutil.rmtree(self.sprite_dir, ignore_errors=True)

    def test_missing_sprite_is_an_unchecked_box(self):
        self.assertIn("- [ ] `Raw_shark.png`", self.markdown)

    def test_present_sprite_is_a_checked_box(self):
        self.assertIn("- [x] `Willow_logs.png`", self.markdown)

    def test_bot_heading_shows_how_many_sprites_it_has(self):
        self.assertIn("## Example.py (1/2 sprites)", self.markdown)

    def test_sprites_seen_missing_at_runtime_are_listed(self):
        markdown = render_markdown([], runtime_missing={"Feather.png": {"item_id": 314, "requested_by": ["OSRSWDFishing"]}})
        self.assertIn("- [ ] `Feather.png` (item 314) needed by OSRSWDFishing", markdown)


if __name__ == "__main__":
    unittest.main()
