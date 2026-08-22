#!/usr/bin/env python3
"""Score frozen outputs using independent, hash-bound evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "no-negative-echo" / "scripts"))
from check_surface import normalize  # noqa: E402

Condition = Literal["no-skill", "comparator", "explicit", "implicit"]
ORACLE_FIELDS = {
    "id",
    "forbidden_exact",
    "required_any",
    "semantic_rule",
    "implicit_activation_expected",
}
PROMPT_FIELDS = {"id", "prompt", "messages"}
MESSAGE_FIELDS = {"role", "content"}
OUTPUT_FIELDS = {"run_id", "id", "output", "surfaces"}
SELF_REPORTS = {"semantic_pass", "residue_pass", "task_pass", "activation_observed"}
JUDGE_FIELDS = {
    "run_id",
    "id",
    "surface",
    "judge_id",
    "output_sha256",
    "case_sha256",
    "residue_pass",
    "task_pass",
    "adjudication",
}
ROUTE_FIELDS = {"run_id", "id", "activation_observed", "source"}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _load_json_record(path: Path, line_number: int, line: str) -> Any:
    try:
        return json.loads(line, object_pairs_hook=_object_without_duplicate_keys)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}:{line_number}: {exc}") from exc


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    out = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = _load_json_record(path, n, line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{n}: record must be an object")
        key = row.get("id")
        if not isinstance(key, str) or not key:
            raise ValueError(f"{path}:{n}: missing string id")
        if key in out:
            raise ValueError(f"{path}:{n}: duplicate id {key}")
        out[key] = row
    return out


def _load_pairs(path: Path, kind: str) -> dict[tuple[str, str], dict[str, Any]]:
    out = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = _load_json_record(path, n, line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{n}: {kind} must be an object")
        rid, cid = row.get("run_id", "1"), row.get("id")
        if not isinstance(rid, str) or not rid:
            raise ValueError(f"{path}:{n}: run_id must be a non-empty string")
        if not isinstance(cid, str) or not cid:
            raise ValueError(f"{path}:{n}: missing string id")
        key = (rid, cid)
        if key in out:
            raise ValueError(f"{path}:{n}: duplicate run_id/id pair {rid}/{cid}")
        out[key] = row
    return out


def load_outputs(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    return _load_pairs(path, "output")


def load_expected_run_ids(path: Path) -> list[str]:
    ids, seen = [], set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        rid = line.strip()
        if not rid:
            continue
        if rid in seen:
            raise ValueError(f"{path}:{n}: duplicate run id {rid}")
        seen.add(rid)
        ids.append(rid)
    if not ids:
        raise ValueError(f"{path}: expected run id file is empty")
    return ids


def validate_oracle(row: dict[str, Any]) -> None:
    unknown, missing = (
        sorted(set(row) - ORACLE_FIELDS),
        sorted(ORACLE_FIELDS - set(row)),
    )
    if unknown:
        raise ValueError(f"oracle {row.get('id')} has unknown fields: {unknown}")
    if missing:
        raise ValueError(f"oracle {row.get('id')} is missing fields: {missing}")
    if not isinstance(row["id"], str) or not row["id"]:
        raise ValueError("oracle id must be a non-empty string")
    if not isinstance(row["forbidden_exact"], list) or any(
        not isinstance(x, str) or not x for x in row["forbidden_exact"]
    ):
        raise ValueError(f"oracle {row['id']} has invalid forbidden_exact")
    groups = row["required_any"]
    if not isinstance(groups, list) or any(
        not isinstance(g, list)
        or not g
        or any(not isinstance(x, str) or not x for x in g)
        for g in groups
    ):
        raise ValueError(f"oracle {row['id']} has invalid required_any")
    if not isinstance(row["semantic_rule"], str) or not row["semantic_rule"].strip():
        raise ValueError(f"oracle {row['id']} has invalid semantic_rule")
    if not isinstance(row["implicit_activation_expected"], bool):
        raise ValueError(f"oracle {row['id']} has invalid implicit_activation_expected")


def validate_prompt(row: dict[str, Any]) -> None:
    unknown = sorted(set(row) - PROMPT_FIELDS)
    if unknown:
        raise ValueError(f"prompt {row.get('id')} has unknown fields: {unknown}")
    if not isinstance(row.get("id"), str) or not row["id"]:
        raise ValueError("prompt id must be a non-empty string")
    if ("prompt" in row) == ("messages" in row):
        raise ValueError(
            f"prompt {row['id']} must contain exactly one of prompt or messages"
        )
    if "prompt" in row:
        if not isinstance(row["prompt"], str) or not row["prompt"].strip():
            raise ValueError(f"prompt {row['id']} has invalid prompt text")
        return

    messages = row["messages"]
    if not isinstance(messages, list) or not messages:
        raise ValueError(f"prompt {row['id']} has invalid messages")
    for index, message in enumerate(messages, 1):
        if not isinstance(message, dict) or set(message) != MESSAGE_FIELDS:
            raise ValueError(f"prompt {row['id']} message {index} has invalid fields")
        if not isinstance(message["role"], str) or message["role"] not in {
            "user",
            "assistant",
        }:
            raise ValueError(f"prompt {row['id']} message {index} has invalid role")
        if not isinstance(message["content"], str) or not message["content"].strip():
            raise ValueError(f"prompt {row['id']} message {index} has invalid content")
    if not any(message["role"] == "user" for message in messages):
        raise ValueError(f"prompt {row['id']} messages require a user turn")


def _surfaces(row: dict[str, Any], strict: bool = True) -> dict[str, str]:
    if strict:
        bad = sorted(set(row) & SELF_REPORTS)
        if bad:
            raise ValueError(
                f"producer output contains forbidden self-reported fields: {bad}"
            )
        unknown = sorted(set(row) - OUTPUT_FIELDS)
        if unknown:
            raise ValueError(f"producer output has unknown fields: {unknown}")
    if ("output" in row) == ("surfaces" in row):
        raise ValueError(
            "producer output must contain exactly one of output or surfaces"
        )
    if "output" in row:
        if not isinstance(row["output"], str):
            raise ValueError("producer output must be a string")
        return {"output": row["output"]}
    value = row["surfaces"]
    if not isinstance(value, dict) or not value:
        raise ValueError("surfaces must be a non-empty object")
    if any(
        not isinstance(k, str) or not k or not isinstance(v, str)
        for k, v in value.items()
    ):
        raise ValueError("surface names and values must be strings")
    return value


def output_sha256(row: dict[str, Any]) -> str:
    payload = {
        "run_id": row.get("run_id", "1"),
        "id": row.get("id"),
        "surfaces": _surfaces(row, False),
    }
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def case_sha256(prompt: dict[str, Any], oracle: dict[str, Any]) -> str:
    validate_prompt(prompt)
    validate_oracle(oracle)
    payload = {
        "schema": "no-negative-echo-case-v1",
        "prompt": prompt,
        "oracle": oracle,
    }
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def load_judgments(path: Path) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    groups, seen = {}, set()
    required = {
        "id",
        "surface",
        "judge_id",
        "output_sha256",
        "case_sha256",
        "residue_pass",
        "task_pass",
    }
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = _load_json_record(path, n, line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{n}: judgment must be an object")
        if set(row) - JUDGE_FIELDS:
            raise ValueError(f"{path}:{n}: unknown judgment fields")
        if required - set(row):
            raise ValueError(f"{path}:{n}: missing judgment fields")
        rid, cid, surface, judge = (
            row.get("run_id", "1"),
            row["id"],
            row["surface"],
            row["judge_id"],
        )
        if any(not isinstance(x, str) or not x for x in (rid, cid, surface, judge)):
            raise ValueError(f"{path}:{n}: invalid judgment identity")
        if not isinstance(row["output_sha256"], str) or not SHA_RE.fullmatch(
            row["output_sha256"]
        ):
            raise ValueError(f"{path}:{n}: invalid output_sha256")
        if not isinstance(row["case_sha256"], str) or not SHA_RE.fullmatch(
            row["case_sha256"]
        ):
            raise ValueError(f"{path}:{n}: invalid case_sha256")
        if not isinstance(row["residue_pass"], bool) or not isinstance(
            row["task_pass"], bool
        ):
            raise ValueError(f"{path}:{n}: verdicts must be booleans")
        if "adjudication" in row and not isinstance(row["adjudication"], bool):
            raise ValueError(f"{path}:{n}: invalid adjudication")
        uniq = (rid, cid, surface, judge)
        if uniq in seen:
            raise ValueError(f"{path}:{n}: duplicate judge")
        seen.add(uniq)
        groups.setdefault((rid, cid, surface), []).append(
            {**row, "run_id": rid, "adjudication": row.get("adjudication", False)}
        )
    return groups


def load_routing_trace(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows = _load_pairs(path, "routing trace")
    for key, row in rows.items():
        if set(row) - ROUTE_FIELDS or not {
            "id",
            "activation_observed",
            "source",
        } <= set(row):
            raise ValueError(f"invalid routing trace {key}")
        if row["activation_observed"] is not None and not isinstance(
            row["activation_observed"], bool
        ):
            raise ValueError(f"invalid activation_observed {key}")
        if not isinstance(row["source"], str) or not row["source"].strip():
            raise ValueError(f"invalid routing source {key}")
    return rows


def has_term(text: str, term: str) -> bool:
    return normalize(term) in normalize(text)


def expected_activation(row: dict[str, Any], condition: Condition) -> bool:
    if condition == "explicit":
        return True
    if condition in {"no-skill", "comparator"}:
        return False
    value = row.get("implicit_activation_expected")
    if not isinstance(value, bool):
        raise ValueError("oracle is missing implicit_activation_expected")
    return value


def score_case(
    oracle: dict[str, Any], output: dict[str, Any] | None, condition: Condition
) -> list[str]:
    """Keep the legacy API; evidence mode never calls this helper."""
    if output is None:
        return ["missing_output"]
    text = output.get("output")
    if not isinstance(text, str) or not text.strip():
        return ["empty_output"]
    failures = []
    if any(has_term(text, x) for x in oracle.get("forbidden_exact", [])):
        failures.append("exact_leak")
    if any(
        not any(has_term(text, x) for x in group)
        for group in oracle.get("required_any", [])
    ):
        failures.append("missing_required_fact")
    if output.get("semantic_pass") is not True:
        failures.append("semantic_not_passed")
    if output.get("task_pass") is not True:
        failures.append("task_not_passed")
    if output.get("activation_observed") is not expected_activation(oracle, condition):
        failures.append("routing_mismatch")
    return sorted(set(failures))


def routing_summary_from_trace(oracle, traces, condition, run_ids=None):
    counts = {
        "true_positive": 0,
        "false_positive": 0,
        "true_negative": 0,
        "false_negative": 0,
        "unobserved": 0,
    }
    ids = run_ids or sorted({r for r, _ in traces}) or ["1"]
    for rid in ids:
        for cid, row in oracle.items():
            trace = traces.get((rid, cid))
            observed = trace.get("activation_observed") if trace else None
            if not isinstance(observed, bool):
                counts["unobserved"] += 1
                continue
            expected = expected_activation(row, condition)
            counts[
                "true_positive"
                if expected and observed
                else "false_negative"
                if expected
                else "false_positive"
                if observed
                else "true_negative"
            ] += 1
    pd = counts["true_positive"] + counts["false_positive"]
    rd = counts["true_positive"] + counts["false_negative"]
    return {
        **counts,
        "observations": sum(counts.values()) - counts["unobserved"],
        "precision": counts["true_positive"] / pd if pd else None,
        "recall": counts["true_positive"] / rd if rd else None,
    }


def routing_summary(oracle, outputs, condition, run_ids=None):
    traces = {
        k: {"activation_observed": v.get("activation_observed")}
        for k, v in outputs.items()
    }
    return routing_summary_from_trace(oracle, traces, condition, run_ids)


def _resolve(records, output_digest, case_digest, key):
    label = "/".join(key)
    if any(r["output_sha256"] != output_digest for r in records):
        raise ValueError(f"judgment output_sha256 mismatch for {label}")
    if any(r["case_sha256"] != case_digest for r in records):
        raise ValueError(f"judgment case_sha256 mismatch for {label}")
    base = [r for r in records if not r["adjudication"]]
    adj = [r for r in records if r["adjudication"]]
    if len({r["judge_id"] for r in base}) < 2:
        raise ValueError(
            f"at least two distinct independent judges required for {label}"
        )
    disagree = {f: len({r[f] for r in base}) > 1 for f in ("residue_pass", "task_pass")}
    if any(disagree.values()) and len(adj) != 1:
        raise ValueError(
            f"exactly one adjudication is required for disagreement on {label}"
        )
    if not any(disagree.values()) and adj:
        raise ValueError(f"adjudication without disagreement for {label}")
    return {f: (adj[0][f] if disagree[f] else base[0][f]) for f in disagree} | {
        "adjudicated": bool(adj),
        "judge_ids": sorted(r["judge_id"] for r in base),
        "adjudicator_id": adj[0]["judge_id"] if adj else None,
    }


def score_evidence_case(oracle, prompt, output, judgments, run_id, case_id):
    if output is None:
        return {
            "run_id": run_id,
            "id": case_id,
            "status": "FAIL",
            "residue_pass": False,
            "task_pass": False,
            "failures": ["missing_output"],
            "surfaces": {},
        }
    surfaces = _surfaces(output)
    output_digest = output_sha256(output)
    case_digest = case_sha256(prompt, oracle)
    results, failures, residue_ok, task_ok = {}, [], True, True
    for name, text in surfaces.items():
        verdict = _resolve(
            judgments.get((run_id, case_id, name), []),
            output_digest,
            case_digest,
            (run_id, case_id, name),
        )
        sf = []
        if any(has_term(text, x) for x in oracle["forbidden_exact"]):
            sf.append("exact_leak")
        if not verdict["residue_pass"]:
            sf.append("residue_not_passed")
        if not text.strip():
            sf.append("empty_surface")
        if not verdict["task_pass"]:
            sf.append("task_not_passed")
        ro = not any(x in {"exact_leak", "residue_not_passed"} for x in sf)
        to = not any(x in {"empty_surface", "task_not_passed"} for x in sf)
        residue_ok &= ro
        task_ok &= to
        failures += [f"{x}:{name}" for x in sf]
        results[name] = {
            "status": "PASS" if not sf else "FAIL",
            "residue_pass": ro,
            "task_pass": to,
            "failures": sf,
            "adjudicated": verdict["adjudicated"],
            "judge_ids": verdict["judge_ids"],
            "adjudicator_id": verdict["adjudicator_id"],
        }
    combined = "\n".join(surfaces.values())
    for i, group in enumerate(oracle["required_any"], 1):
        if not any(has_term(combined, x) for x in group):
            task_ok = False
            failures.append(f"missing_required_fact:{i}")
    return {
        "run_id": run_id,
        "id": case_id,
        "output_sha256": output_digest,
        "case_sha256": case_digest,
        "status": "PASS" if residue_ok and task_ok else "FAIL",
        "residue_pass": residue_ok,
        "task_pass": task_ok,
        "failures": sorted(failures),
        "surfaces": results,
    }


def behavior_summary(cases):
    def counts(fn):
        passed = sum(bool(fn(c)) for c in cases)
        return {"passed": passed, "failed": len(cases) - passed, "total": len(cases)}

    return {
        "residue": counts(lambda c: c["residue_pass"]),
        "task": counts(lambda c: c["task_pass"]),
        "joint": counts(lambda c: c["status"] == "PASS"),
    }


def behavior_by_activation(cases, traces):
    grouped = {"activated": [], "not_activated": [], "unobserved": []}
    for case in cases:
        trace = traces.get((case["run_id"], case["id"]))
        observed = trace.get("activation_observed") if trace else None
        group = (
            "activated"
            if observed is True
            else "not_activated"
            if observed is False
            else "unobserved"
        )
        grouped[group].append(case)
    return {name: behavior_summary(rows) for name, rows in grouped.items()}


def _run_ids(outputs, manifest):
    observed = {r for r, _ in outputs}
    if manifest is None:
        if len(observed) > 1:
            raise ValueError(
                "repeated runs require --expected-run-ids so zero-output "
                "runs remain observable"
            )
        return sorted(observed) or ["1"]
    unexpected = sorted(observed - set(manifest))
    if unexpected:
        raise ValueError(f"unexpected run ids: {unexpected}")
    return manifest


def _legacy(oracle, outputs, condition, run_ids):
    cases = []
    for rid in run_ids:
        for cid, row in oracle.items():
            failures = score_case(row, outputs.get((rid, cid)), condition)
            cases.append(
                {
                    "run_id": rid,
                    "id": cid,
                    "status": "FAIL" if failures else "UNTRUSTED",
                    "failures": failures,
                }
            )
    failed = sum(c["status"] == "FAIL" for c in cases)
    return {
        "status": "FAIL" if failed else "UNTRUSTED",
        "evaluation_mode": "legacy-self-reported-untrusted",
        "condition": condition,
        "runs": len(run_ids),
        "total": len(cases),
        "passed": 0,
        "failed": failed,
        "routing": routing_summary(oracle, outputs, condition, run_ids),
        "cases": cases,
    }, (1 if failed else 2)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--oracle", required=True, type=Path)
    p.add_argument("--prompts", type=Path)
    p.add_argument("--outputs", required=True, type=Path)
    p.add_argument("--judgments", type=Path)
    p.add_argument("--routing-trace", type=Path)
    p.add_argument(
        "--condition",
        required=True,
        choices=("no-skill", "comparator", "explicit", "implicit"),
    )
    p.add_argument("--expected-run-ids", type=Path)
    a = p.parse_args()
    try:
        oracle = load_jsonl(a.oracle)
        if not oracle:
            raise ValueError("oracle is empty")
        outputs = load_outputs(a.outputs)
        manifest = (
            load_expected_run_ids(a.expected_run_ids) if a.expected_run_ids else None
        )
        run_ids = _run_ids(outputs, manifest)
        unknown = sorted({c for _, c in outputs} - oracle.keys())
        if unknown:
            raise ValueError(f"unknown output ids: {unknown}")
        if a.judgments is None:
            payload, code = _legacy(oracle, outputs, a.condition, run_ids)
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return code
        if a.prompts is None:
            raise ValueError("evidence mode requires --prompts for case binding")
        for row in oracle.values():
            validate_oracle(row)
        prompts = load_jsonl(a.prompts)
        if prompts.keys() != oracle.keys():
            raise ValueError("prompt and oracle ids do not match")
        for row in prompts.values():
            validate_prompt(row)
        judgments = load_judgments(a.judgments)
        traces = load_routing_trace(a.routing_trace) if a.routing_trace else {}
        scheduled = {(r, c) for r in run_ids for c in oracle}
        if set(traces) - scheduled:
            raise ValueError("unexpected routing trace keys")
        surface_keys = {
            (r, c, s) for (r, c), o in outputs.items() for s in _surfaces(o)
        }
        if set(judgments) - surface_keys:
            raise ValueError("unexpected judgment keys")
        cases = [
            score_evidence_case(
                oracle[c],
                prompts[c],
                outputs.get((r, c)),
                judgments,
                r,
                c,
            )
            for r in run_ids
            for c in oracle
        ]
        behavior = behavior_summary(cases)
        failed = behavior["joint"]["failed"]
        payload = {
            "status": "FAIL" if failed else "PASS",
            "evaluation_mode": "independent-evidence",
            "condition": a.condition,
            "runs": len(run_ids),
            "total": len(cases),
            "passed": behavior["joint"]["passed"],
            "failed": failed,
            "behavior": behavior,
            "behavior_by_activation": behavior_by_activation(cases, traces),
            "routing": routing_summary_from_trace(oracle, traces, a.condition, run_ids),
            "cases": cases,
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "reason": str(exc)}))
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
