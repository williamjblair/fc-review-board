from __future__ import annotations

import os
import unittest
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
        self.assertEqual(
            profile["immutable_audit"]["advisory_synthesis"]["advisory"],
            "inconclusive",
        )

    def test_changed_head_is_stale_not_a_new_verdict(self) -> None:
        current = {"number": 4884, "head_commit_oid": "0" * 40, "state": "OPEN"}
        profile = review_report.build_profile(
            self.source, "conditional-erdos-427-4884", current)
        self.assertFalse(profile["current_github_observation"]["matches_core_head"])
        self.assertEqual(
            profile["immutable_audit"]["advisory_synthesis"]["advisory"],
            "inconclusive",
        )


if __name__ == "__main__":
    unittest.main()
