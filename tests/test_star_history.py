import importlib.util
import unittest
from datetime import date, datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "update_star_history.py"
SPEC = importlib.util.spec_from_file_location("update_star_history", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class StarHistoryTests(unittest.TestCase):
    def test_daily_series_counts_stars_in_utc(self):
        timestamps = [
            datetime(2026, 8, 21, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 23, tzinfo=timezone.utc),
            datetime(2026, 8, 23, 5, tzinfo=timezone.utc),
        ]

        self.assertEqual(
            MODULE.daily_series(timestamps, date(2026, 8, 24)),
            [
                (date(2026, 8, 21), 2),
                (date(2026, 8, 22), 2),
                (date(2026, 8, 23), 3),
                (date(2026, 8, 24), 3),
            ],
        )

    def test_empty_repository_renders_zero_state(self):
        generated_on = date(2026, 8, 23)
        svg = MODULE.render_svg("owner/repo", [], generated_on)

        self.assertIn(">000</text>", svg)
        self.assertIn("NO STARGAZER EVENTS YET", svg)
        self.assertIn("2026-08-23", svg)
        self.assertIn("owner/repo", svg)

    def test_render_uses_each_timestamp_as_a_step(self):
        timestamps = [
            datetime(2026, 8, 21, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 2, tzinfo=timezone.utc),
            datetime(2026, 8, 22, 3, tzinfo=timezone.utc),
        ]
        svg = MODULE.render_svg("owner/repo", timestamps, date(2026, 8, 23))

        trace = next(line for line in svg.splitlines() if 'class="signal"' in line)
        self.assertEqual(trace.count(" H "), 4)
        self.assertEqual(trace.count(" V "), 3)
        self.assertIn("each step represents one stargazer event", svg)
        self.assertIn("AUG 21 ·", svg)
        tick_lines = [line for line in svg.splitlines() if "·" in line]
        self.assertIn('text-anchor="start"', tick_lines[0])
        self.assertIn('text-anchor="end"', tick_lines[-1])

    def test_axis_uses_a_250_ceiling_for_222_stars(self):
        self.assertEqual(MODULE._nice_axis(222), (250, 50))

    def test_next_link_selects_next_relation(self):
        header = (
            '<https://api.github.com/example?page=2>; rel="next", '
            '<https://api.github.com/example?page=4>; rel="last"'
        )
        self.assertEqual(
            MODULE._next_link(header), "https://api.github.com/example?page=2"
        )


if __name__ == "__main__":
    unittest.main()
