#!/usr/bin/env python3

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from io import StringIO
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
    InstallActivationUncertainError,
    InstallRollbackError,
    InstallValidationError,
    install_skill,
)


def refresh_provenance(root: Path) -> None:
    files = {
        relative.as_posix(): hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in sorted(
            installer_module.RUNTIME_FILES - {installer_module.PROVENANCE_FILE},
            key=str,
        )
    }
    payload = {
        "schema_version": 1,
        "package_id": installer_module.PACKAGE_ID,
        "source_repository": installer_module.SOURCE_REPOSITORY,
        "files": files,
    }
    marker = root / installer_module.PROVENANCE_FILE
    marker.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    test_digest = hashlib.sha256(marker.read_bytes()).hexdigest()
    installer_module.KNOWN_OFFICIAL_PROVENANCE_SHA256 = frozenset(
        {*installer_module.KNOWN_OFFICIAL_PROVENANCE_SHA256, test_digest}
    )


def printed_messages(print_mock: mock.Mock) -> list[str]:
    return [
        call.args[0]
        for call in print_mock.call_args_list
        if call.args and isinstance(call.args[0], str)
    ]


def paths_refer_to_same_file(expected: Path, reported: str) -> bool:
    try:
        return os.path.samefile(expected, Path(reported))
    except OSError:
        return False


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
    refresh_provenance(source)
    return source


def git_history_available(commit: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def make_official_legacy_runtime(
    root: Path, commit: str, *, crlf_checkout: bool = False
) -> Path:
    target = root / "skills" / "no-negative-echo"
    for relative in installer_module.LEGACY_OFFICIAL_MANIFESTS[commit]:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        contents = subprocess.check_output(
            ["git", "show", f"{commit}:no-negative-echo/{relative.as_posix()}"],
            cwd=REPOSITORY_ROOT,
        )
        if crlf_checkout and relative.suffix in installer_module.LEGACY_TEXT_SUFFIXES:
            contents = contents.replace(b"\n", b"\r\n")
        destination.write_bytes(contents)
    return target


class HardenedInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._real_cli_lock_path = installer_module._cli_lock_path
        self._coordination_temp = TemporaryDirectory()
        self.addCleanup(self._coordination_temp.cleanup)
        coordination_lock = Path(self._coordination_temp.name) / "coordination.lock"
        self._coordination_patch = mock.patch.object(
            installer_module,
            "_cli_lock_path",
            return_value=coordination_lock,
        )
        self._coordination_patch.start()
        self.addCleanup(self._coordination_patch.stop)

    def test_embedded_legacy_manifests_match_official_git_history(self) -> None:
        if not all(
            git_history_available(commit)
            for commit in installer_module.LEGACY_OFFICIAL_MANIFESTS
        ):
            self.skipTest("full repository history is unavailable")

        for commit, expected in installer_module.LEGACY_OFFICIAL_MANIFESTS.items():
            with self.subTest(commit=commit):
                listed = subprocess.check_output(
                    [
                        "git",
                        "ls-tree",
                        "-r",
                        "--name-only",
                        commit,
                        "no-negative-echo",
                    ],
                    cwd=REPOSITORY_ROOT,
                    text=True,
                ).splitlines()
                prefix = "no-negative-echo/"
                relative_paths = {Path(path.removeprefix(prefix)) for path in listed}
                self.assertEqual(relative_paths, set(expected))
                for relative, digest in expected.items():
                    blob = subprocess.check_output(
                        [
                            "git",
                            "show",
                            f"{commit}:no-negative-echo/{relative.as_posix()}",
                        ],
                        cwd=REPOSITORY_ROOT,
                    )
                    self.assertEqual(hashlib.sha256(blob).hexdigest(), digest)

    def test_migrates_exact_latest_unmarked_official_runtime(self) -> None:
        commit = "5ba55a4217568e94f22414cb5bbcde4b51c37995"
        if not git_history_available(commit):
            self.skipTest("legacy release is unavailable in this checkout")

        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = make_official_legacy_runtime(root, commit)
            notices: list[str] = []

            installed = install_skill(source, root / "skills", cleanup_notices=notices)

            self.assertTrue(os.path.samefile(installed, target))
            self.assertTrue((target / installer_module.PROVENANCE_FILE).is_file())
            self.assertEqual(
                (target / "agents" / "openai.yaml").read_text(encoding="utf-8"),
                "name: test\n",
            )
            backups = list(root.glob(".*-backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "SKILL.md").is_file())
            self.assertEqual(len(notices), 1)
            self.assertIn("previous validated installation", notices[0])

    def test_recognizes_historical_windows_crlf_checkouts(self) -> None:
        if not all(
            git_history_available(commit)
            for commit in installer_module.LEGACY_OFFICIAL_MANIFESTS
        ):
            self.skipTest("full repository history is unavailable")

        for commit in installer_module.LEGACY_OFFICIAL_MANIFESTS:
            with self.subTest(commit=commit), TemporaryDirectory() as temp:
                target = make_official_legacy_runtime(
                    Path(temp), commit, crlf_checkout=True
                )

                recognized = installer_module._validate_legacy_official_runtime(
                    target, allow_ignored=True
                )

                self.assertEqual(recognized, commit)

    def test_modified_unmarked_official_runtime_is_preserved(self) -> None:
        commit = "5ba55a4217568e94f22414cb5bbcde4b51c37995"
        if not git_history_available(commit):
            self.skipTest("legacy release is unavailable in this checkout")

        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = make_official_legacy_runtime(root, commit)
            skill_file = target / "SKILL.md"
            skill_file.write_text(
                skill_file.read_text(encoding="utf-8") + "\nlocal customization\n",
                encoding="utf-8",
            )

            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

            self.assertIn("local customization", skill_file.read_text(encoding="utf-8"))
            self.assertFalse((target / installer_module.PROVENANCE_FILE).exists())

    def test_expected_provenance_mismatch_makes_no_destination(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"

            with self.assertRaises(InstallValidationError):
                install_skill(
                    source,
                    skills_dir,
                    expected_provenance_sha256="0" * 64,
                )

            self.assertFalse(skills_dir.exists())

    def test_expected_provenance_accepts_reviewed_marker(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            expected = hashlib.sha256(
                (source / installer_module.PROVENANCE_FILE).read_bytes()
            ).hexdigest()

            target = install_skill(
                source,
                root / "skills",
                expected_provenance_sha256=expected,
            )

            self.assertTrue((target / installer_module.PROVENANCE_FILE).is_file())

    def test_boolean_provenance_schema_is_rejected(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            marker = source / installer_module.PROVENANCE_FILE
            payload = json.loads(marker.read_text(encoding="utf-8"))
            payload["schema_version"] = True
            marker.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

            self.assertFalse((root / "skills").exists())

    def test_current_runtime_marker_is_an_embedded_official_identity(self) -> None:
        marker = REPOSITORY_ROOT / "no-negative-echo" / installer_module.PROVENANCE_FILE
        digest = hashlib.sha256(marker.read_bytes()).hexdigest()
        payload = json.loads(marker.read_text(encoding="utf-8"))
        expected_files = {
            path.as_posix()
            for path in installer_module.RUNTIME_FILES
            - {installer_module.PROVENANCE_FILE}
        }

        self.assertEqual(digest, installer_module.CURRENT_PROVENANCE_SHA256)
        self.assertIn(digest, installer_module.KNOWN_OFFICIAL_PROVENANCE_SHA256)
        self.assertEqual(set(payload["files"]), expected_files)

    def test_default_skills_directories_follow_agent_conventions(self) -> None:
        with TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            expected = {
                "codex": home / ".agents" / "skills",
                "claude": home / ".claude" / "skills",
                "cursor": home / ".cursor" / "skills",
                "gemini": home / ".gemini" / "skills",
                "copilot": home / ".copilot" / "skills",
                "shared": home / ".agents" / "skills",
                "codex-legacy": home / ".codex" / "skills",
            }
            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ, {}, clear=True),
            ):
                for agent, directory in expected.items():
                    with self.subTest(agent=agent):
                        self.assertEqual(
                            installer_module.default_skills_dir(agent), directory
                        )
                self.assertEqual(
                    installer_module.default_skills_dir(),
                    home / ".agents" / "skills",
                )

    def test_codex_home_affects_only_the_legacy_codex_destination(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            codex_home = root / "custom-codex"
            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(
                    os.environ, {"CODEX_HOME": str(codex_home)}, clear=True
                ),
            ):
                self.assertEqual(
                    installer_module.default_skills_dir(),
                    home / ".agents" / "skills",
                )
                self.assertEqual(
                    installer_module.default_skills_dir("codex-legacy"),
                    codex_home / "skills",
                )
                self.assertEqual(
                    installer_module.default_skills_dir("codex"),
                    home / ".agents" / "skills",
                )

    def test_every_agent_preset_installs_into_its_default_directory(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            relative_destinations = {
                "codex": Path(".agents/skills"),
                "claude": Path(".claude/skills"),
                "cursor": Path(".cursor/skills"),
                "gemini": Path(".gemini/skills"),
                "copilot": Path(".copilot/skills"),
                "shared": Path(".agents/skills"),
                "codex-legacy": Path(".codex/skills"),
            }

            for agent, relative_destination in relative_destinations.items():
                home = root / f"home-{agent}"
                home.mkdir()
                skills_dir = home / relative_destination
                arguments = [
                    "install_skill.py",
                    "--source",
                    str(source),
                    "--agent",
                    agent,
                ]
                with (
                    self.subTest(agent=agent),
                    mock.patch.object(Path, "home", return_value=home),
                    mock.patch.dict(os.environ, {}, clear=True),
                    mock.patch.object(sys, "argv", arguments),
                    mock.patch("builtins.print"),
                ):
                    self.assertEqual(installer_module.main(), 0)
                target = skills_dir / "no-negative-echo"
                self.assertTrue((target / "SKILL.md").is_file())
                self.assertTrue((target / "scripts" / "check_surface.py").is_file())

    def test_no_agent_uses_current_codex_destination_when_neither_exists(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            source = make_source(root)
            arguments = ["install_skill.py", "--source", str(source)]

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print") as print_mock,
            ):
                self.assertEqual(installer_module.main(), 0)

            target = home / ".agents" / "skills" / "no-negative-echo"
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertFalse(
                any(
                    "legacy Codex destination" in str(call)
                    for call in print_mock.call_args_list
                )
            )

    def test_no_agent_reuses_an_existing_legacy_codex_destination(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            source = make_source(root)
            legacy_target = home / ".codex" / "skills" / "no-negative-echo"
            shutil.copytree(source, legacy_target)
            arguments = ["install_skill.py", "--source", str(source)]

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print") as print_mock,
            ):
                self.assertEqual(installer_module.main(), 0)

            self.assertTrue((legacy_target / "SKILL.md").is_file())
            self.assertFalse(
                (home / ".agents" / "skills" / "no-negative-echo").exists()
            )
            self.assertTrue(
                any(
                    "legacy Codex destination" in str(call)
                    for call in print_mock.call_args_list
                )
            )

    def test_no_agent_reuses_an_existing_current_codex_destination(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            source = make_source(root)
            current_target = home / ".agents" / "skills" / "no-negative-echo"
            shutil.copytree(source, current_target)
            arguments = ["install_skill.py", "--source", str(source)]

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(installer_module.main(), 0)

            self.assertTrue((current_target / "SKILL.md").is_file())
            self.assertFalse((home / ".codex" / "skills" / "no-negative-echo").exists())

    def test_codex_presets_refuse_a_second_cross_location_install(self) -> None:
        for agent in ("codex", "shared"):
            with self.subTest(agent=agent), TemporaryDirectory() as temp:
                root = Path(temp)
                home = root / "home"
                source = make_source(root)
                legacy_target = home / ".codex" / "skills" / "no-negative-echo"
                shutil.copytree(source, legacy_target)
                marker = legacy_target / ".DS_Store"
                marker.write_text("preserve", encoding="utf-8")
                arguments = [
                    "install_skill.py",
                    "--source",
                    str(source),
                    "--agent",
                    agent,
                ]

                with (
                    mock.patch.object(Path, "home", return_value=home),
                    mock.patch.dict(os.environ, {}, clear=True),
                    mock.patch.object(sys, "argv", arguments),
                    mock.patch("builtins.print") as print_mock,
                ):
                    self.assertEqual(installer_module.main(), 1)

                self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
                self.assertFalse(
                    (home / ".agents" / "skills" / "no-negative-echo").exists()
                )
                self.assertTrue(
                    any(
                        "second Codex install" in str(call)
                        for call in print_mock.call_args_list
                    )
                )

    def test_legacy_preset_refuses_when_current_codex_install_exists(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            source = make_source(root)
            current_target = home / ".agents" / "skills" / "no-negative-echo"
            shutil.copytree(source, current_target)
            marker = current_target / ".DS_Store"
            marker.write_text("preserve", encoding="utf-8")
            arguments = [
                "install_skill.py",
                "--source",
                str(source),
                "--agent",
                "codex-legacy",
            ]

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print") as print_mock,
            ):
                self.assertEqual(installer_module.main(), 1)

            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
            self.assertFalse((home / ".codex" / "skills" / "no-negative-echo").exists())
            self.assertTrue(
                any(
                    "second Codex install" in str(call)
                    for call in print_mock.call_args_list
                )
            )

    def test_native_presets_refuse_when_shared_install_exists(self) -> None:
        for agent in ("cursor", "gemini", "copilot"):
            with self.subTest(agent=agent), TemporaryDirectory() as temp:
                root = Path(temp)
                home = root / "home"
                source = make_source(root)
                shared_target = home / ".agents" / "skills" / "no-negative-echo"
                shutil.copytree(source, shared_target)
                marker = shared_target / ".DS_Store"
                marker.write_text("preserve", encoding="utf-8")
                arguments = [
                    "install_skill.py",
                    "--source",
                    str(source),
                    "--agent",
                    agent,
                ]

                with (
                    mock.patch.object(Path, "home", return_value=home),
                    mock.patch.dict(os.environ, {}, clear=True),
                    mock.patch.object(sys, "argv", arguments),
                    mock.patch("builtins.print") as print_mock,
                ):
                    self.assertEqual(installer_module.main(), 1)

                native_target = home / f".{agent}" / "skills" / "no-negative-echo"
                self.assertFalse(native_target.exists())
                self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
                self.assertTrue(
                    any(
                        "multiple discoverable installs" in str(call)
                        for call in print_mock.call_args_list
                    )
                )

    def test_cursor_preset_refuses_its_compatible_personal_roots(self) -> None:
        for existing_relative in (
            Path(".claude/skills/no-negative-echo"),
            Path(".codex/skills/no-negative-echo"),
        ):
            with (
                self.subTest(existing_relative=existing_relative),
                TemporaryDirectory() as temp,
            ):
                root = Path(temp)
                home = root / "home"
                source = make_source(root)
                existing_target = home / existing_relative
                shutil.copytree(source, existing_target)
                marker = existing_target / ".DS_Store"
                marker.write_text("preserve", encoding="utf-8")
                arguments = [
                    "install_skill.py",
                    "--source",
                    str(source),
                    "--agent",
                    "cursor",
                ]

                with (
                    mock.patch.object(Path, "home", return_value=home),
                    mock.patch.dict(os.environ, {}, clear=True),
                    mock.patch.object(sys, "argv", arguments),
                    mock.patch("builtins.print") as print_mock,
                ):
                    self.assertEqual(installer_module.main(), 1)

                cursor_target = home / ".cursor" / "skills" / "no-negative-echo"
                self.assertFalse(cursor_target.exists())
                self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
                self.assertTrue(
                    any(
                        "multiple discoverable installs" in str(call)
                        for call in print_mock.call_args_list
                    )
                )

    def test_cursor_preset_checks_custom_codex_home(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            codex_home = root / "custom-codex"
            source = make_source(root)
            legacy_target = codex_home / "skills" / "no-negative-echo"
            shutil.copytree(source, legacy_target)
            marker = legacy_target / ".DS_Store"
            marker.write_text("preserve", encoding="utf-8")
            arguments = [
                "install_skill.py",
                "--source",
                str(source),
                "--agent",
                "cursor",
            ]

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(
                    os.environ, {"CODEX_HOME": str(codex_home)}, clear=True
                ),
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(installer_module.main(), 1)

            self.assertFalse(
                (home / ".cursor" / "skills" / "no-negative-echo").exists()
            )
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_shared_destinations_refuse_when_native_install_exists(self) -> None:
        for selector in ("shared", "codex", None):
            for native_agent in ("cursor", "gemini", "copilot"):
                with (
                    self.subTest(selector=selector, native_agent=native_agent),
                    TemporaryDirectory() as temp,
                ):
                    root = Path(temp)
                    home = root / "home"
                    source = make_source(root)
                    native_target = (
                        home / f".{native_agent}" / "skills" / "no-negative-echo"
                    )
                    shutil.copytree(source, native_target)
                    marker = native_target / ".DS_Store"
                    marker.write_text("preserve", encoding="utf-8")
                    arguments = ["install_skill.py", "--source", str(source)]
                    if selector is not None:
                        arguments.extend(["--agent", selector])

                    with (
                        mock.patch.object(Path, "home", return_value=home),
                        mock.patch.dict(os.environ, {}, clear=True),
                        mock.patch.object(sys, "argv", arguments),
                        mock.patch("builtins.print"),
                    ):
                        self.assertEqual(installer_module.main(), 1)

                    shared_target = home / ".agents" / "skills" / "no-negative-echo"
                    self.assertFalse(shared_target.exists())
                    self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_claude_native_install_is_independent_of_shared_location(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            source = make_source(root)
            shared_target = home / ".agents" / "skills" / "no-negative-echo"
            shutil.copytree(source, shared_target)
            real_lstat = installer_module._lstat

            def inaccessible_shared(path: Path) -> os.stat_result | None:
                if path == shared_target:
                    raise PermissionError("shared location is unrelated to Claude")
                return real_lstat(path)

            arguments = [
                "install_skill.py",
                "--source",
                str(source),
                "--agent",
                "claude",
            ]

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(sys, "argv", arguments),
                mock.patch.object(
                    installer_module, "_lstat", side_effect=inaccessible_shared
                ),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(installer_module.main(), 0)

            claude_target = home / ".claude" / "skills" / "no-negative-echo"
            self.assertTrue((shared_target / "SKILL.md").is_file())
            self.assertTrue((claude_target / "SKILL.md").is_file())

    def test_no_agent_refuses_distinct_current_and_legacy_installs(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            source = make_source(root)
            current_target = home / ".agents" / "skills" / "no-negative-echo"
            legacy_target = home / ".codex" / "skills" / "no-negative-echo"
            shutil.copytree(source, current_target)
            shutil.copytree(source, legacy_target)
            current_marker = current_target / ".DS_Store"
            legacy_marker = legacy_target / ".DS_Store"
            current_marker.write_text("current", encoding="utf-8")
            legacy_marker.write_text("legacy", encoding="utf-8")
            arguments = ["install_skill.py", "--source", str(source)]

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(installer_module.main(), 1)

            self.assertEqual(current_marker.read_text(encoding="utf-8"), "current")
            self.assertEqual(legacy_marker.read_text(encoding="utf-8"), "legacy")

    def test_no_agent_refuses_current_and_legacy_aliases_of_the_same_install(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            source = make_source(root)
            current_target = home / ".agents" / "skills" / "no-negative-echo"
            legacy_target = home / ".codex" / "skills" / "no-negative-echo"
            shutil.copytree(source, current_target)
            marker = current_target / ".DS_Store"
            marker.write_text("preserve", encoding="utf-8")
            legacy_target.parent.mkdir(parents=True)
            try:
                legacy_target.symlink_to(current_target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            arguments = ["install_skill.py", "--source", str(source)]

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(installer_module.main(), 1)

            self.assertTrue(legacy_target.is_symlink())
            self.assertTrue(os.path.samefile(current_target, legacy_target))
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_cursor_preset_refuses_nested_compatible_skill(self) -> None:
        for nested_relative in (
            Path(".cursor/skills/team/no-negative-echo"),
            Path(".agents/skills/team/no-negative-echo"),
            Path(".claude/skills/team/no-negative-echo"),
            Path(".codex/skills/team/no-negative-echo"),
        ):
            with (
                self.subTest(nested_relative=nested_relative),
                TemporaryDirectory() as temp,
            ):
                root = Path(temp)
                home = root / "home"
                source = make_source(root)
                nested_target = home / nested_relative
                shutil.copytree(source, nested_target)
                marker = nested_target / ".DS_Store"
                marker.write_text("preserve", encoding="utf-8")
                arguments = [
                    "install_skill.py",
                    "--source",
                    str(source),
                    "--agent",
                    "cursor",
                ]

                with (
                    mock.patch.object(Path, "home", return_value=home),
                    mock.patch.dict(os.environ, {}, clear=True),
                    mock.patch.object(sys, "argv", arguments),
                    mock.patch("builtins.print"),
                ):
                    self.assertEqual(installer_module.main(), 1)

                selected = home / ".cursor" / "skills" / "no-negative-echo"
                self.assertFalse(selected.exists())
                self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_shared_destinations_refuse_nested_cursor_install(self) -> None:
        for selector in ("shared", "codex", None):
            with self.subTest(selector=selector), TemporaryDirectory() as temp:
                root = Path(temp)
                home = root / "home"
                source = make_source(root)
                nested_target = (
                    home / ".cursor" / "skills" / "team" / "no-negative-echo"
                )
                shutil.copytree(source, nested_target)
                marker = nested_target / ".DS_Store"
                marker.write_text("preserve", encoding="utf-8")
                arguments = ["install_skill.py", "--source", str(source)]
                if selector is not None:
                    arguments.extend(["--agent", selector])

                with (
                    mock.patch.object(Path, "home", return_value=home),
                    mock.patch.dict(os.environ, {}, clear=True),
                    mock.patch.object(sys, "argv", arguments),
                    mock.patch("builtins.print"),
                ):
                    self.assertEqual(installer_module.main(), 1)

                selected = home / ".agents" / "skills" / "no-negative-echo"
                self.assertFalse(selected.exists())
                self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_claude_preset_refuses_nested_personal_skill(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            source = make_source(root)
            nested_target = home / ".claude" / "skills" / "synced" / "no-negative-echo"
            shutil.copytree(source, nested_target)
            marker = nested_target / ".DS_Store"
            marker.write_text("preserve", encoding="utf-8")
            arguments = [
                "install_skill.py",
                "--source",
                str(source),
                "--agent",
                "claude",
            ]

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(installer_module.main(), 1)

            selected = home / ".claude" / "skills" / "no-negative-echo"
            self.assertFalse(selected.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_explicit_skills_dir_installs_to_the_custom_destination(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            custom = root / "custom-skills"
            arguments = [
                "install_skill.py",
                "--source",
                str(source),
                "--skills-dir",
                str(custom),
                "--discovery-root",
                str(custom),
            ]
            with (
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(installer_module.main(), 0)

            self.assertTrue((custom / "no-negative-echo" / "SKILL.md").is_file())

    def test_explicit_skills_dir_requires_absolute_path_and_discovery_roots(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            for extra_arguments in (
                ["--skills-dir", str(root / "custom-skills")],
                [
                    "--skills-dir",
                    "relative-skills",
                    "--discovery-root",
                    str(root),
                ],
            ):
                with self.subTest(arguments=extra_arguments):
                    arguments = [
                        "install_skill.py",
                        "--source",
                        str(source),
                        *extra_arguments,
                    ]
                    with (
                        mock.patch.object(sys, "argv", arguments),
                        mock.patch("builtins.print"),
                    ):
                        self.assertEqual(installer_module.main(), 1)

    def test_declared_discovery_root_blocks_custom_duplicate(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            workspace = root / "workspace"
            existing = workspace / ".agents" / "skills" / "no-negative-echo"
            shutil.copytree(source, existing)
            custom = workspace / ".github" / "skills"
            arguments = [
                "install_skill.py",
                "--source",
                str(source),
                "--skills-dir",
                str(custom),
                "--discovery-root",
                str(workspace),
            ]

            with (
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(installer_module.main(), 1)

            self.assertFalse((custom / "no-negative-echo").exists())
            self.assertTrue((existing / "SKILL.md").is_file())

    def test_declared_workspace_root_blocks_preset_duplicate(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            source = make_source(root)
            workspace = root / "workspace"
            existing = workspace / ".agents" / "skills" / "no-negative-echo"
            shutil.copytree(source, existing)
            arguments = [
                "install_skill.py",
                "--source",
                str(source),
                "--agent",
                "codex",
                "--discovery-root",
                str(workspace),
            ]

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(installer_module.main(), 1)

            self.assertFalse(
                (home / ".agents" / "skills" / "no-negative-echo").exists()
            )
            self.assertTrue((existing / "SKILL.md").is_file())

    def test_agent_and_skills_dir_are_mutually_exclusive(self) -> None:
        with TemporaryDirectory() as temp:
            arguments = [
                "install_skill.py",
                "--agent",
                "claude",
                "--skills-dir",
                str(Path(temp) / "skills"),
            ]
            with (
                mock.patch.object(sys, "argv", arguments),
                mock.patch.object(sys, "stderr", new=StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                installer_module.main()

            self.assertEqual(raised.exception.code, 2)

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

    def test_rejects_symlinked_installation_lock_without_touching_target(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            skills_dir.mkdir()
            outside = root / "outside.lock"
            outside.write_bytes(b"preserve")
            lock = skills_dir / ".no-negative-echo-install.lock"
            try:
                lock.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            with self.assertRaises(InstallValidationError):
                install_skill(source, skills_dir)

            self.assertEqual(outside.read_bytes(), b"preserve")
            self.assertTrue(lock.is_symlink())
            self.assertFalse((skills_dir / "no-negative-echo").exists())

    def test_rejects_dangling_symlinked_lock_without_creating_its_target(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            skills_dir.mkdir()
            outside = root / "missing-outside.lock"
            lock = skills_dir / ".no-negative-echo-install.lock"
            try:
                lock.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            with self.assertRaises(InstallValidationError):
                install_skill(source, skills_dir)

            self.assertFalse(outside.exists())
            self.assertTrue(lock.is_symlink())
            self.assertFalse((skills_dir / "no-negative-echo").exists())

    def test_migrates_legacy_empty_installation_lock(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            skills_dir.mkdir()
            lock = skills_dir / ".no-negative-echo-install.lock"
            lock.write_bytes(b"")

            target = install_skill(source, skills_dir)

            self.assertTrue((target / "SKILL.md").is_file())
            self.assertEqual(lock.read_bytes(), installer_module.LOCK_MAGIC)

    @unittest.skipIf(sys.platform == "win32", "POSIX mode bits are unavailable")
    def test_rejects_lock_writable_by_other_users(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            skills_dir.mkdir()
            lock = skills_dir / ".no-negative-echo-install.lock"
            lock.write_bytes(installer_module.LOCK_MAGIC)
            lock.chmod(0o666)

            with self.assertRaises(InstallValidationError):
                install_skill(source, skills_dir)

            self.assertEqual(lock.read_bytes(), installer_module.LOCK_MAGIC)
            self.assertFalse((skills_dir / "no-negative-echo").exists())

    @unittest.skipIf(
        sys.platform == "win32", "Windows prevents renaming an open lock file"
    )
    def test_lock_path_is_revalidated_after_exclusive_lock(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            skills_dir.mkdir()
            lock = skills_dir / ".no-negative-echo-install.lock"
            displaced = root / "displaced.lock"
            real_lock = installer_module._lock_file

            def replace_path_before_lock(handle: object) -> None:
                lock.rename(displaced)
                lock.write_bytes(installer_module.LOCK_MAGIC)
                real_lock(handle)

            with mock.patch.object(
                installer_module,
                "_lock_file",
                side_effect=replace_path_before_lock,
            ):
                with self.assertRaises(InstallValidationError):
                    install_skill(source, skills_dir)

            self.assertEqual(displaced.read_bytes(), installer_module.LOCK_MAGIC)
            self.assertEqual(lock.read_bytes(), installer_module.LOCK_MAGIC)
            self.assertFalse((skills_dir / "no-negative-echo").exists())

    def test_coordination_lock_path_does_not_follow_tmpdir(self) -> None:
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            with mock.patch.dict(os.environ, {"TMPDIR": first}, clear=False):
                first_path = self._real_cli_lock_path()
            with mock.patch.dict(os.environ, {"TMPDIR": second}, clear=False):
                second_path = self._real_cli_lock_path()

            self.assertEqual(first_path, second_path)
            if hasattr(os, "getuid"):
                self.assertEqual(first_path.parent, Path("/tmp"))

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
            old_metadata = target / "agents" / "openai.yaml"
            old_metadata.write_text("name: old\n", encoding="utf-8")
            refresh_provenance(target)
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

            self.assertEqual(old_metadata.read_text(encoding="utf-8"), "name: old\n")
            self.assertFalse(list(root.glob(".*-backup-*")))

    def test_same_name_target_with_unknown_file_is_preserved(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            valuable = target / "valuable.bin"
            valuable.write_bytes(b"preserve")
            old_metadata = target / "agents" / "openai.yaml"
            old_metadata.write_text("name: old\n", encoding="utf-8")
            refresh_provenance(target)

            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

            self.assertEqual(valuable.read_bytes(), b"preserve")
            self.assertEqual(old_metadata.read_text(encoding="utf-8"), "name: old\n")
            self.assertFalse(list(root.glob(".*-backup-*")))

    def test_modified_marked_runtime_is_preserved(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            skill_file = target / "SKILL.md"
            skill_file.write_text(
                skill_file.read_text(encoding="utf-8") + "\nlocal customization\n",
                encoding="utf-8",
            )

            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

            self.assertIn("local customization", skill_file.read_text(encoding="utf-8"))
            self.assertFalse(list(root.glob(".*-backup-*")))

    def test_self_asserted_custom_provenance_is_not_ownership(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            custom_file = target / "SKILL.md"
            custom_file.write_text(
                custom_file.read_text(encoding="utf-8")
                + "\nself-asserted custom package\n",
                encoding="utf-8",
            )
            trusted_before = installer_module.KNOWN_OFFICIAL_PROVENANCE_SHA256
            refresh_provenance(target)
            installer_module.KNOWN_OFFICIAL_PROVENANCE_SHA256 = trusted_before

            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

            self.assertIn(
                "self-asserted custom package", custom_file.read_text(encoding="utf-8")
            )
            self.assertFalse(list(root.glob(".*-backup-*")))

    def test_non_cache_file_inside_pycache_is_preserved(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            valuable = target / "scripts" / "__pycache__" / "notes.txt"
            valuable.parent.mkdir()
            valuable.write_text("preserve", encoding="utf-8")

            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

            self.assertEqual(valuable.read_text(encoding="utf-8"), "preserve")
            self.assertFalse(list(root.glob(".*-backup-*")))

    def test_symlink_inside_pycache_is_rejected_and_preserved(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            outside = root / "outside.bin"
            outside.write_bytes(b"preserve")
            cache = target / "scripts" / "__pycache__"
            cache.mkdir()
            linked_cache = cache / "linked.pyc"
            try:
                linked_cache.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            with self.assertRaises(InstallValidationError):
                install_skill(source, root / "skills")

            self.assertEqual(outside.read_bytes(), b"preserve")
            self.assertTrue(linked_cache.is_symlink())
            self.assertFalse(list(root.glob(".*-backup-*")))

    def test_existing_manifest_is_rechecked_after_backup_rename(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            target = skills_dir / "no-negative-echo"
            shutil.copytree(source, target)
            old_metadata = target / "agents" / "openai.yaml"
            old_metadata.write_text("name: old\n", encoding="utf-8")
            refresh_provenance(target)
            real_rename = Path.rename

            def tamper_after_backup_rename(path: Path, destination: Path) -> Path:
                result = real_rename(path, destination)
                if path.name == "no-negative-echo" and "-backup-" in destination.name:
                    (destination / "valuable.bin").write_bytes(b"preserve")
                return result

            with mock.patch.object(Path, "rename", new=tamper_after_backup_rename):
                with self.assertRaises(InstallValidationError):
                    install_skill(source, skills_dir)

            self.assertEqual(old_metadata.read_text(encoding="utf-8"), "name: old\n")
            self.assertEqual((target / "valuable.bin").read_bytes(), b"preserve")
            self.assertFalse(list(skills_dir.parent.glob(".*-backup-*")))

    def test_staged_runtime_is_revalidated_after_target_lock(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            real_installation_lock = installer_module._installation_lock

            @contextmanager
            def tamper_before_yield(directory: Path) -> object:
                with real_installation_lock(directory):
                    staged = next(
                        directory.parent.glob(".no-negative-echo-install-*/staged")
                    )
                    (staged / "scripts" / "check_surface.py").write_text(
                        "tampered\n", encoding="utf-8"
                    )
                    yield

            with mock.patch.object(
                installer_module,
                "_installation_lock",
                new=tamper_before_yield,
            ):
                with self.assertRaises(InstallValidationError):
                    install_skill(source, skills_dir)

            self.assertFalse((skills_dir / "no-negative-echo").exists())

    def test_post_rename_inspection_failure_is_activation_uncertain(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            target = skills_dir.resolve() / "no-negative-echo"
            real_rename = Path.rename
            real_lstat = installer_module._lstat
            target_renamed = False
            inspection_failed = False

            def mark_target_rename(path: Path, destination: Path) -> Path:
                nonlocal target_renamed
                result = real_rename(path, destination)
                if path.name == "staged":
                    target_renamed = True
                return result

            def fail_first_post_rename_target_stat(
                path: Path,
            ) -> os.stat_result | None:
                nonlocal inspection_failed
                if target_renamed and path == target and not inspection_failed:
                    inspection_failed = True
                    raise PermissionError("injected post-rename inspection failure")
                return real_lstat(path)

            with (
                mock.patch.object(Path, "rename", new=mark_target_rename),
                mock.patch.object(
                    installer_module,
                    "_lstat",
                    side_effect=fail_first_post_rename_target_stat,
                ),
                self.assertRaises(InstallActivationUncertainError) as raised,
            ):
                install_skill(source, skills_dir)

            self.assertEqual(raised.exception.target, target)
            self.assertIsNone(raised.exception.backup)
            self.assertTrue((target / "SKILL.md").is_file())

    def test_keyboard_interrupt_restores_previous_install(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            old_metadata = target / "agents" / "openai.yaml"
            old_metadata.write_text("name: old\n", encoding="utf-8")
            refresh_provenance(target)
            real_rename = Path.rename

            def interrupted(path: Path, destination: Path) -> Path:
                if path.name == "staged":
                    raise KeyboardInterrupt
                return real_rename(path, destination)

            with mock.patch.object(Path, "rename", new=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    install_skill(source, root / "skills")
            self.assertEqual(old_metadata.read_text(encoding="utf-8"), "name: old\n")
            self.assertFalse(list(root.glob(".*-backup-*")))

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

    def test_successful_upgrade_preserves_previous_backup(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            shutil.copytree(source, target)
            old_metadata = target / "agents" / "openai.yaml"
            old_metadata.write_text("name: old\n", encoding="utf-8")
            refresh_provenance(target)

            notices: list[str] = []
            installed = install_skill(source, root / "skills", cleanup_notices=notices)

            self.assertTrue(os.path.samefile(installed, target))
            self.assertEqual(
                (target / "agents" / "openai.yaml").read_text(encoding="utf-8"),
                "name: test\n",
            )
            backups = list(root.glob(".*-backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(
                (backups[0] / "agents" / "openai.yaml").read_text(encoding="utf-8"),
                "name: old\n",
            )
            self.assertEqual(
                set((root / "skills").rglob("SKILL.md")),
                {target / "SKILL.md"},
            )
            self.assertEqual(len(notices), 1)
            prefix = "the previous validated installation was preserved at "
            self.assertTrue(notices[0].startswith(prefix))
            reported = notices[0][len(prefix) :].split(";", 1)[0]
            self.assertTrue(paths_refer_to_same_file(backups[0], reported))

    def test_backup_path_swap_after_activation_deletes_nothing(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            target = skills_dir / "no-negative-echo"
            shutil.copytree(source, target)
            (target / "agents" / "openai.yaml").write_text(
                "name: old\n", encoding="utf-8"
            )
            refresh_provenance(target)
            victim = root / "victim"
            victim.mkdir()
            (victim / "keep.txt").write_text("preserve", encoding="utf-8")
            saved_backup = root / "saved-backup"
            real_rename = Path.rename

            def swap_backup_path(path: Path, destination: Path) -> Path:
                result = real_rename(path, destination)
                if path.name == "staged":
                    backups = list(skills_dir.parent.glob(".*-backup-*"))
                    self.assertEqual(len(backups), 1)
                    real_rename(backups[0], saved_backup)
                    real_rename(victim, backups[0])
                return result

            notices: list[str] = []
            with mock.patch.object(Path, "rename", new=swap_backup_path):
                installed = install_skill(source, skills_dir, cleanup_notices=notices)

            self.assertTrue(os.path.samefile(installed, target))
            swapped_path = next(skills_dir.parent.glob(".*-backup-*"))
            self.assertEqual(
                (swapped_path / "keep.txt").read_text(encoding="utf-8"),
                "preserve",
            )
            self.assertTrue((saved_backup / "SKILL.md").is_file())
            self.assertEqual(len(notices), 1)
            prefix = "the previous validated installation was preserved at "
            self.assertTrue(notices[0].startswith(prefix))
            reported = notices[0][len(prefix) :].split(";", 1)[0]
            self.assertTrue(paths_refer_to_same_file(swapped_path, reported))

    def test_staging_cleanup_failure_is_a_post_activation_notice(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            target = root / "skills" / "no-negative-echo"
            notices: list[str] = []
            real_rmdir = Path.rmdir

            def fail_staging_rmdir(path: Path) -> None:
                if path.name.startswith(".no-negative-echo-install-"):
                    raise PermissionError("staging directory is locked")
                real_rmdir(path)

            with mock.patch.object(Path, "rmdir", new=fail_staging_rmdir):
                installed = install_skill(
                    source, root / "skills", cleanup_notices=notices
                )

            self.assertTrue(os.path.samefile(installed, target))
            self.assertEqual(len(notices), 1)
            self.assertIn("staging directory was preserved", notices[0])
            self.assertEqual(len(list(root.glob(".no-negative-echo-install-*"))), 1)

    def test_staging_path_swap_after_activation_deletes_nothing(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            target = skills_dir / "no-negative-echo"
            victim = root / "victim"
            victim.mkdir()
            (victim / "keep.txt").write_text("preserve", encoding="utf-8")
            saved_staging = root / "saved-staging"
            notices: list[str] = []
            real_rmdir = Path.rmdir
            real_rename = Path.rename

            def swap_before_rmdir(path: Path) -> None:
                if path.name.startswith(".no-negative-echo-install-"):
                    real_rename(path, saved_staging)
                    real_rename(victim, path)
                real_rmdir(path)

            with mock.patch.object(Path, "rmdir", new=swap_before_rmdir):
                installed = install_skill(source, skills_dir, cleanup_notices=notices)

            self.assertTrue(os.path.samefile(installed, target))
            swapped_path = next(root.glob(".no-negative-echo-install-*"))
            self.assertEqual(
                (swapped_path / "keep.txt").read_text(encoding="utf-8"),
                "preserve",
            )
            self.assertTrue(saved_staging.is_dir())
            self.assertEqual(len(notices), 1)
            prefix = "staging directory was preserved at "
            self.assertTrue(notices[0].startswith(prefix))
            reported = notices[0][len(prefix) :].split(": ", 1)[0]
            self.assertTrue(paths_refer_to_same_file(swapped_path, reported))

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

    def test_main_reports_unlock_failures_as_warnings_after_activation(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            arguments = [
                "install_skill.py",
                "--source",
                str(source),
                "--skills-dir",
                str(skills_dir),
                "--discovery-root",
                str(skills_dir),
            ]

            with (
                mock.patch.object(sys, "argv", arguments),
                mock.patch.object(
                    installer_module,
                    "_unlock_file",
                    side_effect=OSError("lock release failed"),
                ),
                mock.patch("builtins.print") as print_mock,
            ):
                result = installer_module.main()

            self.assertEqual(result, 0)
            self.assertTrue((skills_dir / "no-negative-echo" / "SKILL.md").is_file())
            self.assertTrue(
                any(
                    "Install warning" in str(call) for call in print_mock.call_args_list
                )
            )
            self.assertTrue(
                any(
                    "Installed no-negative-echo" in str(call)
                    for call in print_mock.call_args_list
                )
            )
            self.assertTrue(
                any(
                    "Coordination lock" in str(call)
                    for call in print_mock.call_args_list
                )
            )

    def test_main_reports_legacy_coordination_lock_migration(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            coordination_lock = root / "coordination.lock"
            coordination_lock.write_bytes(b"\0")
            arguments = [
                "install_skill.py",
                "--source",
                str(source),
                "--skills-dir",
                str(skills_dir),
                "--discovery-root",
                str(skills_dir),
            ]

            with (
                mock.patch.object(sys, "argv", arguments),
                mock.patch.object(
                    installer_module,
                    "_cli_lock_path",
                    return_value=coordination_lock,
                ),
                mock.patch("builtins.print") as print_mock,
            ):
                result = installer_module.main()

            self.assertEqual(result, 0)
            self.assertEqual(
                coordination_lock.read_bytes(), installer_module.LOCK_MAGIC
            )
            coordination_message = next(
                message
                for message in printed_messages(print_mock)
                if message.startswith("Coordination lock: ")
            )
            suffix = " (migrated-legacy)"
            self.assertTrue(coordination_message.endswith(suffix))
            reported = coordination_message[len("Coordination lock: ") : -len(suffix)]
            self.assertTrue(paths_refer_to_same_file(coordination_lock, reported))

    def test_main_reports_preserved_staging_path_on_failure(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            skills_dir = root / "skills"
            target = skills_dir / "no-negative-echo"
            target.mkdir(parents=True)
            (target / "valuable.bin").write_bytes(b"preserve")
            arguments = [
                "install_skill.py",
                "--source",
                str(source),
                "--skills-dir",
                str(skills_dir),
                "--discovery-root",
                str(skills_dir),
            ]

            with (
                mock.patch.object(sys, "argv", arguments),
                mock.patch("builtins.print") as print_mock,
            ):
                result = installer_module.main()

            self.assertEqual(result, 1)
            staging = list(root.glob(".no-negative-echo-install-*"))
            self.assertEqual(len(staging), 1)
            prefix = (
                "Install warning: failed installation preserved staging data "
                "for inspection at "
            )
            warning = next(
                message
                for message in printed_messages(print_mock)
                if message.startswith(prefix)
            )
            reported = warning[len(prefix) :]
            self.assertTrue(paths_refer_to_same_file(staging[0], reported))
            self.assertEqual((target / "valuable.bin").read_bytes(), b"preserve")

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
