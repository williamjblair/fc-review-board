from __future__ import annotations

import unittest

import generate


class ReviewerWorkbenchContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.template = generate.TEMPLATE

    def test_primary_route_is_one_case_not_a_dashboard(self) -> None:
        self.assertIn("['pilot','Current case']", self.template)
        self.assertIn("['queue','Review queue']", self.template)
        self.assertIn("['all','All open PRs']", self.template)
        self.assertIn('id="moreViews"', self.template)
        self.assertNotIn('id="tabs"', self.template)
        self.assertNotIn("const PRIMARY_VIEWS", self.template)
        self.assertNotIn("review-summary", self.template)
        self.assertNotIn("evidence-path", self.template)
        self.assertNotIn("case-utilities", self.template)
        self.assertNotIn("inline-sources", self.template)
        self.assertIn("['queue','all','pr-audits','method'].includes(key)", self.template)
        self.assertNotIn('aria-live="polite"', self.template)

    def test_case_page_has_exactly_three_sequential_findings(self) -> None:
        for label in (
            "Formal Conjectures PR #",
            "1. What happened",
            "2. Review finding",
            "3. Maintainer decision",
        ):
            self.assertIn(label, self.template)
        self.assertEqual(self.template.count('class="finding"'), 3)
        self.assertLess(self.template.index("1. What happened"), self.template.index("2. Review finding"))
        self.assertLess(self.template.index("2. Review finding"), self.template.index("3. Maintainer decision"))
        self.assertIn("Evidence '+(fresh?'is current':'is stale')+'.", self.template)
        self.assertIn("Maintainer decision is", self.template)

    def test_execution_error_never_reads_as_a_policy_verdict(self) -> None:
        self.assertIn("stopped with an execution <strong>error</strong>", self.template)
        self.assertIn("before it produced a structured result", self.template)
        self.assertIn("no proof-property conclusion was reached", self.template)

    def test_method_and_replay_details_are_progressive(self) -> None:
        self.assertIn('<details class="disclosure">', self.template)
        self.assertIn("Evidence and replay details", self.template)
        self.assertIn("Outcome chain", self.template)
        self.assertIn("Exact replay pins", self.template)
        self.assertIn("Preservation and freshness", self.template)
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
        self.assertIn("Advisory evidence only", self.template)
        self.assertIn("cannot approve, reject, or declare the pull request merge-ready", self.template)
        self.assertIn("Only Formal Conjectures maintainers decide", self.template)


if __name__ == "__main__":
    unittest.main()
