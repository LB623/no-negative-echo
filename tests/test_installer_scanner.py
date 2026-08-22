#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import install_skill as installer_module  # noqa: E402
from install_skill import (  # noqa: E402
    InstallRollbackError,
    InstallValidationError,
    install_skill,
)


def make_source(root: Path) -> Path:
    source = root / "source"
    for directory in ("agents", "assets", "scripts"):
        (source / directory).mkdir(parents=True, exist_ok=True)
    (source / "SKILL.md").write_text(
        "---\nname: no-negative-echo\n---\n", encoding="utf-8"
    )
    (source / "agents" / "openai.yaml").write_text("name: test\n", encoding="utf-8")
    for filename in ("decision-boundary.png", "icon-400.png", "icon.png"):
        (source / "assets" / filename).write_bytes(b"PNG")
    (source / "scripts" / "check_surface.py").write_text(
        "#!/usr/bin/env python3\n", encoding="utf-8"
    )
    return source


class HardenedInstallerTests(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "POSIX executable bits are not used")
    def test_python_entrypoints_remain_directly_executable(self) -> None:
        with TemporaryDirectory() as temp:
            target = install_skill(
                REPOSITORY_ROOT / "no-negative-echo", Path(temp) / "skills"
            )
            entrypoints = [
                REPOSITORY_ROOT / "evals" / "score_eval.py",
                target / "scripts" / "check_surface.py",
            ]
            for entrypoint in entrypoints:
                with self.subTest(entrypoint=entrypoint.name):
                    result = subprocess.run(
                        [str(entrypoint), "--help"],
                        capture_output=True,
                        check=False,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_symlink_and_unknown_secret_file(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            outside = root / "outside"
            outside.write_text("canary", encoding="utf-8")
            icon = source / "assets" / "icon.png"
            icon.unlink()
            try:
                icon.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

            icon.unlink()
            icon.write_bytes(b"PNG")
            (source / ".env").write_text("TOKEN=canary", encoding="utf-8")
            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

    def test_rejects_nested_yaml_name_in_source_and_destination(self) -> None:
        forged_frontmatter = "---\ndescription: |\n  name: no-negative-echo\n---\n"
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            (source / "SKILL.md").write_text(forged_frontmatter, encoding="utf-8")
            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text(forged_frontmatter, encoding="utf-8")
            valuable = target / "valuable.bin"
            valuable.write_bytes(b"preserve")

            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

            self.assertEqual(valuable.read_bytes(), b"preserve")

    def test_destination_identity_is_rechecked_after_rename(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            valuable = target / "valuable.bin"
            valuable.write_bytes(b"preserve")
            real_identity = installer_module._recognized_existing_install_identity

            def wrong_identity(path: Path) -> tuple[int, int] | None:
                identity = real_identity(path)
                assert identity is not None
                return identity[0], identity[1] + 1

            with mock.patch.object(
                installer_module,
                "_recognized_existing_install_identity",
                side_effect=wrong_identity,
            ):
                with self.assertRaises(InstallValidationError):
                    install_skill(source, root / "skills")

            self.assertEqual(valuable.read_bytes(), b"preserve")
            self.assertFalse(list((root / "skills").glob(".*-backup-*")))

    def test_keyboard_interrupt_restores_previous_install(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            marker = target / "old-marker"
            marker.write_text("old", encoding="utf-8")
            real_rename = Path.rename

            def interrupted(path: Path, destination: Path) -> Path:
                if path.name == "staged":
                    raise KeyboardInterrupt
                return real_rename(path, destination)

            with mock.patch.object(Path, "rename", new=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    install_skill(source, root / "skills")
            self.assertEqual(marker.read_text(encoding="utf-8"), "old")
            self.assertFalse(list((root / "skills").glob(".*-backup-*")))

    def test_failed_rollback_preserves_external_backup(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            real_rename = Path.rename

            def broken(path: Path, destination: Path) -> Path:
                if path.name == "staged" or "-backup-" in path.name:
                    raise OSError("injected")
                return real_rename(path, destination)

            with mock.patch.object(Path, "rename", new=broken):
                with self.assertRaises(InstallRollbackError) as raised:
                    install_skill(source, root / "skills")
            self.assertTrue(raised.exception.backup.is_dir())

    def test_backup_cleanup_failure_warns_after_successful_activation(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            old_marker = target / "old-marker"
            old_marker.write_text("old", encoding="utf-8")

            notices: list[str] = []
            with mock.patch.object(
                installer_module,
                "_remove_path",
                side_effect=PermissionError("backup is locked"),
            ):
                installed = install_skill(
                    source, root / "skills", cleanup_notices=notices
                )

            self.assertTrue(os.path.samefile(installed, target))
            self.assertFalse((target / "old-marker").exists())
            backups = list((root / "skills").glob(".*-backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / "old-marker").read_text(), "old")
            self.assertEqual(len(notices), 1)
            self.assertIn("backup may remain", notices[0])

    def test_backup_inspection_failure_is_a_post_activation_notice(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            real_lstat = installer_module._lstat
            backup_stats = 0

            def fail_second_backup_stat(path: Path) -> os.stat_result | None:
                nonlocal backup_stats
                if "-backup-" in path.name:
                    backup_stats += 1
                    if backup_stats == 2:
                        raise PermissionError("backup cannot be inspected")
                return real_lstat(path)

            notices: list[str] = []
            with mock.patch.object(
                installer_module, "_lstat", side_effect=fail_second_backup_stat
            ):
                installed = install_skill(
                    source, root / "skills", cleanup_notices=notices
                )

            self.assertTrue(os.path.samefile(installed, target))
            self.assertEqual(len(notices), 1)
            self.assertIn("backup may remain", notices[0])
            self.assertEqual(len(list((root / "skills").glob(".*-backup-*"))), 1)

    def test_changed_backup_identity_is_preserved_after_activation(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            real_lstat = installer_module._lstat
            backup_stats = 0

            def change_second_backup_identity(path: Path) -> os.stat_result | None:
                nonlocal backup_stats
                result = real_lstat(path)
                if "-backup-" in path.name and result is not None:
                    backup_stats += 1
                    if backup_stats == 2:
                        return mock.Mock(
                            st_mode=result.st_mode,
                            st_dev=result.st_dev,
                            st_ino=result.st_ino + 1,
                        )
                return result

            notices: list[str] = []
            with mock.patch.object(
                installer_module, "_lstat", side_effect=change_second_backup_identity
            ):
                installed = install_skill(
                    source, root / "skills", cleanup_notices=notices
                )

            self.assertTrue(os.path.samefile(installed, target))
            self.assertEqual(len(notices), 1)
            self.assertIn("identity changed", notices[0])
            self.assertEqual(len(list((root / "skills").glob(".*-backup-*"))), 1)

    def test_staging_cleanup_failure_is_a_post_activation_notice(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            notices: list[str] = []

            with mock.patch.object(
                installer_module.TemporaryDirectory,
                "cleanup",
                side_effect=PermissionError("staging directory is locked"),
            ):
                installed = install_skill(
                    source, root / "skills", cleanup_notices=notices
                )

            self.assertTrue(os.path.samefile(installed, target))
            self.assertEqual(len(notices), 1)
            self.assertIn("staging data may remain", notices[0])

    def test_unlock_failure_is_a_post_activation_notice(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            notices: list[str] = []

            with mock.patch.object(
                installer_module,
                "_unlock_file",
                side_effect=OSError("lock release failed"),
            ):
                installed = install_skill(
                    source, root / "skills", cleanup_notices=notices
                )

            self.assertTrue(os.path.samefile(installed, target))
            self.assertEqual(len(notices), 1)
            self.assertIn("post-activation housekeeping failed", notices[0])

    def test_refuses_non_skill_destination_and_nested_skills_dir(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            target.mkdir(parents=True)
            marker = target / "keep"
            marker.write_text("valuable", encoding="utf-8")
            legacy_marker = target / "references" / "evaluation-oracle.jsonl"
            legacy_marker.parent.mkdir()
            legacy_marker.write_text("spoof", encoding="utf-8")
            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")
            self.assertTrue(marker.exists())
            with self.assertRaises(InstallValidationError):
                install_skill(source, source / "skills")

    def test_refuses_installing_source_onto_itself(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "no-negative-echo"
            shutil.copytree(make_source(root), source)
            marker = source / "keep-this-source"
            marker.write_text("source", encoding="utf-8")

            with self.assertRaises(InstallValidationError):
                install_skill(source, root)

            self.assertEqual(marker.read_text(encoding="utf-8"), "source")
            self.assertFalse(list(root.glob(".*-backup-*")))

    def test_refuses_case_alias_of_source_on_insensitive_filesystem(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "No-Negative-Echo"
            shutil.copytree(make_source(root), source)
            target_alias = root / "no-negative-echo"
            if not target_alias.exists() or not os.path.samefile(source, target_alias):
                self.skipTest("filesystem is case-sensitive")
            marker = source / ".DS_Store"
            marker.write_text("preserve", encoding="utf-8")

            with self.assertRaises(InstallValidationError):
                install_skill(source, root)

            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_refuses_source_nested_in_case_aliased_target(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            template = make_source(root)
            old_target = root / "No-Negative-Echo"
            shutil.copytree(template, old_target)
            source = old_target / "nested-source"
            shutil.copytree(template, source)
            valuable = old_target / "valuable.bin"
            valuable.write_bytes(b"preserve")
            target_alias = root / "no-negative-echo"
            if not target_alias.exists() or not os.path.samefile(
                old_target, target_alias
            ):
                self.skipTest("filesystem is case-sensitive")

            with self.assertRaises(InstallValidationError):
                install_skill(source, root)

            self.assertEqual(valuable.read_bytes(), b"preserve")
            self.assertTrue(source.is_dir())
            self.assertFalse(list(root.glob(".*-backup-*")))

    def test_refuses_case_aliased_skills_dir_inside_source(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "No-Negative-Echo"
            shutil.copytree(make_source(root), source)
            source_alias = root / "no-negative-echo"
            if not source_alias.exists() or not os.path.samefile(source, source_alias):
                self.skipTest("filesystem is case-sensitive")

            with self.assertRaises(InstallValidationError):
                install_skill(source, source_alias / "scripts")

            self.assertFalse(list((source / "scripts").glob(".*-install-*")))


class HardenedScannerTests(unittest.TestCase):
    def run_scan(
        self,
        root: Path,
        terms: bytes,
        filename: str,
        surface: bytes,
        *,
        scan_root: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        terms_path = root / "terms.txt"
        target = root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        terms_path.write_bytes(terms)
        target.write_bytes(surface)
        command = [
            sys.executable,
            str(REPOSITORY_ROOT / "no-negative-echo" / "scripts" / "check_surface.py"),
            "--terms-file",
            str(terms_path),
        ]
        if scan_root:
            command.extend(["--root", str(root)])
        command.append(str(target))
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
        )
        return result, json.loads(result.stdout)

    def test_bom_terms_and_utf16_surface_fail(self) -> None:
        with TemporaryDirectory() as temp:
            result, payload = self.run_scan(
                Path(temp),
                b"\xef\xbb\xbfredis\n",
                "surface.txt",
                "Redis".encode("utf-16"),
            )
            self.assertEqual((result.returncode, payload["status"]), (1, "FAIL"))

    def test_filename_is_scanned_without_echoing_it(self) -> None:
        with TemporaryDirectory() as temp:
            result, payload = self.run_scan(
                Path(temp), b"SENSITIVE_CANARY\n", "SENSITIVE_CANARY.txt", b"clean"
            )
            self.assertEqual((result.returncode, payload["status"]), (1, "FAIL"))
            self.assertNotIn("SENSITIVE_CANARY", result.stdout)
            self.assertEqual(payload["failures"][0]["file_index"], 1)
            self.assertNotIn("path_sha256", result.stdout)

    def test_root_relative_directory_name_is_scanned(self) -> None:
        with TemporaryDirectory() as temp:
            result, payload = self.run_scan(
                Path(temp),
                b"redis\n",
                "Redis/clean.txt",
                b"clean",
                scan_root=True,
            )
            self.assertEqual((result.returncode, payload["status"]), (1, "FAIL"))
            self.assertEqual(payload["failures"][0]["surfaces"], ["relative_path"])

    def test_root_scan_rejects_symlinked_ancestor(self) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            target = outside / "secret.txt"
            target.write_text("Redis", encoding="utf-8")
            alias = root / "alias"
            try:
                alias.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            terms = base / "terms.txt"
            terms.write_text("redis\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(
                        REPOSITORY_ROOT
                        / "no-negative-echo"
                        / "scripts"
                        / "check_surface.py"
                    ),
                    "--terms-file",
                    str(terms),
                    "--root",
                    str(root),
                    str(alias / "secret.txt"),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            payload = json.loads(result.stdout)

            self.assertEqual((result.returncode, payload["status"]), (2, "ERROR"))
            self.assertEqual(payload["reason_code"], "unsafe_path_component")

    def test_zero_width_requires_review(self) -> None:
        with TemporaryDirectory() as temp:
            result, payload = self.run_scan(
                Path(temp), b"redis\n", "surface.txt", "Re\u200bdis".encode()
            )
            self.assertEqual((result.returncode, payload["status"]), (1, "REVIEW"))

    def test_non_format_default_ignorable_requires_review(self) -> None:
        with TemporaryDirectory() as temp:
            result, payload = self.run_scan(
                Path(temp), b"redis\n", "surface.txt", "Re\u115fdis".encode()
            )
            self.assertEqual((result.returncode, payload["status"]), (1, "REVIEW"))

    def test_default_ignorable_in_terms_is_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            result, payload = self.run_scan(
                Path(temp), "re\u200bdis\n".encode(), "surface.txt", b"Redis"
            )
            self.assertEqual((result.returncode, payload["status"]), (2, "ERROR"))
            self.assertEqual(payload["reason_code"], "unsafe_terms_characters")

    def test_invalid_encoding_is_structured_error(self) -> None:
        with TemporaryDirectory() as temp:
            result, payload = self.run_scan(
                Path(temp), b"redis\n", "surface.txt", b"\xff"
            )
            self.assertEqual((result.returncode, payload["status"]), (2, "ERROR"))
            self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
