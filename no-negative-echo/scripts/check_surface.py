#!/usr/bin/env python3
"""Check exact terms across final text surfaces without printing matched values."""

from __future__ import annotations

import argparse
import codecs
import json
import os
from pathlib import Path
import stat
import sys
import unicodedata


MAX_TERMS_FILE_BYTES = 1024 * 1024
MAX_TERMS = 4096
MAX_TERM_CHARACTERS = 4096
MAX_SURFACE_BYTES = 16 * 1024 * 1024
OTHER_DEFAULT_IGNORABLE_RANGES = (
    (0x034F, 0x034F),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x2065, 0x2065),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)


class ScanInputError(ValueError):
    """An input cannot be scanned safely."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def prepare_terms(terms: list[str]) -> list[str]:
    prepared: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = normalize(term)
        if normalized and normalized not in seen:
            seen.add(normalized)
            prepared.append(normalized)
    return prepared


def _read_regular_bytes(path: Path, *, maximum_bytes: int) -> bytes:
    try:
        entry_stat = path.lstat()
    except OSError as exc:
        raise ScanInputError("unreadable_file") from exc
    if not stat.S_ISREG(entry_stat.st_mode):
        raise ScanInputError("not_regular_file")
    if entry_stat.st_size > maximum_bytes:
        raise ScanInputError("file_too_large")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ScanInputError("unreadable_file") from exc

    try:
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise ScanInputError("not_regular_file")
        if (entry_stat.st_dev, entry_stat.st_ino) != (
            opened_stat.st_dev,
            opened_stat.st_ino,
        ):
            raise ScanInputError("file_changed_during_scan")
        if opened_stat.st_size > maximum_bytes:
            raise ScanInputError("file_too_large")

        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(maximum_bytes + 1)
        if len(data) > maximum_bytes:
            raise ScanInputError("file_too_large")
        return data
    except OSError as exc:
        raise ScanInputError("unreadable_file") from exc
    finally:
        os.close(descriptor)


def load_terms(path: Path) -> list[str]:
    data = _read_regular_bytes(path, maximum_bytes=MAX_TERMS_FILE_BYTES)
    try:
        text = data.decode("utf-8-sig", errors="strict")
    except UnicodeError as exc:
        raise ScanInputError("invalid_terms_encoding") from exc

    raw_terms = [line.strip() for line in text.splitlines()]
    raw_terms = [term for term in raw_terms if term]
    if len(raw_terms) > MAX_TERMS:
        raise ScanInputError("too_many_terms")
    if any(len(term) > MAX_TERM_CHARACTERS for term in raw_terms):
        raise ScanInputError("term_too_long")
    if any(_contains_review_characters(term) for term in raw_terms):
        raise ScanInputError("unsafe_terms_characters")

    terms = prepare_terms(raw_terms)
    if not terms:
        raise ScanInputError("terms_file_empty")
    return terms


def _matched_prepared_terms(text: str, prepared_terms: list[str]) -> set[int]:
    normalized = normalize(text)
    return {index for index, term in enumerate(prepared_terms) if term in normalized}


def count_matches(text: str, terms: list[str]) -> int:
    return len(_matched_prepared_terms(text, prepare_terms(terms)))


def _decode_surface(data: bytes) -> str:
    try:
        if data.startswith(codecs.BOM_UTF32_LE) or data.startswith(codecs.BOM_UTF32_BE):
            raise ScanInputError("unsupported_text_encoding")
        if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
            return data.decode("utf-16", errors="strict")
        return data.decode("utf-8-sig", errors="strict")
    except UnicodeError as exc:
        raise ScanInputError("invalid_text_encoding") from exc


def _contains_review_characters(value: str) -> bool:
    bidi_controls = {
        "LRE",
        "RLE",
        "LRO",
        "RLO",
        "PDF",
        "LRI",
        "RLI",
        "FSI",
        "PDI",
        "BN",
    }
    for character in value:
        codepoint = ord(character)
        if unicodedata.category(character) == "Cf":
            return True
        if unicodedata.bidirectional(character) in bidi_controls:
            return True
        if any(
            start <= codepoint <= end for start, end in OTHER_DEFAULT_IGNORABLE_RANGES
        ):
            return True
    return False


def _print_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def _scan_root(path: Path) -> Path:
    root_stat = _lstat_for_scan(path)
    if root_stat is None or not _is_plain_directory(root_stat):
        raise ScanInputError("scan_root_not_directory")
    return Path(os.path.abspath(path))


def _lstat_for_scan(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except OSError:
        return None


def _is_plain_directory(entry_stat: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(entry_stat, "st_file_attributes", 0)
    return stat.S_ISDIR(entry_stat.st_mode) and not (attributes & reparse_flag)


def _validate_relative_ancestors(root: Path, relative_surface: str) -> None:
    current = root
    for component in Path(relative_surface).parts[:-1]:
        if component in {"", os.curdir, os.pardir}:
            raise ScanInputError("unsafe_path_component")
        current /= component
        entry_stat = _lstat_for_scan(current)
        if entry_stat is None or not _is_plain_directory(entry_stat):
            raise ScanInputError("unsafe_path_component")


def _relative_path_surface(path: Path, root: Path) -> str:
    absolute = os.path.abspath(path)
    try:
        common = os.path.commonpath((os.fspath(root), absolute))
    except ValueError as exc:
        raise ScanInputError("path_outside_root") from exc
    if os.path.normcase(common) != os.path.normcase(os.fspath(root)):
        raise ScanInputError("path_outside_root")
    relative_surface = Path(os.path.relpath(absolute, root)).as_posix()
    _validate_relative_ancestors(root, relative_surface)
    return relative_surface


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check final text files and filenames for exact forbidden terms."
    )
    parser.add_argument("--terms-file", required=True, type=Path)
    parser.add_argument(
        "--root",
        type=Path,
        help="scan each file's root-relative path, including directory names",
    )
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    try:
        prepared_terms = load_terms(args.terms_file)
    except ScanInputError as exc:
        _print_payload({"status": "ERROR", "reason_code": exc.reason_code})
        return 2

    try:
        root = _scan_root(args.root) if args.root is not None else None
    except ScanInputError as exc:
        _print_payload({"status": "ERROR", "reason_code": exc.reason_code})
        return 2

    failures: list[dict[str, object]] = []
    reviews: list[dict[str, object]] = []
    checked = 0

    for index, path in enumerate(args.paths, start=1):
        try:
            path_surface = (
                _relative_path_surface(path, root) if root is not None else path.name
            )
        except ScanInputError as exc:
            _print_payload(
                {
                    "status": "ERROR",
                    "files_checked": checked,
                    "file_index": index,
                    "reason_code": exc.reason_code,
                }
            )
            return 2
        try:
            data = _read_regular_bytes(path, maximum_bytes=MAX_SURFACE_BYTES)
            text = _decode_surface(data)
        except ScanInputError as exc:
            _print_payload(
                {
                    "status": "ERROR",
                    "files_checked": checked,
                    "file_index": index,
                    "reason_code": exc.reason_code,
                }
            )
            return 2

        checked += 1
        content_matches = _matched_prepared_terms(text, prepared_terms)
        path_matches = _matched_prepared_terms(path_surface, prepared_terms)
        matched_terms = content_matches | path_matches
        matched_surfaces: list[str] = []
        if content_matches:
            matched_surfaces.append("content")
        if path_matches:
            matched_surfaces.append("relative_path" if root is not None else "filename")
        if matched_terms:
            failures.append(
                {
                    "file_index": index,
                    "matched_term_count": len(matched_terms),
                    "surfaces": matched_surfaces,
                }
            )

        review_surfaces: list[str] = []
        if _contains_review_characters(text):
            review_surfaces.append("content")
        if _contains_review_characters(path_surface):
            review_surfaces.append("relative_path" if root is not None else "filename")
        if review_surfaces:
            reviews.append(
                {
                    "file_index": index,
                    "reason_code": "default_ignorable_or_bidi",
                    "surfaces": review_surfaces,
                }
            )

    if failures:
        status = "FAIL"
        return_code = 1
    elif reviews:
        status = "REVIEW"
        return_code = 1
    else:
        status = "PASS"
        return_code = 0

    _print_payload(
        {
            "status": status,
            "files_checked": checked,
            "failures": failures,
            "reviews": reviews,
        }
    )
    return return_code


if __name__ == "__main__":
    sys.exit(main())
