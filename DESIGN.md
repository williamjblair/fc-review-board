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
typography:
  headline:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "31px"
    fontWeight: 710
    lineHeight: 1.14
    letterSpacing: "-0.028em"
  title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "18px"
    fontWeight: 680
    lineHeight: 1.35
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "0.075em"
rounded:
  compact: "5px"
  control: "8px"
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
  tab-active:
    backgroundColor: "transparent"
    textColor: "{colors.ink-primary}"
    rounded: "0"
    padding: "9px 11px 10px"
  status-chip:
    backgroundColor: "transparent"
    textColor: "{colors.ink-primary}"
    rounded: "0"
    padding: "0"
  search-input:
    backgroundColor: "{colors.card-blue}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.control}"
    padding: "6px 11px 6px 30px"
---

# Design System: Open Formal Workflows

Deployment: **Formal Conjectures · Review, Verification & Preservation**

## 1. Overview

**Creative North Star: "The Reviewer Desk"**

This product should feel like a reviewer has placed one exact pull request and
its evidence packet on a clear desk in ordinary office light. The case identity,
freshness, evidence boundary, advisory conclusion, and missing maintainer
decision are visible together. Everything else waits until requested.

The layout uses flat paper-like surfaces, hairline rules, compact labels, and one
cool link accent. Semantic color appears only when it carries a typed outcome or
freshness state. The case is task-first; technical replay detail and protocol
are progressive disclosure. The queue puts ready work first and collapses other
states by default.

**Key Characteristics:**

- Forensic, calm, accountable.
- Exact identities before interpretation.
- Five first-screen answers before technical detail.
- Unknown and not-evaluated states remain visible.
- Flat structure with rhythm from rules and spacing, not card grids.
- Dedicated mobile review rows instead of forcing the desktop table into 390px.

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

- **Headline** (710, 31px, 1.14): selected case declaration.
- **Title** (680, 18px, 1.35): task and evidence-section headings.
- **Body** (400, 15px, 1.5): explanations, capped near 70 characters where prose permits.
- **Label** (700, 11px, 0.075em, uppercase): authority, pilot, and protocol context.
- **Hash** (400, 11px): commits, roots, and digests with wrap-anywhere behavior.

### Named Rules

**The Identity First Rule.** A PR number, declaration, commit, root, or file path is set as readable text, never hidden behind an unexplained icon.

## 4. Elevation

The system is flat by default. Depth comes from tonal layers and 1px rules. A
restrained shadow appears only on transient menus. Active navigation uses a 2px
underline, not a raised tab.

### Shadow Vocabulary

- **Filter Menu** (`0 8px 24px color-mix(in oklab, var(--ink0) 18%, transparent)`): separates an open popover from dense table content.

### Named Rules

**The Flat Evidence Rule.** Evidence rows, reports, and method steps use rules, not decorative shadow or glass.

## 5. Components

### Buttons

- **Shape:** gently compact controls (7px to 8px radius).
- **Primary:** the single dark action opens the selected upstream PR. It never
  approves, merges, or writes repository state.
- **Hover / Focus:** quiet tonal hover and a 2px Evidence Blue focus outline.
- **Ghost:** filters and clear actions use plain or card-blue surfaces with standard text labels.

### Chips

- **Style:** compact text labels with a 7px state dot. No decorative pill shell.
- **State:** green means current or pass, red means stale or error, amber means open or pending, and gray means neutral. Color never stands alone.

### Cards / Containers

- **Corner Style:** 9px for the execution note and transient menus; 12px for table scroll frames.
- **Background:** Paper Blue holds the page; Card Blue is reserved for controls,
  tables, and the replay-stop note.
- **Shadow Strategy:** flat at rest.
- **Border:** 1px neutral full borders. Colored side stripes are forbidden.
- **Internal Padding:** 11px to 16px for bounded surfaces; evidence rows use 14px vertical rhythm without a card wrapper.

### Inputs / Fields

- **Style:** Card Blue fill, 1px neutral border, 8px radius, 13px text.
- **Focus:** 2px Evidence Blue outline with 2px offset.
- **Error / Disabled:** use semantic text plus a label; never encode state with fill alone.

### Navigation

Three primary tabs expose Case review, Review queue, and All PRs. Discovery,
inventory, fidelity, and method live under More. The active tab uses stronger ink
and a 2px underline. Mobile keeps all three primary tasks visible without a
horizontal tab scroller.

### Review Summary

Four ledger rows sit beside the exact case identity: evidence freshness,
upstream PR state, advisory ReviewReport synthesis, and maintainer disposition.
The advisory and maintainer rows never collapse into one status.

### Evidence Path

A code-native five-step line shows source head, proof conditions, replay
workspace, execution, and policy. The detailed evidence rows remain immediately
below it with exact links and typed outcomes.

### Progressive Disclosure

Pinned revisions and hashes, preservation mechanics, and protocol/non-goals use
native `details` controls. They remain keyboard accessible and collapsed by
default.

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
- **Do** use familiar tables, tabs, focus states, and system typography.
- **Do** keep evidence rows flat and readable from 390px through wide review monitors.
- **Do** answer the five first-screen questions before exposing replay internals.
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
