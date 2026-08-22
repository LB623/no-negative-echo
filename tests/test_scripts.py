#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "no-negative-echo" / "scripts"))
sys.path.insert(0, str(REPOSITORY_ROOT / "evals"))

from check_surface import count_matches, normalize  # noqa: E402
from score_eval import (  # noqa: E402
    expected_activation,
    load_jsonl,
    load_outputs,
    routing_summary,
    score_case,
)


class SurfaceCheckTests(unittest.TestCase):
    def test_normalization_catches_case_and_width_variants(self) -> None:
        self.assertEqual(normalize("Ａbc"), "abc")
        self.assertEqual(count_matches("Use REDIS here", ["redis"]), 1)

    def test_clean_surface_passes(self) -> None:
        self.assertEqual(count_matches("PostgreSQL queue", ["redis"]), 0)

    def test_rejected_label_prefix_is_detected(self) -> None:
        self.assertEqual(count_matches("无提示场景下的评测", ["无提示"]), 1)


class EvaluationScoringTests(unittest.TestCase):
    def test_activation_expectation_depends_on_condition(self) -> None:
        oracle = {"implicit_activation_expected": False}
        self.assertFalse(expected_activation(oracle, "no-skill"))
        self.assertFalse(expected_activation(oracle, "comparator"))
        self.assertTrue(expected_activation(oracle, "explicit"))
        self.assertFalse(expected_activation(oracle, "implicit"))

    def test_complete_case_passes(self) -> None:
        oracle = {
            "forbidden_exact": ["redis"],
            "required_any": [["postgresql"]],
            "implicit_activation_expected": True,
        }
        output = {
            "output": "PostgreSQL queue",
            "semantic_pass": True,
            "task_pass": True,
            "activation_observed": True,
        }
        self.assertEqual(score_case(oracle, output, "implicit"), [])

    def test_all_failure_classes_are_reported(self) -> None:
        oracle = {
            "forbidden_exact": ["redis"],
            "required_any": [["postgresql"]],
            "implicit_activation_expected": True,
        }
        output = {
            "output": "Redis queue",
            "semantic_pass": False,
            "task_pass": False,
            "activation_observed": False,
        }
        self.assertEqual(
            score_case(oracle, output, "implicit"),
            [
                "exact_leak",
                "missing_required_fact",
                "routing_mismatch",
                "semantic_not_passed",
                "task_not_passed",
            ],
        )

    def test_explicit_invocation_overrides_non_trigger_routing(self) -> None:
        oracle = {
            "forbidden_exact": [],
            "required_any": [["tomato"]],
            "implicit_activation_expected": False,
        }
        output = {
            "output": "Tomato soup",
            "semantic_pass": True,
            "task_pass": True,
            "activation_observed": True,
        }
        self.assertEqual(score_case(oracle, output, "explicit"), [])

    def test_output_loader_accepts_repeated_cases_with_distinct_run_ids(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "outputs.jsonl"
            path.write_text(
                '{"run_id":"001","id":"case-a"}\n' '{"run_id":"002","id":"case-a"}\n',
                encoding="utf-8",
            )
            self.assertEqual(
                set(load_outputs(path)), {("001", "case-a"), ("002", "case-a")}
            )

    def test_routing_summary_reports_precision_and_recall(self) -> None:
        oracle = {
            "trigger": {"implicit_activation_expected": True},
            "neutral": {"implicit_activation_expected": False},
        }
        outputs = {
            ("001", "trigger"): {"activation_observed": True},
            ("001", "neutral"): {"activation_observed": True},
            ("002", "trigger"): {"activation_observed": False},
            ("002", "neutral"): {"activation_observed": False},
        }
        self.assertEqual(
            routing_summary(oracle, outputs, "implicit"),
            {
                "true_positive": 1,
                "false_positive": 1,
                "true_negative": 1,
                "false_negative": 1,
                "unobserved": 0,
                "observations": 4,
                "precision": 0.5,
                "recall": 0.5,
            },
        )

    def test_cli_reports_invalid_implicit_oracle_as_json_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            oracle_path = root / "oracle.jsonl"
            outputs_path = root / "outputs.jsonl"
            oracle_path.write_text('{"id":"case-a"}\n', encoding="utf-8")
            outputs_path.write_text(
                '{"id":"case-a","output":"done","semantic_pass":true,'
                '"task_pass":true,"activation_observed":true}\n',
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "evals" / "score_eval.py"),
                    "--oracle",
                    str(oracle_path),
                    "--outputs",
                    str(outputs_path),
                    "--condition",
                    "implicit",
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "ERROR")
            self.assertEqual(result.stderr, "")

    def test_cli_counts_a_completely_missing_scheduled_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            oracle_path = root / "oracle.jsonl"
            outputs_path = root / "outputs.jsonl"
            run_ids_path = root / "run-ids.txt"
            oracle_path.write_text(
                '{"id":"case-a","forbidden_exact":[],"required_any":[],'
                '"implicit_activation_expected":true}\n',
                encoding="utf-8",
            )
            outputs_path.write_text(
                '{"run_id":"001","id":"case-a","output":"done",'
                '"semantic_pass":true,"task_pass":true,'
                '"activation_observed":true}\n',
                encoding="utf-8",
            )
            run_ids_path.write_text("001\n002\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "evals" / "score_eval.py"),
                    "--oracle",
                    str(oracle_path),
                    "--outputs",
                    str(outputs_path),
                    "--expected-run-ids",
                    str(run_ids_path),
                    "--condition",
                    "explicit",
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["runs"], 2)
            self.assertEqual(payload["failed"], 1)
            self.assertEqual(payload["routing"]["unobserved"], 1)
            missing = next(case for case in payload["cases"] if case["run_id"] == "002")
            self.assertEqual(missing["failures"], ["missing_output"])

    def test_cli_rejects_repeated_runs_without_a_manifest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            oracle_path = root / "oracle.jsonl"
            outputs_path = root / "outputs.jsonl"
            oracle_path.write_text(
                '{"id":"case-a","forbidden_exact":[],"required_any":[],'
                '"implicit_activation_expected":true}\n',
                encoding="utf-8",
            )
            outputs_path.write_text(
                '{"run_id":"001","id":"case-a","output":"done",'
                '"semantic_pass":true,"task_pass":true,'
                '"activation_observed":true}\n'
                '{"run_id":"002","id":"case-a","output":"done",'
                '"semantic_pass":true,"task_pass":true,'
                '"activation_observed":true}\n',
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "evals" / "score_eval.py"),
                    "--oracle",
                    str(oracle_path),
                    "--outputs",
                    str(outputs_path),
                    "--condition",
                    "explicit",
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("--expected-run-ids", result.stdout)
            self.assertEqual(json.loads(result.stdout)["status"], "ERROR")


class InstallerTests(unittest.TestCase):
    def test_installer_replaces_a_valid_existing_runtime(self) -> None:
        with TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir) / "skills"
            old_target = skills_dir / "no-negative-echo"
            shutil.copytree(REPOSITORY_ROOT / "no-negative-echo", old_target)
            ignored_cache = old_target / "scripts" / "__pycache__" / "stale.pyc"
            ignored_cache.parent.mkdir(exist_ok=True)
            ignored_cache.write_bytes(b"stale")
            coordination_lock = Path(temp_dir) / "coordination.lock"
            runner = (
                "from pathlib import Path\n"
                "import sys\n"
                f"sys.path.insert(0, {str(REPOSITORY_ROOT / 'scripts')!r})\n"
                "import install_skill\n"
                "lock = Path(sys.argv[1])\n"
                "skills = Path(sys.argv[2])\n"
                "install_skill._cli_lock_path = lambda: lock\n"
                "sys.argv = ['install_skill.py', '--skills-dir', str(skills), "
                "'--discovery-root', str(skills)]\n"
                "raise SystemExit(install_skill.main())\n"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    runner,
                    str(coordination_lock),
                    str(skills_dir),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(coordination_lock.is_file())
            self.assertFalse(ignored_cache.exists())
            self.assertTrue(
                (old_target / ".no-negative-echo-provenance.json").is_file()
            )
            self.assertTrue((old_target / "SKILL.md").is_file())
            self.assertTrue((old_target / "agents" / "openai.yaml").is_file())
            self.assertTrue((old_target / "assets" / "icon.png").is_file())
            self.assertTrue((old_target / "assets" / "icon-400.png").is_file())
            self.assertTrue((old_target / "scripts" / "check_surface.py").is_file())
            self.assertFalse(any(old_target.rglob("__pycache__")))
            self.assertFalse(any(old_target.rglob("*.pyc")))


class FixtureContractTests(unittest.TestCase):
    def test_runtime_hash_inputs_are_forced_to_lf_by_git(self) -> None:
        paths = [
            "no-negative-echo/.no-negative-echo-provenance.json",
            "no-negative-echo/SKILL.md",
            "no-negative-echo/agents/openai.yaml",
            "no-negative-echo/scripts/check_surface.py",
            "scripts/install_skill.py",
            "INSTALL.md",
        ]
        result = subprocess.run(
            ["git", "check-attr", "eol", "--", *paths],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode != 0:
            self.skipTest("Git attributes are unavailable outside a checkout")

        observed = {
            line.split(": ", 2)[0]: line.split(": ", 2)[2]
            for line in result.stdout.splitlines()
        }
        self.assertEqual(observed, {path: "lf" for path in paths})

        unsafe_attributes = subprocess.check_output(
            [
                "git",
                "check-attr",
                "filter",
                "ident",
                "working-tree-encoding",
                "--",
                *paths,
            ],
            cwd=REPOSITORY_ROOT,
            text=True,
        ).splitlines()
        self.assertTrue(unsafe_attributes)
        self.assertTrue(all(line.endswith(": unset") for line in unsafe_attributes))

    def test_published_provenance_digest_matches_install_docs(self) -> None:
        marker = (
            REPOSITORY_ROOT / "no-negative-echo" / ".no-negative-echo-provenance.json"
        )
        digest = hashlib.sha256(marker.read_bytes()).hexdigest()
        for relative in ("INSTALL.md", "README.md", "README_EN.md"):
            with self.subTest(relative=relative):
                contents = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(digest, contents)

    def test_interface_icon_assets_are_valid(self) -> None:
        skill_root = REPOSITORY_ROOT / "no-negative-echo"
        metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")

        for filename, expected_dimensions in {
            "icon.png": (1024, 1024),
            "icon-400.png": (400, 400),
        }.items():
            png = (skill_root / "assets" / filename).read_bytes()
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            dimensions = (
                int.from_bytes(png[16:20], "big"),
                int.from_bytes(png[20:24], "big"),
            )
            self.assertEqual(dimensions, expected_dimensions)
            self.assertIn(png[25], {4, 6}, f"{filename} must preserve alpha")

        self.assertIn('icon_small: "./assets/icon-400.png"', metadata)
        self.assertIn('icon_large: "./assets/icon.png"', metadata)

    def test_installable_skill_excludes_evaluation_harness(self) -> None:
        skill_root = REPOSITORY_ROOT / "no-negative-echo"
        forbidden_names = {
            "evaluation-oracle.jsonl",
            "evaluation-prompts.jsonl",
            "evaluation-protocol.md",
            "score_eval.py",
            "test_scripts.py",
        }
        packaged_names = {
            path.name
            for path in skill_root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertTrue(forbidden_names.isdisjoint(packaged_names))

    def test_prompt_and_oracle_ids_match(self) -> None:
        prompts = load_jsonl(REPOSITORY_ROOT / "evals" / "evaluation-prompts.jsonl")
        oracle = load_jsonl(REPOSITORY_ROOT / "evals" / "evaluation-oracle.jsonl")
        self.assertEqual(prompts.keys(), oracle.keys())

    def test_implicit_routing_has_positive_and_negative_cases(self) -> None:
        oracle = load_jsonl(REPOSITORY_ROOT / "evals" / "evaluation-oracle.jsonl")
        expected = {
            case_id: case["implicit_activation_expected"]
            for case_id, case in oracle.items()
        }
        self.assertTrue(any(expected.values()))
        self.assertTrue(any(not value for value in expected.values()))
        for case_id in {
            "retain-real-removal",
            "retain-safety-fact",
            "retain-requested-comparison",
            "retain-quoted-data",
            "retain-domain-negative-rule",
            "routing-ordinary-deletion",
            "routing-performance-avoidance",
            "routing-non-trigger",
        }:
            self.assertFalse(expected[case_id], case_id)


if __name__ == "__main__":
    unittest.main()
