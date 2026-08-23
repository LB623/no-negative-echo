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
from datetime import date, datetime, time, timezone
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
    """Return the legacy daily aggregation used by older callers and tests."""
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


def _nice_axis(value: int, desired_intervals: int = 5) -> tuple[int, int]:
    """Return a human scale ceiling and interval (222 -> 250 by 50)."""
    if value <= 0:
        return 5, 1
    rough_interval = value / desired_intervals
    magnitude = 10 ** math.floor(math.log10(rough_interval))
    normalized = rough_interval / magnitude
    multiple = next(item for item in (1, 2, 2.5, 5, 10) if item >= normalized)
    interval = max(1, round(multiple * magnitude))
    return math.ceil(value / interval) * interval, interval


def _utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        raise ValueError("stargazer timestamps must be timezone-aware")
    return timestamp.astimezone(timezone.utc)


def render_svg(
    repository: str,
    timestamps: Iterable[datetime],
    generated_on: date,
    *,
    source_label: str = "GITHUB STARGAZERS API",
) -> str:
    """Render every stargazer event as a seekable step trace."""
    stars = sorted(_utc(timestamp) for timestamp in timestamps)
    width, height = 1120, 560
    left, right, top, bottom = 88, 42, 148, 74
    plot_width = width - left - right
    plot_height = height - top - bottom
    total = len(stars)
    max_count, interval = _nice_axis(total)

    snapshot = datetime.combine(generated_on, time.max, tzinfo=timezone.utc)
    if stars:
        start_time = stars[0]
        end_time = max(stars[-1], snapshot)
    else:
        start_time = datetime.combine(generated_on, time.min, tzinfo=timezone.utc)
        end_time = snapshot
    span = max((end_time - start_time).total_seconds(), 1)

    def x(timestamp: datetime) -> float:
        elapsed = (_utc(timestamp) - start_time).total_seconds()
        return left + plot_width * max(0, min(elapsed / span, 1))

    def y(value: int) -> float:
        return top + plot_height * (1 - value / max_count)

    # Every event gets a horizontal approach and a vertical increment. Unlike a
    # daily polyline, this preserves bursts and quiet periods in the API data.
    commands = [f"M {left:.1f} {y(0):.1f}"]
    for count, timestamp in enumerate(stars, 1):
        event_x = x(timestamp)
        commands.extend((f"H {event_x:.1f}", f"V {y(count):.1f}"))
    commands.append(f"H {left + plot_width:.1f}")
    trace_path = " ".join(commands)
    area_path = (
        f"{trace_path} V {top + plot_height:.1f} H {left:.1f} Z"
        if stars
        else f"M {left:.1f} {top + plot_height:.1f} H {left + plot_width:.1f} Z"
    )

    title = escape(repository)
    source = escape(source_label.upper())
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">Stargazer trace for {title}</title>',
        f'<desc id="desc">{total} current GitHub stargazers as of {generated_on.isoformat()}; each step represents one stargazer event.</desc>',
        "<defs>",
        '<linearGradient id="signal-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff7a18" stop-opacity=".22"/><stop offset="1" stop-color="#ff7a18" stop-opacity="0"/></linearGradient>',
        '<filter id="signal-glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
        "</defs>",
        "<style>",
        ".surface{fill:#f6f8fa}.panel{fill:#fff;stroke:#d8dee4}.divider,.grid{stroke:#d8dee4}.grid{stroke-dasharray:2 7}.ink{fill:#1f2328}.muted{fill:#656d76}.faint{fill:#8c959f}.sans{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.signal{stroke:#f76707}.endpoint{fill:#f76707;stroke:#fff}.milestone-line{stroke:#f76707}.milestone-dot{fill:#f76707;stroke:#fff}",
        "@media (prefers-color-scheme:dark){.surface{fill:#0d1117}.panel{fill:#161b22;stroke:#30363d}.divider,.grid{stroke:#30363d}.ink{fill:#f0f6fc}.muted{fill:#8b949e}.faint{fill:#6e7681}.signal{stroke:#ff8a24}.endpoint{fill:#ff8a24;stroke:#161b22}.milestone-line{stroke:#ff8a24}.milestone-dot{fill:#ff8a24;stroke:#161b22}}",
        "</style>",
        f'<rect class="surface" width="{width}" height="{height}" rx="20"/>',
        f'<rect class="panel" x="16" y="16" width="{width - 32}" height="{height - 32}" rx="16"/>',
        '<text class="mono muted" x="52" y="58" font-size="12" font-weight="700" letter-spacing="2.2">STARGAZER TRACE</text>',
        f'<text class="sans ink" x="52" y="94" font-size="24" font-weight="650">{title}</text>',
        '<circle cx="52" cy="119" r="3.5" fill="#f76707"/>',
        '<text class="mono muted" x="64" y="123" font-size="12">EVENT STREAM / CUMULATIVE</text>',
        f'<text class="mono faint" x="{width - 52}" y="58" text-anchor="end" font-size="11" letter-spacing="1.5">CURRENT</text>',
        f'<text class="mono ink" x="{width - 52}" y="96" text-anchor="end" font-size="34" font-weight="700">{total:03d}</text>',
        f'<line class="divider" x1="52" y1="132" x2="{width - 52}" y2="132"/>',
    ]

    for value in range(0, max_count + 1, interval):
        tick_y = y(value)
        lines.append(
            f'<line class="grid" x1="{left}" y1="{tick_y:.1f}" x2="{left + plot_width}" y2="{tick_y:.1f}"/>'
        )
        lines.append(
            f'<text class="mono faint" x="{left - 16}" y="{tick_y + 4:.1f}" text-anchor="end" font-size="11">{value:03d}</text>'
        )

    lines.extend(
        [
            f'<path d="{area_path}" fill="url(#signal-fill)"/>',
            f'<path class="signal" d="{trace_path}" fill="none" stroke-width="2.25" stroke-linecap="square" stroke-linejoin="miter"/>',
        ]
    )

    for milestone in (50, 100, 200):
        if total < milestone:
            continue
        milestone_x = x(stars[milestone - 1])
        milestone_y = y(milestone)
        anchor = "end" if milestone_x > width - 190 else "start"
        label_x = milestone_x - 10 if anchor == "end" else milestone_x + 10
        lines.extend(
            [
                f'<line class="milestone-line" x1="{milestone_x:.1f}" y1="{milestone_y - 17:.1f}" x2="{milestone_x:.1f}" y2="{milestone_y + 17:.1f}" opacity=".45"/>',
                f'<circle class="milestone-dot" cx="{milestone_x:.1f}" cy="{milestone_y:.1f}" r="4" stroke-width="2"/>',
                f'<text class="mono muted" x="{label_x:.1f}" y="{milestone_y - 9:.1f}" text-anchor="{anchor}" font-size="10" letter-spacing="1">MILESTONE {milestone}</text>',
            ]
        )

    tick_count = 5
    label_times = [
        start_time + (end_time - start_time) * index / (tick_count - 1)
        for index in range(tick_count)
    ]
    short_window = (end_time - start_time).days < 7
    for index, timestamp in enumerate(label_times):
        tick_x = x(timestamp)
        label = timestamp.strftime("%b %d · %H:%M" if short_window else "%b %d").upper()
        anchor = "start" if index == 0 else "end" if index == tick_count - 1 else "middle"
        lines.append(
            f'<text class="mono faint" x="{tick_x:.1f}" y="{top + plot_height + 27}" text-anchor="{anchor}" font-size="11">{label}</text>'
        )

    if stars:
        end_y = y(total)
        lines.append(
            f'<circle class="endpoint" cx="{left + plot_width:.1f}" cy="{end_y:.1f}" r="5.5" stroke-width="3" filter="url(#signal-glow)"/>'
        )
    else:
        lines.append(
            f'<text class="mono muted" x="{left + plot_width / 2:.1f}" y="{top + plot_height / 2:.1f}" text-anchor="middle" font-size="13" letter-spacing="1.5">NO STARGAZER EVENTS YET</text>'
        )

    lines.extend(
        [
            f'<line class="divider" x1="52" y1="{height - 54}" x2="{width - 52}" y2="{height - 54}"/>',
            f'<text class="mono faint" x="52" y="{height - 29}" font-size="10" letter-spacing="1.2">{source}</text>',
            f'<text class="mono faint" x="{width - 52}" y="{height - 29}" text-anchor="end" font-size="10" letter-spacing="1.2">SNAPSHOT {generated_on.isoformat()} UTC</text>',
            "</svg>",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument(
        "--output", type=Path, default=Path("docs/assets/star-history.svg")
    )
    parser.add_argument(
        "--date", type=date.fromisoformat, default=datetime.now(timezone.utc).date()
    )
    args = parser.parse_args()
    if not args.repo:
        parser.error("--repo is required outside GitHub Actions")

    timestamps = fetch_stargazers(args.repo, os.environ.get("GITHUB_TOKEN"))
    svg = render_svg(args.repo, timestamps, args.date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(f"Wrote {args.output} with {len(timestamps)} stargazers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
