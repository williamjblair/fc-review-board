from __future__ import annotations

import unittest

import generate


class ReviewerWorkbenchContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.template = generate.TEMPLATE

    def test_primary_navigation_is_task_first(self) -> None:
        self.assertIn("['pilot','Case review']", self.template)
        self.assertIn("['queue','Review queue']", self.template)
        self.assertIn("['all','All PRs']", self.template)
        self.assertIn("const PRIMARY_VIEWS = new Set(['pilot','queue','all'])", self.template)
        self.assertIn('id="moreViews"', self.template)

    def test_case_first_screen_separates_all_decision_states(self) -> None:
        for label in (
            "Selected case",
            "Evidence",
            "Upstream PR",
            "Advisory review",
            "Maintainer decision",
            "Not recorded",
        ):
            self.assertIn(label, self.template)
        self.assertIn("Reader-facing synthesis with no authority effect", self.template)

    def test_execution_error_never_reads_as_a_policy_verdict(self) -> None:
        self.assertIn("Replay stopped before a policy verdict", self.template)
        self.assertIn("Result parsing was not attempted", self.template)
        self.assertIn("axiom policy was not evaluated", self.template)
        self.assertIn("never promoted to a failed proof-property verdict", self.template)

    def test_method_and_replay_details_are_progressive(self) -> None:
        self.assertIn('<details class="disclosure">', self.template)
        self.assertIn("Pinned inputs and replay environment", self.template)
        self.assertIn("Method and authority", self.template)
        self.assertIn("No Vela authority path", self.template)
        self.assertIn("No Econlib integration or partner representation", self.template)

    def test_queue_and_mobile_contract_prioritize_actionable_work(self) -> None:
        self.assertLess(
            self.template.index("['review','Ready for review']"),
            self.template.index("['approved','Approval recorded']"),
        )
        self.assertIn('class="queue-primary"', self.template)
        self.assertIn('class="queue-group"', self.template)
        self.assertIn('class="mobile-pr-list"', self.template)
        self.assertIn("container-type: inline-size", self.template)
        self.assertIn("@container (max-width: 760px)", self.template)
        self.assertIn(".data-set > .scroll { display: none; }", self.template)

    def test_authority_boundary_remains_persistent(self) -> None:
        self.assertIn("Formal Conjectures is canonical", self.template)
        self.assertIn("Evidence here never means approval or merge acceptance", self.template)
        self.assertIn("Return to Formal Conjectures for every authoritative action", self.template)


if __name__ == "__main__":
    unittest.main()
