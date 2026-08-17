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

REVIEWER_ATTRIBUTION_FIELDS = {
    "kind", "attribution", "method", "exact_inputs", "scope",
    "independence", "shared_dependencies", "results",
}
GIT_EVIDENCE_FIELDS = {"repository", "commit_oid", "path", "sha256"}
PROFILE_FIELDS = {
    "schema", "authority_effect", "immutable_audit",
    "current_github_observation", "comparator_evidence",
    "reviewer_attributions", "maintainer_disposition", "separation",
    "nonclaims",
}
REQUIRED_SEPARATION = {
    "advisory_is_not_maintainer_disposition",
    "github_state_does_not_change_advisory_synthesis",
    "head_mismatch_is_rendered_as_stale_not_reinterpreted",
    "comparator_evidence_does_not_set_maintainer_disposition",
    "terminal_text_is_never_a_policy_verdict",
    "reviewer_kind_is_attribution_not_quality",
    "review_evidence_does_not_set_maintainer_disposition",
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


def validate_reviewer_attributions(value: Any) -> list[dict[str, Any]]:
    """Bind peer human/AI reviewer evidence to exact Git-owned inputs/results.

    Reviewer kind is attribution, not a quality score. The same required
    method, scope, independence, dependency, and content-addressing fields
    apply to both kinds. No attempt/session identity is introduced.
    """
    if not isinstance(value, list):
        raise ReviewReportError("reviewer attributions must be a list")
    validated = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != REVIEWER_ATTRIBUTION_FIELDS:
            raise ReviewReportError(
                f"invalid reviewer attribution fields at index {index}")
        if item["kind"] not in {"human", "ai"}:
            raise ReviewReportError("reviewer kind must be human or ai")
        for field in ("attribution", "method"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise ReviewReportError(f"reviewer {field} must be a nonempty string")
        if not isinstance(item["scope"], list) or not item["scope"] or not all(
            isinstance(part, str) and part for part in item["scope"]
        ):
            raise ReviewReportError("reviewer scope must be nonempty strings")
        if item["independence"] not in {
            "independent", "shared_dependencies", "not_assessed",
        }:
            raise ReviewReportError("invalid reviewer independence value")
        dependencies = item["shared_dependencies"]
        if not isinstance(dependencies, list) or not all(
            isinstance(part, str) and part for part in dependencies
        ):
            raise ReviewReportError("shared dependencies must be strings")
        if item["independence"] == "shared_dependencies" and not dependencies:
            raise ReviewReportError(
                "shared-dependencies attribution must name the dependencies")
        for field in ("exact_inputs", "results"):
            evidence = item[field]
            if not isinstance(evidence, list) or not evidence:
                raise ReviewReportError(f"reviewer {field} must be nonempty")
            for entry in evidence:
                if not isinstance(entry, dict) or set(entry) != GIT_EVIDENCE_FIELDS:
                    raise ReviewReportError(
                        f"reviewer {field} must use exact Git evidence fields")
                if not isinstance(entry["repository"], str) or not entry["repository"]:
                    raise ReviewReportError("Git evidence repository must be nonempty")
                if not isinstance(entry["commit_oid"], str) or not re.fullmatch(
                    r"[0-9a-f]{40}", entry["commit_oid"]
                ):
                    raise ReviewReportError("Git evidence commit_oid must be 40 lowercase hex")
                if not isinstance(entry["path"], str) or not entry["path"]:
                    raise ReviewReportError("Git evidence path must be nonempty")
                if not isinstance(entry["sha256"], str) or not re.fullmatch(
                    r"sha256:[0-9a-f]{64}", entry["sha256"]
                ):
                    raise ReviewReportError("Git evidence sha256 is invalid")
        validated.append(json.loads(json.dumps(item)))
    return validated


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


def validate_profile(value: Any) -> dict[str, Any]:
    """Validate a rendered ReviewReport without recreating source authority.

    The builder validates the pinned source records. This validator protects the
    board's later file boundary, where a generated report is loaded and rendered.
    It checks the report's separations and internal bindings rather than treating
    the report as a new canonical record.
    """
    if not isinstance(value, dict) or set(value) != PROFILE_FIELDS:
        raise ReviewReportError("invalid ReviewReport profile fields")
    if value["schema"] != "formal-conjectures.review-report-profile.v1":
        raise ReviewReportError("unsupported ReviewReport profile schema")
    if value["authority_effect"] != "none":
        raise ReviewReportError("ReviewReport cannot have authority effect")
    if value["maintainer_disposition"] is not None:
        raise ReviewReportError("generated ReviewReport cannot set maintainer disposition")

    immutable = value["immutable_audit"]
    required_immutable = {
        "source_url", "repository", "pull_request", "base", "head",
        "core", "observation", "checks", "advisory_synthesis",
    }
    if not isinstance(immutable, dict) or set(immutable) != required_immutable:
        raise ReviewReportError("invalid immutable audit profile fields")
    pr = immutable["pull_request"]
    if not isinstance(pr, dict) or set(pr) != {"number", "url"}:
        raise ReviewReportError("invalid immutable pull-request identity")
    for side in ("base", "head"):
        revision = immutable[side]
        if not isinstance(revision, dict) or set(revision) != {
            "commit_oid", "tree_oid",
        } or not all(
            isinstance(revision[key], str)
            and re.fullmatch(r"[0-9a-f]{40}", revision[key])
            for key in revision
        ):
            raise ReviewReportError(f"invalid immutable {side} revision")
    for record in ("core", "observation"):
        binding = immutable[record]
        if not isinstance(binding, dict) or set(binding) != {"root", "sha256"}:
            raise ReviewReportError(f"invalid immutable {record} binding")
        if not all(
            isinstance(binding[key], str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", binding[key])
            for key in binding
        ):
            raise ReviewReportError(f"invalid immutable {record} digest")
    if not isinstance(immutable["checks"], list) or not immutable["checks"]:
        raise ReviewReportError("immutable audit must include typed checks")
    for check in immutable["checks"]:
        if not isinstance(check, dict) or set(check) != {
            "id", "kind", "property", "outcome", "severity",
        } or check["outcome"] not in {
            "pass", "fail", "inconclusive", "error", "unavailable",
        }:
            raise ReviewReportError("invalid immutable typed check")
    synthesis = immutable["advisory_synthesis"]
    if not isinstance(synthesis, dict) or synthesis.get("advisory") not in {
        "clean", "needs_revision", "inconclusive", "unavailable",
    }:
        raise ReviewReportError("invalid advisory synthesis")

    current = value["current_github_observation"]
    if current is not None:
        if not isinstance(current, dict) or current.get("authority") != (
            "github_observation_only"
        ):
            raise ReviewReportError("invalid current GitHub observation boundary")
        core_current = {key: current[key] for key in current if key in CURRENT_GITHUB_FIELDS}
        validate_current_github(core_current, pr=pr)
        matches = current.get("head_commit_oid") == immutable["head"]["commit_oid"]
        if current.get("matches_core_head") is not matches or current.get(
            "freshness"
        ) != ("current" if matches else "stale"):
            raise ReviewReportError("invalid current GitHub freshness binding")

    comparator = value["comparator_evidence"]
    if comparator is not None:
        if not isinstance(comparator, dict) or set(comparator) != {
            "canonical_sha256", "typed_outcome", "authority",
        } or comparator["authority"] != "advisory_execution_evidence_only":
            raise ReviewReportError("invalid Comparator evidence boundary")
        typed = validate_comparator_outcome(comparator["typed_outcome"])
        if comparator["canonical_sha256"] != _canonical_sha256(typed):
            raise ReviewReportError("Comparator canonical binding mismatch")

    reviewers = value["reviewer_attributions"]
    if reviewers is not None:
        validate_reviewer_attributions(reviewers)
    separation = value["separation"]
    if not isinstance(separation, dict) or set(separation) != REQUIRED_SEPARATION or (
        not all(flag is True for flag in separation.values())
    ):
        raise ReviewReportError("ReviewReport separation boundary is incomplete")
    nonclaims = value["nonclaims"]
    if not isinstance(nonclaims, list) or not {
        "not_an_acceptance_or_merge_decision",
        "not_a_claim_of_mathematical_truth",
        "not_an_independent_review_board_verdict",
    } <= set(nonclaims):
        raise ReviewReportError("ReviewReport nonclaims are incomplete")
    return json.loads(json.dumps(value))


def build_profile(source: Path, fixture: str,
                  current_github: dict[str, Any] | None = None,
                  comparator_outcome: dict[str, Any] | None = None,
                  reviewer_attributions: list[dict[str, Any]] | None = None,
                  ) -> dict[str, Any]:
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

    reviewers = None
    if reviewer_attributions is not None:
        reviewers = validate_reviewer_attributions(reviewer_attributions)

    profile = {
        "schema": "formal-conjectures.review-report-profile.v1",
        "authority_effect": "none",
        "immutable_audit": immutable,
        "current_github_observation": current,
        "comparator_evidence": comparator,
        "reviewer_attributions": reviewers,
        "maintainer_disposition": None,
        "separation": {
            "advisory_is_not_maintainer_disposition": True,
            "github_state_does_not_change_advisory_synthesis": True,
            "head_mismatch_is_rendered_as_stale_not_reinterpreted": True,
            "comparator_evidence_does_not_set_maintainer_disposition": True,
            "terminal_text_is_never_a_policy_verdict": True,
            "reviewer_kind_is_attribution_not_quality": True,
            "review_evidence_does_not_set_maintainer_disposition": True,
        },
        "nonclaims": sorted(set(core["disposition"]["nonclaims"] + [
            "not_a_repository_decision_or_standing",
            "not_an_independent_review_board_verdict",
        ])),
    }
    return validate_profile(profile)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("fixture", choices=sorted(fc_pr_audit.FIXTURES))
    parser.add_argument("--github-json", type=Path)
    parser.add_argument("--comparator-json", type=Path)
    parser.add_argument("--reviewer-attributions-json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    current = json.loads(args.github_json.read_text()) if args.github_json else None
    comparator = (
        json.loads(args.comparator_json.read_text()) if args.comparator_json else None
    )
    reviewers = (
        json.loads(args.reviewer_attributions_json.read_text())
        if args.reviewer_attributions_json else None
    )
    rendered = json.dumps(
        build_profile(args.source, args.fixture, current, comparator, reviewers),
        indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
