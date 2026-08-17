from __future__ import annotations

import os
import unittest
from unittest import mock
from pathlib import Path

import review_report


class ReviewReportProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = os.environ.get("FC_PR_AUDIT_SOURCE")
        if not source:
            raise RuntimeError("FC_PR_AUDIT_SOURCE must name the exact audit checkout")
        cls.source = Path(source)

    def test_4884_round_trips_without_reinterpretation(self) -> None:
        profile = review_report.build_profile(
            self.source, "conditional-erdos-427-4884")
        audit = profile["immutable_audit"]
        self.assertEqual(audit["advisory_synthesis"]["advisory"], "inconclusive")
        self.assertEqual(
            audit["core"]["root"],
            "sha256:e112acd89b801c121d8aebebd4756a481a9db7c2e9790a3a1fd19802b39ab37e",
        )
        self.assertIsNone(profile["maintainer_disposition"])
        self.assertEqual(profile["authority_effect"], "none")

    def test_current_state_is_separate_and_head_bound(self) -> None:
        current = {
            "number": 4884,
            "head_commit_oid": "601aff40d6fa6c3150242144fadba5dbcc24c89c",
            "state": "OPEN",
            "review_decision": "REVIEW_REQUIRED",
        }
        profile = review_report.build_profile(
            self.source, "conditional-erdos-427-4884", current)
        self.assertTrue(profile["current_github_observation"]["matches_core_head"])
        self.assertEqual(profile["current_github_observation"]["freshness"], "current")
        self.assertEqual(
            profile["immutable_audit"]["advisory_synthesis"]["advisory"],
            "inconclusive",
        )

    def test_changed_head_is_stale_not_a_new_verdict(self) -> None:
        current = {"number": 4884, "head_commit_oid": "0" * 40, "state": "OPEN"}
        profile = review_report.build_profile(
            self.source, "conditional-erdos-427-4884", current)
        self.assertFalse(profile["current_github_observation"]["matches_core_head"])
        self.assertEqual(profile["current_github_observation"]["freshness"], "stale")
        self.assertEqual(
            profile["immutable_audit"]["advisory_synthesis"]["advisory"],
            "inconclusive",
        )

    def test_rejects_unbound_or_unknown_github_observation_fields(self) -> None:
        with self.assertRaisesRegex(review_report.ReviewReportError, "40 lowercase hex"):
            review_report.build_profile(
                self.source, "conditional-erdos-427-4884",
                {"number": 4884, "head_commit_oid": "main", "state": "OPEN"})
        with self.assertRaisesRegex(review_report.ReviewReportError, "unknown.*fields"):
            review_report.build_profile(
                self.source, "conditional-erdos-427-4884",
                {"number": 4884, "head_commit_oid": "0" * 40,
                 "state": "OPEN", "mergeable": True})

    def test_rejects_invalid_observation_timestamp_and_state(self) -> None:
        base = {"number": 4884, "head_commit_oid": "0" * 40, "state": "OPEN"}
        with self.assertRaisesRegex(review_report.ReviewReportError, "RFC3339"):
            review_report.build_profile(
                self.source, "conditional-erdos-427-4884",
                {**base, "observed_at": "yesterday"})
        with self.assertRaisesRegex(review_report.ReviewReportError, "state is invalid"):
            review_report.build_profile(
                self.source, "conditional-erdos-427-4884",
                {**base, "state": "UNKNOWN"})

    def test_framed_byte_hashes_are_checked_before_validation(self) -> None:
        fixture = "conditional-erdos-427-4884"
        with mock.patch.dict(
            review_report.fc_pr_audit.FIXTURES[fixture], {"core_sha256": "0" * 64}
        ):
            with self.assertRaisesRegex(review_report.ReviewReportError, "framed bytes drift"):
                review_report.build_profile(self.source, fixture)

    @staticmethod
    def invocation_error() -> dict:
        return {
            "schema": "formal-conjectures.comparator-outcome.v1",
            "authority_effect": "none",
            "invocation": {
                "outcome": "error", "reason": "nonzero_exit", "exit_code": 1,
            },
            "result_parse": {
                "outcome": "not_attempted",
                "reason": "invocation_not_successful",
            },
            "policy_result": {"outcome": "not_evaluated"},
            "terminal_evidence": {
                "stdout_sha256": "sha256:" + "0" * 64,
                "stderr_sha256": "sha256:" + "1" * 64,
                "stdout_bytes": 0,
                "stderr_bytes": 31,
            },
            "nonclaims": [
                "not_an_acceptance_or_merge_decision",
                "not_a_claim_of_mathematical_truth",
                "terminal_text_was_not_used_as_a_property_verdict",
            ],
        }

    def test_typed_invocation_error_stays_not_evaluated_and_hash_bound(self) -> None:
        outcome = self.invocation_error()
        profile = review_report.build_profile(
            self.source, "conditional-erdos-427-4884",
            comparator_outcome=outcome)
        evidence = profile["comparator_evidence"]
        self.assertRegex(evidence["canonical_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            evidence["typed_outcome"]["policy_result"]["outcome"],
            "not_evaluated",
        )
        self.assertIsNone(profile["maintainer_disposition"])

    def test_terminal_exception_cannot_be_relabelled_as_policy_fail(self) -> None:
        outcome = self.invocation_error()
        outcome["policy_result"] = {
            "schema": "formal-conjectures.comparator-result.v1",
            "property": "statement_equivalence_and_permitted_axioms",
            "outcome": "fail",
            "witnesses": ["terminal text said illegal axiom"],
        }
        with self.assertRaisesRegex(
            review_report.ReviewReportError, "cannot produce a parsed policy verdict"
        ):
            review_report.build_profile(
                self.source, "conditional-erdos-427-4884",
                comparator_outcome=outcome)

    def test_structured_policy_failure_requires_a_witness(self) -> None:
        outcome = self.invocation_error()
        outcome["invocation"] = {"outcome": "pass", "exit_code": 0}
        outcome["result_parse"] = {"outcome": "pass"}
        outcome["policy_result"] = {
            "schema": "formal-conjectures.comparator-result.v1",
            "property": "statement_equivalence_and_permitted_axioms",
            "outcome": "fail",
            "witnesses": [],
        }
        with self.assertRaisesRegex(review_report.ReviewReportError, "requires a witness"):
            review_report.validate_comparator_outcome(outcome)

    @staticmethod
    def reviewer(kind: str) -> dict:
        evidence = {
            "repository": "https://github.com/google-deepmind/formal-conjectures",
            "commit_oid": "601aff40d6fa6c3150242144fadba5dbcc24c89c",
            "path": "FormalConjectures/ErdosProblems/427.lean",
            "sha256": "sha256:" + "2" * 64,
        }
        return {
            "kind": kind,
            "attribution": "named reviewer",
            "method": "source fidelity and assumption audit",
            "exact_inputs": [evidence],
            "scope": ["statement fidelity", "declared proof condition"],
            "independence": "shared_dependencies",
            "shared_dependencies": ["same immutable audit core"],
            "results": [{**evidence, "path": "reviews/4884.json"}],
        }

    def test_human_and_ai_are_peer_attributed_kinds(self) -> None:
        reviewers = [self.reviewer("human"), self.reviewer("ai")]
        profile = review_report.build_profile(
            self.source, "conditional-erdos-427-4884",
            reviewer_attributions=reviewers)
        self.assertEqual(
            {item["kind"] for item in profile["reviewer_attributions"]},
            {"human", "ai"},
        )
        self.assertTrue(profile["separation"]["reviewer_kind_is_attribution_not_quality"])
        self.assertIsNone(profile["maintainer_disposition"])

    def test_reviewer_quality_inputs_are_required_for_both_kinds(self) -> None:
        for kind in ("human", "ai"):
            item = self.reviewer(kind)
            item["exact_inputs"] = []
            with self.assertRaisesRegex(
                review_report.ReviewReportError, "exact_inputs must be nonempty"
            ):
                review_report.validate_reviewer_attributions([item])

    def test_shared_dependencies_must_be_visible(self) -> None:
        item = self.reviewer("human")
        item["shared_dependencies"] = []
        with self.assertRaisesRegex(
            review_report.ReviewReportError, "must name the dependencies"
        ):
            review_report.validate_reviewer_attributions([item])


if __name__ == "__main__":
    unittest.main()
