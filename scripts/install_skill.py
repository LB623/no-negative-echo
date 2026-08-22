#!/usr/bin/env python3
"""Install the local no-negative-echo runtime package into Codex."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import stat
import sys
from tempfile import TemporaryDirectory
from typing import BinaryIO, Iterator
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPOSITORY_ROOT / "no-negative-echo"
SKILL_NAME = "no-negative-echo"
RUNTIME_FILES = frozenset(
    {
        Path("SKILL.md"),
        Path("agents/openai.yaml"),
        Path("assets/decision-boundary.png"),
        Path("assets/icon-400.png"),
        Path("assets/icon.png"),
        Path("scripts/check_surface.py"),
    }
)
RUNTIME_DIRECTORIES = frozenset({Path("agents"), Path("assets"), Path("scripts")})


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


def default_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return root / "skills"


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


def _is_ignored_runtime_artifact(relative: Path) -> bool:
    return (
        "__pycache__" in relative.parts
        or relative.name == ".DS_Store"
        or relative.suffix in {".pyc", ".pyo"}
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


def _validate_runtime_tree(root: Path, *, allow_ignored: bool) -> None:
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
            if allow_ignored and _is_ignored_runtime_artifact(relative):
                continue
            if relative not in RUNTIME_DIRECTORIES:
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
            if allow_ignored and _is_ignored_runtime_artifact(relative):
                continue
            if relative not in RUNTIME_FILES:
                raise InstallValidationError(
                    f"runtime package contains an unknown file: {relative}"
                )
            found_files.add(relative)

    missing_files = RUNTIME_FILES - found_files
    missing_directories = RUNTIME_DIRECTORIES - found_directories
    if missing_files or missing_directories:
        missing = sorted(str(path) for path in missing_directories | missing_files)
        raise InstallValidationError(
            "runtime package is incomplete; missing: " + ", ".join(missing)
        )

    if _read_skill_name(root / "SKILL.md") != SKILL_NAME:
        raise InstallValidationError(f"SKILL.md name must be exactly {SKILL_NAME!r}")


def _identity(entry_stat: os.stat_result) -> tuple[int, int]:
    return entry_stat.st_dev, entry_stat.st_ino


def _recognized_existing_install_identity(target: Path) -> tuple[int, int] | None:
    before = _lstat(target)
    if before is None or not stat.S_ISDIR(before.st_mode):
        return None

    try:
        if _read_skill_name(target / "SKILL.md") != SKILL_NAME:
            return None
    except InstallValidationError:
        return None

    after = _lstat(target)
    if after is None or not stat.S_ISDIR(after.st_mode):
        return None
    if _identity(after) != _identity(before):
        return None
    return _identity(after)


def _remove_path(path: Path) -> None:
    entry_stat = _lstat(path)
    if entry_stat is None:
        return
    if stat.S_ISDIR(entry_stat.st_mode):
        shutil.rmtree(path)
    else:
        path.unlink()


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
    temporary = TemporaryDirectory(prefix=f".{SKILL_NAME}-install-", dir=skills_dir)
    temporary_path = Path(temporary.name)
    try:
        yield temporary_path
    except BaseException as exc:
        if activation_state["active"]:
            _record_cleanup_notice(
                notices,
                f"post-activation housekeeping failed: {exc}",
            )
        else:
            try:
                temporary.cleanup()
            except BaseException as cleanup_error:
                _record_cleanup_notice(
                    notices,
                    f"failed installation left staging data at "
                    f"{temporary_path}: {cleanup_error}",
                )
            raise
    try:
        temporary.cleanup()
    except BaseException as exc:
        if activation_state["active"]:
            _record_cleanup_notice(
                notices,
                f"staging data may remain at {temporary_path}: {exc}",
            )
        else:
            raise


def _cleanup_previous_backup(
    backup: Path,
    expected_identity: tuple[int, int],
    notices: list[str] | None,
) -> None:
    try:
        backup_stat = _lstat(backup)
        if backup_stat is None:
            return
        if (
            not stat.S_ISDIR(backup_stat.st_mode)
            or _identity(backup_stat) != expected_identity
        ):
            _record_cleanup_notice(
                notices,
                f"the previous backup identity changed; it was left at {backup}",
            )
            return
        _remove_path(backup)
    except BaseException as exc:
        _record_cleanup_notice(
            notices,
            f"the previous backup may remain at {backup}: {exc}",
        )


@contextmanager
def _installation_lock(skills_dir: Path) -> Iterator[None]:
    """Serialize cooperating installers using only the Python standard library."""

    lock_path = skills_dir / f".{SKILL_NAME}-install.lock"
    with lock_path.open("a+b") as handle:
        _lock_file(handle)
        try:
            yield
        finally:
            _unlock_file(handle)


def _lock_file(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
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

    _validate_runtime_tree(source, allow_ignored=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    activation_state = {"active": False}
    with _staging_directory(skills_dir, activation_state, cleanup_notices) as temp:
        staged = temp / "staged"
        shutil.copytree(
            source,
            staged,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.py[cod]", ".DS_Store"),
        )
        _validate_runtime_tree(staged, allow_ignored=False)
        staged_stat = _lstat(staged)
        if staged_stat is None or not stat.S_ISDIR(staged_stat.st_mode):
            raise InstallValidationError("staged runtime package disappeared")
        staged_identity = _identity(staged_stat)

        with _installation_lock(skills_dir):
            had_previous = _exists_without_following(target)
            previous_identity = (
                _recognized_existing_install_identity(target) if had_previous else None
            )
            if had_previous and previous_identity is None:
                raise InstallValidationError(
                    f"refusing to replace non-{SKILL_NAME} destination: {target}"
                )

            backup = skills_dir / f".{SKILL_NAME}-backup-{uuid4().hex}"
            previous_moved = False
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
                staged.rename(target)
                installed_stat = _lstat(target)
                if (
                    installed_stat is None
                    or not stat.S_ISDIR(installed_stat.st_mode)
                    or _identity(installed_stat) != staged_identity
                ):
                    raise InstallValidationError(
                        "install target changed while it was being activated"
                    )
                activation_state["active"] = True
            except BaseException:
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
                _cleanup_previous_backup(backup, previous_identity, cleanup_notices)

    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--skills-dir", type=Path, default=default_skills_dir())
    args = parser.parse_args()

    cleanup_notices: list[str] = []
    try:
        target = install_skill(
            args.source, args.skills_dir, cleanup_notices=cleanup_notices
        )
    except (OSError, InstallError, ValueError) as exc:
        print(f"Install failed: {exc}", file=sys.stderr)
        return 1

    for notice in cleanup_notices:
        print(f"Install warning: {notice}", file=sys.stderr)
    print(f"Installed {SKILL_NAME} to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
