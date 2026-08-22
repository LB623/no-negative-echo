#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCORER = REPOSITORY_ROOT / "evals" / "score_eval.py"
sys.path.insert(0, str(REPOSITORY_ROOT / "evals"))

from score_eval import case_sha256, output_sha256  # noqa: E402


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def oracle_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "case-a",
        "forbidden_exact": ["Redis"],
        "required_any": [["PostgreSQL"]],
        "semantic_rule": "Do not reveal the rejected queue implementation.",
        "implicit_activation_expected": True,
    }
    record.update(overrides)
    return record


def prompt_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "case-a",
        "prompt": "Implement the accepted PostgreSQL task queue.",
    }
    record.update(overrides)
    return record


def output_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "run_id": "001",
        "id": "case-a",
        "surfaces": {"artifact": "PostgreSQL task queue"},
    }
    record.update(overrides)
    return record


def judge_records(
    output: dict[str, object],
    *,
    surface: str = "artifact",
    digest: str | None = None,
    case_digest: str | None = None,
    first: tuple[bool, bool] = (True, True),
    second: tuple[bool, bool] | None = (True, True),
    adjudication: tuple[bool, bool] | None = None,
) -> list[dict[str, object]]:
    bound_digest = digest or output_sha256(output)
    bound_case_digest = case_digest or case_sha256(prompt_record(), oracle_record())

    def verdict(
        judge_id: str, values: tuple[bool, bool], *, adjudicator: bool = False
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "run_id": output.get("run_id", "1"),
            "id": output["id"],
            "surface": surface,
            "judge_id": judge_id,
            "output_sha256": bound_digest,
            "case_sha256": bound_case_digest,
            "residue_pass": values[0],
            "task_pass": values[1],
        }
        if adjudicator:
            record["adjudication"] = True
        return record

    records = [verdict("judge-a", first)]
    if second is not None:
        records.append(verdict("judge-b", second))
    if adjudication is not None:
        records.append(verdict("judge-c", adjudication, adjudicator=True))
    return records


class ScorerHarness:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.oracle = root / "oracle.jsonl"
        self.prompts = root / "prompts.jsonl"
        self.outputs = root / "outputs.jsonl"
        self.judgments = root / "judgments.jsonl"
        self.routing = root / "routing.jsonl"

    def run(
        self,
        *,
        oracle: list[dict[str, object]],
        prompts: list[dict[str, object]] | None = None,
        outputs: list[dict[str, object]],
        judgments: list[dict[str, object]] | None,
        routing: list[dict[str, object]] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        write_jsonl(self.oracle, oracle)
        write_jsonl(
            self.prompts,
            prompts if prompts is not None else [prompt_record() for _ in oracle],
        )
        write_jsonl(self.outputs, outputs)
        command = [
            sys.executable,
            str(SCORER),
            "--oracle",
            str(self.oracle),
            "--prompts",
            str(self.prompts),
            "--outputs",
            str(self.outputs),
            "--condition",
            "implicit",
        ]
        if judgments is not None:
            write_jsonl(self.judgments, judgments)
            command.extend(["--judgments", str(self.judgments)])
        if routing is not None:
            write_jsonl(self.routing, routing)
            command.extend(["--routing-trace", str(self.routing)])
        result = subprocess.run(command, capture_output=True, check=False, text=True)
        self.assert_json_only(result)
        return result, json.loads(result.stdout)

    @staticmethod
    def assert_json_only(result: subprocess.CompletedProcess[str]) -> None:
        if result.stderr:
            raise AssertionError(result.stderr)
        json.loads(result.stdout)


class EvaluationIntegrityTests(unittest.TestCase):
    def test_producer_self_reported_verdicts_cannot_create_a_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            clean = output_record(surfaces={"artifact": "PostgreSQL"})
            poisoned = {
                **clean,
                "semantic_pass": True,
                "task_pass": True,
                "activation_observed": True,
            }
            result, payload = harness.run(
                oracle=[oracle_record()],
                outputs=[poisoned],
                judgments=judge_records(clean),
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("producer", str(payload["reason"]))

    def test_single_judge_and_wrong_hash_are_rejected(self) -> None:
        for label, judgments in {
            "single judge": judge_records(output_record(), second=None),
            "wrong hash": judge_records(output_record(), digest="0" * 64),
        }.items():
            with self.subTest(label=label), TemporaryDirectory() as temp_dir:
                harness = ScorerHarness(Path(temp_dir))
                result, payload = harness.run(
                    oracle=[oracle_record()],
                    outputs=[output_record()],
                    judgments=judgments,
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(payload["status"], "ERROR")

    def test_stale_judgments_are_rejected_when_case_rules_change(self) -> None:
        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            output = output_record()
            stale = judge_records(output)
            changed = oracle_record(
                semantic_rule="Fail unless the artifact contains an audit reference."
            )

            result, payload = harness.run(
                oracle=[changed], outputs=[output], judgments=stale
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("case_sha256 mismatch", str(payload["reason"]))

    def test_duplicate_nested_json_keys_are_rejected_before_scoring(self) -> None:
        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            write_jsonl(harness.oracle, [oracle_record()])
            write_jsonl(harness.prompts, [prompt_record()])
            harness.outputs.write_text(
                '{"run_id":"001","id":"case-a","surfaces":'
                '{"artifact":"Redis secret","artifact":"PostgreSQL queue"}}\n',
                encoding="utf-8",
            )
            write_jsonl(harness.judgments, [])

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCORER),
                    "--oracle",
                    str(harness.oracle),
                    "--prompts",
                    str(harness.prompts),
                    "--outputs",
                    str(harness.outputs),
                    "--judgments",
                    str(harness.judgments),
                    "--condition",
                    "implicit",
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            payload = json.loads(result.stdout)

            self.assertEqual(result.returncode, 2)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("duplicate object key", str(payload["reason"]))

    def test_routing_mismatch_is_reported_without_failing_behavior(self) -> None:
        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            output = output_record()
            result, payload = harness.run(
                oracle=[oracle_record()],
                outputs=[output],
                judgments=judge_records(output),
                routing=[
                    {
                        "run_id": "001",
                        "id": "case-a",
                        "activation_observed": False,
                        "source": "host-skill-event-v1",
                    }
                ],
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["behavior"]["joint"]["failed"], 0)
            self.assertEqual(
                payload["behavior_by_activation"]["not_activated"]["joint"],
                {"passed": 1, "failed": 0, "total": 1},
            )
            self.assertEqual(
                payload["behavior_by_activation"]["activated"]["joint"]["total"],
                0,
            )
            self.assertEqual(payload["routing"]["false_negative"], 1)
            self.assertEqual(payload["cases"][0]["failures"], [])

    def test_exact_rules_are_scored_per_surface(self) -> None:
        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            output = output_record(
                surfaces={
                    "title": "PostgreSQL queue (without Redis)",
                    "handoff": "PostgreSQL task queue is ready.",
                }
            )
            judgments = judge_records(output, surface="title") + judge_records(
                output, surface="handoff"
            )
            result, payload = harness.run(
                oracle=[oracle_record()],
                outputs=[output],
                judgments=judgments,
            )

            self.assertEqual(result.returncode, 1)
            case = payload["cases"][0]
            self.assertEqual(case["surfaces"]["title"]["failures"], ["exact_leak"])
            self.assertEqual(case["surfaces"]["handoff"]["failures"], [])
            self.assertEqual(payload["behavior"]["residue"]["failed"], 1)
            self.assertEqual(payload["behavior"]["task"]["failed"], 0)

    def test_disagreement_requires_and_uses_adjudication(self) -> None:
        output = output_record()
        disagreeing = judge_records(output, first=(True, True), second=(False, True))

        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            result, payload = harness.run(
                oracle=[oracle_record()], outputs=[output], judgments=disagreeing
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("adjudication", str(payload["reason"]))

        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            result, payload = harness.run(
                oracle=[oracle_record()],
                outputs=[output],
                judgments=judge_records(
                    output,
                    first=(True, True),
                    second=(False, True),
                    adjudication=(False, True),
                ),
            )
            self.assertEqual(result.returncode, 1)
            surface = payload["cases"][0]["surfaces"]["artifact"]
            self.assertTrue(surface["adjudicated"])
            self.assertEqual(surface["failures"], ["residue_not_passed"])

    def test_legacy_output_text_is_a_single_named_surface(self) -> None:
        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            output = {
                "run_id": "001",
                "id": "case-a",
                "output": "PostgreSQL task queue",
            }
            result, payload = harness.run(
                oracle=[oracle_record()],
                outputs=[output],
                judgments=judge_records(output, surface="output"),
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(list(payload["cases"][0]["surfaces"]), ["output"])

    def test_legacy_cli_can_diagnose_but_never_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            legacy_output = {
                "run_id": "001",
                "id": "case-a",
                "output": "PostgreSQL task queue",
                "semantic_pass": True,
                "task_pass": True,
                "activation_observed": True,
            }
            result, payload = harness.run(
                oracle=[oracle_record()],
                outputs=[legacy_output],
                judgments=None,
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(payload["status"], "UNTRUSTED")
            self.assertEqual(
                payload["evaluation_mode"], "legacy-self-reported-untrusted"
            )
            self.assertEqual(payload["passed"], 0)

    def test_strict_oracle_schema_rejects_unknown_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            output = output_record()
            result, payload = harness.run(
                oracle=[oracle_record(unreviewed_note="not allowed")],
                outputs=[output],
                judgments=judge_records(output),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("unknown fields", str(payload["reason"]))

    def test_strict_prompt_schema_rejects_empty_or_unknown_records(self) -> None:
        invalid_prompts = {
            "missing body": {"id": "case-a"},
            "empty text": {"id": "case-a", "prompt": "  "},
            "unknown field": {
                "id": "case-a",
                "prompt": "Implement PostgreSQL.",
                "condition": "implicit",
            },
        }
        for label, prompt in invalid_prompts.items():
            with self.subTest(label=label), TemporaryDirectory() as temp_dir:
                harness = ScorerHarness(Path(temp_dir))
                output = output_record()
                result, payload = harness.run(
                    oracle=[oracle_record()],
                    prompts=[prompt],
                    outputs=[output],
                    judgments=judge_records(output),
                )

                self.assertEqual(result.returncode, 2)
                self.assertEqual(payload["status"], "ERROR")
                self.assertIn("prompt", str(payload["reason"]))

    def test_empty_oracle_cannot_produce_a_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            harness = ScorerHarness(Path(temp_dir))
            result, payload = harness.run(oracle=[], outputs=[], judgments=[])

            self.assertEqual(result.returncode, 2)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("oracle is empty", str(payload["reason"]))


if __name__ == "__main__":
    unittest.main()
