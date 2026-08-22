#!/usr/bin/env python3
"""Install the local no-negative-echo runtime package for a supported agent."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
from tempfile import mkdtemp
from typing import BinaryIO, Iterable, Iterator
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPOSITORY_ROOT / "no-negative-echo"
SKILL_NAME = "no-negative-echo"
PROVENANCE_FILE = Path(".no-negative-echo-provenance.json")
PACKAGE_ID = "io.github.lb623.no-negative-echo"
SOURCE_REPOSITORY = "https://github.com/LB623/no-negative-echo"
CURRENT_PROVENANCE_SHA256 = (
    "9cc10a0f1d2d87f0de8517bf40c59e364783e2410308a0c8f815288f53a7cc47"
)
# Preserve prior published marker digests here when the runtime changes.
KNOWN_OFFICIAL_PROVENANCE_SHA256 = frozenset({CURRENT_PROVENANCE_SHA256})
RUNTIME_FILES = frozenset(
    {
        PROVENANCE_FILE,
        Path("SKILL.md"),
        Path("agents/openai.yaml"),
        Path("assets/decision-boundary.png"),
        Path("assets/icon-400.png"),
        Path("assets/icon.png"),
        Path("scripts/check_surface.py"),
    }
)
RUNTIME_DIRECTORIES = frozenset({Path("agents"), Path("assets"), Path("scripts")})
AGENT_SKILLS_DIRS = {
    "codex": Path(".agents/skills"),
    "claude": Path(".claude/skills"),
    "cursor": Path(".cursor/skills"),
    "gemini": Path(".gemini/skills"),
    "copilot": Path(".copilot/skills"),
    "shared": Path(".agents/skills"),
}
AGENT_PRESETS = (*AGENT_SKILLS_DIRS, "codex-legacy")
NATIVE_SHARED_AGENTS = ("cursor", "gemini", "copilot")
LOCK_MAGIC = b"no-negative-echo-install-lock-v1\n"
LEGACY_TEXT_SUFFIXES = frozenset({".md", ".py", ".svg", ".yaml"})
LEGACY_OFFICIAL_MANIFESTS: dict[str, dict[Path, str]] = {
    "5ba55a4217568e94f22414cb5bbcde4b51c37995": {
        Path(
            "SKILL.md"
        ): "287c76a9cd417b89e871e8f7de1e76e526eb6f8fa18386aae0c134c9601059a5",
        Path(
            "agents/openai.yaml"
        ): "52252e049b122733259dc17f17d54359b4e6445eed1482c393e7744a6f8e9a4c",
        Path(
            "assets/decision-boundary.png"
        ): "3c80021dc245b4a3fe02a18434fc200fae0db3810c8fd451acc25bfb2e831d7a",
        Path(
            "assets/icon-400.png"
        ): "9ba3b39b106a1f6b6a376a4ccf91373e8f80923d87ca244892c35c7f95a1a121",
        Path(
            "assets/icon.png"
        ): "052b7bf0101ab53cbfe2a909155d36df7554acbfbefeefbe94f00e5cf2e74b74",
        Path(
            "scripts/check_surface.py"
        ): "d63a03fb1052706e1e5d1b23d413251dff5690e0c3e837c069826de6fe06661b",
    },
    "bc20e6b0eb7d224f32600ce972bb333a2f1ca3f0": {
        Path(
            "SKILL.md"
        ): "4447f3ba40746ef566785662963f5eb0260149845c53f58bd67009680b0b4603",
        Path(
            "agents/openai.yaml"
        ): "52252e049b122733259dc17f17d54359b4e6445eed1482c393e7744a6f8e9a4c",
        Path(
            "assets/decision-boundary.png"
        ): "3c80021dc245b4a3fe02a18434fc200fae0db3810c8fd451acc25bfb2e831d7a",
        Path(
            "assets/icon-400.png"
        ): "9ba3b39b106a1f6b6a376a4ccf91373e8f80923d87ca244892c35c7f95a1a121",
        Path(
            "assets/icon.png"
        ): "052b7bf0101ab53cbfe2a909155d36df7554acbfbefeefbe94f00e5cf2e74b74",
        Path(
            "scripts/check_surface.py"
        ): "275d3172c118bf5578e7b71a074a9407b135f20bb8f7e7790dc5c15332c4979e",
    },
    "df9b15cda4288e4e804a0650ca5b05a81ff222ae": {
        Path(
            "SKILL.md"
        ): "4447f3ba40746ef566785662963f5eb0260149845c53f58bd67009680b0b4603",
        Path(
            "agents/openai.yaml"
        ): "52252e049b122733259dc17f17d54359b4e6445eed1482c393e7744a6f8e9a4c",
        Path(
            "assets/decision-boundary-en.svg"
        ): "8ad70ca4b20271fb41ea8042930ff13a4416106a51924d47566b1a05ca96395f",
        Path(
            "assets/decision-boundary-zh.svg"
        ): "463565dbdd39cd009915074cd2d78ec67c18385fea79ba2f0f58cf68f5747ff1",
        Path(
            "assets/icon-400.png"
        ): "9ba3b39b106a1f6b6a376a4ccf91373e8f80923d87ca244892c35c7f95a1a121",
        Path(
            "assets/icon.png"
        ): "052b7bf0101ab53cbfe2a909155d36df7554acbfbefeefbe94f00e5cf2e74b74",
        Path(
            "scripts/check_surface.py"
        ): "275d3172c118bf5578e7b71a074a9407b135f20bb8f7e7790dc5c15332c4979e",
    },
    "367e09d5c95df6d7fa5864cad1b3b7ee5c2678ae": {
        Path(
            "SKILL.md"
        ): "4447f3ba40746ef566785662963f5eb0260149845c53f58bd67009680b0b4603",
        Path(
            "agents/openai.yaml"
        ): "52252e049b122733259dc17f17d54359b4e6445eed1482c393e7744a6f8e9a4c",
        Path(
            "assets/icon-400.png"
        ): "9ba3b39b106a1f6b6a376a4ccf91373e8f80923d87ca244892c35c7f95a1a121",
        Path(
            "assets/icon.png"
        ): "052b7bf0101ab53cbfe2a909155d36df7554acbfbefeefbe94f00e5cf2e74b74",
        Path(
            "scripts/check_surface.py"
        ): "275d3172c118bf5578e7b71a074a9407b135f20bb8f7e7790dc5c15332c4979e",
    },
    "56f5ff22c7c2af894065f991c057f1526ffae6aa": {
        Path(
            "SKILL.md"
        ): "4447f3ba40746ef566785662963f5eb0260149845c53f58bd67009680b0b4603",
        Path(
            "agents/openai.yaml"
        ): "bec5b6b8b177371ee450d3f3a992bc06954b0942f5839490e2312dc895229158",
        Path(
            "assets/icon-400.png"
        ): "4e3c6290779d886bc00df239f36bf8f50bf36daa64acdbb21b69d51c7abae946",
        Path(
            "assets/icon.svg"
        ): "e960d3c2276ec328f8562628869c6c16deb5853b0bdf452d5352dfee2e3715d3",
        Path(
            "scripts/check_surface.py"
        ): "275d3172c118bf5578e7b71a074a9407b135f20bb8f7e7790dc5c15332c4979e",
    },
    "9bb1d2cceac31c5129bc7f541c3fc4631cf52b25": {
        Path(
            "SKILL.md"
        ): "4447f3ba40746ef566785662963f5eb0260149845c53f58bd67009680b0b4603",
        Path(
            "agents/openai.yaml"
        ): "3a1245ee261d5507530959131077bd9597c98538a78c6799fd517ecfa892ad6c",
        Path(
            "scripts/check_surface.py"
        ): "275d3172c118bf5578e7b71a074a9407b135f20bb8f7e7790dc5c15332c4979e",
    },
}


class InstallError(RuntimeError):
    """Base class for installation failures with a safe user-facing message."""


class InstallValidationError(InstallError, ValueError):
    """The source or existing destination is not a valid package."""


class InstallRollbackError(InstallError):
    """Installation and rollback both failed, but the backup was preserved."""

    def __init__(self, backup: Path) -> None:
        self.backup = backup
        super().__init__(
            "installation failed and automatic rollback also failed; "
            f"manual recovery is required at {backup}"
        )


class InstallActivationUncertainError(InstallError):
    """A target rename completed, but the activated target was not verified."""

    def __init__(self, target: Path, backup: Path | None) -> None:
        self.target = target
        self.backup = backup
        recovery = (
            f"; the previous validated installation is preserved at {backup}"
            if backup is not None
            else ""
        )
        super().__init__(
            "the target rename completed but activation could not be verified; "
            f"do not treat the installation as successful; inspect {target}{recovery}"
        )


def default_skills_dir(agent: str = "codex") -> Path:
    """Return the current user-level skills directory for an agent preset."""

    if agent == "codex-legacy":
        codex_home = os.environ.get("CODEX_HOME")
        root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
        return root / "skills"
    try:
        relative = AGENT_SKILLS_DIRS[agent]
    except KeyError as exc:
        raise ValueError(f"unknown agent preset: {agent}") from exc
    return Path.home() / relative


def _first_existing_target(counterparts: Iterable[Path]) -> Path | None:
    for counterpart in counterparts:
        if _exists_without_following(counterpart):
            return counterpart
    return None


def _first_nested_skill_target(root: Path, selected: Path) -> Path | None:
    """Find another conventionally named Skill without following nested links."""

    if not _exists_without_following(root):
        return None
    try:
        if not stat.S_ISDIR(root.stat().st_mode):
            raise InstallValidationError(
                f"skill discovery root is not a directory: {root}"
            )
    except OSError as exc:
        raise InstallValidationError(
            f"skill discovery root could not be inspected: {root}"
        ) from exc

    def fail_on_walk_error(exc: OSError) -> None:
        raise InstallValidationError(
            f"skill discovery root could not be inspected: {root}"
        ) from exc

    for current, directory_names, _ in os.walk(
        root, topdown=True, followlinks=False, onerror=fail_on_walk_error
    ):
        current_path = Path(current)
        for name in sorted(directory_names):
            candidate = current_path / name
            if (
                name == SKILL_NAME
                and candidate != selected
                and _exists_without_following(candidate / "SKILL.md")
            ):
                return candidate
    return None


def _resolve_cli_skills_dir(
    agent: str | None, override: Path | None
) -> tuple[Path, str | None]:
    """Resolve CLI destination and prevent ambiguous duplicate installations."""

    if override is not None:
        expanded = override.expanduser()
        if not expanded.is_absolute():
            raise InstallValidationError("--skills-dir must be an absolute path")
        return expanded.resolve(), None

    current_dir = default_skills_dir("codex")
    legacy_dir = default_skills_dir("codex-legacy")
    claude_dir = default_skills_dir("claude")
    current_target = current_dir / SKILL_NAME
    legacy_target = legacy_dir / SKILL_NAME
    native_dirs = {
        native_agent: default_skills_dir(native_agent)
        for native_agent in NATIVE_SHARED_AGENTS
    }
    native_targets = {
        native_agent: directory / SKILL_NAME
        for native_agent, directory in native_dirs.items()
    }

    def reject_discovery_duplicate(
        selected: Path,
        counterparts: Iterable[Path],
        recursive_roots: Iterable[Path],
    ) -> None:
        conflict = _first_existing_target(counterparts)
        if conflict is None:
            inspected_roots: set[Path] = set()
            for root in recursive_roots:
                if root in inspected_roots:
                    continue
                inspected_roots.add(root)
                conflict = _first_nested_skill_target(root, selected)
                if conflict is not None:
                    break
        if conflict is not None:
            raise InstallValidationError(
                "refusing to create multiple discoverable installs for the "
                "selected agent: another no-negative-echo target already exists "
                f"at {conflict}; resolve it manually before installing"
            )

    if agent == "claude":
        reject_discovery_duplicate(
            claude_dir / SKILL_NAME,
            (),
            (claude_dir,),
        )
        return claude_dir, None

    if agent in NATIVE_SHARED_AGENTS:
        native_dir = native_dirs[agent]
        counterparts = [current_target]
        if agent == "cursor":
            counterparts.extend(
                [
                    claude_dir / SKILL_NAME,
                    legacy_target,
                ]
            )
        recursive_roots = [native_dir, current_dir]
        if agent == "cursor":
            recursive_roots.extend(
                [
                    claude_dir,
                    legacy_dir,
                ]
            )
        reject_discovery_duplicate(
            native_dir / SKILL_NAME,
            counterparts,
            recursive_roots,
        )
        return native_dir, None

    current_exists = _exists_without_following(current_target)
    legacy_exists = _exists_without_following(legacy_target)
    duplicate_error = (
        "refusing to create a second Codex install across the current and legacy "
        "locations: another no-negative-echo target already exists; resolve it "
        "manually before installing"
    )

    if agent in {"codex", "shared"}:
        if legacy_exists:
            raise InstallValidationError(duplicate_error)
        reject_discovery_duplicate(
            current_target,
            (*native_targets.values(), claude_dir / SKILL_NAME),
            (current_dir, legacy_dir, *native_dirs.values(), claude_dir),
        )
        return current_dir, None

    if agent == "codex-legacy":
        if current_exists:
            raise InstallValidationError(duplicate_error)
        reject_discovery_duplicate(
            legacy_target,
            (
                current_target,
                native_targets["cursor"],
                claude_dir / SKILL_NAME,
            ),
            (
                legacy_dir,
                current_dir,
                native_dirs["cursor"],
                claude_dir,
            ),
        )
        return legacy_dir, None

    if agent is None:
        if current_exists and legacy_exists:
            raise InstallValidationError(duplicate_error)
        if legacy_exists and not current_exists:
            reject_discovery_duplicate(
                legacy_target,
                (
                    current_target,
                    native_targets["cursor"],
                    claude_dir / SKILL_NAME,
                ),
                (
                    legacy_dir,
                    current_dir,
                    native_dirs["cursor"],
                    claude_dir,
                ),
            )
            return (
                legacy_dir,
                "reusing the existing legacy Codex destination; migrate it "
                "manually before switching to --agent codex",
            )
        reject_discovery_duplicate(
            current_target,
            (*native_targets.values(), claude_dir / SKILL_NAME),
            (current_dir, legacy_dir, *native_dirs.values(), claude_dir),
        )
        return current_dir, None

    return default_skills_dir(agent), None


def _check_additional_discovery_roots(
    skills_dir: Path, discovery_roots: Iterable[Path]
) -> None:
    """Recheck caller-declared discovery roots while the global lock is held."""

    selected = skills_dir.resolve() / SKILL_NAME
    inspected: set[Path] = set()
    for supplied_root in discovery_roots:
        expanded = supplied_root.expanduser()
        if not expanded.is_absolute():
            raise InstallValidationError(
                "--discovery-root values must be absolute paths"
            )
        root = expanded.resolve()
        if root in inspected:
            continue
        inspected.add(root)
        conflict = _first_nested_skill_target(root, selected)
        if conflict is not None:
            raise InstallValidationError(
                "refusing to create multiple discoverable installs: another "
                f"no-negative-echo target exists at {conflict}; resolve it "
                "manually before installing"
            )


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _exists_without_following(path: Path) -> bool:
    return _lstat(path) is not None


def _is_physical_ancestor_or_same(ancestor: Path, descendant: Path) -> bool:
    """Compare existing path identities, including case-insensitive aliases."""

    if not _exists_without_following(ancestor):
        return False

    current = descendant
    while True:
        if _exists_without_following(current):
            try:
                if os.path.samefile(ancestor, current):
                    return True
            except FileNotFoundError:
                # A concurrent rename is rechecked by the activation transaction.
                pass
            except OSError as exc:
                raise InstallValidationError(
                    "path overlap identity could not be verified"
                ) from exc
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _is_ignored_runtime_directory(relative: Path) -> bool:
    return relative.name == "__pycache__" and "__pycache__" not in relative.parent.parts


def _is_ignored_runtime_file(relative: Path) -> bool:
    return relative.name == ".DS_Store" or (
        relative.parent.name == "__pycache__" and relative.suffix in {".pyc", ".pyo"}
    )


def _read_skill_name(skill_file: Path) -> str:
    file_stat = _lstat(skill_file)
    if file_stat is None or not stat.S_ISREG(file_stat.st_mode):
        raise InstallValidationError("SKILL.md must be a regular file")

    try:
        text = skill_file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise InstallValidationError("SKILL.md must be readable UTF-8 text") from exc

    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise InstallValidationError("SKILL.md is missing YAML frontmatter")

    names: list[str] = []
    for line in lines[1:]:
        if line == "---":
            break
        if line.startswith("name:"):
            value = line.split(":", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            names.append(value)
    else:
        raise InstallValidationError("SKILL.md frontmatter is not terminated")

    if len(names) != 1:
        raise InstallValidationError("SKILL.md must contain exactly one name field")
    return names[0]


def _sha256_regular_file(path: Path) -> str:
    before = _lstat(path)
    if before is None or not stat.S_ISREG(before.st_mode):
        raise InstallValidationError(f"runtime file must be regular: {path.name}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if _identity(opened) != _identity(before):
                raise InstallValidationError(
                    f"runtime file changed while it was inspected: {path.name}"
                )
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise InstallValidationError(
            f"runtime file could not be read: {path.name}"
        ) from exc
    after = _lstat(path)
    if after is None or _identity(after) != _identity(before):
        raise InstallValidationError(
            f"runtime file changed while it was inspected: {path.name}"
        )
    return digest.hexdigest()


def _sha256_legacy_file(path: Path, relative: Path) -> str:
    """Hash a legacy file, canonicalizing checkout-only CRLF text changes."""

    if relative.suffix not in LEGACY_TEXT_SUFFIXES:
        return _sha256_regular_file(path)
    before = _lstat(path)
    if before is None or not stat.S_ISREG(before.st_mode):
        raise InstallValidationError(f"runtime file must be regular: {path.name}")
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if _identity(opened) != _identity(before):
                raise InstallValidationError(
                    f"runtime file changed while it was inspected: {path.name}"
                )
            contents = handle.read()
    except OSError as exc:
        raise InstallValidationError(
            f"runtime file could not be read: {path.name}"
        ) from exc
    after = _lstat(path)
    if after is None or _identity(after) != _identity(before):
        raise InstallValidationError(
            f"runtime file changed while it was inspected: {path.name}"
        )
    return hashlib.sha256(contents.replace(b"\r\n", b"\n")).hexdigest()


def _normalized_sha256(value: str, label: str) -> str:
    normalized = value.strip()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise InstallValidationError(f"{label} must be 64 lowercase hex characters")
    return normalized


def _load_provenance(root: Path) -> dict[str, object]:
    marker = root / PROVENANCE_FILE
    before = _lstat(marker)
    if before is None or not stat.S_ISREG(before.st_mode):
        raise InstallValidationError("runtime provenance marker must be regular")
    try:
        with marker.open("r", encoding="utf-8") as handle:
            opened = os.fstat(handle.fileno())
            if _identity(opened) != _identity(before):
                raise InstallValidationError(
                    "runtime provenance marker changed while it was inspected"
                )
            pairs: list[tuple[str, object]] = json.load(
                handle, object_pairs_hook=lambda value: value
            )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallValidationError(
            "runtime provenance marker must be readable JSON"
        ) from exc
    after = _lstat(marker)
    if after is None or _identity(after) != _identity(before):
        raise InstallValidationError(
            "runtime provenance marker changed while it was inspected"
        )

    def unique_object(value: object, label: str) -> dict[str, object]:
        if not isinstance(value, list):
            raise InstallValidationError(f"{label} must be a JSON object")
        result: dict[str, object] = {}
        for item in value:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
            ):
                raise InstallValidationError(f"{label} must be a JSON object")
            key, nested_value = item
            if key in result:
                raise InstallValidationError(f"{label} contains a duplicate key")
            result[key] = nested_value
        return result

    payload = unique_object(pairs, "runtime provenance marker")
    if set(payload) != {
        "schema_version",
        "package_id",
        "source_repository",
        "files",
    }:
        raise InstallValidationError("runtime provenance marker has invalid fields")
    schema_version = payload["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        raise InstallValidationError("runtime provenance schema is unsupported")
    if payload["package_id"] != PACKAGE_ID:
        raise InstallValidationError("runtime provenance package identity is invalid")
    if payload["source_repository"] != SOURCE_REPOSITORY:
        raise InstallValidationError("runtime provenance source is invalid")

    files = unique_object(payload["files"], "runtime provenance files")
    expected_files = {str(path) for path in RUNTIME_FILES - {PROVENANCE_FILE}}
    if set(files) != expected_files:
        raise InstallValidationError("runtime provenance file manifest is invalid")
    for relative, expected_digest in files.items():
        if (
            not isinstance(expected_digest, str)
            or len(expected_digest) != 64
            or any(character not in "0123456789abcdef" for character in expected_digest)
        ):
            raise InstallValidationError(
                f"runtime provenance digest is invalid: {relative}"
            )
        actual_digest = _sha256_regular_file(root / relative)
        if actual_digest != expected_digest:
            raise InstallValidationError(
                f"runtime file does not match provenance: {relative}"
            )
    return payload


def _scan_runtime_tree(
    root: Path,
    *,
    allow_ignored: bool,
    allowed_files: frozenset[Path] | set[Path],
    allowed_directories: frozenset[Path] | set[Path],
) -> tuple[set[Path], set[Path]]:
    root_stat = _lstat(root)
    if root_stat is None or not stat.S_ISDIR(root_stat.st_mode):
        raise InstallValidationError("runtime source must be a regular directory")

    found_files: set[Path] = set()
    found_directories: set[Path] = set()

    for current, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        retained_directories: list[str] = []

        for name in sorted(directory_names):
            path = current_path / name
            relative = path.relative_to(root)
            entry_stat = _lstat(path)
            if entry_stat is None or not stat.S_ISDIR(entry_stat.st_mode):
                raise InstallValidationError(
                    f"runtime package contains a symlink or special entry: {relative}"
                )
            if allow_ignored and _is_ignored_runtime_directory(relative):
                retained_directories.append(name)
                continue
            if relative not in allowed_directories:
                raise InstallValidationError(
                    f"runtime package contains an unknown directory: {relative}"
                )
            found_directories.add(relative)
            retained_directories.append(name)

        directory_names[:] = retained_directories

        for name in sorted(file_names):
            path = current_path / name
            relative = path.relative_to(root)
            entry_stat = _lstat(path)
            if entry_stat is None or not stat.S_ISREG(entry_stat.st_mode):
                raise InstallValidationError(
                    f"runtime package contains a symlink or special entry: {relative}"
                )
            if allow_ignored and _is_ignored_runtime_file(relative):
                continue
            if relative not in allowed_files:
                raise InstallValidationError(
                    f"runtime package contains an unknown file: {relative}"
                )
            found_files.add(relative)

    return found_files, found_directories


def _require_complete_runtime_structure(
    found_files: set[Path],
    found_directories: set[Path],
    expected_files: frozenset[Path] | set[Path],
    expected_directories: frozenset[Path] | set[Path],
) -> None:
    missing_files = expected_files - found_files
    missing_directories = expected_directories - found_directories
    if missing_files or missing_directories:
        missing = sorted(str(path) for path in missing_directories | missing_files)
        raise InstallValidationError(
            "runtime package is incomplete; missing: " + ", ".join(missing)
        )


def _validate_runtime_tree(root: Path, *, allow_ignored: bool) -> None:
    found_files, found_directories = _scan_runtime_tree(
        root,
        allow_ignored=allow_ignored,
        allowed_files=RUNTIME_FILES,
        allowed_directories=RUNTIME_DIRECTORIES,
    )
    _require_complete_runtime_structure(
        found_files,
        found_directories,
        RUNTIME_FILES,
        RUNTIME_DIRECTORIES,
    )
    if _read_skill_name(root / "SKILL.md") != SKILL_NAME:
        raise InstallValidationError(f"SKILL.md name must be exactly {SKILL_NAME!r}")
    _load_provenance(root)


def _manifest_directories(files: set[Path]) -> set[Path]:
    return {
        parent
        for relative in files
        for parent in relative.parents
        if parent != Path(".")
    }


def _validate_legacy_official_runtime(root: Path, *, allow_ignored: bool) -> str:
    """Recognize only exact official packages released before provenance v1."""

    allowed_files = {
        relative
        for manifest in LEGACY_OFFICIAL_MANIFESTS.values()
        for relative in manifest
    }
    allowed_directories = _manifest_directories(allowed_files)
    found_files, found_directories = _scan_runtime_tree(
        root,
        allow_ignored=allow_ignored,
        allowed_files=allowed_files,
        allowed_directories=allowed_directories,
    )
    if _read_skill_name(root / "SKILL.md") != SKILL_NAME:
        raise InstallValidationError(f"SKILL.md name must be exactly {SKILL_NAME!r}")

    candidates = [
        (commit, manifest)
        for commit, manifest in LEGACY_OFFICIAL_MANIFESTS.items()
        if set(manifest) == found_files
        and _manifest_directories(set(manifest)) == found_directories
    ]
    if not candidates:
        raise InstallValidationError(
            "existing runtime does not match a recognized official legacy release"
        )
    actual_digests = {
        relative: _sha256_legacy_file(root / relative, relative)
        for relative in found_files
    }
    for commit, manifest in candidates:
        if actual_digests == manifest:
            return commit
    raise InstallValidationError(
        "existing runtime does not match a recognized official legacy release"
    )


def _validate_existing_runtime_tree(root: Path, *, allow_ignored: bool) -> str | None:
    if _exists_without_following(root / PROVENANCE_FILE):
        marker_digest = _sha256_regular_file(root / PROVENANCE_FILE)
        if marker_digest not in KNOWN_OFFICIAL_PROVENANCE_SHA256:
            raise InstallValidationError(
                "existing runtime provenance is not a recognized official release"
            )
        _validate_runtime_tree(root, allow_ignored=allow_ignored)
        if _sha256_regular_file(root / PROVENANCE_FILE) != marker_digest:
            raise InstallValidationError(
                "existing runtime provenance changed during validation"
            )
        return None
    return _validate_legacy_official_runtime(root, allow_ignored=allow_ignored)


def _identity(entry_stat: os.stat_result) -> tuple[int, int]:
    return entry_stat.st_dev, entry_stat.st_ino


def _recognized_existing_install_identity(target: Path) -> tuple[int, int] | None:
    before = _lstat(target)
    if before is None or not stat.S_ISDIR(before.st_mode):
        return None

    try:
        _validate_existing_runtime_tree(target, allow_ignored=True)
    except InstallValidationError:
        return None

    after = _lstat(target)
    if after is None or not stat.S_ISDIR(after.st_mode):
        return None
    if _identity(after) != _identity(before):
        return None
    return _identity(after)


def _record_cleanup_notice(notices: list[str] | None, message: str) -> None:
    try:
        if notices is None:
            print(f"Install warning: {message}", file=sys.stderr)
        else:
            notices.append(message)
    except BaseException:
        # Reporting must not turn an already-activated install into a failure.
        pass


@contextmanager
def _staging_directory(
    skills_dir: Path,
    activation_state: dict[str, bool],
    notices: list[str] | None,
) -> Iterator[Path]:
    temporary_path = Path(
        mkdtemp(prefix=f".{SKILL_NAME}-install-", dir=skills_dir.parent)
    )
    temporary_stat = _lstat(temporary_path)
    if temporary_stat is None or not stat.S_ISDIR(temporary_stat.st_mode):
        raise InstallValidationError("staging directory was not created safely")
    temporary_identity = _identity(temporary_stat)

    def remove_if_same_and_empty() -> None:
        try:
            current_stat = _lstat(temporary_path)
            if current_stat is None:
                return
            if (
                not stat.S_ISDIR(current_stat.st_mode)
                or _identity(current_stat) != temporary_identity
            ):
                _record_cleanup_notice(
                    notices,
                    "staging directory identity changed; no cleanup was attempted "
                    f"at {temporary_path}",
                )
                return
            temporary_path.rmdir()
        except BaseException as exc:
            _record_cleanup_notice(
                notices,
                f"staging directory was preserved at {temporary_path}: {exc}",
            )

    try:
        yield temporary_path
    except BaseException as exc:
        if activation_state["active"]:
            _record_cleanup_notice(
                notices,
                f"post-activation housekeeping failed: {exc}",
            )
            remove_if_same_and_empty()
            return
        if activation_state["target_renamed"]:
            remove_if_same_and_empty()
        else:
            _record_cleanup_notice(
                notices,
                "failed installation preserved staging data for inspection at "
                f"{temporary_path}",
            )
        raise
    remove_if_same_and_empty()


def _validate_lock_identity(lock_path: Path, handle: BinaryIO) -> os.stat_result:
    current_stat = _lstat(lock_path)
    handle_stat = os.fstat(handle.fileno())
    if (
        current_stat is None
        or not stat.S_ISREG(current_stat.st_mode)
        or current_stat.st_nlink != 1
        or _identity(current_stat) != _identity(handle_stat)
    ):
        raise InstallValidationError(f"installation lock identity changed: {lock_path}")
    if hasattr(os, "geteuid") and current_stat.st_uid != os.geteuid():
        raise InstallValidationError(
            f"installation lock has an unexpected owner: {lock_path}"
        )
    if os.name != "nt" and current_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise InstallValidationError(
            f"installation lock is writable by another user: {lock_path}"
        )
    return current_stat


@contextmanager
def _open_lock_file(lock_path: Path) -> Iterator[tuple[BinaryIO, bool]]:
    """Open a lock descriptor; callers must revalidate it after locking."""

    binary_flag = getattr(os, "O_BINARY", 0)
    no_follow_flag = getattr(os, "O_NOFOLLOW", 0)
    for _ in range(3):
        lock_stat = _lstat(lock_path)
        created = lock_stat is None
        if lock_stat is not None and (
            not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1
        ):
            raise InstallValidationError(
                f"installation lock must be a regular file: {lock_path}"
            )
        flags = os.O_RDWR | binary_flag | no_follow_flag
        if created:
            flags |= os.O_CREAT | os.O_EXCL
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except FileExistsError:
            continue
        except OSError as exc:
            raise InstallValidationError(
                f"installation lock could not be opened: {lock_path}"
            ) from exc

        with os.fdopen(descriptor, "r+b") as handle:
            _validate_lock_identity(lock_path, handle)
            if created:
                handle.write(LOCK_MAGIC)
                handle.flush()
            yield handle, created
            return
    raise InstallValidationError(
        f"installation lock changed repeatedly while opening: {lock_path}"
    )


def _validate_locked_lock(
    lock_path: Path,
    handle: BinaryIO,
    created: bool,
    observation: dict[str, str] | None = None,
) -> None:
    """Bind the locked descriptor back to its path and validate its marker."""

    _validate_lock_identity(lock_path, handle)
    handle.seek(0)
    contents = handle.read(len(LOCK_MAGIC) + 1)
    status = "created" if created else "validated"
    if not created and contents in {b"", b"\0"}:
        handle.seek(0)
        handle.truncate()
        handle.write(LOCK_MAGIC)
        handle.flush()
        contents = LOCK_MAGIC
        status = "migrated-legacy"
    if contents != LOCK_MAGIC:
        raise InstallValidationError(
            f"installation lock has invalid contents: {lock_path}"
        )
    _validate_lock_identity(lock_path, handle)
    if observation is not None:
        observation["path"] = str(lock_path)
        observation["status"] = status


@contextmanager
def _named_installation_lock(
    lock_path: Path, observation: dict[str, str] | None = None
) -> Iterator[None]:
    with _open_lock_file(lock_path) as (handle, created):
        _lock_file(handle)
        try:
            _validate_locked_lock(lock_path, handle, created, observation)
            yield
        finally:
            _unlock_file(handle)


@contextmanager
def _installation_lock(skills_dir: Path) -> Iterator[None]:
    """Serialize cooperating installers for one destination root."""

    lock_path = skills_dir / f".{SKILL_NAME}-install.lock"
    with _named_installation_lock(lock_path):
        yield


def _cli_lock_path() -> Path:
    if hasattr(os, "getuid"):
        lock_root = Path("/tmp")
        user_key = str(os.getuid())
    else:
        lock_root = Path.home().resolve()
        home_key = os.path.normcase(str(lock_root)).encode("utf-8")
        user_key = hashlib.sha256(home_key).hexdigest()[:16]
    return lock_root / f".{SKILL_NAME}-cli-{user_key}.lock"


@contextmanager
def _cli_installation_lock(
    completion_state: dict[str, bool],
    notices: list[str],
    observation: dict[str, str],
) -> Iterator[None]:
    """Serialize preset selection and activation across discovery roots."""

    lock_path = _cli_lock_path()
    try:
        with _open_lock_file(lock_path) as (handle, created):
            _lock_file(handle)
            try:
                _validate_locked_lock(lock_path, handle, created, observation)
                yield
            except BaseException:
                try:
                    _unlock_file(handle)
                except BaseException:
                    pass
                raise
            try:
                _unlock_file(handle)
            except BaseException as exc:
                if not completion_state["complete"]:
                    raise
                _record_cleanup_notice(
                    notices,
                    "global coordination lock release failed after activation: "
                    f"{exc}",
                )
    except BaseException as exc:
        if not completion_state["complete"]:
            raise
        _record_cleanup_notice(
            notices,
            f"global coordination lock housekeeping failed after activation: {exc}",
        )


def _lock_file(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_file(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def install_skill(
    source: Path,
    skills_dir: Path,
    *,
    cleanup_notices: list[str] | None = None,
    expected_provenance_sha256: str | None = None,
) -> Path:
    source_input = source.expanduser()
    source_stat = _lstat(source_input)
    if source_stat is None or not stat.S_ISDIR(source_stat.st_mode):
        raise InstallValidationError("runtime source must be a regular directory")

    source = source_input.resolve()
    skills_dir = skills_dir.expanduser().resolve()
    if (
        skills_dir == source
        or skills_dir.is_relative_to(source)
        or _is_physical_ancestor_or_same(source, skills_dir)
    ):
        raise InstallValidationError("skills directory must not be inside the source")

    target = skills_dir / SKILL_NAME
    if (
        source == target
        or source.is_relative_to(target)
        or target.is_relative_to(source)
        or _is_physical_ancestor_or_same(source, target)
        or _is_physical_ancestor_or_same(target, source)
    ):
        raise InstallValidationError(
            "runtime source and install target must not overlap"
        )

    source_provenance_sha256 = _sha256_regular_file(source / PROVENANCE_FILE)
    if expected_provenance_sha256 is not None:
        expected_provenance_sha256 = _normalized_sha256(
            expected_provenance_sha256,
            "expected provenance SHA-256",
        )
        if source_provenance_sha256 != expected_provenance_sha256:
            raise InstallValidationError(
                "runtime provenance does not match the expected SHA-256"
            )
    _validate_runtime_tree(source, allow_ignored=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    activation_state = {"active": False, "target_renamed": False}
    with _staging_directory(skills_dir, activation_state, cleanup_notices) as temp:
        staged = temp / "staged"
        shutil.copytree(
            source,
            staged,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.py[cod]", ".DS_Store"),
        )
        _validate_runtime_tree(staged, allow_ignored=False)
        if _sha256_regular_file(staged / PROVENANCE_FILE) != source_provenance_sha256:
            raise InstallValidationError(
                "runtime provenance changed while the package was staged"
            )
        staged_stat = _lstat(staged)
        if staged_stat is None or not stat.S_ISDIR(staged_stat.st_mode):
            raise InstallValidationError("staged runtime package disappeared")
        staged_identity = _identity(staged_stat)

        def validate_staged_runtime() -> None:
            _validate_runtime_tree(staged, allow_ignored=False)
            if (
                _sha256_regular_file(staged / PROVENANCE_FILE)
                != source_provenance_sha256
            ):
                raise InstallValidationError(
                    "runtime provenance changed while the package was staged"
                )
            current_staged_stat = _lstat(staged)
            if (
                current_staged_stat is None
                or not stat.S_ISDIR(current_staged_stat.st_mode)
                or _identity(current_staged_stat) != staged_identity
            ):
                raise InstallValidationError(
                    "staged runtime package changed before activation"
                )

        with _installation_lock(skills_dir):
            validate_staged_runtime()
            had_previous = _exists_without_following(target)
            previous_identity = (
                _recognized_existing_install_identity(target) if had_previous else None
            )
            if had_previous and previous_identity is None:
                raise InstallValidationError(
                    "refusing to replace a destination that is not a validated "
                    f"{SKILL_NAME} runtime: {target}"
                )

            # Keep recovery data outside the host's discovery root so a
            # recursive skill scanner cannot discover both old and new copies.
            backup = skills_dir.parent / f".{SKILL_NAME}-backup-{uuid4().hex}"
            previous_moved = False
            target_renamed = False
            try:
                if had_previous:
                    target.rename(backup)
                    moved_stat = _lstat(backup)
                    if (
                        moved_stat is None
                        or not stat.S_ISDIR(moved_stat.st_mode)
                        or _identity(moved_stat) != previous_identity
                    ):
                        try:
                            if _exists_without_following(target):
                                raise OSError(
                                    "destination changed while it was being replaced"
                                )
                            backup.rename(target)
                        except BaseException as rollback_error:
                            raise InstallRollbackError(backup) from rollback_error
                        raise InstallValidationError(
                            "destination changed while it was being replaced"
                        )
                    previous_moved = True
                    _validate_existing_runtime_tree(backup, allow_ignored=True)
                validate_staged_runtime()
                staged.rename(target)
                target_renamed = True
                activation_state["target_renamed"] = True
                installed_stat = _lstat(target)
                if (
                    installed_stat is None
                    or not stat.S_ISDIR(installed_stat.st_mode)
                    or _identity(installed_stat) != staged_identity
                ):
                    raise InstallValidationError(
                        "install target changed while it was being activated"
                    )
                _validate_runtime_tree(target, allow_ignored=False)
                if (
                    _sha256_regular_file(target / PROVENANCE_FILE)
                    != source_provenance_sha256
                ):
                    raise InstallValidationError(
                        "installed runtime provenance changed during activation"
                    )
                final_installed_stat = _lstat(target)
                if (
                    final_installed_stat is None
                    or not stat.S_ISDIR(final_installed_stat.st_mode)
                    or _identity(final_installed_stat) != staged_identity
                ):
                    raise InstallValidationError(
                        "install target changed while it was verified"
                    )
                activation_state["active"] = True
            except BaseException as exc:
                if target_renamed:
                    raise InstallActivationUncertainError(
                        target, backup if previous_moved else None
                    ) from exc
                if previous_moved:
                    try:
                        backup_stat = _lstat(backup)
                        if (
                            backup_stat is None
                            or not stat.S_ISDIR(backup_stat.st_mode)
                            or _identity(backup_stat) != previous_identity
                            or _exists_without_following(target)
                        ):
                            raise OSError("previous installation cannot be restored")
                        backup.rename(target)
                    except BaseException as rollback_error:
                        raise InstallRollbackError(backup) from rollback_error
                raise

            if previous_moved:
                _record_cleanup_notice(
                    cleanup_notices,
                    "the previous validated installation was preserved at "
                    f"{backup}; automatic recursive deletion is intentionally "
                    "disabled",
                )

    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--expected-provenance-sha256",
        help="expected SHA-256 of the source provenance marker",
    )
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "--agent",
        choices=AGENT_PRESETS,
        default=None,
        help=(
            "agent host whose user-level skills directory should be used "
            "(when omitted, existing Codex installs are discovered safely)"
        ),
    )
    destination.add_argument(
        "--skills-dir",
        type=Path,
        help="advanced absolute destination; requires --discovery-root",
    )
    parser.add_argument(
        "--discovery-root",
        action="append",
        default=[],
        type=Path,
        help=(
            "absolute host discovery root to recheck under the coordination "
            "lock; repeat for every documented user/workspace root"
        ),
    )
    args = parser.parse_args()

    cleanup_notices: list[str] = []
    completion_state = {"complete": False}
    coordination = {
        "path": str(_cli_lock_path()),
        "status": "validation-failed",
    }
    try:
        with _cli_installation_lock(completion_state, cleanup_notices, coordination):
            if args.skills_dir is not None and not args.discovery_root:
                raise InstallValidationError(
                    "--skills-dir requires at least one --discovery-root so "
                    "collision checks can be repeated under the coordination lock"
                )
            skills_dir, selection_notice = _resolve_cli_skills_dir(
                args.agent, args.skills_dir
            )
            _check_additional_discovery_roots(skills_dir, args.discovery_root)
            if selection_notice is not None:
                print(f"Install notice: {selection_notice}", file=sys.stderr)
            target = install_skill(
                args.source,
                skills_dir,
                cleanup_notices=cleanup_notices,
                expected_provenance_sha256=args.expected_provenance_sha256,
            )
            completion_state["complete"] = True
    except (OSError, InstallError, ValueError) as exc:
        print(
            f"Coordination lock: {coordination['path']} " f"({coordination['status']})",
            file=sys.stderr,
        )
        for notice in cleanup_notices:
            print(f"Install warning: {notice}", file=sys.stderr)
        print(f"Install failed: {exc}", file=sys.stderr)
        return 1

    for notice in cleanup_notices:
        print(f"Install warning: {notice}", file=sys.stderr)
    print(f"Coordination lock: {coordination['path']} " f"({coordination['status']})")
    print(f"Installed {SKILL_NAME} to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
