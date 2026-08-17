#!/usr/bin/env python3
"""Validate and assemble the one-case reviewer pilot projection.

The component records remain the evidence sources. This module only checks
their bindings and prepares a browser-friendly projection. It cannot set a
maintainer disposition or reinterpret a typed execution outcome.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import review_report


HERE = Path(__file__).parent
PILOT_DIR = HERE / "pilot"
REPORT_PATH = HERE / "pilot_review_report.json"
PR_NUMBER = 4884
PR_HEAD = "601aff40d6fa6c3150242144fadba5dbcc24c89c"
DECLARATION = "Erdos427.erdos_427"
INPUT_SHA256 = "sha256:792a4b5fab29e5855fbcb1115d54e28a054d8fcf7ee2bd5589834a73b387c052"


class PilotError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotError(f"cannot load pilot component: {path.name}") from exc


def _raw_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _commit(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def validate_preparation(value: Any) -> dict[str, Any]:
    fields = {
        "authority_effect", "formal_conjectures_revision", "input_sha256",
        "mathlib_revision", "schema", "source_head", "workspace_files",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise PilotError("invalid preparation fields")
    if value["schema"] != "formal-conjectures.calibration-preparation.v1" or (
        value["authority_effect"] != "none"
    ):
        raise PilotError("invalid preparation boundary")
    if not all(_commit(value[key]) for key in (
        "formal_conjectures_revision", "mathlib_revision", "source_head"
    )) or value["input_sha256"] != INPUT_SHA256:
        raise PilotError("invalid preparation source binding")
    required_files = {
        "Challenge.lean", "Solution.lean", "Submission.lean",
        "Submission/External.lean", "config.json", "lakefile.toml",
        "lean-toolchain",
    }
    files = value["workspace_files"]
    if not isinstance(files, dict) or set(files) != required_files or not all(
        _digest(digest) for digest in files.values()
    ):
        raise PilotError("invalid content-addressed workspace manifest")
    return json.loads(json.dumps(value))


def validate_execution(value: Any) -> dict[str, Any]:
    fields = {
        "authority_effect", "image_id", "network", "outcome_sha256",
        "preparation_sha256", "schema", "stderr_sha256", "stdout_sha256",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise PilotError("invalid execution-manifest fields")
    if value["schema"] != "formal-conjectures.calibration-execution-manifest.v1" or (
        value["authority_effect"] != "none" or value["network"] != "none"
    ):
        raise PilotError("invalid execution boundary")
    if not all(_digest(value[key]) for key in fields if key.endswith("sha256")) or (
        not _digest(value["image_id"])
    ):
        raise PilotError("invalid execution digest")
    return json.loads(json.dumps(value))


def validate_lean_eval_profile(value: Any) -> dict[str, Any]:
    fields = {
        "schema", "authority_effect", "profile_status", "source_identity",
        "answer_cases", "submission_contract", "tool_pins", "nonclaims",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise PilotError("invalid LeanEval profile fields")
    if value["schema"] != "formal-conjectures.fc-lean-eval-profile.v1" or (
        value["authority_effect"] != "none" or value["profile_status"] != "derived"
    ):
        raise PilotError("invalid LeanEval profile boundary")
    source = value["source_identity"]
    if source.get("repository") != "google-deepmind/formal-conjectures" or (
        source.get("declaration") != DECLARATION or not _commit(source.get("head_commit_oid"))
    ):
        raise PilotError("invalid LeanEval source identity")
    tools = value["tool_pins"]
    if set(tools) != {
        "lean_eval_interface_commit", "comparator_interface_commit",
        "comparator_execution_commit", "lean_toolchain", "mathlib_commit",
    }:
        raise PilotError("invalid LeanEval tool-pin fields")
    for key in (
        "lean_eval_interface_commit", "comparator_interface_commit",
        "comparator_execution_commit", "mathlib_commit",
    ):
        if not _commit(tools.get(key)):
            raise PilotError("invalid LeanEval tool pin")
    if tools.get("lean_toolchain") != "leanprover/lean4:v4.27.0":
        raise PilotError("invalid Lean toolchain pin")
    submission = value["submission_contract"]
    if submission.get("multi_file") is not True or submission.get(
        "entrypoint"
    ) != "Submission.lean" or submission.get("licensing_status") != "review_required":
        raise PilotError("invalid multi-file submission boundary")
    source_files = submission.get("source_files")
    if not isinstance(source_files, list) or len(source_files) != 2 or {
        item.get("path") for item in source_files if isinstance(item, dict)
    } != {"Submission.lean", "Submission/External.lean"} or not all(
        isinstance(item, dict) and set(item) == {"path", "sha256"}
        and _digest(item["sha256"]) for item in source_files
    ):
        raise PilotError("invalid LeanEval submission file manifest")
    if value["answer_cases"] != [{
        "mode": "proof", "status": "supported", "mechanism": "theorem_names",
        "gate": None,
    }]:
        raise PilotError("invalid LeanEval answer-case projection")
    if "not_maintainer_or_upstream_acceptance" not in value["nonclaims"]:
        raise PilotError("LeanEval profile lacks acceptance boundary")
    return json.loads(json.dumps(value))


def build_pilot_bundle(
    report: dict[str, Any], *, pilot_dir: Path = PILOT_DIR
) -> dict[str, Any]:
    report = review_report.validate_profile(report)
    audit = report["immutable_audit"]
    if audit["pull_request"]["number"] != PR_NUMBER or audit["head"][
        "commit_oid"
    ] != PR_HEAD:
        raise PilotError("ReviewReport is not bound to the selected calibration case")
    current = report["current_github_observation"]
    if current is None or not all(current.get(key) is not None for key in (
        "observed_at", "repository", "url",
    )):
        raise PilotError("pilot requires a timestamped current GitHub observation")
    if report["maintainer_disposition"] is not None:
        raise PilotError("pilot cannot render a filled maintainer disposition")

    comparator_path = pilot_dir / "comparator-outcome.json"
    preparation_path = pilot_dir / "preparation.json"
    execution_path = pilot_dir / "execution-manifest.json"
    lean_eval_path = pilot_dir / "lean-eval-profile.json"
    comparator = review_report.validate_comparator_outcome(_load(comparator_path))
    preparation = validate_preparation(_load(preparation_path))
    execution = validate_execution(_load(execution_path))
    lean_eval = validate_lean_eval_profile(_load(lean_eval_path))

    attached = report["comparator_evidence"]
    if attached is None or attached["typed_outcome"] != comparator:
        raise PilotError("ReviewReport Comparator attachment does not match the pilot outcome")
    if execution["outcome_sha256"] != _raw_sha256(comparator_path) or execution[
        "preparation_sha256"
    ] != _raw_sha256(preparation_path):
        raise PilotError("execution manifest does not bind the retained component bytes")
    terminal = comparator["terminal_evidence"]
    if execution["stdout_sha256"] != terminal["stdout_sha256"] or execution[
        "stderr_sha256"
    ] != terminal["stderr_sha256"]:
        raise PilotError("execution manifest does not bind the typed terminal evidence")
    if lean_eval["source_identity"]["head_commit_oid"] != preparation["source_head"] or (
        lean_eval["tool_pins"]["mathlib_commit"]
        != preparation["mathlib_revision"]
    ):
        raise PilotError("LeanEval profile does not bind the retained preparation")
    submission = {item["path"]: item["sha256"] for item in (
        lean_eval["submission_contract"]["source_files"]
    )}
    if any(preparation["workspace_files"].get(path) != digest for path, digest in submission.items()):
        raise PilotError("LeanEval submission files do not match the retained workspace")

    tools = lean_eval["tool_pins"]
    return {
        "case": {
            "number": PR_NUMBER,
            "title": "ErdosProblems/427: mark the linked proof conditional on Shiu's theorem",
            "declaration": DECLARATION,
            "selection": "Negative calibration: declared proof condition plus a typed execution error",
        },
        "review_report": report,
        "preparation": preparation,
        "execution": execution,
        "lean_eval": lean_eval,
        "links": {
            "protocol": "https://github.com/google-deepmind/formal-conjectures/issues/4394",
            "pull_request": f"https://github.com/google-deepmind/formal-conjectures/pull/{PR_NUMBER}",
            "head": f"https://github.com/google-deepmind/formal-conjectures/commit/{PR_HEAD}",
            "source_file": (
                "https://github.com/google-deepmind/formal-conjectures/blob/"
                f"{PR_HEAD}/FormalConjectures/ErdosProblems/427.lean"
            ),
            "linked_proof": (
                "https://gist.githubusercontent.com/JohnEdwardJennings/"
                "e2c6ef0daab55857b7cc9d340de7af84/raw/"
                "8ff97800e38582c71246a238e7541a9d69488cbd/Erdos427.lean"
            ),
            "audit_packet": audit["source_url"],
            "historical_run": (
                "https://github.com/williamjblair/formal-conjectures/"
                "actions/runs/31862100273"
            ),
            "calibration_source": (
                "https://github.com/williamjblair/formal-conjectures/commit/"
                f"{preparation['source_head']}"
            ),
            "workspace_source": (
                "https://github.com/williamjblair/formal-conjectures/commit/"
                f"{preparation['formal_conjectures_revision']}"
            ),
            "lean_eval": (
                "https://github.com/leanprover/lean-eval/tree/"
                f"{tools['lean_eval_interface_commit']}"
            ),
            "comparator_interface": (
                "https://github.com/leanprover/comparator/tree/"
                f"{tools['comparator_interface_commit']}"
            ),
            "comparator_execution": (
                "https://github.com/leanprover/comparator/tree/"
                f"{tools['comparator_execution_commit']}"
            ),
        },
        "boundary": {
            "canonical_authority": "Formal Conjectures and its maintainers",
            "board_role": "Advisory evidence projection",
            "maintainer_disposition": None,
            "external_projection": "Vela/problems.science may link later; it is not an authority input",
        },
    }


def load_pilot_bundle(path: Path = REPORT_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return build_pilot_bundle(_load(path))
