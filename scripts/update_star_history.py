#!/usr/bin/env python3
"""Render a repository's current stargazer history as a dependency-free SVG."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape


API_VERSION = "2022-11-28"
STAR_MEDIA_TYPE = "application/vnd.github.star+json"
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def fetch_stargazers(repository: str, token: str | None = None) -> list[datetime]:
    """Return UTC timestamps for all current stargazers, following pagination."""
    if not REPOSITORY_RE.fullmatch(repository):
        raise ValueError("repository must use the owner/name form")

    url: str | None = (
        f"https://api.github.com/repos/{repository}/stargazers?per_page=100&page=1"
    )
    timestamps: list[datetime] = []
    while url:
        headers = {
            "Accept": STAR_MEDIA_TYPE,
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "star-history-action",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
                next_url = _next_link(response.headers.get("Link", ""))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API returned HTTP {error.code}: {detail}") from error

        if not isinstance(payload, list):
            raise RuntimeError("GitHub API returned an unexpected stargazer payload")
        for entry in payload:
            starred_at = entry.get("starred_at") if isinstance(entry, dict) else None
            if not isinstance(starred_at, str):
                raise RuntimeError(
                    "GitHub API omitted starred_at; check the stargazer media type"
                )
            timestamps.append(_parse_github_datetime(starred_at))
        url = next_url

    return sorted(timestamps)


def _parse_github_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _next_link(header: str) -> str | None:
    for part in header.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part)
        if match and match.group(2) == "next":
            return match.group(1)
    return None


def daily_series(timestamps: Iterable[datetime], through: date) -> list[tuple[date, int]]:
    days = sorted(timestamp.astimezone(timezone.utc).date() for timestamp in timestamps)
    if not days:
        return [(through, 0)]
    start = min(days[0], through)
    end = max(days[-1], through)
    counts: dict[date, int] = {}
    for day in days:
        counts[day] = counts.get(day, 0) + 1

    result: list[tuple[date, int]] = []
    running = 0
    ordinal = start.toordinal()
    while ordinal <= end.toordinal():
        day = date.fromordinal(ordinal)
        running += counts.get(day, 0)
        result.append((day, running))
        ordinal += 1
    return result


def _nice_ceiling(value: int) -> int:
    if value <= 4:
        return max(1, value)
    magnitude = 10 ** math.floor(math.log10(value))
    for multiple in (1, 2, 4, 5, 10):
        candidate = multiple * magnitude
        if candidate >= value:
            return candidate
    raise AssertionError("unreachable")


def _sample_indices(length: int, desired: int) -> list[int]:
    if length <= 1:
        return [0]
    return sorted({round(index * (length - 1) / (desired - 1)) for index in range(desired)})


def render_svg(repository: str, series: list[tuple[date, int]], generated_on: date) -> str:
    if not series:
        raise ValueError("series must contain at least one point")

    width, height = 1100, 600
    left, right, top, bottom = 105, 55, 115, 85
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_count = _nice_ceiling(max(value for _, value in series))

    def x(index: int) -> float:
        return left if len(series) == 1 else left + plot_width * index / (len(series) - 1)

    def y(value: int) -> float:
        return top + plot_height * (1 - value / max_count)

    points = " ".join(f"{x(index):.1f},{y(value):.1f}" for index, (_, value) in enumerate(series))
    area_points = f"{left},{top + plot_height} {points} {left + plot_width},{top + plot_height}"
    total = series[-1][1]
    title = escape(repository)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f"<title id=\"title\">Star history for {title}</title>",
        f"<desc id=\"desc\">{total} current GitHub stargazers as of {generated_on.isoformat()}</desc>",
        '<rect width="1100" height="600" rx="14" fill="#ffffff"/>',
        '<style>text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.label{fill:#64748b;font-size:18px}.tick{fill:#64748b;font-size:15px}.grid{stroke:#e2e8f0;stroke-width:1}.axis{stroke:#94a3b8;stroke-width:1.5}</style>',
        f'<circle cx="67" cy="55" r="7" fill="#f97316"/><text x="86" y="63" fill="#0f172a" font-size="25" font-weight="650">{title}</text>',
        f'<text x="{width - 55}" y="63" text-anchor="end" fill="#0f172a" font-size="25" font-weight="650">★ {total}</text>',
    ]

    for value in sorted({round(max_count * tick / 4) for tick in range(5)}):
        tick_y = y(value)
        lines.append(f'<line class="grid" x1="{left}" y1="{tick_y:.1f}" x2="{left + plot_width}" y2="{tick_y:.1f}"/>')
        lines.append(f'<text class="tick" x="{left - 18}" y="{tick_y + 5:.1f}" text-anchor="end">{value}</text>')

    lines.extend(
        [
            f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}"/>',
            f'<line class="axis" x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}"/>',
            f'<polygon points="{area_points}" fill="#f97316" opacity="0.10"/>',
            f'<polyline points="{points}" fill="none" stroke="#f97316" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>',
        ]
    )

    for index in _sample_indices(len(series), min(6, len(series))):
        tick_x = x(index)
        day = series[index][0]
        label = f"{day.strftime('%b')} {day.day}"
        lines.append(f'<line class="axis" x1="{tick_x:.1f}" y1="{top + plot_height}" x2="{tick_x:.1f}" y2="{top + plot_height + 8}"/>')
        lines.append(f'<text class="tick" x="{tick_x:.1f}" y="{top + plot_height + 32}" text-anchor="middle">{label}</text>')

    end_x, end_y = x(len(series) - 1), y(total)
    lines.extend(
        [
            f'<circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="7" fill="#f97316" stroke="#ffffff" stroke-width="4"/>',
            f'<text class="label" x="{width - 55}" y="{height - 28}" text-anchor="end">data: GitHub API · {generated_on.isoformat()}</text>',
            "</svg>",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--output", type=Path, default=Path("docs/assets/star-history.svg"))
    parser.add_argument("--date", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    args = parser.parse_args()
    if not args.repo:
        parser.error("--repo is required outside GitHub Actions")

    timestamps = fetch_stargazers(args.repo, os.environ.get("GITHUB_TOKEN"))
    svg = render_svg(args.repo, daily_series(timestamps, args.date), args.date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(f"Wrote {args.output} with {len(timestamps)} stargazers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
