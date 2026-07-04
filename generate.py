#!/usr/bin/env python3
"""Render a review dashboard for formal-conjectures open PRs.

In the spirit of mathlib's queueboard: it turns the open PRs into one page so
maintainers can see what is ready to review, what is waiting on its author, and
what has waited longest. It also joins each Erdos-problem PR to the public Erdos
fidelity audit (https://erdos.constellate.science) and shows, per problem,
whether the linked proof was found unconditional, conditional, or signed by a
named reviewer. The audit surfaces a fact; the merge decision stays the
maintainer's.

generate.py fetches the open PRs (paginating gh api graphql) and the audit
feed, bakes them into one self-contained HTML file as JSON, and ships a small
vanilla-JS app that renders three views (queue / all / fidelity) with search,
faceted filters, sortable columns, and URL-bookmarkable state. No server, no
external fetch at view time.

    curl -sfL https://erdos.constellate.science/verdicts.json > verdicts.json
    python3 generate.py            # writes index.html
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = "google-deepmind/formal-conjectures"
STATEMENT_DIRS = ("ErdosProblems/", "Paper/", "Arxiv/", "Books/", "Wikipedia/",
                  "OEIS/", "OptimizationConstants/", "GreensOpenProblems/")

# The audit feed. Configurable so the board stays a neutral tool: point it at
# any compatible verdicts.json, or drop the column by pointing it at an empty
# feed.
DEFAULT_VERDICTS_URL = "https://erdos.constellate.science/verdicts.json"
FINDING_URL = "https://erdos.constellate.science/finding.html?n={n}"
ERDOS_URL = "https://www.erdosproblems.com/{n}"
ERDOS_FILE_RE = re.compile(r"ErdosProblems/(\d+)\.lean")

# Connective links (not branding: data provenance + how-it-works pointers).
FRONTIER_URL = "https://erdos.constellate.science"
METHOD_URL = "https://erdos.constellate.science/method.html"
FC_REPO_URL = f"https://github.com/{REPO}"
FC_SITE_URL = "https://google-deepmind.github.io/formal-conjectures"
BOARD_REPO_URL = "https://github.com/williamjblair/fc-review-board"

# --- data -----------------------------------------------------------------
# A single `gh pr list --json ...files...` over ~200 PRs asks GitHub for tens
# of thousands of nodes in one query and reliably 502s. Paginate instead: small
# pages via `gh api graphql`, transformed into the flat shape the renderer uses.

_OWNER, _NAME = REPO.split("/")
GRAPHQL_QUERY = """
query($cursor: String) {
  repository(owner: "%s", name: "%s") {
    pullRequests(states: OPEN, first: 25, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title isDraft createdAt updatedAt reviewDecision
        mergeStateStatus additions deletions
        author { login }
        labels(first: 20) { nodes { name } }
        latestOpinionatedReviews(first: 30) { nodes { state } }
        files(first: 100) { nodes { path } }
        commits(last: 1) { nodes { commit { statusCheckRollup {
          contexts(first: 100) { nodes {
            __typename
            ... on CheckRun { name conclusion }
            ... on StatusContext { context state }
          } }
        } } } }
      }
    }
  }
}
""" % (_OWNER, _NAME)


def _gql_page(cursor: str | None) -> dict:
    cmd = ["gh", "api", "graphql", "-f", f"query={GRAPHQL_QUERY}"]
    if cursor is not None:
        cmd += ["-F", f"cursor={cursor}"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200] or "gh api graphql failed")
    return json.loads(out.stdout)


def _status_rollup(node: dict) -> list[dict]:
    commits = (node.get("commits") or {}).get("nodes") or []
    if not commits:
        return []
    scr = (commits[0].get("commit") or {}).get("statusCheckRollup")
    if not scr:
        return []
    out = []
    for c in (scr.get("contexts") or {}).get("nodes") or []:
        if c.get("__typename") == "CheckRun":
            out.append({"name": c.get("name"), "conclusion": c.get("conclusion")})
        elif c.get("__typename") == "StatusContext":
            out.append({"name": c.get("context"), "conclusion": c.get("state")})
    return out


def _transform(n: dict) -> dict:
    return {
        "number": n["number"], "title": n["title"], "isDraft": n["isDraft"],
        "createdAt": n["createdAt"], "updatedAt": n["updatedAt"],
        "reviewDecision": n.get("reviewDecision"),
        "mergeStateStatus": n.get("mergeStateStatus"),
        "additions": n.get("additions", 0), "deletions": n.get("deletions", 0),
        "author": {"login": (n.get("author") or {}).get("login")},
        "labels": [{"name": l["name"]} for l in (n.get("labels") or {}).get("nodes", [])],
        "latestReviews": [{"state": r["state"]}
                          for r in (n.get("latestOpinionatedReviews") or {}).get("nodes", [])],
        "files": [{"path": f["path"]} for f in (n.get("files") or {}).get("nodes", [])],
        "statusCheckRollup": _status_rollup(n),
    }


def pull_prs() -> list[dict]:
    nodes: list[dict] = []
    cursor: str | None = None
    while True:
        for attempt in range(5):
            try:
                data = _gql_page(cursor)
                break
            except RuntimeError as e:
                if attempt == 4:
                    raise SystemExit(f"could not fetch PRs from GitHub: {e}")
                time.sleep(8)
        conn = data["data"]["repository"]["pullRequests"]
        nodes.extend(conn["nodes"])
        if conn["pageInfo"]["hasNextPage"]:
            cursor = conn["pageInfo"]["endCursor"]
        else:
            break
    return [_transform(n) for n in nodes]


def load_prs() -> list[dict]:
    cache = HERE / "prs.json"
    if cache.exists() and cache.read_text().strip():
        prs = json.loads(cache.read_text())
    else:
        prs = pull_prs()
    if not prs:
        raise SystemExit("no PRs to render (empty prs.json) - refusing to write "
                         "an empty board")
    cache.write_text(json.dumps(prs, indent=1))
    return prs


def load_verdicts() -> dict[int, dict]:
    """Index the audit feed by problem number. Prefer a local verdicts.json
    (the Action curls it, tests drop it in); otherwise fetch the live feed."""
    cache = HERE / "verdicts.json"
    if cache.exists():
        data = json.loads(cache.read_text())
    else:
        url = os.environ.get("VERDICTS_URL", DEFAULT_VERDICTS_URL)
        with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310
            data = json.loads(r.read().decode())
    rows = data.get("rows", []) if isinstance(data, dict) else data
    return {r["problem"]: r for r in rows if "problem" in r}


# --- classification -------------------------------------------------------

def ci_state(pr: dict) -> str:
    build = [c for c in (pr.get("statusCheckRollup") or [])
             if c.get("name") == "Build project"]
    if not build:
        return "none"
    concl = (build[0].get("conclusion") or "").upper()
    if concl == "SUCCESS":
        return "green"
    if concl in ("FAILURE", "CANCELLED", "TIMED_OUT"):
        return "failing"
    return "running"


def is_statement(pr: dict) -> bool:
    for f in pr.get("files") or []:
        p = f.get("path", "")
        if p.startswith("FormalConjectures/") and any(d in p for d in STATEMENT_DIRS):
            return True
    return False


def approvals(pr: dict) -> int:
    return sum(1 for r in (pr.get("latestReviews") or [])
               if (r.get("state") or "").upper() == "APPROVED")


def has_conflict(pr: dict) -> bool:
    return (pr.get("mergeStateStatus") or "").upper() == "DIRTY"


def days_since(iso: str, now: datetime) -> int:
    return (now - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days


def classify(pr: dict) -> str:
    labels = {l["name"].lower() for l in pr.get("labels") or []}
    review = pr.get("reviewDecision")
    ci = ci_state(pr)
    if pr.get("isDraft") or "wip" in labels:
        return "draft"
    if review == "APPROVED":
        return "approved"
    if (review == "CHANGES_REQUESTED" or "awaiting-author" in labels
            or ci == "failing" or has_conflict(pr)):
        return "author"
    return "review"


# --- audit join -----------------------------------------------------------

def problem_numbers(pr: dict) -> list[int]:
    nums = set()
    for f in pr.get("files") or []:
        m = ERDOS_FILE_RE.search(f.get("path", ""))
        if m:
            nums.add(int(m.group(1)))
    return sorted(nums)


def _assumptions(row: dict) -> str:
    """Readable form of the Prop hypotheses a conditional proof rests on:
    'hconv : Erdos94.ConvexPosition P' -> 'ConvexPosition P'."""
    labels = []
    for na in row.get("named_assumptions") or []:
        t = na.split(":", 1)[-1].strip()
        labels.append(re.sub(r"\bErdos\d+\.", "", t))
    return ", ".join(labels)


def audit_class(row: dict | None) -> tuple[str, str]:
    """Map an audit row to a (badge-class, tooltip-note). The base colour comes
    from the machine verdict; a signed human verdict overrides it."""
    if row is None:
        return "ab--none", "not in the audit feed"
    signed = row.get("signed_fidelity_verdict")
    mv = row.get("machine_verdict")
    by = row.get("signed_by") or ""
    if signed == "faithful":
        return "ab--signed", f"signed faithful by {by}"
    if signed == "unfaithful":
        return "ab--discrepancy", f"signed unfaithful by {by}"
    if signed == "variant":
        return "ab--variant", f"signed variant by {by}"
    if mv == "unconditional":
        return "ab--unconditional", "machine-checked, unconditional"
    if mv == "conditional":
        asm = _assumptions(row)
        return "ab--conditional", "conditional" + (f" — assumes {asm}" if asm else "")
    return "ab--unaudited", f"not yet audited ({row.get('bucket', 'open')})"


# Severity order (highest first): a PR's headline audit status is the most
# notable thing found among its problems. Maps class -> facet status key.
SEVERITY = ["ab--discrepancy", "ab--conditional", "ab--variant",
            "ab--signed", "ab--unconditional"]
STATUS_KEY = {"ab--signed": "signed", "ab--unconditional": "unconditional",
              "ab--conditional": "conditional", "ab--variant": "conditional",
              "ab--discrepancy": "flagged", "ab--unaudited": "unaudited",
              "ab--none": "unaudited"}


def pr_top_status(audit: list[dict]) -> str | None:
    classes = {a["cls"] for a in audit}
    for s in SEVERITY:
        if s in classes:
            return s
    return None


def build_record(pr: dict, verdicts: dict[int, dict], now: datetime) -> dict:
    audit = []
    for n in problem_numbers(pr):
        row = verdicts.get(n)
        cls, note = audit_class(row)
        href = ERDOS_URL.format(n=n) if row is None else FINDING_URL.format(n=n)
        audit.append({"n": n, "cls": cls, "status": STATUS_KEY[cls],
                      "note": note, "href": href})
    ci = ci_state(pr)
    return {
        "n": pr["number"],
        "title": pr["title"],
        "author": (pr.get("author") or {}).get("login") or "ghost",
        "kind": "statement" if is_statement(pr) else "infra",
        "bucket": classify(pr),
        "ci": ci,
        "ciPending": (not pr.get("isDraft")) and ci == "none",
        "conflict": has_conflict(pr),
        "age": days_since(pr["createdAt"], now),
        "idle": days_since(pr["updatedAt"], now),
        "appr": approvals(pr),
        "churn": (pr.get("additions", 0) or 0) + (pr.get("deletions", 0) or 0),
        "audit": audit,
        "auditTop": pr_top_status(audit),
        "auditStatuses": sorted({a["status"] for a in audit}),
    }


def main() -> None:
    prs = load_prs()
    verdicts = load_verdicts()
    now = datetime.now(timezone.utc)
    records = [build_record(p, verdicts, now) for p in prs]
    meta = {
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "repo": REPO, "hasAudit": bool(verdicts),
    }
    data = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    doc = (TEMPLATE
           .replace("__DATA__", data)
           .replace("__META__", json.dumps(meta).replace("</", "<\\/"))
           .replace("__STAMP__", meta["generated"])
           .replace("__FC_REPO__", FC_REPO_URL)
           .replace("__FC_SITE__", FC_SITE_URL)
           .replace("__BOARD_REPO__", BOARD_REPO_URL)
           .replace("__METHOD__", METHOD_URL)
           .replace("__FRONTIER__", FRONTIER_URL))
    (HERE / "index.html").write_text(doc)
    review = [r for r in records if r["bucket"] == "review"]
    print(f"wrote index.html - {len(records)} PRs, {len(review)} ready for "
          f"review ({sum(1 for r in review if r['kind'] == 'statement')} "
          f"statements), oldest waiting {max((r['age'] for r in review), default=0)}d")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>formal-conjectures &middot; review queue</title>
<style>
:root {
  /* Constellate / Vela canonical tokens (colours only, no branding) — matched to
     erdos-frontier so the trust vocabulary renders identically across both. */
  --paper: oklch(97.2% 0.008 248); --panel: oklch(93.4% 0.011 250); --card: oklch(99.2% 0.004 248);
  --ink0: oklch(20% 0.030 262); --ink1: oklch(38% 0.026 258); --ink2: oklch(54% 0.018 252);
  --rule: color-mix(in oklab, var(--ink0) 12%, transparent);
  --rule2: color-mix(in oklab, var(--ink0) 22%, transparent); --hover: var(--ink0);
  --accent: oklch(40% 0.072 252);
  --ok: oklch(52% 0.075 145); --bad: oklch(52% 0.12 34); --run: oklch(66% 0.10 80);
  --stmt: oklch(40% 0.060 250); --infra: oklch(54% 0.018 252);
  --moss: oklch(43.5% 0.043 128); --brass: oklch(45.5% 0.082 83);
  --gold: oklch(72% 0.130 86); --gold-ink: oklch(46.8% 0.102 82);
  --gold-glow: color-mix(in oklab, var(--gold) 20%, transparent);
  --stone: oklch(55% 0.022 80); --cinnabar: oklch(49.5% 0.128 35);
}
@media (prefers-color-scheme: dark) {
  :root {
    /* Observatory night — deep prussian indigo; gold stays the one warm light. */
    --paper: oklch(17.4% 0.024 252); --panel: oklch(22% 0.026 254); --card: oklch(20.6% 0.024 253);
    --ink0: oklch(92% 0.012 258); --ink1: oklch(74% 0.016 256); --ink2: oklch(60% 0.016 256);
    --rule: color-mix(in oklab, var(--ink0) 16%, transparent);
    --rule2: color-mix(in oklab, var(--ink0) 28%, transparent); --hover: var(--ink0);
    --accent: oklch(74% 0.058 250);
    --ok: oklch(66% 0.085 145); --bad: oklch(64% 0.13 35); --run: oklch(76% 0.10 80);
    --stmt: oklch(74% 0.060 250); --infra: oklch(62% 0.016 256);
    --moss: oklch(60% 0.055 128); --brass: oklch(62% 0.095 83);
    --gold: oklch(77% 0.120 85); --gold-ink: oklch(80% 0.100 84);
    --gold-glow: color-mix(in oklab, var(--gold) 16%, transparent);
    --stone: oklch(64% 0.020 258); --cinnabar: oklch(64% 0.130 35);
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink0);
  font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased; }
.wrap { max-width: 1120px; margin: 0 auto; padding: 44px 24px 72px; }
a { color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }

header { margin-bottom: 18px; }
h1 { font-size: 23px; font-weight: 640; letter-spacing: -.015em; margin: 0 0 7px; }
h1 .h1-sub { color: var(--ink2); font-weight: 460; }
.lede { margin: 0; max-width: 64ch; color: var(--ink1); font-size: 14.5px; line-height: 1.55; }
.meta { margin-top: 11px; font-size: 12.5px; color: var(--ink2); }
.meta a { color: var(--ink1); text-decoration: none; border-bottom: 1px solid var(--rule2); }
.meta a:hover { color: var(--accent); border-color: var(--accent); }
.sep { margin: 0 8px; color: var(--rule2); }

.strip { display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px 26px;
  padding: 15px 18px; margin: 0 0 12px; background: var(--panel);
  border: 1px solid var(--rule); border-radius: 12px; }
.grp { display: flex; flex-wrap: wrap; gap: 10px 22px; align-items: baseline; }
.grp--audit { position: relative; padding-left: 26px; }
.grp--audit::before { content: ""; position: absolute; left: 0; top: 3px; bottom: 3px;
  width: 1px; background: var(--rule2); }
.stat { display: flex; align-items: baseline; gap: 6px; }
.sv { font-size: 19px; font-weight: 660; font-variant-numeric: tabular-nums;
  letter-spacing: -.01em; color: var(--ink0); }
.sl { font-size: 12.5px; color: var(--ink2); }
.sv--gold { color: var(--gold-ink); } .sv--brass { color: var(--brass); } .sv--cinnabar { color: var(--cinnabar); }

.key { display: flex; flex-wrap: wrap; align-items: center; gap: 7px 15px;
  margin: 0 2px 16px; font-size: 12px; color: var(--ink2); }
.key-t { font-weight: 640; color: var(--ink1); text-transform: uppercase;
  letter-spacing: .06em; font-size: 10.5px; }
.key .item { display: inline-flex; align-items: center; gap: 6px; }
.kd { width: 11px; height: 11px; border-radius: 4px; display: inline-block; border: 1px solid transparent; }
.kd--moss { background: color-mix(in oklab, var(--moss) 52%, transparent); }
.kd--brass { background: color-mix(in oklab, var(--brass) 58%, transparent); }
.kd--stone { background: color-mix(in oklab, var(--stone) 40%, transparent); }
.kd--gold { background: var(--gold-glow); border-color: color-mix(in oklab, var(--gold) 55%, transparent); }
.kd--cinnabar { background: color-mix(in oklab, var(--cinnabar) 42%, transparent); }

.toolbar { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center;
  padding: 12px 0; margin-bottom: 6px; border-top: 1px solid var(--rule); }
.search input { font: inherit; font-size: 13px; padding: 6px 11px; width: 210px; max-width: 60vw;
  background: var(--card); color: var(--ink0); border: 1px solid var(--rule2); border-radius: 8px; }
.search input::placeholder { color: var(--ink2); }
.facets { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
.facet { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.facet-l { font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em;
  color: var(--ink2); font-weight: 640; }
.chip { font: inherit; font-size: 12px; padding: 3px 9px; border-radius: 999px;
  border: 1px solid var(--rule2); background: none; color: var(--ink1); cursor: pointer; transition: all .12s ease; }
.chip:hover { border-color: var(--ink2); }
.chip.on { background: color-mix(in oklab, var(--accent) 13%, transparent);
  border-color: color-mix(in oklab, var(--accent) 45%, transparent); color: var(--accent); font-weight: 640; }
.spacer { margin-left: auto; }
.tabs { display: flex; gap: 3px; background: var(--panel); border: 1px solid var(--rule);
  border-radius: 9px; padding: 3px; }
.tab { font: inherit; font-size: 13px; padding: 4px 12px; border-radius: 7px; border: 0;
  background: none; color: var(--ink1); cursor: pointer; transition: all .12s ease; }
.tab:hover { color: var(--ink0); }
.tab.active { background: var(--card); color: var(--ink0); font-weight: 640;
  box-shadow: 0 1px 2px color-mix(in oklab, var(--ink0) 12%, transparent); }
.count { font-size: 12.5px; color: var(--ink2); font-variant-numeric: tabular-nums; }

section { margin: 22px 0; }
.sec-h { display: flex; align-items: baseline; gap: 8px; margin: 0 0 9px; }
.sec-h h2 { font-size: 14px; font-weight: 640; margin: 0; letter-spacing: -.005em; }
.sec-h .n { font-size: 12px; color: var(--ink2); font-weight: 500; font-variant-numeric: tabular-nums; }
.scroll { overflow-x: auto; border: 1px solid var(--rule); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; background: var(--card); }
th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--ink2); font-weight: 640; padding: 9px 12px; background: var(--panel);
  border-bottom: 1px solid var(--rule); white-space: nowrap; }
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { color: var(--ink1); }
th.active { color: var(--ink0); }
td { padding: 9px 12px; border-bottom: 1px solid var(--rule); font-size: 14px; }
tr:last-child td { border-bottom: 0; }
tbody tr { transition: background .12s ease; }
tbody tr:hover { background: color-mix(in oklab, var(--hover) 4%, transparent); }
.num a { color: var(--accent); text-decoration: none; font-variant-numeric: tabular-nums; font-weight: 640; }
.num a:hover { color: var(--gold-ink); text-decoration: underline; }
.ttl { max-width: 440px; }
.ttl-t { display: inline-block; max-width: 440px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; vertical-align: bottom; color: var(--ink0); }
.who { color: var(--ink1); white-space: nowrap; }
.mono { font-variant-numeric: tabular-nums; color: var(--ink1); text-align: right; white-space: nowrap; }
.tag { font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 640; white-space: nowrap; }
.tag--statement { background: color-mix(in oklab, var(--stmt) 12%, transparent); color: var(--stmt); }
.tag--infra { background: color-mix(in oklab, var(--infra) 13%, transparent); color: var(--infra); }
.audit { max-width: 240px; }
.ab { display: inline-block; font-size: 11px; font-variant-numeric: tabular-nums; font-weight: 650;
  text-decoration: none; padding: 1px 6px; margin: 1px 3px 1px 0; border-radius: 5px;
  border: 1px solid transparent; }
.ab:hover { filter: brightness(1.04) saturate(1.1); }
.ab--unconditional { color: var(--moss); background: color-mix(in oklab, var(--moss) 13%, transparent);
  border-color: color-mix(in oklab, var(--moss) 38%, transparent); }
.ab--conditional { color: var(--brass); background: color-mix(in oklab, var(--brass) 14%, transparent);
  border-color: color-mix(in oklab, var(--brass) 40%, transparent); }
.ab--unaudited, .ab--none { color: var(--stone); background: none; border-color: var(--rule2); }
.ab--signed { color: var(--gold-ink); background: var(--gold-glow);
  border-color: color-mix(in oklab, var(--gold) 55%, transparent); }
.ab--variant { color: var(--brass); background: color-mix(in oklab, var(--brass) 14%, transparent);
  border-color: color-mix(in oklab, var(--gold) 55%, transparent); }
.ab--discrepancy { color: var(--cinnabar); background: color-mix(in oklab, var(--cinnabar) 12%, transparent);
  border-color: color-mix(in oklab, var(--cinnabar) 42%, transparent); }
.roll { font-size: 12px; color: var(--ink1); line-height: 1.9; }
.roll b { color: var(--ink0); font-variant-numeric: tabular-nums; }
.rc { display: inline-block; font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums;
  padding: 0 5px; border-radius: 5px; border: 1px solid transparent; }
.ci { display: inline-block; width: 9px; height: 9px; border-radius: 999px; }
.ci--ok { background: var(--ok); } .ci--bad { background: var(--bad); }
.ci--run { background: var(--run); } .ci--na { background: var(--rule2); }
.appr { color: var(--moss); font-weight: 650; }
.appr-c { text-align: center; }
.prlink { font-variant-numeric: tabular-nums; text-decoration: none; color: var(--accent);
  font-weight: 600; font-size: 13px; margin-right: 2px; }
.prlink:hover { color: var(--gold-ink); }
.flag { display: inline-block; font-size: 10px; font-weight: 650; padding: 1px 6px; margin-left: 6px;
  border-radius: 5px; vertical-align: middle; text-transform: uppercase; letter-spacing: .03em; }
.flag--ci { background: color-mix(in oklab, var(--run) 18%, transparent);
  color: color-mix(in oklab, var(--run) 55%, var(--ink0)); }
.flag--conflict { background: color-mix(in oklab, var(--cinnabar) 15%, transparent); color: var(--cinnabar); }
.empty { padding: 44px 12px; text-align: center; color: var(--ink2); font-size: 14px; }
.linkish { font: inherit; color: var(--accent); background: none; border: 0; cursor: pointer; text-decoration: underline; }

footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--rule);
  color: var(--ink2); font-size: 12px; line-height: 1.75; }
footer p { margin: 0 0 8px; max-width: 82ch; }
footer a { color: var(--ink1); text-decoration: none; border-bottom: 1px solid var(--rule2); }
footer a:hover { color: var(--accent); border-color: var(--accent); }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style></head>
<body><div class="wrap">
<header>
  <h1>formal-conjectures <span class="h1-sub">&middot; review queue</span></h1>
  <p class="lede">Open pull requests, oldest waiting first. The audit column shows what the fidelity
  check found for each linked proof; the merge decision stays the maintainer's.</p>
  <div class="meta">Updated __STAMP__ &middot; refreshes hourly<span class="sep">|</span><a href="__FC_REPO__/pulls">pull requests</a><span class="sep">|</span><a href="__FC_SITE__">formal-conjectures</a><span class="sep">|</span><a href="__BOARD_REPO__">source</a></div>
</header>
<div id="strip" class="strip"></div>
<div class="key">
  <span class="key-t">audit</span>
  <span class="item"><span class="kd kd--moss"></span>unconditional</span>
  <span class="item"><span class="kd kd--brass"></span>conditional</span>
  <span class="item"><span class="kd kd--stone"></span>not yet audited</span>
  <span class="item"><span class="kd kd--gold"></span>signed by a reviewer</span>
  <span class="item"><span class="kd kd--cinnabar"></span>flagged unfaithful</span>
</div>
<div class="toolbar">
  <div class="search"><input id="search" type="search" placeholder="Search #, title, author" aria-label="Search pull requests"></div>
  <div class="facets" id="facets"></div>
  <div class="spacer"></div>
  <div class="tabs" id="tabs" role="tablist"></div>
  <span class="count" id="count"></span>
</div>
<div id="app" aria-live="polite"></div>
<noscript><p class="empty">This board needs JavaScript to filter and render.
See the open pull requests at <a href="__FC_REPO__/pulls">github.com/google-deepmind/formal-conjectures</a>.</p></noscript>
<footer>
  <p><strong>The audit column</strong> joins each Erd&#337;s-problem PR to the public fidelity audit &mdash;
  whether the linked proof is machine-checked unconditional, rests on a named assumption, or carries a
  signed reviewer verdict. It reports a fact next to the PR; the merge decision is the maintainer's.
  <a href="__METHOD__">How the audit works &rarr;</a></p>
  <p><strong>Ready for review</strong> = not draft, no changes requested, no merge conflict, CI not failing.
  &check; counts approvals, &pm; is lines changed. &ldquo;CI pending&rdquo; marks PRs whose build has not run yet.
  Filters and sort are shareable: they live in the page URL.</p>
  <p>PR data via the GitHub API. Problem-audit data via the <a href="__FRONTIER__">Erd&#337;s frontier</a>
  snapshot. In the spirit of mathlib's queueboard. An independent tool, not affiliated with the
  formal-conjectures maintainers.</p>
</footer>
</div>
<script>
const DATA = __DATA__;
const META = __META__;

const AUDIT_LABEL = {signed:'signed', unconditional:'unconditional', conditional:'conditional', flagged:'flagged', unaudited:'unaudited'};
const AUDIT_ORDER = ['flagged','conditional','signed','unconditional','unaudited'];
const CLS_OF = {signed:'ab--signed', unconditional:'ab--unconditional', conditional:'ab--conditional', flagged:'ab--discrepancy', unaudited:'ab--unaudited'};
const FID_TITLE = {flagged:'Flagged unfaithful', conditional:'Conditional — rests on an assumption', signed:'Signed faithful', unconditional:'Machine-checked unconditional', unaudited:'Not yet audited'};
const BUCKETS = [['approved','Approved, ready to merge'],['review','Ready for review'],['author','Waiting on the author'],['draft','Draft / work in progress']];
const COLS = [['n','PR'],['title','title'],['author','author'],['kind','kind'],['audit','audit'],['age','open'],['idle','idle'],['ci','CI'],['appr','&check;'],['churn','&pm;']];
const SORTABLE = {n:1, author:1, audit:1, age:1, idle:1, ci:1, appr:1, churn:1};
const FACETS = [
  {group:'audit', label:'Audit', opts:['signed','unconditional','conditional','flagged','unaudited']},
  {group:'kind', label:'Kind', opts:['statement','infra']},
  {group:'ci', label:'CI', opts:['passing','failing','pending','running']},
];

const state = {view:'queue', q:'', facets:{audit:new Set(), kind:new Set(), ci:new Set()}, sort:{col:'idle', dir:'desc'}};

const el = id => document.getElementById(id);
const app = el('app'), searchEl = el('search'), facetsEl = el('facets'), tabsEl = el('tabs'), countEl = el('count');
function esc(s){ const d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
function ciKey(r){ return r.ci === 'green' ? 'passing' : r.ci === 'failing' ? 'failing' : r.ci === 'running' ? 'running' : 'pending'; }

function matches(r){
  if (state.q){ const q = state.q.toLowerCase();
    if (!(('#'+r.n).includes(q) || r.title.toLowerCase().includes(q) || r.author.toLowerCase().includes(q))) return false; }
  const f = state.facets;
  if (f.audit.size && !r.auditStatuses.some(s => f.audit.has(s))) return false;
  if (f.kind.size && !f.kind.has(r.kind)) return false;
  if (f.ci.size && !f.ci.has(ciKey(r))) return false;
  return true;
}

function badge(a){ return '<a class="ab '+a.cls+'" href="'+a.href+'" title="#'+a.n+': '+esc(a.note)+'">'+a.n+'</a>'; }
function auditCell(r){
  if (!r.audit.length) return '<td class="audit"></td>';
  if (r.audit.length <= 8) return '<td class="audit">'+r.audit.map(badge).join('')+'</td>';
  const counts = {}; r.audit.forEach(a => counts[a.status] = (counts[a.status]||0)+1);
  const parts = AUDIT_ORDER.filter(s => counts[s]).map(s => '<span class="rc '+CLS_OF[s]+'">'+counts[s]+'</span>&thinsp;'+AUDIT_LABEL[s]);
  return '<td class="audit"><span class="roll"><b>'+r.audit.length+'</b> problems &middot; '+parts.join(' &middot; ')+'</span></td>';
}
function flagsHtml(r){ let s = '';
  if (r.ciPending) s += '<span class="flag flag--ci" title="CI has not run yet (often waiting on a maintainer to approve the workflow)">CI pending</span>';
  if (r.conflict) s += '<span class="flag flag--conflict" title="Merge conflict with the base branch">conflict</span>';
  return s; }
function ciDot(r){ const m = {green:'ok', failing:'bad', running:'run', none:'na'}; return '<span class="ci ci--'+m[r.ci]+'" title="'+r.ci+'"></span>'; }
function rowHtml(r){
  const appr = r.appr ? '<span class="appr">&check;'+r.appr+'</span>' : '';
  return '<tr>'
    + '<td class="num"><a href="https://github.com/'+META.repo+'/pull/'+r.n+'">#'+r.n+'</a></td>'
    + '<td class="ttl"><span class="ttl-t">'+esc(r.title)+'</span>'+flagsHtml(r)+'</td>'
    + '<td class="who">'+esc(r.author)+'</td>'
    + '<td><span class="tag tag--'+r.kind+'">'+r.kind+'</span></td>'
    + auditCell(r)
    + '<td class="mono">'+r.age+'d</td><td class="mono">'+r.idle+'d</td>'
    + '<td>'+ciDot(r)+'</td><td class="mono appr-c">'+appr+'</td><td class="mono">'+r.churn+'</td>'
    + '</tr>';
}

const AUDIT_RANK = {'ab--discrepancy':0, 'ab--conditional':1, 'ab--variant':1, 'ab--signed':2, 'ab--unconditional':3};
function auditRank(r){ return r.auditTop != null ? AUDIT_RANK[r.auditTop] : (r.audit.length ? 4 : 5); }
function sortVal(r, col){
  if (col === 'audit') return auditRank(r);
  if (col === 'ci'){ return {failing:0, running:1, none:2, green:3}[r.ci]; }
  return r[col];
}
function sortRecs(recs){ const {col, dir} = state.sort, m = dir === 'asc' ? 1 : -1;
  return recs.slice().sort((a, b) => { const x = sortVal(a, col), y = sortVal(b, col);
    return typeof x === 'string' ? m*x.localeCompare(y) : m*(x - y); }); }

function tableHtml(recs, sortable){
  const head = COLS.map(([k, l]) => {
    const s = sortable && SORTABLE[k], cur = state.sort.col === k;
    const arrow = cur ? (state.sort.dir === 'asc' ? ' &uarr;' : ' &darr;') : '';
    return s ? '<th class="sortable'+(cur?' active':'')+'" data-col="'+k+'" title="Sort by '+k+'">'+l+arrow+'</th>' : '<th>'+l+'</th>';
  }).join('');
  return '<div class="scroll"><table><thead><tr>'+head+'</tr></thead><tbody>'+recs.map(rowHtml).join('')+'</tbody></table></div>';
}
function emptyState(msg){ return '<div class="empty">'+(msg||'No pull requests match these filters.')+' <button class="linkish" data-reset>Clear filters</button></div>'; }

function renderQueue(recs){
  const out = BUCKETS.map(([b, title]) => {
    const g = recs.filter(r => r.bucket === b); if (!g.length) return '';
    const sorted = b === 'review' ? g.slice().sort((a, b2) => b2.age - a.age) : g.slice().sort((a, b2) => b2.idle - a.idle);
    return '<section><div class="sec-h"><h2>'+title+'</h2><span class="n">'+g.length+'</span></div>'+tableHtml(sorted, false)+'</section>';
  }).join('');
  return out || emptyState();
}
function renderAll(recs){ return recs.length ? '<section>'+tableHtml(sortRecs(recs), true)+'</section>' : emptyState(); }
function renderFidelity(recs){
  const byProblem = {};
  recs.forEach(r => r.audit.forEach(a => { (byProblem[a.n] || (byProblem[a.n] = {n:a.n, cls:a.cls, status:a.status, note:a.note, href:a.href, prs:[]})).prs.push(r); }));
  const probs = Object.values(byProblem);
  if (!probs.length) return emptyState('No audited Erdős-problem PRs match.');
  const sel = state.facets.audit;  // in this view the audit facet selects problem groups directly
  const groups = AUDIT_ORDER.map(s => [s, probs.filter(p => p.status === s).sort((a, b) => a.n - b.n)])
    .filter(g => g[1].length && (!sel.size || sel.has(g[0])));
  return groups.map(([s, ps]) => '<section><div class="sec-h"><h2>'+FID_TITLE[s]+'</h2><span class="n">'+ps.length+'</span></div>'
    + '<div class="scroll"><table><thead><tr><th>problem</th><th>audit</th><th>open PRs</th></tr></thead><tbody>'
    + ps.map(p => '<tr><td class="num"><a href="'+p.href+'">#'+p.n+'</a></td>'
        + '<td><span class="ab '+p.cls+'" title="#'+p.n+': '+esc(p.note)+'">'+AUDIT_LABEL[p.status]+'</span></td>'
        + '<td>'+p.prs.map(r => '<a class="prlink" href="https://github.com/'+META.repo+'/pull/'+r.n+'" title="'+esc(r.title)+'">#'+r.n+'</a>').join('')+'</td></tr>').join('')
    + '</tbody></table></div></section>').join('');
}

function statHtml(v, l, cls){ return '<div class="stat"><span class="sv '+(cls||'')+'">'+v+'</span> <span class="sl">'+l+'</span></div>'; }
function renderStrip(){
  const review = DATA.filter(r => r.bucket === 'review');
  const stmt = review.filter(r => r.kind === 'statement').length;
  const oldest = review.reduce((m, r) => Math.max(m, r.age), 0);
  let html = '<div class="grp">'+statHtml(DATA.length,'open')+statHtml(review.length,'ready to review')+statHtml(stmt,'statements')+statHtml(oldest+'d','oldest waiting')+'</div>';
  if (META.hasAudit){
    const top = DATA.filter(r => r.bucket === 'review' || r.bucket === 'approved').map(r => r.auditTop);
    const c = k => top.filter(x => x === k).length;
    html += '<div class="grp grp--audit">'+statHtml(c('ab--signed'),'signed faithful','sv--gold')
      + statHtml(c('ab--conditional')+c('ab--variant'),'conditional','sv--brass')
      + statHtml(c('ab--discrepancy'),'flagged','sv--cinnabar')+'</div>';
  }
  el('strip').innerHTML = html;
}

function render(){
  const recs = DATA.filter(matches);
  countEl.textContent = recs.length === DATA.length ? DATA.length+' PRs' : recs.length+' of '+DATA.length+' PRs';
  app.innerHTML = state.view === 'queue' ? renderQueue(recs) : state.view === 'fidelity' ? renderFidelity(recs) : renderAll(recs);
  app.querySelectorAll('th.sortable').forEach(th => th.addEventListener('click', () => {
    const c = th.dataset.col;
    if (state.sort.col === c) state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
    else { state.sort.col = c; state.sort.dir = c === 'author' ? 'asc' : 'desc'; }
    syncUrl(); render();
  }));
  app.querySelectorAll('[data-reset]').forEach(b => b.addEventListener('click', resetAll));
}
function updateTabs(){ tabsEl.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.view === state.view)); }
function updateChips(){ facetsEl.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', state.facets[c.dataset.group].has(c.dataset.val))); }

function buildToolbar(){
  tabsEl.innerHTML = [['queue','Queue'],['all','All PRs'],['fidelity','Fidelity']]
    .map(([k, l]) => '<button class="tab" role="tab" data-view="'+k+'">'+l+'</button>').join('');
  tabsEl.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => { state.view = b.dataset.view; syncUrl(); updateTabs(); render(); }));
  facetsEl.innerHTML = FACETS.filter(f => f.group !== 'audit' || META.hasAudit).map(f =>
    '<div class="facet"><span class="facet-l">'+f.label+'</span>'
    + f.opts.map(o => '<button class="chip" data-group="'+f.group+'" data-val="'+o+'">'+o+'</button>').join('')+'</div>').join('');
  facetsEl.querySelectorAll('.chip').forEach(c => c.addEventListener('click', () => {
    const set = state.facets[c.dataset.group]; const v = c.dataset.val;
    set.has(v) ? set.delete(v) : set.add(v); syncUrl(); updateChips(); render();
  }));
  searchEl.addEventListener('input', () => { state.q = searchEl.value.trim(); syncUrl(); render(); });
}
function resetAll(){ state.q = ''; searchEl.value = '';
  state.facets = {audit:new Set(), kind:new Set(), ci:new Set()}; syncUrl(); updateChips(); render(); }

function syncUrl(){
  const p = new URLSearchParams();
  if (state.view !== 'queue') p.set('view', state.view);
  if (state.q) p.set('q', state.q);
  ['audit','kind','ci'].forEach(g => { if (state.facets[g].size) p.set(g, [...state.facets[g]].join(',')); });
  if (state.view !== 'queue') p.set('sort', state.sort.col+':'+state.sort.dir);
  const h = p.toString();
  history.replaceState(null, '', h ? '#'+h : location.pathname + location.search);
}
function loadUrl(){
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get('view')) state.view = p.get('view');
  if (p.get('q')){ state.q = p.get('q'); searchEl.value = state.q; }
  ['audit','kind','ci'].forEach(g => { if (p.get(g)) state.facets[g] = new Set(p.get(g).split(',')); });
  if (p.get('sort')){ const s = p.get('sort').split(':'); state.sort = {col:s[0], dir:s[1] || 'desc'}; }
}

renderStrip();
buildToolbar();
loadUrl();
updateTabs();
updateChips();
render();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
