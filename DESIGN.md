---
name: Open Formal Workflows: Formal Conjectures Review, Verification & Preservation
description: A calm, task-first reviewer workbench for exact evidence, uncertainty, and source authority.
colors:
  evidence-blue: "oklch(40% 0.072 252)"
  paper-blue: "oklch(97.6% 0.006 238)"
  panel-blue: "oklch(94.1% 0.009 242)"
  card-blue: "oklch(99.2% 0.003 238)"
  ink-primary: "oklch(19% 0.024 258)"
  ink-secondary: "oklch(35% 0.022 254)"
  ink-muted: "oklch(52% 0.016 250)"
  outcome-pass: "oklch(52% 0.075 145)"
  outcome-error: "oklch(52% 0.12 34)"
  outcome-pending: "oklch(66% 0.10 80)"
  dark-paper-blue: "oklch(17.4% 0.024 252)"
  dark-card-blue: "oklch(20.6% 0.024 253)"
  dark-ink-primary: "oklch(92% 0.012 258)"
  dark-evidence-blue: "oklch(74% 0.058 250)"
typography:
  headline:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "35px"
    fontWeight: 710
    lineHeight: 1.14
    letterSpacing: "-0.028em"
  title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "20px"
    fontWeight: 680
    lineHeight: 1.35
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "15.5px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "10px"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "0.075em"
  metadata:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.5
  micro:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.5
  control:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.5
  table:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  indicator:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "17px"
    fontWeight: 500
    lineHeight: 1
  disclosure-icon:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "18px"
    fontWeight: 500
    lineHeight: 1
  brand:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.3
  view-title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "25px"
    fontWeight: 680
    lineHeight: 1.3
  mobile-headline:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "27px"
    fontWeight: 710
    lineHeight: 1.13
  method-title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "28px"
    fontWeight: 680
    lineHeight: 1.3
rounded:
  marker: "3px"
  focus: "4px"
  compact: "5px"
  menu-item: "6px"
  control: "8px"
  menu: "9px"
  surface: "10px"
  table: "12px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "14px"
  lg: "22px"
  xl: "38px"
components:
  disclosure:
    backgroundColor: "transparent"
    textColor: "{colors.ink-secondary}"
    rounded: "0"
    padding: "15px 0"
  text-button:
    backgroundColor: "transparent"
    textColor: "{colors.evidence-blue}"
    rounded: "0"
    padding: "2px 0"
  search-input:
    backgroundColor: "{colors.card-blue}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.control}"
    padding: "6px 11px 6px 30px"
---

# Design System: Open Formal Workflows

Deployment: **Formal Conjectures · Review, Verification & Preservation**

## 1. Overview

**Creative North Star: "The Case Note"**

This product should feel like a reviewer opened one short, carefully prepared
case note in ordinary office light. The exact source and one status sentence
lead into three findings: what happened, the advisory review finding, and the
maintainer decision. Everything else waits until requested.

The layout uses one narrow reading column, hairline rules, quiet labels, and one
cool link accent. Semantic color appears only when it carries a typed outcome or
freshness state. Technical replay detail and protocol are collapsed. The queue
still exists as a secondary tool.

**Key Characteristics:**

- Forensic, calm, accountable.
- Exact identities before interpretation.
- One status sentence and three sequential findings before technical detail.
- Unknown and not-evaluated states remain visible.
- Flat structure with rhythm from rules and spacing, not card grids.
- No persistent dashboard navigation or summary metrics on the case route.

## 2. Colors

The palette is restrained: cool blue paper and ink, one evidence-blue link accent, and semantic colors reserved for outcomes.

### Primary

- **Evidence Blue** (`oklch(40% 0.072 252)`): links, keyboard focus, active filters, and other inspectable source affordances.

### Neutral

- **Paper Blue** (`oklch(97.6% 0.006 238)`): the daylight review surface.
- **Panel Blue** (`oklch(94.1% 0.009 242)`): controls and table headers.
- **Card Blue** (`oklch(99.2% 0.003 238)`): inputs and bounded evidence notes.
- **Primary Ink** (`oklch(19% 0.024 258)`): headings and source identities.
- **Secondary Ink** (`oklch(35% 0.022 254)`): body copy and evidence descriptions.
- **Muted Ink** (`oklch(52% 0.016 250)`): metadata, labels, and limitations.

### Named Rules

**The Evidence Color Rule.** Pass green, error red, and pending amber may only describe the state named beside them. They never imply merge readiness or maintainer acceptance.

**The Restrained Accent Rule.** Evidence Blue marks inspectable sources and current interaction. It is not decoration.

## 3. Typography

**Display Font:** system UI sans-serif stack
**Body Font:** system UI sans-serif stack
**Label/Mono Font:** SFMono-Regular, Menlo, Consolas, monospace

**Character:** Native, technical, and quiet. Weight and scale carry hierarchy; no display face competes with the evidence.

### Hierarchy

- **Headline** (710, 35px desktop / 27px narrow, 1.13): selected case declaration.
- **Title** (680, 20px, 1.35): the three case findings.
- **Body** (400, 15.5px, 1.66): explanations, capped near 70 characters where prose permits.
- **Label** (700, 10px, 0.08em, uppercase): authority, pilot, and protocol context.
- **Hash** (400, 11px): commits, roots, and digests with wrap-anywhere behavior.

### Named Rules

**The Identity First Rule.** A PR number, declaration, commit, root, or file path is set as readable text, never hidden behind an unexplained icon.

## 4. Elevation

The system is flat by default. Depth comes from tonal layers and 1px rules. A
restrained shadow appears only on transient menus.

### Shadow Vocabulary

- **Filter Menu** (`0 8px 24px color-mix(in oklab, var(--ink0) 18%, transparent)`): separates an open popover from dense table content.

### Named Rules

**The Flat Evidence Rule.** Evidence rows, reports, and method steps use rules, not decorative shadow or glass.

## 5. Components

### Buttons

- **Primary case actions:** ordinary source links, not command buttons.
- **Secondary navigation:** underlined text buttons with no filled surface.
- **Queue controls:** compact 7px to 8px controls only inside secondary tools.
- **Hover / Focus:** quiet tonal hover and a 2px Evidence Blue focus outline.

### Badges and Chips

The primary case route uses no badges or chips. Typed outcome markers appear
only inside expanded evidence detail, where text carries the meaning and color
is supplemental.

### Cards / Containers

- **Corner Style:** 9px for transient menus; 12px for secondary table scroll frames.
- **Background:** Paper Blue holds the page; Card Blue is reserved for controls,
  tables, and secondary tools.
- **Shadow Strategy:** flat at rest.
- **Border:** 1px neutral full borders. Colored side stripes are forbidden.
- **Internal Padding:** 11px to 16px for bounded surfaces; evidence rows use 14px vertical rhythm without a card wrapper.

### Inputs / Fields

- **Style:** Card Blue fill, 1px neutral border, 8px radius, 13px text.
- **Focus:** 2px Evidence Blue outline with 2px offset.
- **Error / Disabled:** use semantic text plus a label; never encode state with fill alone.

### Navigation

The current case is the default and only persistent task. A small native
disclosure labeled Other tools contains queue, all-PR, inventory, discovery,
fidelity, and method views. Secondary views always expose a Current case return
link. There are no persistent tabs or dashboard metrics on the case route.

### Case Findings

The selected declaration and exact source link lead into a compact sentence
that names freshness, advisory state, and maintainer-decision state. Three
separated sections then explain what happened, the advisory finding, and the
unfilled maintainer decision. These states never collapse into one verdict.

### Progressive Disclosure

Evidence rows and replay pins, preservation mechanics, and protocol/non-goals
use native `details` controls. They remain keyboard accessible and collapsed by
default. This follows Shadcn-style Accordion/Collapsible discipline without
adding a component framework to the single-file static runtime.

### Triage Queue

Ready-for-review pull requests appear first, longest waiting first. Waiting on
author, approval recorded, and draft states remain available in collapsed
groups. Desktop uses the dense table; mobile uses compact review rows with PR,
title, CI, author, waiting time, churn, and advisory audit state.

The responsive switch is a 760px workbench container query, so the same compact
layout activates in a narrow app panel as well as a phone viewport.

### Evidence Row

Each row has a claim name, source plus limitation, and typed outcome. Desktop uses three columns; mobile stacks them in that order. Sources remain links, hashes wrap, and terminal text never occupies the outcome position.

## 6. Do's and Don'ts

### Do:

- **Do** keep Formal Conjectures authority visible at every decision boundary.
- **Do** show exact source identities, environments, roots, hashes, and typed outcomes close to each claim.
- **Do** preserve error, unavailable, stale, and not-evaluated as different states.
- **Do** use familiar links, disclosures, separators, focus states, and system typography.
- **Do** keep evidence rows flat and readable from 390px through wide review monitors.
- **Do** answer case status through one sentence and three findings before exposing replay internals.
- **Do** put actionable review work before non-actionable queue states.

### Don't:

- **Don't** resemble generic AI-agent control planes, autonomous governance dashboards, or multi-agent orchestration theater.
- **Don't** collapse evidence into a green score, approval, merge readiness, or mathematical truth.
- **Don't** use marketing-heavy grant-demo styling that hides exact inputs, hashes, errors, or missing maintainer decisions.
- **Don't** create a new problem registry, proof repository, or Vela-owned source of truth.
- **Don't** show fake partner or integration logos, especially Econlib.
- **Don't** use colored side-stripe borders, gradient text, decorative glass, nested cards, or identical card grids.
- **Don't** make method, architecture, hashes, or inventory compete with the
  selected case and its review boundary.

## 7. Final Impeccable Audit

The 2026-08-17 release gate used an independent design assessment plus
deterministic browser, Lighthouse, responsive, and contract checks. Scores are
deductions from 100, not a restatement of Lighthouse categories.

| Dimension | Score | Evidence and deductions |
| --- | ---: | --- |
| Hierarchy | 98 | The exact PR and declaration, one tri-state sentence, and three numbered findings form a single reading path. Two points are reserved because the product identity and authority line still precede the case. |
| Information architecture | 97 | Other tools has four choices. Replay outcomes, exact pins, non-claims, preservation, and method are progressively disclosed. Three points are reserved for the retained secondary queue surface. |
| Clarity | 97 | Visible copy states metadata pass, execution error, no proof-property conclusion, inconclusive advisory finding, and unrecorded maintainer decision in ordinary language. Three points are reserved for unavoidable domain terms such as metadata and replay. |
| Interaction and accessibility | 97 | Lighthouse accessibility is 100. Keyboard focus, skip navigation, native disclosures, Escape and outside dismissal, semantic headings and regions, 44px mobile controls, and text-carried states were verified. Three points are reserved for the denser secondary data tables. |
| Responsive behavior | 96 | Browser checks at 1280x900, 390x844, and 320x720 show no horizontal overflow. The mobile menu reflows instead of covering the case, and exact hashes remain nested. Four points are reserved for long secondary queue and evidence views on a phone. |
| Visual craft | 98 | One 760px reading column, restrained OKLCH color, system typography, hairline separators, light and dark themes, and no cards, gradients, glass, hero metrics, or decorative badges. Two points are reserved for the intentionally ordinary native aesthetic. |

The first independent pass scored information architecture 93, clarity 90,
interaction and accessibility 93, and responsive behavior 94. The release pass
removed parser and policy jargon, reduced the six-choice utility menu to four,
made menu targets 44px, added Escape and outside dismissal, removed the broad
live region, made the mobile menu reflow, split typed outcomes from collapsed
exact pins, and added a direct upstream continuation link. A second independent
browser pass found no remaining dimension below 95.

The generated page is about 420 KB uncompressed and 59 KB with gzip. Compact
embedded data improved local throttled Lighthouse performance from 89 to 91;
accessibility and best practices score 100. The local performance score includes
Python's uncompressed development server, while the public Pages response is
verified separately after deployment.

The final deterministic Impeccable scan reports one warning and no other
findings. Its flat-type-hierarchy warning samples the utility sizes 12px through
19px and omits the case hierarchy. The primary route uses 35px, 20px, and 15.5px
steps, ratios of 1.75 and 1.29, so the warning is a verified false positive for
the secondary product controls rather than an unresolved release issue.
