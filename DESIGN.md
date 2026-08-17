---
name: Open Formal Workflows: Formal Conjectures Review, Verification & Preservation
description: A forensic review notebook for exact evidence, uncertainty, and source authority.
colors:
  evidence-blue: "oklch(40% 0.072 252)"
  paper-blue: "oklch(97.2% 0.008 248)"
  panel-blue: "oklch(93.4% 0.011 250)"
  card-blue: "oklch(99.2% 0.004 248)"
  ink-primary: "oklch(20% 0.030 262)"
  ink-secondary: "oklch(38% 0.026 258)"
  ink-muted: "oklch(54% 0.018 252)"
  outcome-pass: "oklch(52% 0.075 145)"
  outcome-error: "oklch(52% 0.12 34)"
  outcome-pending: "oklch(66% 0.10 80)"
typography:
  headline:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "27px"
    fontWeight: 670
    lineHeight: 1.2
    letterSpacing: "-0.022em"
  title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 640
    lineHeight: 1.5
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
    backgroundColor: "{colors.card-blue}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.control}"
    padding: "4px 13px"
  status-chip:
    backgroundColor: "{colors.card-blue}"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.pill}"
    padding: "3px 8px"
  search-input:
    backgroundColor: "{colors.card-blue}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.control}"
    padding: "6px 11px 6px 30px"
---

# Design System: Open Formal Workflows

Deployment: **Formal Conjectures · Review, Verification & Preservation**

## 1. Overview

**Creative North Star: "The Evidence Notebook"**

This product should feel like a well-kept technical notebook opened beside a pull request: calm in ordinary office light, dense without becoming cryptic, and explicit about which observations are checked, derived, stale, or absent. The interface serves reviewers. It never performs institutional confidence or turns a diagnostic into a decision.

The layout uses flat paper-like surfaces, hairline rules, compact labels, and one cool link accent. Semantic color appears only when it carries a typed outcome or freshness state. The bounded pilot is narrative and source-first; the queue remains a familiar dense table.

**Key Characteristics:**

- Forensic, calm, accountable.
- Exact identities before interpretation.
- Unknown and not-evaluated states remain visible.
- Flat structure with rhythm from rules and spacing, not card grids.
- Responsive from a 390px review check to a large monitor without page overflow.

## 2. Colors

The palette is restrained: cool blue paper and ink, one evidence-blue link accent, and semantic colors reserved for outcomes.

### Primary

- **Evidence Blue** (`oklch(40% 0.072 252)`): links, keyboard focus, active filters, and other inspectable source affordances.

### Neutral

- **Paper Blue** (`oklch(97.2% 0.008 248)`): the page field in light mode.
- **Panel Blue** (`oklch(93.4% 0.011 250)`): control groups and table headers.
- **Card Blue** (`oklch(99.2% 0.004 248)`): inputs, active tabs, and bounded surfaces.
- **Primary Ink** (`oklch(20% 0.030 262)`): headings and source identities.
- **Secondary Ink** (`oklch(38% 0.026 258)`): body copy and evidence descriptions.
- **Muted Ink** (`oklch(54% 0.018 252)`): metadata, labels, and limitations.

### Named Rules

**The Evidence Color Rule.** Pass green, error red, and pending amber may only describe the state named beside them. They never imply merge readiness or maintainer acceptance.

**The Restrained Accent Rule.** Evidence Blue marks inspectable sources and current interaction. It is not decoration.

## 3. Typography

**Display Font:** system UI sans-serif stack
**Body Font:** system UI sans-serif stack
**Label/Mono Font:** SFMono-Regular, Menlo, Consolas, monospace

**Character:** Native, technical, and quiet. Weight and scale carry hierarchy; no display face competes with the evidence.

### Hierarchy

- **Headline** (670, 27px, 1.2): selected case identity and primary method title.
- **Title** (640, 15px, 1.5): section headings and evidence names.
- **Body** (400, 15px, 1.5): explanations, capped near 70 characters where prose permits.
- **Label** (700, 11px, 0.075em, uppercase): authority, pilot, and protocol context.
- **Hash** (400, 11px): commits, roots, and digests with wrap-anywhere behavior.

### Named Rules

**The Identity First Rule.** A PR number, declaration, commit, root, or file path is set as readable text, never hidden behind an unexplained icon.

## 4. Elevation

The system is flat by default. Depth comes from tonal layers and 1px rules. A restrained shadow appears only on transient menus and the active tab, where it clarifies interaction state.

### Shadow Vocabulary

- **Active Tab** (`0 1px 2px color-mix(in oklab, var(--ink0) 12%, transparent)`): a minimal state cue inside the tab rail.
- **Filter Menu** (`0 8px 24px color-mix(in oklab, var(--ink0) 18%, transparent)`): separates an open popover from dense table content.

### Named Rules

**The Flat Evidence Rule.** Evidence rows, reports, and method steps use rules, not decorative shadow or glass.

## 5. Components

### Buttons

- **Shape:** gently compact controls (7px to 8px radius).
- **Primary:** there is no persistent primary action on the evidence surface.
- **Hover / Focus:** quiet tonal hover and a 2px Evidence Blue focus outline.
- **Ghost:** filters and clear actions use plain or card-blue surfaces with standard text labels.

### Chips

- **Style:** 999px status chips with a visible text label, 7px state dot, card-blue fill, and full neutral border.
- **State:** green means current or pass, red means stale or error, amber means open or pending, and gray means neutral. Color never stands alone.

### Cards / Containers

- **Corner Style:** 10px for the authority boundary and empty maintainer disposition; 12px for table scroll frames.
- **Background:** Paper Blue holds the page, Card Blue holds bounded controls and tables.
- **Shadow Strategy:** flat at rest.
- **Border:** 1px neutral full borders. Colored side stripes are forbidden.
- **Internal Padding:** 11px to 16px for bounded surfaces; evidence rows use 14px vertical rhythm without a card wrapper.

### Inputs / Fields

- **Style:** Card Blue fill, 1px neutral border, 8px radius, 13px text.
- **Focus:** 2px Evidence Blue outline with 2px offset.
- **Error / Disabled:** use semantic text plus a label; never encode state with fill alone.

### Navigation

Tabs sit in one Panel Blue rail. The active tab uses Card Blue, stronger ink, and a minimal shadow. At narrow widths the rail scrolls horizontally and labels never wrap.

### Evidence Row

Each row has a claim name, source plus limitation, and typed outcome. Desktop uses three columns; mobile stacks them in that order. Sources remain links, hashes wrap, and terminal text never occupies the outcome position.

## 6. Do's and Don'ts

### Do:

- **Do** keep Formal Conjectures authority visible at every decision boundary.
- **Do** show exact source identities, environments, roots, hashes, and typed outcomes close to each claim.
- **Do** preserve error, unavailable, stale, and not-evaluated as different states.
- **Do** use familiar tables, tabs, focus states, and system typography.
- **Do** keep evidence rows flat and readable from 390px through wide review monitors.

### Don't:

- **Don't** resemble generic AI-agent control planes, autonomous governance dashboards, or multi-agent orchestration theater.
- **Don't** collapse evidence into a green score, approval, merge readiness, or mathematical truth.
- **Don't** use marketing-heavy grant-demo styling that hides exact inputs, hashes, errors, or missing maintainer decisions.
- **Don't** create a new problem registry, proof repository, or Vela-owned source of truth.
- **Don't** show fake partner or integration logos, especially Econlib.
- **Don't** use colored side-stripe borders, gradient text, decorative glass, nested cards, or identical card grids.
