from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import pilot
import review_report


class PilotBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = os.environ.get("FC_PR_AUDIT_SOURCE")
        if not source:
            raise RuntimeError("FC_PR_AUDIT_SOURCE must name the exact audit checkout")
        cls.source = Path(source)
        comparator = json.loads((pilot.PILOT_DIR / "comparator-outcome.json").read_text())
        cls.report = review_report.build_profile(
            cls.source,
            "conditional-erdos-427-4884",
            {
                "number": 4884,
                "head_commit_oid": pilot.PR_HEAD,
                "state": "OPEN",
                "review_decision": "REVIEW_REQUIRED",
                "observed_at": "2026-08-17T18:00:00Z",
                "repository": "google-deepmind/formal-conjectures",
                "url": "https://github.com/google-deepmind/formal-conjectures/pull/4884",
            },
            comparator,
        )

    def test_selected_case_is_exact_and_maintainer_disposition_is_empty(self) -> None:
        bundle = pilot.build_pilot_bundle(self.report)
        self.assertEqual(bundle["case"]["number"], 4884)
        self.assertEqual(bundle["case"]["declaration"], "Erdos427.erdos_427")
        self.assertEqual(
            bundle["review_report"]["current_github_observation"]["freshness"],
            "current",
        )
        self.assertIsNone(bundle["boundary"]["maintainer_disposition"])

    def test_execution_error_never_becomes_policy_failure(self) -> None:
        bundle = pilot.build_pilot_bundle(self.report)
        typed = bundle["review_report"]["comparator_evidence"]["typed_outcome"]
        self.assertEqual(typed["invocation"]["outcome"], "error")
        self.assertEqual(typed["result_parse"]["outcome"], "not_attempted")
        self.assertEqual(typed["policy_result"]["outcome"], "not_evaluated")

    def test_retained_component_byte_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "pilot"
            shutil.copytree(pilot.PILOT_DIR, copied)
            path = copied / "preparation.json"
            value = json.loads(path.read_text())
            value["workspace_files"]["Challenge.lean"] = "sha256:" + "0" * 64
            path.write_text(json.dumps(value, indent=2) + "\n")
            with self.assertRaisesRegex(pilot.PilotError, "does not bind"):
                pilot.build_pilot_bundle(self.report, pilot_dir=copied)


if __name__ == "__main__":
    unittest.main()
