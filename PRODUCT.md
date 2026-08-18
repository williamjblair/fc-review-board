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

Provide a review workbench over Formal Conjectures pull requests plus a bounded review, verification, and preservation loop for one calibration case. The queue helps reviewers triage what is ready; the selected case identifies the exact source and revision, exposes pinned evidence and typed outcomes, distinguishes checked facts from errors and interpretation, leaves maintainer disposition explicitly unfilled, and makes drift or recurrence visible. Success means a reviewer can understand the work and its limits quickly, then return to Formal Conjectures for every authoritative action.

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

## First-Screen Contract

The default route is the information-rich **Review queue**, not a landing page
or a one-case narrative. It must immediately state what the table is for, place
ready-for-review work first, and expose familiar search, filters, grouped tables,
CI state, approvals, queue age, and advisory audit evidence. The **Selected
case** remains a first-class tab for the deeper pinned ReviewReport. Evidence,
method, and fidelity views support the workbench; they do not replace it.

## Accessibility & Inclusion

Target WCAG 2.2 AA. Do not rely on color alone for outcome or freshness states; preserve keyboard focus, readable contrast, semantic headings and tables, reduced-motion compatibility, and useful layouts from narrow mobile screens through large review monitors.
