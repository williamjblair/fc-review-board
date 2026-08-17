# Product

## Product Identity

**Primary program name:** Open Formal Workflows

**Deployment subtitle:** Formal Conjectures · Review, Verification & Preservation

The repository and public deployment use the `open-formal-workflows` slug. The
legacy `fc-review-board.pr-audit-projection.v1` schema identifier remains stable
for evidence-consumer compatibility. The name does not imply Formal Conjectures
maintainer endorsement or transfer authority away from the upstream repository.

## Register

product

## Users

Formal Conjectures maintainers and technically fluent reviewers who need to inspect a small, exact evidence package without confusing advisory checks for repository authority. Secondary readers include AI for Math Seed Grant evaluators assessing whether the pilot reduces review effort while preserving provenance and uncertainty.

## Product Purpose

Provide a bounded review, verification, and preservation loop for one calibration case at a time: identify the exact Formal Conjectures source and revision, expose pinned evidence and typed outcomes, distinguish checked facts from errors and interpretation, leave maintainer disposition explicitly unfilled, and make drift or recurrence visible. Success means a reviewer can understand the evidence and its limits quickly, then return to Formal Conjectures for every authoritative action.

## First-Screen Contract

A first-time reviewer should answer five questions without scrolling or opening
technical detail:

1. What exact Formal Conjectures case is selected?
2. Does the retained evidence still match the live PR head?
3. What evidence exists, and where did the replay stop?
4. What did the advisory ReviewReport conclude?
5. Has a Formal Conjectures maintainer recorded a disposition?

Method, architecture, hashes, tool pins, and recurrence mechanics are secondary
progressive disclosure. They must remain inspectable without competing with the
review task.

## Brand Personality

Forensic, calm, and accountable. The interface should feel like a well-kept lab notebook or code-review evidence packet: precise enough to trust, modest about what it knows, and direct about what remains unresolved.

## Anti-references

- Generic AI-agent control planes, autonomous governance dashboards, and multi-agent orchestration theater.
- Green-score dashboards that collapse evidence into approval, merge readiness, or mathematical truth.
- Marketing-heavy grant demos that hide exact inputs, hashes, errors, or missing maintainer decisions.
- A new problem registry, proof repository, or Vela-owned source of truth.
- Fake partner or integration logos, especially Econlib.

## Design Principles

- Authority is visible at every decision boundary: Formal Conjectures owns declarations, PR state, CI, and maintainer decisions.
- Evidence stays inspectable: show exact source identities, environments, roots, hashes, and typed outcomes close to each claim.
- Unknown is a first-class state: errors, unavailable evidence, staleness, and unfilled maintainer disposition remain distinct.
- Reduce maintainer reading time: one selected calibration case, strong information hierarchy, progressive detail, and direct upstream links.
- Preserve provenance without creating a silo: the board is a disposable advisory projection over source-owned records.
- Keep navigation task-first: case review, review queue, and all PRs are primary;
  discovery, inventory, fidelity, and method are secondary.
- Put actionable review work before approval-recorded, author-blocked, and draft
  queues; keep those states available but collapsed by default.

## Accessibility & Inclusion

Target WCAG 2.2 AA. Do not rely on color alone for outcome or freshness states; preserve keyboard focus, readable contrast, semantic headings and tables, reduced-motion compatibility, and useful layouts from narrow mobile screens through large review monitors.
