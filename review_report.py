#!/usr/bin/env python3
"""Reader-facing ReviewReport profile over the pinned FC audit pair.

This is an advisory adapter, not a new authority record. The immutable audit
and its rooted observation remain the source objects; current GitHub state is
displayed separately and never changes the advisory synthesis.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import fc_pr_audit


class ReviewReportError(ValueError):
    pass


CURRENT_GITHUB_FIELDS = {
    "number", "head_commit_oid", "state", "review_decision",
    "observed_at", "repository", "url",
}

COMPARATOR_FIELDS = {
    "schema", "authority_effect", "invocation", "result_parse",
    "policy_result", "terminal_evidence", "nonclaims",
}


def _canonical_sha256(value: Any) -> str:
    framed = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(framed).hexdigest()


def validate_comparator_outcome(value: Any) -> dict[str, Any]:
    """Validate the typed Comparator adapter without reading terminal text."""
    if not isinstance(value, dict) or set(value) != COMPARATOR_FIELDS:
        raise ReviewReportError("invalid typed Comparator outcome fields")
    if value["schema"] != "formal-conjectures.comparator-outcome.v1":
        raise ReviewReportError("unsupported typed Comparator outcome schema")
    if value["authority_effect"] != "none":
        raise ReviewReportError("Comparator evidence cannot have authority effect")

    invocation = value["invocation"]
    if not isinstance(invocation, dict) or invocation.get("outcome") not in {
        "pass", "error", "unavailable",
    }:
        raise ReviewReportError("invalid Comparator invocation outcome")
    if invocation["outcome"] == "pass" and invocation != {
        "outcome": "pass", "exit_code": 0,
    }:
        raise ReviewReportError("successful Comparator invocation must have exit code zero")

    parsing = value["result_parse"]
    if not isinstance(parsing, dict) or parsing.get("outcome") not in {
        "pass", "error", "not_attempted",
    }:
        raise ReviewReportError("invalid Comparator result-parse outcome")
    policy = value["policy_result"]
    if not isinstance(policy, dict) or policy.get("outcome") not in {
        "pass", "fail", "not_evaluated",
    }:
        raise ReviewReportError("invalid Comparator policy outcome")

    if invocation["outcome"] != "pass":
        if parsing.get("outcome") != "not_attempted" or policy != {
            "outcome": "not_evaluated"
        }:
            raise ReviewReportError(
                "unsuccessful invocation cannot produce a parsed policy verdict")
    elif parsing["outcome"] != "pass":
        if policy != {"outcome": "not_evaluated"}:
            raise ReviewReportError("parse failure cannot produce a policy verdict")
    else:
        if set(policy) != {"schema", "property", "outcome", "witnesses"}:
            raise ReviewReportError("invalid structured Comparator policy result")
        if policy["schema"] != "formal-conjectures.comparator-result.v1" or policy[
            "property"
        ] != "statement_equivalence_and_permitted_axioms":
            raise ReviewReportError("unsupported structured Comparator property")
        witnesses = policy["witnesses"]
        if not isinstance(witnesses, list) or not all(
            isinstance(item, str) and item for item in witnesses
        ):
            raise ReviewReportError("Comparator witnesses must be nonempty strings")
        if policy["outcome"] == "fail" and not witnesses:
            raise ReviewReportError("Comparator policy failure requires a witness")

    terminal = value["terminal_evidence"]
    if not isinstance(terminal, dict) or set(terminal) != {
        "stdout_sha256", "stderr_sha256", "stdout_bytes", "stderr_bytes",
    }:
        raise ReviewReportError("invalid Comparator terminal-evidence fields")
    for key in ("stdout_sha256", "stderr_sha256"):
        if not isinstance(terminal[key], str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", terminal[key]
        ):
            raise ReviewReportError("invalid Comparator terminal-evidence digest")
    for key in ("stdout_bytes", "stderr_bytes"):
        if not isinstance(terminal[key], int) or terminal[key] < 0:
            raise ReviewReportError("invalid Comparator terminal-evidence size")
    nonclaims = value["nonclaims"]
    if not isinstance(nonclaims, list) or (
        "terminal_text_was_not_used_as_a_property_verdict" not in nonclaims
    ):
        raise ReviewReportError("typed Comparator outcome lacks terminal-text boundary")
    return json.loads(json.dumps(value))


def validate_current_github(value: Any, *, pr: dict[str, Any]) -> dict[str, Any]:
    """Validate a closed, head-bound observation without interpreting it."""
    if not isinstance(value, dict):
        raise ReviewReportError("current GitHub observation must be an object")
    extra = set(value) - CURRENT_GITHUB_FIELDS
    if extra:
        raise ReviewReportError(
            f"unknown current GitHub observation fields: {sorted(extra)}")
    required = {"number", "head_commit_oid", "state"}
    if not required <= set(value):
        raise ReviewReportError("current GitHub observation is missing required fields")
    if value["number"] != pr["number"]:
        raise ReviewReportError("current GitHub observation names a different PR")
    if not isinstance(value["head_commit_oid"], str) or not re.fullmatch(
        r"[0-9a-f]{40}", value["head_commit_oid"]
    ):
        raise ReviewReportError("current GitHub head_commit_oid must be 40 lowercase hex")
    if value["state"] not in {"OPEN", "CLOSED", "MERGED"}:
        raise ReviewReportError("current GitHub state is invalid")
    decision = value.get("review_decision")
    if decision not in {None, "APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED"}:
        raise ReviewReportError("current GitHub review_decision is invalid")
    repository = value.get("repository")
    if repository is not None and repository != "google-deepmind/formal-conjectures":
        raise ReviewReportError("current GitHub observation names a different repository")
    url = value.get("url")
    if url is not None and url != pr["url"]:
        raise ReviewReportError("current GitHub observation names a different PR URL")
    observed_at = value.get("observed_at")
    if observed_at is not None:
        if not isinstance(observed_at, str) or not observed_at.endswith("Z"):
            raise ReviewReportError("current GitHub observed_at must be an RFC3339 UTC time")
        try:
            parsed = datetime.fromisoformat(observed_at[:-1] + "+00:00")
        except ValueError as exc:
            raise ReviewReportError(
                "current GitHub observed_at must be an RFC3339 UTC time") from exc
        if parsed.utcoffset() is None:
            raise ReviewReportError("current GitHub observed_at must be timezone-bound")
    return dict(value)


def build_profile(source: Path, fixture: str,
                  current_github: dict[str, Any] | None = None,
                  comparator_outcome: dict[str, Any] | None = None) -> dict[str, Any]:
    source = source.resolve(strict=True)
    fc_pr_audit._assert_source(source)
    expected = fc_pr_audit.FIXTURES.get(fixture)
    if expected is None:
        raise ReviewReportError(f"unknown pinned audit fixture: {fixture}")
    validator = fc_pr_audit._load_validator(source)
    directory = source / "audit/pr-audit-v1/fixtures" / fixture
    core_path = directory / "expected-core.json"
    observation_path = directory / "expected-observation.json"
    core_raw = core_path.read_bytes()
    observation_raw = observation_path.read_bytes()
    if fc_pr_audit._sha256(core_raw) != expected["core_sha256"]:
        raise ReviewReportError("pinned audit core framed bytes drift")
    if fc_pr_audit._sha256(observation_raw) != expected["observation_sha256"]:
        raise ReviewReportError("pinned audit observation framed bytes drift")
    core = validator.validate_core(
        validator.parse_json_bytes(core_raw, label=str(core_path)))
    observation = validator.validate_observation(
        validator.parse_json_bytes(observation_raw, label=str(observation_path)))
    if core["root"] != expected["core_root"] or observation["root"] != expected["observation_root"]:
        raise ReviewReportError("pinned audit pair root mismatch")
    if observation["core"]["root"] != core["root"]:
        raise ReviewReportError("observation is not bound to the immutable core")

    repository = core["repository"]
    pr = repository["pull_request"]
    immutable = {
        "source_url": (
            f"{fc_pr_audit.SOURCE_REPOSITORY}/tree/{fc_pr_audit.SOURCE_COMMIT}/"
            f"audit/pr-audit-v1/fixtures/{fixture}"
        ),
        "repository": repository["repository"],
        "pull_request": pr,
        "base": repository["base"],
        "head": repository["head"],
        "core": {"root": core["root"], "sha256": observation["core"]["sha256"]},
        "observation": {
            "root": observation["root"],
            "sha256": f"sha256:{expected['observation_sha256']}",
        },
        "checks": [
            {key: check[key] for key in ("id", "kind", "property", "outcome", "severity")}
            for check in core["checks"]
        ],
        "advisory_synthesis": core["disposition"],
    }
    current = None
    if current_github is not None:
        current = validate_current_github(current_github, pr=pr)
        current["matches_core_head"] = (
            current_github.get("head_commit_oid") == repository["head"]["commit_oid"])
        current["freshness"] = "current" if current["matches_core_head"] else "stale"
        current["authority"] = "github_observation_only"

    comparator = None
    if comparator_outcome is not None:
        typed = validate_comparator_outcome(comparator_outcome)
        comparator = {
            "canonical_sha256": _canonical_sha256(typed),
            "typed_outcome": typed,
            "authority": "advisory_execution_evidence_only",
        }

    return {
        "schema": "formal-conjectures.review-report-profile.v1",
        "authority_effect": "none",
        "immutable_audit": immutable,
        "current_github_observation": current,
        "comparator_evidence": comparator,
        "maintainer_disposition": None,
        "separation": {
            "advisory_is_not_maintainer_disposition": True,
            "github_state_does_not_change_advisory_synthesis": True,
            "head_mismatch_is_rendered_as_stale_not_reinterpreted": True,
            "comparator_evidence_does_not_set_maintainer_disposition": True,
            "terminal_text_is_never_a_policy_verdict": True,
        },
        "nonclaims": sorted(set(core["disposition"]["nonclaims"] + [
            "not_a_repository_decision_or_standing",
            "not_an_independent_review_board_verdict",
        ])),
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("fixture", choices=sorted(fc_pr_audit.FIXTURES))
    parser.add_argument("--github-json", type=Path)
    parser.add_argument("--comparator-json", type=Path)
    args = parser.parse_args()
    current = json.loads(args.github_json.read_text()) if args.github_json else None
    comparator = (
        json.loads(args.comparator_json.read_text()) if args.comparator_json else None
    )
    print(json.dumps(
        build_profile(args.source, args.fixture, current, comparator),
        indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
