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


if __name__ == "__main__":
    unittest.main()
