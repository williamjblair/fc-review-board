#!/usr/bin/env python3
"""Reader-facing ReviewReport profile over the pinned FC audit pair.

This is an advisory adapter, not a new authority record. The immutable audit
and its rooted observation remain the source objects; current GitHub state is
displayed separately and never changes the advisory synthesis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fc_pr_audit


class ReviewReportError(ValueError):
    pass


def build_profile(source: Path, fixture: str,
                  current_github: dict[str, Any] | None = None) -> dict[str, Any]:
    source = source.resolve(strict=True)
    fc_pr_audit._assert_source(source)
    expected = fc_pr_audit.FIXTURES.get(fixture)
    if expected is None:
        raise ReviewReportError(f"unknown pinned audit fixture: {fixture}")
    validator = fc_pr_audit._load_validator(source)
    directory = source / "audit/pr-audit-v1/fixtures" / fixture
    core_path = directory / "expected-core.json"
    observation_path = directory / "expected-observation.json"
    core = validator.validate_core(
        validator.parse_json_bytes(core_path.read_bytes(), label=str(core_path)))
    observation = validator.validate_observation(
        validator.parse_json_bytes(observation_path.read_bytes(), label=str(observation_path)))
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
        "observation": {"root": observation["root"]},
        "checks": [
            {key: check[key] for key in ("id", "kind", "property", "outcome", "severity")}
            for check in core["checks"]
        ],
        "advisory_synthesis": core["disposition"],
    }
    current = None
    if current_github is not None:
        if current_github.get("number") != pr["number"]:
            raise ReviewReportError("current GitHub observation names a different PR")
        current = dict(current_github)
        current["matches_core_head"] = (
            current_github.get("head_commit_oid") == repository["head"]["commit_oid"])
        current["authority"] = "github_observation_only"

    return {
        "schema": "formal-conjectures.review-report-profile.v1",
        "authority_effect": "none",
        "immutable_audit": immutable,
        "current_github_observation": current,
        "maintainer_disposition": None,
        "separation": {
            "advisory_is_not_maintainer_disposition": True,
            "github_state_does_not_change_advisory_synthesis": True,
            "head_mismatch_is_rendered_as_stale_not_reinterpreted": True,
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
    args = parser.parse_args()
    current = json.loads(args.github_json.read_text()) if args.github_json else None
    print(json.dumps(build_profile(args.source, args.fixture, current), indent=2,
                     sort_keys=True))


if __name__ == "__main__":
    main()
