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
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = "google-deepmind/formal-conjectures"
BASE = "main"
STATEMENT_DIRS = ("ErdosProblems/", "Paper/", "Arxiv/", "Books/", "Wikipedia/",
                  "OEIS/", "OptimizationConstants/", "GreensOpenProblems/")

# The audit feed. Configurable so the board stays a neutral tool: point it at
# any compatible verdicts.json, or drop the column by pointing it at an empty
# feed.
COLLECTION_LABELS = {
    "erdos-problems": "Erdős", "oeis": "OEIS", "wikipedia": "Wikipedia",
    "arxiv": "arXiv", "paper": "papers", "Books": "books",
    "green-problems": "Green", "kourovka": "Kourovka",
    "written-on-the-wall": "WOWII", "open-quantum-problems": "quantum",
    "millenium-problems": "millennium", "HilbertProblems": "Hilbert",
    "mathoverflow": "MathOverflow",
}

VERDICTS_URL = os.environ.get("VERDICTS_URL", "")
# Where a per-problem finding lives, for the audit chips. Derived from the feed
# so nothing is hardcoded to one provider.
AUDIT_SITE = VERDICTS_URL.rsplit("/", 1)[0] if VERDICTS_URL else ""
FINDING_URL = (AUDIT_SITE + "/finding.html?n={n}") if AUDIT_SITE else "{n}"
ERDOS_URL = "https://www.erdosproblems.com/{n}"
ERDOS_FILE_RE = re.compile(r"ErdosProblems/(\d+)\.lean")

# Provenance pointers, present only when an audit feed is configured.
FRONTIER_URL = AUDIT_SITE
METHOD_URL = (AUDIT_SITE + "/method.html") if AUDIT_SITE else ""
FC_REPO_URL = f"https://github.com/{REPO}"
FC_SITE_URL = "https://google-deepmind.github.io/formal-conjectures"
BOARD_REPO_URL = "https://github.com/williamjblair/open-formal-workflows"
BOARD_SITE_URL = "https://williamjblair.github.io/open-formal-workflows/"

# --- data -----------------------------------------------------------------
# PR state comes from queueboard, the same tool mathlib's review dashboard is
# built on. Its pipeline writes api/snapshot.json: a versioned
# {meta, lists, prs} document with each PR's classified status, CI state,
# labels, diff size and the cumulative time it has actually spent on the review
# queue. Consuming that means the fragile parts (paginating the GitHub API,
# parsing check rollups, deciding what "awaiting review" means) are maintained
# upstream rather than here.
#
# Three things queueboard does not carry are fetched separately: createdAt,
# whether the PR has a merge conflict, and when its checks last ran. That last
# one matters because a passing tick says nothing about the current main: 111
# of the open PRs import a module deleted in July and still show green, because
# their checks ran before the deletion. mergeStateStatus is computed on demand
# by GitHub, so this stays on small pages: 50 returns truncated responses
# under load and 100 502s outright.

SNAPSHOT = HERE / "snapshot.json"
BASICS = HERE / "pr_basics.json"
PR_AUDITS = HERE / "pr_audits.json"


def _unwrap(v):
    """queueboard tags some values as {__type__, __value__}; take the value."""
    return v.get("__value__") if isinstance(v, dict) and "__value__" in v else v


BUCKET = {"AwaitingReview": "review", "AwaitingAuthor": "author", "NotReady": "draft"}
CI = {"pass": "green", "fail": "failing"}


def load_snapshot() -> dict:
    if not SNAPSHOT.exists():
        raise SystemExit(f"{SNAPSHOT.name} not found. Run ./sync.sh first.")
    snap = json.loads(SNAPSHOT.read_text())
    if not snap.get("prs"):
        raise SystemExit("snapshot contains no PRs - refusing to write an empty board")
    return snap


def load_basics() -> dict[int, dict]:
    """`createdAt` and merge-conflict state, which the snapshot does not carry.

    sync.sh lifts these out of the per-PR data queueboard already downloaded. It
    used to be a second pass over the GitHub API here, which cost more than
    everything else in this script put together."""
    if not BASICS.exists():
        return {}
    return {int(k): v for k, v in json.loads(BASICS.read_text()).items()}


ISSUES = HERE / "issues.json"
BASE_PATHS = HERE / "base_paths.txt"


def main_paths() -> set[str]:
    """Every path on the base branch, written by sync.sh. Absent is fine: the supersession
    prompt just does not appear."""
    if not BASE_PATHS.exists():
        return set()
    return set(BASE_PATHS.read_text().split())
def load_issues(claimed: dict[int, list[int]] | None = None,
                base: set[str] | None = None) -> list[dict]:
    """Open issues, for the picking-something-up view. Written by sync.sh; absent is fine,
    the view just does not appear."""
    if not ISSUES.exists() or not ISSUES.read_text().strip():
        return []
    out = []
    for it in json.loads(ISSUES.read_text()):
        labels = [l["name"] for l in it.get("labels") or []]
        out.append({
            "n": it["number"],
            "title": it["title"],
            "labels": labels,
            # The template has the author tick either "I plan on working on this" or "up for
            # grabs". Going by labels alone lists conjectures their author has claimed.
            "ready": ("new conjecture" in labels and "needs-prerequisites" not in labels
                      and it.get("upForGrabs", True)),
            "ams": next((l.split(":")[0].replace("ams-", "AMS ").strip()
                         for l in labels if l.startswith("ams-")), ""),
            "age": days_since(it["createdAt"], datetime.now(timezone.utc)),
            "prs": sorted((claimed or {}).get(it["number"], [])),
            "have": already_stated(it["title"], base or set()),
        })
    return out


ERDOS_TITLE_RE = re.compile(r"Erd[őo]s Problem (\d+)")


def already_stated(title: str, base: set[str]) -> str:
    """The file already on the base branch that this issue asks for, if any.

    Only exact for issues titled `Erdős Problem N`, which is 279 of the 444 unclaimed ones.
    An issue stays open after the conjecture lands, so without this the list sends people to
    write something the repository already has.
    """
    m = ERDOS_TITLE_RE.search(title)
    if not m:
        return ""
    path = f"FormalConjectures/ErdosProblems/{m.group(1)}.lean"
    return path if path in base else ""


CLOSES_RE = re.compile(r"\b(?:closes|fixes|resolves|close|fix|resolve)\s+#(\d+)", re.I)


def claims(snapshot: dict) -> dict[int, list[int]]:
    """Issue number -> the open PRs saying they close it.

    The site knows what problems exist and GitHub knows what is in flight; nobody joins the
    two, so a conjecture with an open PR against it looks exactly as unclaimed as one without.
    That is how the same problem gets formalised twice.
    """
    out: dict[int, list[int]] = {}
    for num, pr in (snapshot.get("prs") or {}).items():
        for issue in set(CLOSES_RE.findall(pr.get("description") or "")):
            out.setdefault(int(issue), []).append(int(num))
    return out


def load_verdicts() -> dict[int, dict]:
    """Index the audit feed by problem number. Prefer a local verdicts.json
    (the Action curls it, tests drop it in); otherwise fetch the live feed."""
    cache = HERE / "verdicts.json"
    url = VERDICTS_URL
    if cache.exists():
        data = json.loads(cache.read_text())
    elif url:
        with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310
            data = json.loads(r.read().decode())
    else:
        return {}
    rows = data.get("rows", []) if isinstance(data, dict) else data
    return {r["problem"]: r for r in rows if "problem" in r}


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key in audit feed: {key}")
        out[key] = value
    return out


def load_pr_audits() -> dict[int, dict]:
    """Load the exact per-PR advisory projection when it is present."""
    if not PR_AUDITS.exists():
        return {}
    from fc_pr_audit import validate_projection
    data = json.loads(PR_AUDITS.read_text(), object_pairs_hook=_unique_pairs)
    validate_projection(data)
    return {row["pull_request"]["number"]: row for row in data["rows"]}


def load_pilot() -> dict | None:
    """Load the validated one-case pilot projection when its report is present.

    The scheduled build creates the report from the pinned audit source and a
    fresh GitHub observation. Component byte drift or a filled maintainer
    disposition fails the build instead of being rendered.
    """
    from pilot import load_pilot_bundle

    return load_pilot_bundle()


# --- classification -------------------------------------------------------
# Buckets, CI state and idle time are queueboard's, not ours. What stays here
# is the FC-specific reading: whether a PR touches a statement file, and how
# long it has been waiting.

def ci_state(pr: dict) -> str:
    return CI.get(_unwrap(pr.get("ci_status")), "none")


def maybe_superseded(basic: dict, main_paths: set[str]) -> bool:
    """Every file this PR adds is already on the base branch, so the work may have landed
    another way.

    A prompt, not a verdict. "Adds" here means "no deletions", which is as close as the data
    gets; a PR that only appends to an existing file looks the same. The file cap keeps out
    branches with an ancient base, which report hundreds of files and would otherwise all
    match."""
    added = basic.get("addedFiles") or []
    return 0 < len(added) <= 5 and all(f in main_paths for f in added)


def is_statement(pr: dict) -> bool:
    return any(p.startswith("FormalConjectures/") and any(d in p for d in STATEMENT_DIRS)
               for p in pr.get("modified_files") or [])


def approvals(pr: dict) -> int:
    return len(pr.get("approvals") or [])


# Changes on `main` that break branches predating them. "CI is N days old" is a proxy for
# this; naming the change is sharper, since it separates a branch that is merely old from one
# whose tick was earned against a `main` that no longer exists. Add an entry when you land
# something that breaks existing branches.
BREAKING_CHANGES = [
    ("2026-07-17T00:00:00Z",
     "FormalConjectures.Util.ProblemImports was deleted (#4433); "
     "these branches need `import FormalConjecturesUtil` and a rebase"),
    ("2026-08-02T16:22:00Z",
     "the openClassical linter was switched on (#4671); a branch adding "
     "`open Classical` now fails under --wfail"),
]


def stale_reason(ran: str | None) -> str | None:
    """The most recent breaking change on `main` that this PR's checks predate."""
    if not ran:
        return None
    for when, what in sorted(BREAKING_CHANGES, reverse=True):
        if ran < when:
            return what
    return None


def ci_ran_at(basic: dict) -> str | None:
    """When this PR's checks last completed."""
    try:
        return (basic["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
                ["contexts"]["nodes"][0]["completedAt"])
    except (KeyError, IndexError, TypeError):
        return None


def has_conflict(pr: dict, basic: dict) -> bool:
    return (basic.get("mergeStateStatus") or "").upper() == "DIRTY"


def days_since(iso: str, now: datetime) -> int:
    return (now - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days


def queue_days(pr: dict) -> int | None:
    """Time actually spent on the review queue, excluding spells where the ball
    was in the author's court. None when queueboard could not reconstruct it."""
    t = pr.get("total_queue_time") or {}
    if t.get("status") != "valid" or not t.get("value_td"):
        return None
    return round(t["value_td"] / 86400)


def idle_days(pr: dict) -> int | None:
    """Days since the PR's status last changed."""
    lsc = pr.get("last_status_change") or {}
    if lsc.get("status") != "valid":
        return None
    d = lsc.get("delta") or {}
    return round(d.get("months", 0) * 30 + d.get("days", 0) + d.get("hours", 0) / 24)


def classify(pr: dict, approved: set[int], number: int) -> str:
    if number in approved:
        return "approved"
    return BUCKET.get(_unwrap(pr.get("pr_status")), "draft")



# --- audit join -----------------------------------------------------------

def problem_numbers(pr: dict) -> list[int]:
    nums = set()
    for path in pr.get("modified_files") or []:
        m = ERDOS_FILE_RE.search(path)
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
        return "ab--conditional", "conditional" + (f": assumes {asm}" if asm else "")
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


def build_record(number: int, pr: dict, basic: dict, verdicts: dict[int, dict],
                 pr_audits: dict[int, dict],
                 approved: set[int], now: datetime, on_main: set[str]) -> dict:
    audit = []
    for n in problem_numbers(pr):
        row = verdicts.get(n)
        cls, note = audit_class(row)
        href = ERDOS_URL.format(n=n) if row is None else FINDING_URL.format(n=n)
        audit.append({"n": n, "cls": cls, "status": STATUS_KEY[cls],
                      "note": note, "href": href})
    ci = ci_state(pr)
    created = basic.get("createdAt")
    # Prefer time on the queue; fall back to age when queueboard could not
    # reconstruct the timeline (PRs synced with the reduced query).
    waiting = queue_days(pr)
    age = days_since(created, now) if created else (waiting or 0)
    idle = idle_days(pr)
    return {
        "n": number,
        "title": pr.get("title") or "",
        "author": pr.get("author") or "ghost",
        "kind": "statement" if is_statement(pr) else "infra",
        "coll": sorted({COLLECTION_LABELS[l["name"]] for l in (pr.get("labels") or [])
                        if l["name"] in COLLECTION_LABELS}),
        "bucket": classify(pr, approved, number),
        "ci": ci,
        "ciPending": (not pr.get("is_draft")) and ci == "none",
        "conflict": has_conflict(pr, basic),
        "age": age,
        "waiting": waiting,
        "idle": idle if idle is not None else age,
        "appr": approvals(pr),
        "who": sorted(pr.get("assignees") or []),
        "ciAge": (days_since(ran, now) if (ran := ci_ran_at(basic)) else None),
        "staleWhy": stale_reason(basic.get("headDate")) or "",
        "onMain": maybe_superseded(basic, on_main),
        "churn": (pr.get("additions") or 0) + (pr.get("deletions") or 0),
        "audit": audit,
        "auditTop": pr_top_status(audit),
        "auditStatuses": sorted({a["status"] for a in audit}),
        "prAudit": pr_audits.get(number),
    }


def main() -> None:
    snap = load_snapshot()
    basics = load_basics()
    verdicts = load_verdicts()
    pr_audits = load_pr_audits()
    pilot_bundle = load_pilot()
    approved = set(snap.get("lists", {}).get("dashboards", {}).get("Approved") or [])
    now = datetime.now(timezone.utc)
    on_main = main_paths()
    issues = load_issues(claims(snap), on_main)
    records = [build_record(int(num), pr, basics.get(int(num), {}), verdicts, pr_audits,
                            approved, now,
                            on_main)
               for num, pr in snap["prs"].items()]
    records.sort(key=lambda r: -(r["waiting"] if r["waiting"] is not None else r["age"]))
    joined_pr_audits = [record for record in records if record["prAudit"] is not None]
    meta = {
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "repo": REPO, "hasAudit": bool(verdicts),
        "hasPrAudit": bool(joined_pr_audits), "hasPrAuditFeed": bool(pr_audits),
        "hasIssues": bool(issues), "hasPilot": pilot_bundle is not None,
    }
    data = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    doc = (TEMPLATE
           .replace("__DATA__", data)
           .replace("__PR_AUDITS__", json.dumps(list(pr_audits.values()), ensure_ascii=False)
                    .replace("</", "<\\/"))
           .replace("__PILOT__", json.dumps(pilot_bundle, ensure_ascii=False)
                    .replace("</", "<\\/"))
           .replace("__ISSUES__", json.dumps(issues, ensure_ascii=False).replace("</", "<\\/"))
           .replace("__META__", json.dumps(meta).replace("</", "<\\/"))
           .replace("__STAMP__", meta["generated"])
           .replace("__FC_REPO__", FC_REPO_URL)
           .replace("__FC_SITE__", FC_SITE_URL)
           .replace("__BOARD_REPO__", BOARD_REPO_URL)
           .replace("__BOARD_SITE__", BOARD_SITE_URL)
           .replace("__METHOD__", METHOD_URL)
           .replace("__FRONTIER__", FRONTIER_URL)
           .replace("__PR_AUDIT_NOTE__", (
               '<p><strong>The PR audit column</strong> is a deterministic projection of '
               'the exact source-local FC audit records. Its labels are advisory evidence, '
               'not approval, merge readiness, mathematical truth, or Repository authority.</p>'
               if pr_audits else "")))
    if not verdicts:
        doc = re.sub(r"\s*<p><strong>The audit column</strong>.*?</p>", "", doc, flags=re.S)
        doc = re.sub(r"\s*<p>PR data via the GitHub API\..*?</p>",
                     "\n  <p>PR data via the GitHub API. PR state, timings and CI classification "
                     "via <a href=\"https://github.com/leanprover-community/queueboard-core\">"
                     "queueboard</a>, the tool mathlib's review dashboard is built on. "
                     "An independent tool, not affiliated with the formal-conjectures "
                     "maintainers.</p>", doc, flags=re.S)
    (HERE / "index.html").write_text(doc)
    review = [r for r in records if r["bucket"] == "review"]
    longest = max((r["waiting"] or r["age"] for r in review), default=0)
    print(f"wrote index.html - {len(records)} PRs, {len(review)} ready for "
          f"review ({sum(1 for r in review if r['kind'] == 'statement')} "
          f"statements), longest waiting {longest}d")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Open Formal Workflows | Formal Conjectures Review, Verification &amp; Preservation</title>
<meta name="application-name" content="Open Formal Workflows">
<meta name="description" content="Formal Conjectures review, verification, and preservation pilot. Advisory evidence only; Formal Conjectures retains authority.">
<link rel="canonical" href="__BOARD_SITE__">
<meta property="og:title" content="Open Formal Workflows | Formal Conjectures Review, Verification &amp; Preservation">
<meta property="og:description" content="A bounded advisory evidence pilot for Formal Conjectures review, verification, and preservation.">
<meta property="og:url" content="__BOARD_SITE__">
<style>
:root {
  /* Restrained evidence palette: cool paper, one blue link accent, and semantic
     colors reserved for typed outcomes and freshness. */
  --paper: oklch(97.6% 0.006 238); --panel: oklch(94.1% 0.009 242); --card: oklch(99.2% 0.003 238);
  --ink0: oklch(19% 0.024 258); --ink1: oklch(35% 0.022 254); --ink2: oklch(52% 0.016 250);
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
    /* The same evidence hierarchy in low ambient light. */
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
[hidden] { display: none !important; }
body { margin: 0; background: var(--paper); color: var(--ink0);
  font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased; }
.wrap { container-type: inline-size; max-width: 1216px; margin: 0 auto; padding: 26px 28px 72px; }
a { color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
main:focus { outline: none; }

.topbar { display: flex; align-items: center; justify-content: space-between; gap: 24px;
  padding-bottom: 19px; border-bottom: 1px solid var(--rule); }
h1 { display: flex; align-items: baseline; gap: 12px; margin: 0; }
h1 .product-name { font-size: 19px; font-weight: 700; letter-spacing: -.018em; }
h1 .h1-sub { color: var(--ink2); font-size: 12px; font-weight: 520; letter-spacing: .015em; }
.source-nav { display: flex; align-items: center; gap: 15px; color: var(--ink2); font-size: 12px; }
.source-nav a { color: var(--ink1); text-decoration: none; }
.source-nav a:hover { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }
.updated { white-space: nowrap; }
.boundary { display: flex; align-items: center; gap: 9px 12px; min-height: 38px;
  padding: 9px 0; border-bottom: 1px solid var(--rule); color: var(--ink2); font-size: 12px; }
.boundary-tag { flex: 0 0 auto; color: var(--ink0); font-size: 10px; font-weight: 760;
  letter-spacing: .075em; text-transform: uppercase; }
.boundary-text { max-width: 82ch; }
.boundary-link { margin-left: auto; padding: 3px 0; border: 0; background: none; color: var(--accent);
  font: inherit; cursor: pointer; white-space: nowrap; text-decoration: underline; text-underline-offset: 3px; }
.boundary-link:hover { color: var(--ink0); }

.appnav { display: flex; align-items: center; justify-content: space-between; gap: 14px;
  padding: 9px 0 0; border-bottom: 1px solid var(--rule2); }
.tabs { display: flex; gap: 4px; }
.tab { position: relative; padding: 9px 11px 10px; border: 0; background: none; color: var(--ink2);
  font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap; }
.tab::after { content: ""; position: absolute; left: 11px; right: 11px; bottom: -1px; height: 2px;
  background: transparent; }
.tab:hover { color: var(--ink0); }
.tab.active { color: var(--ink0); font-weight: 680; }
.tab.active::after { background: var(--accent); }
.view-more { position: relative; }
.view-more summary { list-style: none; padding: 8px 2px 10px; color: var(--ink2); font-size: 13px;
  cursor: pointer; }
.view-more summary::-webkit-details-marker { display: none; }
.view-more summary::after { content: "⌄"; margin-left: 6px; color: var(--ink2); }
.view-more[open] summary, .view-more.is-active summary { color: var(--ink0); }
.more-menu { position: absolute; z-index: 30; right: 0; top: calc(100% + 7px); width: 210px;
  padding: 6px; border: 1px solid var(--rule2); border-radius: 9px; background: var(--card);
  box-shadow: 0 12px 30px color-mix(in oklab, var(--ink0) 16%, transparent); }
.more-tab { display: block; width: 100%; padding: 8px 9px; border: 0; border-radius: 6px;
  background: none; color: var(--ink1); font: inherit; font-size: 13px; text-align: left; cursor: pointer; }
.more-tab:hover, .more-tab.active { color: var(--ink0); background: var(--panel); }

/* Overview: a slim typographic row, not a filled card. */
.strip { display: flex; flex-wrap: wrap; align-items: baseline; gap: 9px 22px;
  padding: 2px 0 18px; margin: 4px 0 0; }
.grp { display: flex; flex-wrap: wrap; gap: 9px 20px; align-items: baseline; }
.grp--audit { position: relative; padding-left: 24px; }
.grp--audit::before { content: ""; position: absolute; left: 0; top: 3px; bottom: 3px;
  width: 1px; background: var(--rule2); }
.stat { display: flex; align-items: baseline; gap: 6px; }
.stat--go { border: 0; background: none; padding: 2px 7px; margin: -2px -7px; border-radius: 5px;
  font: inherit; cursor: pointer; }
.stat--go:hover { background: var(--rule); }
.stat--go.is-on { background: var(--rule); box-shadow: inset 0 0 0 1px var(--rule2); }
.stat--go:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.sv { font-size: 18px; font-weight: 660; font-variant-numeric: tabular-nums;
  letter-spacing: -.01em; color: var(--ink0); }
.sl { font-size: 12.5px; color: var(--ink2); }
.sv--gold { color: var(--gold-ink); } .sv--brass { color: var(--brass); } .sv--cinnabar { color: var(--cinnabar); }

/* Queue controls stay close to the list and disappear from the case review. */
.controls { position: sticky; top: 0; z-index: 5; background: color-mix(in oklab, var(--paper) 96%, transparent);
  padding: 10px 0; margin-bottom: 4px; border-bottom: 1px solid var(--rule); }
.controls-row { display: flex; align-items: center; gap: 10px 14px; flex-wrap: wrap; }
.controls-row + .controls-row { margin-top: 11px; }
.spacer { margin-left: auto; }
.search { position: relative; display: flex; align-items: center; }
.search .s-icon { position: absolute; left: 10px; width: 14px; height: 14px;
  fill: var(--ink2); pointer-events: none; }
.search input { font: inherit; font-size: 13px; padding: 6px 11px 6px 30px; width: 230px; max-width: 62vw;
  background: var(--card); color: var(--ink0); border: 1px solid var(--rule2); border-radius: 8px; }
.search input::placeholder { color: var(--ink2); }
.filterbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.fdd { position: relative; }
.fbtn { display: inline-flex; align-items: center; gap: 5px; font: inherit; font-size: 13px;
  padding: 5px 11px; border-radius: 8px; border: 1px solid var(--rule2); background: var(--card);
  color: var(--ink1); cursor: pointer; transition: all .12s ease; }
.fbtn:hover { border-color: var(--ink2); color: var(--ink0); }
.fbtn.active { color: var(--accent); border-color: color-mix(in oklab, var(--accent) 42%, transparent);
  background: color-mix(in oklab, var(--accent) 10%, transparent); }
.fbtn-n { font-variant-numeric: tabular-nums; font-weight: 660; }
.fbtn svg { opacity: .55; transition: transform .12s ease; }
.fdd.open .fbtn svg { transform: rotate(180deg); }
.fmenu { position: absolute; top: calc(100% + 5px); left: 0; z-index: 20; min-width: 172px;
  background: var(--card); border: 1px solid var(--rule2); border-radius: 10px; padding: 5px;
  box-shadow: 0 8px 24px color-mix(in oklab, var(--ink0) 18%, transparent); }
.fopt { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px;
  font-size: 13px; color: var(--ink1); cursor: pointer; text-transform: capitalize; }
.fopt:hover { background: color-mix(in oklab, var(--hover) 6%, transparent); }
.fopt input { accent-color: var(--accent); margin: 0; cursor: pointer; }
.clear-btn { font: inherit; font-size: 12.5px; color: var(--ink2); background: none; border: 0;
  cursor: pointer; padding: 5px 4px; }
.clear-btn:hover { color: var(--accent); text-decoration: underline; }
.cdot { width: 8px; height: 8px; border-radius: 3px; display: inline-block; border: 1px solid transparent; }
.cdot--moss { background: color-mix(in oklab, var(--moss) 55%, transparent); }
.cdot--brass { background: color-mix(in oklab, var(--brass) 60%, transparent); }
.cdot--stone { background: color-mix(in oklab, var(--stone) 42%, transparent); }
.cdot--gold { background: var(--gold-glow); border-color: color-mix(in oklab, var(--gold) 55%, transparent); }
.cdot--cinnabar { background: color-mix(in oklab, var(--cinnabar) 45%, transparent); }
.count { font-size: 12.5px; color: var(--ink2); font-variant-numeric: tabular-nums; white-space: nowrap; }
.caret { vertical-align: middle; margin-left: 3px; }
.caret.up { transform: rotate(180deg); }

section { margin: 22px 0; }
.view-header { display: flex; align-items: end; justify-content: space-between; gap: 28px;
  padding: 30px 0 18px; }
.view-header h2 { margin: 0; font-size: 25px; letter-spacing: -.022em; }
.view-header p:not(.eyebrow) { max-width: 62ch; margin: 6px 0 0; color: var(--ink1); }
.view-summary { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px 18px;
  color: var(--ink2); font-size: 12px; }
.view-summary strong { color: var(--ink0); font-size: 15px; font-variant-numeric: tabular-nums; }
.sec-h { display: flex; align-items: baseline; gap: 8px; margin: 0 0 9px; }
.sec-h h2 { font-size: 14px; font-weight: 640; margin: 0; letter-spacing: -.005em; }
.sec-h .n { font-size: 12px; color: var(--ink2); font-weight: 500; font-variant-numeric: tabular-nums; }
.scroll { overflow-x: auto; border: 1px solid var(--rule); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; background: var(--card); }
th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--ink2); font-weight: 640; padding: 9px 12px; background: var(--panel);
  border-bottom: 1px solid var(--rule); white-space: nowrap; }
th.sortable { user-select: none; }
th.sortable:hover { color: var(--ink1); }
th.active { color: var(--ink0); }
.sorter { display: inline-flex; align-items: center; gap: 2px; padding: 0; border: 0;
  background: none; color: inherit; font: inherit; letter-spacing: inherit; text-transform: inherit;
  cursor: pointer; }
.sorter:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
td { padding: 9px 12px; border-bottom: 1px solid var(--rule); font-size: 14px; }
tr:last-child td { border-bottom: 0; }
tbody tr { transition: background .12s ease; }
tbody tr:hover { background: color-mix(in oklab, var(--hover) 4%, transparent); }
.mobile-pr-list { display: none; }
.queue-primary { margin-top: 8px; }
.queue-secondary { margin-top: 28px; border-top: 1px solid var(--rule2); }
.queue-group { border-bottom: 1px solid var(--rule2); }
.queue-group > summary { display: flex; align-items: baseline; gap: 9px; padding: 14px 0;
  cursor: pointer; list-style: none; }
.queue-group > summary::-webkit-details-marker { display: none; }
.queue-group > summary::after { content: "+"; margin-left: auto; color: var(--ink2); font-size: 17px; }
.queue-group[open] > summary::after { content: "−"; }
.queue-group > summary strong { font-size: 13px; }
.queue-group > summary span { color: var(--ink2); font-size: 12px; }
.queue-group .data-set { padding-bottom: 18px; }
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
.pa { white-space: nowrap; }
.pa--needs_revision { color: var(--cinnabar); background: color-mix(in oklab, var(--cinnabar) 12%, transparent);
  border-color: color-mix(in oklab, var(--cinnabar) 42%, transparent); }
.pa--inconclusive { color: var(--brass); background: color-mix(in oklab, var(--brass) 14%, transparent);
  border-color: color-mix(in oklab, var(--brass) 40%, transparent); }
.pa--unavailable { color: var(--stone); background: none; border-color: var(--rule2); }
.roll { display: flex; flex-wrap: wrap; align-items: center; gap: 3px; font-size: 12px; color: var(--ink2); }
.roll b { color: var(--ink0); font-variant-numeric: tabular-nums; margin-right: 3px; }
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
.flag--rebase { background: color-mix(in oklab, var(--brass) 16%, transparent); color: var(--brass); }
.flag--ok { background: color-mix(in oklab, var(--ok) 15%, transparent); color: var(--ok); }
.flag--onmain { background: color-mix(in oklab, var(--stone) 16%, transparent); color: var(--stone); }
.empty { padding: 44px 12px; text-align: center; color: var(--ink2); font-size: 14px; }
.linkish { font: inherit; color: var(--accent); background: none; border: 0; cursor: pointer; text-decoration: underline; }
.skip { position: fixed; left: 12px; top: 8px; z-index: 10; transform: translateY(-160%);
  padding: 9px 12px; border-radius: 6px; background: var(--ink0); color: var(--card); }
.skip:focus { transform: none; }
.audit-records { border-top: 1px solid var(--rule); }
.audit-record { padding: 18px 0; border-bottom: 1px solid var(--rule); }
.audit-record-h { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; }
.audit-record-h a { color: var(--accent); text-decoration: none; }
.audit-record-h a:hover { color: var(--gold-ink); text-decoration: underline; }
.audit-record ul { margin: 12px 0; padding-left: 22px; color: var(--ink1); line-height: 1.65; }
.audit-record p { margin: 0; overflow-wrap: anywhere; text-align: left; white-space: normal; }

/* The case view answers identity, freshness, evidence, advisory result, and
   maintainer disposition before exposing implementation detail. */
.eyebrow { margin: 0 0 6px; color: var(--ink2); font-size: 10px; font-weight: 760;
  letter-spacing: .08em; text-transform: uppercase; }
.case-header { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(300px, .75fr);
  gap: 54px; padding: 36px 0 28px; border-bottom: 1px solid var(--rule2); }
.case-intro h2 { margin: 0; max-width: 30ch; font-size: 31px; line-height: 1.14;
  letter-spacing: -.028em; font-weight: 710; }
.case-intro h2 a { color: var(--ink0); text-decoration-thickness: 1px; text-underline-offset: 4px; }
.case-title { max-width: 68ch; margin: 13px 0 0; color: var(--ink1); font-size: 15px; }
.case-selection { max-width: 70ch; margin: 6px 0 0; color: var(--ink2); font-size: 13px; }
.case-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 9px 15px; margin-top: 20px; }
.case-actions a { font-size: 12.5px; font-weight: 620; text-decoration: none; }
.case-actions a:not(.primary-link) { border-bottom: 1px solid var(--rule2); }
.primary-link { padding: 7px 11px; border-radius: 7px; background: var(--ink0); color: var(--card); }
.primary-link:hover { background: var(--accent); color: var(--card); }
.review-summary { margin: 0; border-top: 1px solid var(--rule2); }
.review-summary > div { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 12px;
  padding: 12px 0; border-bottom: 1px solid var(--rule); }
.review-summary dt { color: var(--ink2); font-size: 11.5px; }
.review-summary dd { margin: 0; }
.review-summary strong { display: block; color: var(--ink0); font-size: 15px; }
.review-summary small { display: block; margin-top: 2px; color: var(--ink2); font-size: 11.5px; }
.review-summary .decision-pending strong { color: var(--brass); text-transform: capitalize; }
.state { display: inline-flex; align-items: center; gap: 6px; color: var(--ink0);
  font-size: 13px; font-weight: 680; }
.state::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--stone); }
.state--current::before { background: var(--ok); }
.state--stale::before { background: var(--bad); }
.state--open::before { background: var(--run); }

.execution-note { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 22px;
  margin: 22px 0 0; padding: 14px 16px; border: 1px solid color-mix(in oklab, var(--brass) 34%, var(--rule));
  border-radius: 9px; background: color-mix(in oklab, var(--brass) 7%, var(--card)); }
.execution-note strong { color: var(--ink0); }
.execution-note p { max-width: 74ch; margin: 0; color: var(--ink1); }
.pilot-section { margin: 34px 0 0; }
.pilot-section-h { display: flex; align-items: end; justify-content: space-between;
  gap: 18px; padding-bottom: 10px; border-bottom: 1px solid var(--rule2); }
.pilot-section-h h3 { margin: 0; font-size: 18px; letter-spacing: -.015em; }
.pilot-section-h p { max-width: 56ch; margin: 0; color: var(--ink2); font-size: 12px; text-align: right; }
.evidence-path { display: grid; grid-template-columns: repeat(5, 1fr); margin: 20px 0 28px; padding: 0;
  list-style: none; counter-reset: evidence; }
.evidence-path li { position: relative; min-width: 0; padding: 26px 18px 0 0; border-top: 1px solid var(--rule2); }
.evidence-path li::before { counter-increment: evidence; content: counter(evidence); position: absolute;
  top: -12px; left: 0; display: grid; place-items: center; width: 23px; height: 23px;
  border: 1px solid var(--rule2); border-radius: 50%; background: var(--paper); color: var(--ink2);
  font: 680 10px/1 ui-monospace, SFMono-Regular, Menlo, monospace; }
.evidence-path strong, .evidence-path small { display: block; }
.evidence-path strong { font-size: 12.5px; }
.evidence-path small { margin-top: 3px; color: var(--ink2); font-size: 11px; }
.evidence-row { display: grid; grid-template-columns: 150px minmax(260px, 1fr) 126px;
  gap: 22px; align-items: start; padding: 13px 0; border-bottom: 1px solid var(--rule); }
.evidence-name { font-weight: 650; }
.evidence-source { color: var(--ink1); }
.evidence-source small { display: block; margin-top: 3px; color: var(--ink2); }
.outcome { display: inline-flex; align-items: center; justify-self: start; gap: 7px;
  color: var(--ink1); font-size: 12px; font-weight: 700; }
.outcome::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--stone); }
.outcome--error { color: var(--cinnabar); }
.outcome--pending { color: var(--brass); }
.outcome--pass::before { background: var(--ok); }
.outcome--error::before { background: var(--bad); }
.outcome--pending::before { background: var(--run); }

.review-boundary { display: grid; grid-template-columns: 1fr 1fr; margin: 34px 0 0;
  border-top: 1px solid var(--rule2); border-bottom: 1px solid var(--rule2); }
.review-boundary > div { padding: 22px 28px 22px 0; }
.review-boundary > div + div { padding-left: 28px; border-left: 1px solid var(--rule2); }
.review-boundary h3 { margin: 0; font-size: 22px; letter-spacing: -.018em; }
.review-boundary .advisory-value { color: var(--brass); text-transform: capitalize; }
.review-boundary p:not(.eyebrow) { max-width: 52ch; margin: 7px 0 0; color: var(--ink1); }
.review-boundary small { display: block; margin-top: 8px; color: var(--ink2); }
.nonclaim-disclosure { margin-top: 14px; }
.nonclaim-disclosure summary { color: var(--accent); font-size: 12px; cursor: pointer; }
.nonclaims { margin: 10px 0 0; padding-left: 18px; color: var(--ink1); font-size: 12px; }
.nonclaims li { margin: 5px 0; }

.disclosure-stack { margin-top: 34px; border-top: 1px solid var(--rule2); }
.disclosure { border-bottom: 1px solid var(--rule2); }
.disclosure > summary { display: flex; align-items: baseline; justify-content: space-between; gap: 18px;
  padding: 16px 0; cursor: pointer; list-style: none; }
.disclosure > summary::-webkit-details-marker { display: none; }
.disclosure > summary::after { content: "+"; margin-left: auto; color: var(--ink2); font-size: 18px; }
.disclosure[open] > summary::after { content: "−"; }
.disclosure > summary strong { font-size: 14px; }
.disclosure > summary span { color: var(--ink2); font-size: 12px; }
.disclosure-body { padding: 2px 0 24px; }
.inspection-links { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-bottom: 12px; }
.inspection-links a { color: var(--accent); font-size: 12px; text-decoration: underline; text-underline-offset: 3px; }
.fact-list { margin: 0; }
.fact { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 16px;
  padding: 9px 0; border-bottom: 1px solid var(--rule); }
.fact dt { color: var(--ink2); font-size: 11.5px; }
.fact dd { margin: 0; color: var(--ink1); font-size: 12px; overflow-wrap: anywhere; }
.fact dd a { text-decoration: none; }
.hash { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10.5px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.recurrence { display: flex; gap: 12px; align-items: flex-start; }
.recurrence p { margin: 0; color: var(--ink1); }
.recurrence small { display: block; margin-top: 3px; color: var(--ink2); }

.method-page { padding-top: 34px; }
.method-page h2 { margin: 0; max-width: 28ch; font-size: 28px; letter-spacing: -.025em; }
.method-intro { max-width: 70ch; margin: 13px 0 30px; font-size: 15px; color: var(--ink1); }
.loop { margin: 0; padding: 0; list-style: none; counter-reset: loop; }
.loop li { counter-increment: loop; display: grid; grid-template-columns: 34px minmax(0, 1fr);
  gap: 14px; padding: 17px 0; border-top: 1px solid var(--rule2); }
.loop li::before { content: counter(loop, decimal-leading-zero); color: var(--ink2);
  font: 680 12px/1.8 ui-monospace, SFMono-Regular, Menlo, monospace; }
.loop h3 { margin: 0 0 3px; font-size: 14px; }
.loop p { margin: 0; max-width: 72ch; color: var(--ink1); }
.method-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 38px; margin-top: 34px; }
.method-grid h3 { margin: 0 0 10px; font-size: 14px; }
.method-grid ul { margin: 0; padding-left: 18px; color: var(--ink1); }
.method-grid li { margin: 7px 0; }
@media (max-width: 760px) { .wrap { padding: 18px 16px 56px; } }
@container (max-width: 760px) {
  .topbar { align-items: flex-start; }
  h1 { align-items: flex-start; flex-direction: column; gap: 1px; }
  .updated { display: none; }
  .boundary { align-items: flex-start; flex-wrap: wrap; padding: 9px 0 11px; }
  .boundary-text { flex: 1 1 240px; }
  .boundary-link { margin-left: 0; }
  .appnav { align-items: stretch; }
  .tabs { display: grid; grid-template-columns: repeat(3, 1fr); flex: 1; }
  .tab { padding-inline: 7px; }
  .case-header { grid-template-columns: 1fr; gap: 28px; padding-top: 28px; }
  .case-intro h2 { font-size: 26px; }
  .execution-note { grid-template-columns: 1fr; gap: 5px; }
  .pilot-section-h { align-items: flex-start; flex-direction: column; gap: 4px; }
  .pilot-section-h p { text-align: left; }
  .evidence-path { grid-template-columns: 1fr; margin-left: 11px; }
  .evidence-path li { padding: 4px 0 18px 27px; border-top: 0; border-left: 1px solid var(--rule2); }
  .evidence-path li::before { top: 0; left: -12px; }
  .evidence-row { grid-template-columns: 1fr auto; gap: 4px 14px; }
  .evidence-source { grid-column: 1 / -1; grid-row: 2; }
  .outcome { grid-column: 2; grid-row: 1; }
  .review-boundary { grid-template-columns: 1fr; }
  .review-boundary > div { padding: 20px 0; }
  .review-boundary > div + div { padding-left: 0; border-top: 1px solid var(--rule); border-left: 0; }
  .view-header { align-items: flex-start; flex-direction: column; gap: 10px; padding-top: 24px; }
  .view-summary { justify-content: flex-start; }
  .data-set > .scroll { display: none; }
  .mobile-pr-list { display: block; border-top: 1px solid var(--rule2); }
  .pr-mobile-row { padding: 15px 0; border-bottom: 1px solid var(--rule); }
  .pr-mobile-top { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
  .pr-mobile-number { color: var(--accent); font-weight: 700; text-decoration: none; }
  .pr-mobile-ci { display: inline-flex; align-items: center; gap: 6px; color: var(--ink2);
    font-size: 11px; text-transform: capitalize; }
  .pr-mobile-title { display: block; margin-top: 5px; color: var(--ink0); font-size: 14px;
    font-weight: 640; line-height: 1.35; text-decoration: none; }
  .pr-mobile-flags { margin-top: 5px; }
  .pr-mobile-flags .flag:first-child { margin-left: 0; }
  .pr-mobile-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 5px 13px;
    margin-top: 8px; color: var(--ink2); font-size: 11.5px; }
  .controls { position: static; }
  .search { width: 100%; }
  .search input { width: 100%; max-width: none; }
  .filterbar { gap: 6px; }
  .audit-record-h { align-items: flex-start; flex-direction: column; gap: 8px; }
  .method-grid { grid-template-columns: 1fr; gap: 24px; }
  .fact { grid-template-columns: 1fr; gap: 3px; }
}

footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--rule);
  color: var(--ink2); font-size: 12px; line-height: 1.75; }
footer p { margin: 0 0 8px; max-width: 82ch; }
footer a { color: var(--ink1); text-decoration: none; border-bottom: 1px solid var(--rule2); }
footer a:hover { color: var(--accent); border-color: var(--accent); }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style></head>
<body><a class="skip" href="#app">Skip to content</a><div class="wrap">
<header class="topbar">
  <h1><span class="product-name">Open Formal Workflows</span><span class="h1-sub">Formal Conjectures review workbench</span></h1>
  <nav class="source-nav" aria-label="Source links"><span class="updated">Updated __STAMP__</span><a href="__FC_REPO__/pulls">Upstream PRs</a><a href="__BOARD_REPO__">Source</a></nav>
</header>
<div class="boundary"><strong class="boundary-tag">Advisory workspace</strong><span class="boundary-text">Formal Conjectures is canonical for declarations, PR state, CI, and maintainer decisions. Evidence here never means approval or merge acceptance.</span><button class="boundary-link" type="button" data-switch-view="method">Authority &amp; method</button></div>
<nav class="appnav" aria-label="Workspace views"><div class="tabs" id="tabs" role="tablist"></div><details class="view-more" id="viewMore"><summary id="viewMoreLabel">More</summary><div class="more-menu" id="moreViews"></div></details></nav>
<div id="strip" class="strip"></div>
<div class="controls" id="controls">
  <div class="controls-row">
    <div class="search">
      <svg class="s-icon" viewBox="0 0 256 256" aria-hidden="true"><path d="M229.66 218.34l-50.07-50.06a88.11 88.11 0 1 0-11.31 11.31l50.06 50.07a8 8 0 0 0 11.32-11.32ZM40 112a72 72 0 1 1 72 72 72.08 72.08 0 0 1-72-72Z"/></svg>
      <input id="search" type="search" placeholder="Search #, title, author" aria-label="Search pull requests">
    </div>
    <div class="filterbar" id="filterbar"></div>
    <div class="spacer"></div>
    <span class="count" id="count"></span>
  </div>
</div>
<main id="app" tabindex="-1" aria-live="polite"></main>
<noscript><p class="empty">This board needs JavaScript to filter and render.
See the open pull requests at <a href="__FC_REPO__/pulls">github.com/google-deepmind/formal-conjectures</a>.</p></noscript>
<footer>
  __PR_AUDIT_NOTE__
  <p><strong>The audit column</strong> joins each Erd&#337;s-problem PR to the public fidelity audit:
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
const PR_AUDITS = __PR_AUDITS__;
const PILOT = __PILOT__;
const ISSUES = __ISSUES__;
const META = __META__;

const AUDIT_LABEL = {signed:'signed', unconditional:'unconditional', conditional:'conditional', flagged:'flagged', unaudited:'unaudited'};
const AUDIT_ORDER = ['flagged','conditional','signed','unconditional','unaudited'];
const CLS_OF = {signed:'ab--signed', unconditional:'ab--unconditional', conditional:'ab--conditional', flagged:'ab--discrepancy', unaudited:'ab--unaudited'};
const AUDIT_DOT = {signed:'gold', unconditional:'moss', conditional:'brass', flagged:'cinnabar', unaudited:'stone'};
const CARET = '<svg width="9" height="9" viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const FID_TITLE = {flagged:'Flagged unfaithful', conditional:'Conditional: rests on an assumption', signed:'Signed faithful', unconditional:'Machine-checked unconditional', unaudited:'Not yet audited'};
const BUCKETS = [['review','Ready for review'],['author','Waiting on the author'],['approved','Approval recorded'],['draft','Draft or work in progress']];
const COLS = [['n','PR'],['title','title'],['author','author'],['kind','kind'],['prAudit','PR audit'],['audit','problem audit'],['age','open'],['waiting','waiting'],['idle','idle'],['ci','CI'],['appr','&check;'],['churn','&pm;']];
const COLUMNS = COLS.filter(c => (c[0] !== 'audit' || META.hasAudit) && (c[0] !== 'prAudit' || META.hasPrAudit));
const SORTABLE = {n:1, author:1, audit:1, age:1, waiting:1, idle:1, ci:1, appr:1, churn:1};
// Only offer collections that are actually present, so the menu reflects the
// queue rather than the repo's full label list.
const COLLECTIONS = [...new Set(DATA.flatMap(r => r.coll))].sort();
const FACETS = [
  {group:'audit', label:'Audit', opts:['signed','unconditional','conditional','flagged','unaudited']},
  {group:'kind', label:'Kind', opts:['statement','infra']},
  {group:'coll', label:'Collection', opts:COLLECTIONS},
  {group:'ci', label:'CI', opts:['passing','failing','pending','running']},
];

const DEFAULT_VIEW = META.hasPilot ? 'pilot' : 'queue';
const TAB_SPECS = [['pilot','Case review'],['queue','Review queue'],['all','All PRs'],['pick','Find a case'],['fidelity','Fidelity evidence'],['pr-audits','Evidence inventory'],['method','Method & authority']]
  .filter(v => (v[0] !== 'pilot' && v[0] !== 'method' || META.hasPilot)
            && (v[0] !== 'fidelity' || META.hasAudit)
            && (v[0] !== 'pick' || META.hasIssues)
            && (v[0] !== 'pr-audits' || META.hasPrAuditFeed));
const PRIMARY_VIEWS = new Set(['pilot','queue','all']);
const DATA_VIEWS = new Set(['queue','all','pick','fidelity']);
const FILTER_VIEWS = new Set(['queue','all','fidelity']);
const state = {view:DEFAULT_VIEW, q:'', facets:{audit:new Set(), kind:new Set(), coll:new Set(), ci:new Set()}, sort:{col:'idle', dir:'desc'}};

const el = id => document.getElementById(id);
const app = el('app'), searchEl = el('search'), filterbarEl = el('filterbar'), tabsEl = el('tabs'), countEl = el('count');
const moreViewsEl = el('moreViews'), viewMoreEl = el('viewMore'), viewMoreLabelEl = el('viewMoreLabel');
function esc(s){ const d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
function ciKey(r){ return r.ci === 'green' ? 'passing' : r.ci === 'failing' ? 'failing' : r.ci === 'running' ? 'running' : 'pending'; }

function matches(r){
  if (state.q){ const q = state.q.toLowerCase();
    if (!(('#'+r.n).includes(q) || r.title.toLowerCase().includes(q) || r.author.toLowerCase().includes(q))) return false; }
  const f = state.facets;
  if (f.audit.size && !r.auditStatuses.some(s => f.audit.has(s))) return false;
  if (f.kind.size && !f.kind.has(r.kind)) return false;
  if (f.coll.size && !r.coll.some(c => f.coll.has(c))) return false;
  if (f.ci.size && !f.ci.has(ciKey(r))) return false;
  return true;
}

function badge(a){ return '<a class="ab '+a.cls+'" href="'+a.href+'" title="#'+a.n+': '+esc(a.note)+'">'+a.n+'</a>'; }
function auditCell(r){
  if (!r.audit.length) return '<td class="audit"></td>';
  if (r.audit.length <= 4) return '<td class="audit">'+r.audit.map(badge).join('')+'</td>';
  const counts = {}; r.audit.forEach(a => counts[a.status] = (counts[a.status]||0)+1);
  const order = AUDIT_ORDER.filter(s => counts[s]);
  const chips = order.map(s => '<span class="rc '+CLS_OF[s]+'">'+counts[s]+'</span>').join('');
  const title = r.audit.length+' problems: '+order.map(s => counts[s]+' '+AUDIT_LABEL[s]).join(', ');
  return '<td class="audit"><span class="roll" title="'+title+'"><b>'+r.audit.length+'</b>'+chips+'</span></td>';
}
function prAuditCell(r){
  if (!r.prAudit) return '<td class="audit"></td>';
  const d = r.prAudit.advisory_disposition;
  return '<td class="audit"><a class="ab pa pa--'+d+'" href="'+r.prAudit.source_url+'" title="Inspect the exact advisory FC audit record; not approval or authority">'+d.replaceAll('_', ' ')+'</a></td>';
}
function flagsHtml(r){ let s = '';
  // A tick from months ago was earned against a main that has moved since.
  // Reported as an age, not as a verdict: the reviewer decides what it means.
  if (r.ciAge != null && r.ciAge >= 30) s += '<span class="flag flag--stale" title="checks last ran '
    + r.ciAge + ' days ago, against an older main">CI ' + (r.ciAge >= 60 ? Math.round(r.ciAge/30) + 'mo' : r.ciAge + 'd') + ' old</span>';
  if (r.who && r.who.length) s += '<span class="flag flag--who" title="assigned to '
    + r.who.join(', ') + '">' + esc(r.who[0]) + (r.who.length > 1 ? ' +' + (r.who.length - 1) : '') + '</span>';
  if (r.onMain) s += '<span class="flag flag--onmain" title="Every file this PR adds is already on the base branch, so the work may have landed another way. A prompt to check, not a verdict: the data cannot tell an added file from one that was only appended to.">already on main?</span>';
  if (r.staleWhy) s += '<span class="flag flag--rebase" title="'+esc(r.staleWhy)+'">needs rebase</span>';
  if (r.ciPending) s += '<span class="flag flag--ci" title="CI has not run yet (often waiting on a maintainer to approve the workflow)">CI pending</span>';
  if (r.conflict) s += '<span class="flag flag--conflict" title="Merge conflict with the base branch">conflict</span>';
  return s; }
function ciDot(r){ const m = {green:'ok', failing:'bad', running:'run', none:'na'}; return '<span class="ci ci--'+m[r.ci]+'" title="'+r.ci+'"></span>'; }
function rowHtml(r){
  const appr = r.appr ? '<span class="appr">&check;'+r.appr+'</span>' : '';
  return '<tr>'
    + '<td class="num col-n"><a href="https://github.com/'+META.repo+'/pull/'+r.n+'">#'+r.n+'</a></td>'
    + '<td class="ttl col-title"><span class="ttl-t">'+esc(r.title)+'</span>'+flagsHtml(r)+'</td>'
    + '<td class="who col-author">'+esc(r.author)+'</td>'
    + '<td class="col-kind"><span class="tag tag--'+r.kind+'">'+r.kind+'</span></td>'
    + (META.hasPrAudit ? prAuditCell(r) : '')
    + (META.hasAudit ? auditCell(r) : '')
    + '<td class="mono col-age">'+r.age+'d</td>'
    + '<td class="mono col-waiting" title="time actually spent on the review queue">'+(r.waiting == null ? '<span class="dash">&ndash;</span>' : r.waiting+'d')+'</td>'
    + '<td class="mono col-idle">'+r.idle+'d</td>'
    + '<td class="col-ci">'+ciDot(r)+'</td><td class="mono appr-c col-appr">'+appr+'</td><td class="mono col-churn">'+r.churn+'</td>'
    + '</tr>';
}

function mobileRowHtml(r){
  const waiting = r.waiting == null ? r.age+'d open' : r.waiting+'d waiting';
  const audit = r.prAudit ? '<a class="ab pa pa--'+r.prAudit.advisory_disposition+'" href="'+r.prAudit.source_url+'">'+humanize(r.prAudit.advisory_disposition)+'</a>' : '';
  return '<article class="pr-mobile-row"><div class="pr-mobile-top"><a class="pr-mobile-number" href="https://github.com/'+META.repo+'/pull/'+r.n+'">#'+r.n+'</a>'
    +'<span class="pr-mobile-ci">'+ciDot(r)+' '+esc(ciKey(r))+'</span></div>'
    +'<a class="pr-mobile-title" href="https://github.com/'+META.repo+'/pull/'+r.n+'">'+esc(r.title)+'</a>'
    +'<div class="pr-mobile-flags">'+flagsHtml(r)+'</div>'
    +'<div class="pr-mobile-meta"><span>'+esc(r.author)+'</span><span>'+waiting+'</span><span>'+r.churn+' lines</span>'+audit+'</div></article>';
}

const AUDIT_RANK = {'ab--discrepancy':0, 'ab--conditional':1, 'ab--variant':1, 'ab--signed':2, 'ab--unconditional':3};
function auditRank(r){ return r.auditTop != null ? AUDIT_RANK[r.auditTop] : (r.audit.length ? 4 : 5); }
function sortVal(r, col){
  if (col === 'audit') return auditRank(r);
  if (col === 'waiting') return r.waiting == null ? -1 : r.waiting;
  if (col === 'ci'){ return {failing:0, running:1, none:2, green:3}[r.ci]; }
  return r[col];
}
function sortRecs(recs){ const {col, dir} = state.sort, m = dir === 'asc' ? 1 : -1;
  return recs.slice().sort((a, b) => { const x = sortVal(a, col), y = sortVal(b, col);
    return typeof x === 'string' ? m*x.localeCompare(y) : m*(x - y); }); }

function tableHtml(recs, sortable){
  const head = COLUMNS.map(([k, l]) => {
    const s = sortable && SORTABLE[k], cur = state.sort.col === k;
    const arrow = cur ? '<span class="caret'+(state.sort.dir === 'asc' ? ' up' : '')+'">'+CARET+'</span>' : '';
    return s ? '<th class="col-'+k+' sortable'+(cur?' active':'')+'"><button class="sorter" data-col="'+k+'" aria-label="Sort by '+k+'">'+l+arrow+'</button></th>' : '<th class="col-'+k+'">'+l+'</th>';
  }).join('');
  return '<div class="data-set"><div class="scroll"><table><thead><tr>'+head+'</tr></thead><tbody>'+recs.map(rowHtml).join('')+'</tbody></table></div>'
    +'<div class="mobile-pr-list">'+recs.map(mobileRowHtml).join('')+'</div></div>';
}
function emptyState(msg){ return '<div class="empty">'+(msg||'No pull requests match these filters.')+' <button class="linkish" data-reset>Clear filters</button></div>'; }

function renderQueue(recs){
  const key = r => r.waiting != null ? r.waiting : r.age;
  const ready = recs.filter(r => r.bucket === 'review').sort((a, b) => key(b) - key(a));
  const allReady = DATA.filter(r => r.bucket === 'review');
  const oldest = allReady.reduce((m, r) => Math.max(m, key(r)), 0);
  const header = '<header class="view-header"><div><p class="eyebrow">Triage</p><h2>Review queue</h2>'
    +'<p>Pull requests currently ready for reviewer attention, longest waiting first. Queue labels organize work; they do not approve it.</p></div>'
    +'<div class="view-summary"><span><strong>'+allReady.length+'</strong> ready</span><span><strong>'+oldest+'d</strong> longest wait</span></div></header>';
  const primary = '<section class="queue-primary"><div class="sec-h"><h2>Ready for review</h2><span class="n">'+ready.length+(ready.length !== allReady.length ? ' matching' : '')+'</span></div>'
    +(ready.length ? tableHtml(ready, false) : emptyState('No ready pull requests match these filters.'))+'</section>';
  const secondary = BUCKETS.filter(([b]) => b !== 'review').map(([b, title]) => {
    const group = recs.filter(r => r.bucket === b).sort((a, b2) => b2.idle - a.idle);
    if (!group.length) return '';
    return '<details class="queue-group"><summary><strong>'+title+'</strong><span>'+group.length+'</span></summary>'+tableHtml(group, false)+'</details>';
  }).join('');
  return header+primary+(secondary ? '<div class="queue-secondary" aria-label="Other pull request states">'+secondary+'</div>' : '');
}
function renderAll(recs){
  const header = '<header class="view-header"><div><p class="eyebrow">Repository view</p><h2>All open pull requests</h2><p>Search and sort the full upstream queue. Formal Conjectures remains authoritative for every PR state and decision.</p></div>'
    +'<div class="view-summary"><span><strong>'+recs.length+'</strong> shown</span></div></header>';
  return header+(recs.length ? '<section>'+tableHtml(sortRecs(recs), true)+'</section>' : emptyState());
}
// Conjectures nothing blocks and nobody has started: `new conjecture` without
// `needs-prerequisites`, minus the ones an open PR already says it closes. That last part is
// the whole point of showing this here rather than linking to the issue list, which cannot
// see the pull requests.
function renderPick(){
  const q = (state.q || '').toLowerCase();
  const all = ISSUES.filter(i => i.ready && (!q || i.title.toLowerCase().includes(q)));
  const byAge = (a, b) => b.age - a.age;
  const free = all.filter(i => !i.prs.length && !i.have).sort(byAge);
  const taken = all.filter(i => i.prs.length).sort(byAge);
  const done = all.filter(i => !i.prs.length && i.have).sort(byAge);
  if (!all.length) return emptyState();
  const row = i => '<tr><td class="num"><a href="https://github.com/' + META.repo + '/issues/' + i.n + '">#' + i.n + '</a></td>'
    + '<td class="ti">' + esc(i.title) + '</td><td class="muted">' + esc(i.ams) + '</td>'
    + '<td class="num">' + i.age + 'd</td><td>'
    + (i.have ? '<a class="flag flag--onmain" href="https://github.com/' + META.repo + '/blob/main/' + i.have + '">in repo</a>' : '')
    + i.prs.map(n => '<a class="flag flag--onmain" href="https://github.com/' + META.repo + '/pull/' + n + '">#' + n + '</a>').join(' ')
    + '</td></tr>';
  const table = rows => '<div class="scroll"><table><thead><tr><th>issue</th><th>title</th><th>area</th><th>open</th><th>PR</th></tr></thead><tbody>'
    + rows.map(row).join('') + '</tbody></table></div>';
  return '<header class="view-header"><div><p class="eyebrow">Exploration</p><h2>Find a case</h2><p>Conjecture issues with no missing prerequisites. This is a discovery aid, not an assignment or repository decision.</p></div>'
    +'<div class="view-summary"><span><strong>'+free.length+'</strong> unclaimed</span></div></header><section><p class="muted">' + free.length + ' conjectures with no missing prerequisites and no open PR, oldest first.</p>'
    + table(free)
    + (taken.length ? '<p class="muted" style="margin-top:2rem">' + taken.length
        + ' more are already claimed by an open pull request.</p>' + table(taken) : '')
    + (done.length ? '<p class="muted" style="margin-top:2rem">' + done.length
        + ' already exist in the repository and the issue was never closed.</p>' + table(done) : '')
    + '</section>';
}

function renderFidelity(recs){
  const byProblem = {};
  recs.forEach(r => r.audit.forEach(a => { (byProblem[a.n] || (byProblem[a.n] = {n:a.n, cls:a.cls, status:a.status, note:a.note, href:a.href, prs:[]})).prs.push(r); }));
  const probs = Object.values(byProblem);
  if (!probs.length) return emptyState('No audited Erdős-problem PRs match.');
  const sel = state.facets.audit;  // in this view the audit facet selects problem groups directly
  const groups = AUDIT_ORDER.map(s => [s, probs.filter(p => p.status === s).sort((a, b) => a.n - b.n)])
    .filter(g => g[1].length && (!sel.size || sel.has(g[0])));
  const header = '<header class="view-header"><div><p class="eyebrow">Optional evidence</p><h2>Fidelity evidence</h2><p>Problem-level proof observations beside open PRs. These labels are advisory facts, never approval or mathematical truth.</p></div></header>';
  return header+groups.map(([s, ps]) => '<section><div class="sec-h"><h2>'+FID_TITLE[s]+'</h2><span class="n">'+ps.length+'</span></div>'
    + '<div class="scroll"><table><thead><tr><th>problem</th><th>audit</th><th>open PRs</th></tr></thead><tbody>'
    + ps.map(p => '<tr><td class="num"><a href="'+p.href+'">#'+p.n+'</a></td>'
        + '<td><span class="ab '+p.cls+'" title="#'+p.n+': '+esc(p.note)+'">'+AUDIT_LABEL[p.status]+'</span></td>'
        + '<td>'+p.prs.map(r => '<a class="prlink" href="https://github.com/'+META.repo+'/pull/'+r.n+'" title="'+esc(r.title)+'">#'+r.n+'</a>').join('')+'</td></tr>').join('')
    + '</tbody></table></div></section>').join('');
}

function renderPrAudits(){
  if (!PR_AUDITS.length) return emptyState('No exact per-PR audit records are configured.');
  const rows = PR_AUDITS.map(r => {
    const pr = r.pull_request;
    const checks = r.checks.map(c => '<li><code>'+esc(c.id)+'</code> &middot; '
      +esc(c.property)+' &middot; <strong>'+esc(c.outcome)+'</strong>'
      +(c.severity === 'none' ? '' : ' &middot; '+esc(c.severity))+'</li>').join('');
    return '<article class="audit-record"><div class="audit-record-h"><div><a class="num" href="'+pr.url+'">#'+pr.number+'</a> '
      +'<a href="'+r.source_url+'"><strong>'+esc(r.fixture)+'</strong></a></div>'
      +'<span class="ab pa pa--'+r.advisory_disposition+'">'+r.advisory_disposition.replaceAll('_',' ')+'</span></div>'
      +'<ul>'+checks+'</ul><p class="muted mono">core '+esc(r.core.root)+'<br>observation '+esc(r.observation.root)+'</p></article>';
  }).join('');
  return '<header class="view-header"><div><p class="eyebrow">Preserved evidence</p><h2>Evidence inventory</h2><p>Commit-pinned per-PR audit records. Inventory status does not create repository standing.</p></div>'
    +'<div class="view-summary"><span><strong>'+PR_AUDITS.length+'</strong> records</span></div></header><section><div class="sec-h"><h2>Exact per-PR audit records</h2><span class="n">'+PR_AUDITS.length+'</span></div>'
    +'<p class="muted">Five commit-pinned advisory fixtures. They do not establish approval, merge readiness, mathematical truth, Decision, or Standing.</p>'
    +'<div class="audit-records">'+rows+'</div></section>';
}

function humanize(value){ return String(value == null ? '' : value).replaceAll('_', ' '); }
function outcome(value){
  const cls = value === 'pass' || value === 'current' ? 'pass' : value === 'error' || value === 'stale' ? 'error' : 'pending';
  return '<span class="outcome outcome--'+cls+'">'+esc(humanize(value))+'</span>';
}
function evidenceRow(name, source, detail, result){
  return '<div class="evidence-row"><div class="evidence-name">'+esc(name)+'</div>'
    +'<div class="evidence-source">'+source+'<small>'+esc(detail)+'</small></div>'+outcome(result)+'</div>';
}
function fact(label, value){ return '<div class="fact"><dt>'+esc(label)+'</dt><dd>'+value+'</dd></div>'; }
function hash(value){ return '<span class="hash">'+esc(value)+'</span>'; }

function renderPilot(){
  if (!PILOT) return emptyState('The bounded pilot report is not present in this build.');
  const report = PILOT.review_report, audit = report.immutable_audit;
  const current = report.current_github_observation, typed = report.comparator_evidence.typed_outcome;
  const links = PILOT.links, tools = PILOT.lean_eval.tool_pins;
  const fresh = current && current.freshness === 'current';
  const metadata = audit.checks[0];
  const rows = evidenceRow(
      'Source identity', '<a href="'+links.pull_request+'">Current GitHub observation</a>',
      current ? 'Observed '+current.observed_at+' at '+current.head_commit_oid : 'No current observation',
      current ? current.freshness : 'not observed')
    + evidenceRow('Proof conditions', '<a href="'+links.audit_packet+'">Frozen audit core</a>',
      metadata.property+'; retained manual metadata review', metadata.outcome)
    + evidenceRow('Replay workspace', '<a href="'+links.lean_eval+'">Pinned LeanEval interface</a>',
      'Derived multi-file profile; preparation bytes and workspace files are content-addressed', 'derived')
    + evidenceRow('Comparator execution', '<a href="'+links.comparator_execution+'">Pinned execution source</a>',
      typed.invocation.reason+'; exit code '+typed.invocation.exit_code, typed.invocation.outcome)
    + evidenceRow('Structured result parse', 'Typed Comparator adapter',
      typed.result_parse.reason, typed.result_parse.outcome)
    + evidenceRow('Axiom policy', 'Typed Comparator adapter',
      'Terminal text was retained but was not interpreted as a property verdict', typed.policy_result.outcome);
  const nonclaims = report.nonclaims.map(item => '<li>'+esc(humanize(item))+'</li>').join('');
  const disposition = report.maintainer_disposition == null ? 'Not recorded' : humanize(report.maintainer_disposition);
  const advisory = audit.advisory_synthesis.advisory;
  const path = '<ol class="evidence-path" aria-label="Evidence and replay path">'
    +'<li><strong>Source head</strong><small>'+(fresh?'current':'stale')+'</small></li>'
    +'<li><strong>Proof conditions</strong><small>'+esc(humanize(metadata.outcome))+'</small></li>'
    +'<li><strong>Workspace</strong><small>derived and pinned</small></li>'
    +'<li><strong>Execution</strong><small>'+esc(humanize(typed.invocation.outcome))+'</small></li>'
    +'<li><strong>Policy</strong><small>'+esc(humanize(typed.policy_result.outcome))+'</small></li></ol>';
  const facts = '<dl class="fact-list">'
    +fact('PR head','<a href="'+links.head+'">'+hash(audit.head.commit_oid)+'</a>')
    +fact('Audit core',hash(audit.core.root)+'<br>'+hash(audit.core.sha256))
    +fact('Audit observation',hash(audit.observation.root)+'<br>'+hash(audit.observation.sha256))
    +fact('Linked proof input',hash(PILOT.preparation.input_sha256))
    +fact('Calibration source','<a href="'+links.calibration_source+'">'+hash(PILOT.preparation.source_head)+'</a>')
    +fact('Workspace source','<a href="'+links.workspace_source+'">'+hash(PILOT.preparation.formal_conjectures_revision)+'</a>')
    +fact('Mathlib',hash(PILOT.preparation.mathlib_revision))
    +fact('LeanEval interface','<a href="'+links.lean_eval+'">'+hash(tools.lean_eval_interface_commit)+'</a>')
    +fact('Comparator interface','<a href="'+links.comparator_interface+'">'+hash(tools.comparator_interface_commit)+'</a>')
    +fact('Comparator execution','<a href="'+links.comparator_execution+'">'+hash(tools.comparator_execution_commit)+'</a>')
    +fact('Toolchain',esc(tools.lean_toolchain))
    +fact('Execution image',hash(PILOT.execution.image_id)+'<br>network: '+esc(PILOT.execution.network))
    +fact('Manifest bindings','outcome '+hash(PILOT.execution.outcome_sha256)+'<br>preparation '+hash(PILOT.execution.preparation_sha256))
    +'</dl>';
  return '<article class="pilot">'
    +'<header class="case-header"><div class="case-intro"><p class="eyebrow">Selected case · PR #'+PILOT.case.number+'</p>'
    +'<h2><a href="'+links.pull_request+'">'+esc(PILOT.case.declaration)+'</a></h2>'
    +'<p class="case-title">'+esc(PILOT.case.title)+'.</p><p class="case-selection">Why this case: '+esc(PILOT.case.selection)+'.</p>'
    +'<nav class="case-actions" aria-label="Case sources"><a class="primary-link" href="'+links.pull_request+'">Open upstream PR</a><a href="'+links.source_file+'">Exact source</a><a href="'+links.linked_proof+'">Linked proof</a><a href="'+links.audit_packet+'">Audit packet</a></nav></div>'
    +'<dl class="review-summary" aria-label="Case review summary">'
    +'<div><dt>Evidence</dt><dd><span class="state '+(fresh?'state--current':'state--stale')+'">'+(fresh?'Current':'Stale')+'</span><small>'+(current?'Observed '+esc(current.observed_at):'No current observation')+'</small></dd></div>'
    +'<div><dt>Upstream PR</dt><dd><span class="state state--open">'+esc(current ? current.state : 'Not observed')+'</span><small>GitHub review state: '+esc(current && current.review_decision ? humanize(current.review_decision) : 'not recorded')+'</small></dd></div>'
    +'<div class="decision-pending"><dt>Advisory review</dt><dd><strong>'+esc(humanize(advisory))+'</strong><small>Reader-facing synthesis with no authority effect</small></dd></div>'
    +'<div><dt>Maintainer decision</dt><dd><strong>'+esc(disposition)+'</strong><small>Only a Formal Conjectures maintainer can supply it</small></dd></div></dl></header>'
    +'<aside class="execution-note"><strong>Replay stopped before a policy verdict</strong><p>Comparator invocation ended in a typed <b>error</b>. Result parsing was not attempted and axiom policy was not evaluated. Terminal text was retained as evidence, never promoted to a failed proof-property verdict.</p></aside>'
    +'<section class="pilot-section" aria-labelledby="evidence-heading"><div class="pilot-section-h"><div><p class="eyebrow">Evidence</p><h3 id="evidence-heading">What was checked</h3></div><p>Typed outcomes stay attached to exact sources. An execution error is not a mathematical verdict.</p></div>'+path+rows+'</section>'
    +'<section class="review-boundary" aria-label="Advisory and maintainer outcomes"><div><p class="eyebrow">Advisory ReviewReport</p><h3 class="advisory-value">'+esc(humanize(advisory))+'</h3><p>The report synthesizes the immutable audit and current GitHub observation. It cannot approve or reject the pull request.</p><details class="nonclaim-disclosure"><summary>ReviewReport non-claims</summary><ul class="nonclaims">'+nonclaims+'</ul></details></div>'
    +'<div><p class="eyebrow">Maintainer disposition</p><h3>'+esc(disposition)+'</h3><p>No maintainer acceptance, rejection, or merge decision is represented here.</p><small>Return to Formal Conjectures for every authoritative action.</small></div></section>'
    +'<div class="disclosure-stack">'
    +'<details class="disclosure"><summary><strong>Pinned inputs and replay environment</strong><span>Exact revisions, roots, images, and manifests</span></summary><div class="disclosure-body"><nav class="inspection-links" aria-label="Replay sources"><a href="'+links.historical_run+'">Historical run</a><a href="'+links.lean_eval+'">LeanEval source</a><a href="'+links.comparator_execution+'">Comparator source</a></nav>'+facts+'</div></details>'
    +'<details class="disclosure"><summary><strong>Preservation and freshness</strong><span>Scheduled recurrence and drift behavior</span></summary><div class="disclosure-body"><div class="recurrence">'+outcome(current ? current.freshness : 'not observed')+'<p>'+(fresh?'The live PR head still matches the frozen audit head.':'The live PR head does not match the frozen audit head. Existing findings were not reinterpreted.')+'<small>'+(current ? 'Observed '+esc(current.observed_at)+'. ' : '')+'The scheduled build regenerates the GitHub observation and validates retained report, preparation, outcome, and execution-manifest bytes.</small></p></div></div></details>'
    +'<details class="disclosure"><summary><strong>Method and authority</strong><span>Protocol #4394, pilot success, and non-goals</span></summary><div class="disclosure-body">'+renderMethodBody()+'</div></details></div>'
    +'</article>';
}

function renderMethodBody(){
  return '<p class="method-intro">The workbench follows <a href="'+PILOT.links.protocol+'">Formal Conjectures issue #4394</a>. It is a bounded reading surface for one calibration case, designed to reduce maintainer review effort without creating a second authority or evidence silo.</p>'
    +'<ol class="loop"><li><div><h3>Canonical metadata</h3><p>Start from the exact Formal Conjectures PR head, declaration, proof link, and conditions. Formal Conjectures remains canonical for declarations and repository policy.</p></div></li>'
    +'<li><div><h3>Consumers and checks</h3><p>Bind LeanEval-shaped workspace inputs and Comparator execution to exact source, file, tool, and environment identities. Record typed pass, fail, error, unavailable, and not-evaluated states without reading verdicts from terminal prose.</p></div></li>'
    +'<li><div><h3>Advisory reviewer report</h3><p>Collect checked facts, limitations, and current GitHub state in a ReviewReport. Advisory synthesis stays separate from maintainer disposition. An independent non-author pilot remains an external gate.</p></div></li>'
    +'<li><div><h3>Preservation and recurrence</h3><p>Retain small content-addressed reports, manifests, and logs. Recheck the live PR head, expose stale evidence, and never silently change policy when tools or sources move.</p></div></li></ol>'
    +'<div class="method-grid"><section><h3>What would count as pilot success</h3><ul><li>A non-author can reproduce the report finding from the exact references.</li><li>The report reduces, rather than adds to, maintainer reading time.</li><li>Head drift becomes visibly stale before evidence is reused.</li><li>Execution errors stay distinct from failed proof properties.</li><li>The calibration record remains inspectable after transient workspaces are removed.</li></ul></section>'
    +'<section><h3>Non-goals</h3><ul><li>No merge gate, maintainer approval, or claim of mathematical truth.</li><li>No generic AI platform, centralized governance product, or new proof registry.</li><li>No Vela authority path. A later problems.science projection may only link to FC evidence.</li><li>No Econlib integration or partner representation.</li><li>No claim of reviewer buy-in, upstream adoption, or external validation.</li></ul></section></div>';
}

function renderMethod(){
  if (!PILOT) return emptyState('The pilot method is not configured in this build.');
  return '<article class="method-page"><p class="eyebrow">Pilot protocol</p><h2>Review, verification, and preservation loop</h2>'+renderMethodBody()+'</article>';
}

function statHtml(v, l, cls, facet){
  const body = '<span class="sv '+(cls||'')+'">'+v+'</span> <span class="sl">'+l+'</span>';
  if (!facet) return '<div class="stat">'+body+'</div>';
  const on = state.facets.audit.has(facet);
  return '<button type="button" class="stat stat--go'+(on ? ' is-on' : '')+'" data-audit="'+facet
    + '" aria-pressed="'+on+'" title="Show only '+l+'">'+body+'</button>';
}
function renderStrip(){
  const review = DATA.filter(r => r.bucket === 'review');
  const stmt = review.filter(r => r.kind === 'statement').length;
  // Consistent with the waiting column: time on the queue, age as fallback.
  const oldest = review.reduce((m, r) => Math.max(m, r.waiting != null ? r.waiting : r.age), 0);
  let html = '<div class="grp">'+statHtml(DATA.length,'open')+statHtml(review.length,'ready to review')+statHtml(stmt,'statements')+statHtml(oldest+'d','oldest waiting')+'</div>';
  // Signed-faithful and conditional counts used to sit here. At 1 and 3 against
  // 146 PRs they cost a third of the header for a signal nobody acts on; the
  // per-row chips and the Fidelity view carry that detail already. A signed
  // *unfaithful* proof is different in kind, so it appears only when there is
  // one, which is the only time it means anything.
  if (META.hasAudit){
    const top = DATA.filter(r => r.bucket === 'review' || r.bucket === 'approved').map(r => r.auditTop);
    const flagged = top.filter(x => x === 'ab--discrepancy').length;
    if (flagged) html += '<div class="grp grp--audit">'
      + statHtml(flagged, 'flagged by the audit', 'sv--cinnabar', 'flagged') + '</div>';
  }
  el('strip').innerHTML = html;
  el('strip').querySelectorAll('.stat--go').forEach(b => b.addEventListener('click', () => {
    const set = state.facets.audit, v = b.dataset.audit;
    set.has(v) ? set.delete(v) : set.add(v);
    syncUrl(); updateFilterUI(); render(); renderStrip();
  }));
}

function render(){
  const recs = DATA.filter(matches);
  if (DATA_VIEWS.has(state.view)) countEl.textContent = recs.length === DATA.length ? DATA.length+' open PRs' : recs.length+' of '+DATA.length+' open PRs';
  app.innerHTML = state.view === 'pilot' ? renderPilot()
    : state.view === 'method' ? renderMethod()
    : state.view === 'queue' ? renderQueue(recs)
    : state.view === 'pick' ? renderPick()
    : state.view === 'fidelity' ? renderFidelity(recs)
    : state.view === 'pr-audits' ? renderPrAudits() : renderAll(recs);
  app.querySelectorAll('button.sorter').forEach(button => button.addEventListener('click', () => {
    const c = button.dataset.col;
    if (state.sort.col === c) state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
    else { state.sort.col = c; state.sort.dir = c === 'author' ? 'asc' : 'desc'; }
    syncUrl(); render();
  }));
  app.querySelectorAll('[data-reset]').forEach(b => b.addEventListener('click', resetAll));
}
function updateTabs(){ document.querySelectorAll('[data-view]').forEach(b => {
  const active = b.dataset.view === state.view;
  b.classList.toggle('active', active);
  if (b.classList.contains('tab')) { b.setAttribute('aria-selected', active); b.tabIndex = active ? 0 : -1; }
  else if (b.classList.contains('more-tab')) b.setAttribute('aria-current', active ? 'page' : 'false');
});
  const secondary = TAB_SPECS.find(([key]) => key === state.view && !PRIMARY_VIEWS.has(key));
  viewMoreEl.classList.toggle('is-active', !!secondary);
  viewMoreLabelEl.textContent = secondary ? secondary[1] : 'More';
}
function updateViewChrome(){
  const dataView = DATA_VIEWS.has(state.view);
  el('controls').hidden = !dataView;
  searchEl.closest('.search').hidden = !dataView;
  filterbarEl.hidden = !FILTER_VIEWS.has(state.view);
  countEl.hidden = !dataView || state.view === 'pick';
  el('strip').hidden = true;
}

function closeMenus(){ filterbarEl.querySelectorAll('.fdd.open').forEach(dd => {
  dd.classList.remove('open'); dd.querySelector('.fmenu').hidden = true;
  dd.querySelector('.fbtn').setAttribute('aria-expanded', 'false'); }); }
function updateFilterUI(){
  filterbarEl.querySelectorAll('.fdd').forEach(dd => {
    const g = dd.dataset.group, n = state.facets[g].size;
    dd.querySelector('.fbtn').classList.toggle('active', n > 0);
    dd.querySelector('.fbtn-n').textContent = n ? ' ' + n : '';
    dd.querySelectorAll('.fopt input').forEach(cb => cb.checked = state.facets[g].has(cb.value));
  });
  const any = state.q || ['audit','kind','coll','ci'].some(g => state.facets[g].size);
  const cb = el('clearBtn'); if (cb) cb.hidden = !any;
}

function selectView(view){
  state.view = view; viewMoreEl.open = false; syncUrl(); updateTabs(); updateViewChrome(); renderStrip(); render();
  app.focus({preventScroll:true});
}
function buildToolbar(){
  tabsEl.innerHTML = TAB_SPECS.filter(([key]) => PRIMARY_VIEWS.has(key))
    .map(([k, l]) => '<button class="tab" role="tab" data-view="'+k+'">'+l+'</button>').join('');
  moreViewsEl.innerHTML = TAB_SPECS.filter(([key]) => !PRIMARY_VIEWS.has(key))
    .map(([k, l]) => '<button class="more-tab" type="button" data-view="'+k+'">'+l+'</button>').join('');
  document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => selectView(b.dataset.view)));
  document.querySelectorAll('[data-switch-view]').forEach(b => b.addEventListener('click', () => selectView(b.dataset.switchView)));
  tabsEl.addEventListener('keydown', event => {
    if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    const tabs = [...tabsEl.querySelectorAll('.tab')], current = tabs.indexOf(document.activeElement);
    if (current < 0) return;
    let next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
      : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    event.preventDefault(); tabs[next].focus(); tabs[next].click();
  });
  const groups = FACETS.filter(f => f.group !== 'audit' || META.hasAudit);
  filterbarEl.innerHTML = groups.map(f =>
    '<div class="fdd" data-group="'+f.group+'"><button class="fbtn" type="button" aria-haspopup="true" aria-expanded="false">'
    + f.label + '<span class="fbtn-n"></span>' + CARET + '</button><div class="fmenu" role="menu" hidden>'
    + f.opts.map(o => { const dot = f.group === 'audit' ? '<span class="cdot cdot--'+AUDIT_DOT[o]+'"></span>' : '';
        return '<label class="fopt"><input type="checkbox" data-group="'+f.group+'" value="'+o+'">'+dot+'<span>'+o+'</span></label>'; }).join('')
    + '</div></div>').join('') + '<button class="clear-btn" id="clearBtn" type="button" hidden>Clear all</button>';
  filterbarEl.querySelectorAll('.fbtn').forEach(btn => btn.addEventListener('click', e => {
    e.stopPropagation(); const dd = btn.closest('.fdd'); const open = dd.classList.contains('open'); closeMenus();
    if (!open){ dd.classList.add('open'); dd.querySelector('.fmenu').hidden = false; btn.setAttribute('aria-expanded', 'true'); } }));
  filterbarEl.querySelectorAll('.fmenu').forEach(m => m.addEventListener('click', e => e.stopPropagation()));
  filterbarEl.querySelectorAll('.fopt input').forEach(cb => cb.addEventListener('change', () => {
    const set = state.facets[cb.dataset.group]; cb.checked ? set.add(cb.value) : set.delete(cb.value);
    syncUrl(); updateFilterUI(); render(); }));
  el('clearBtn').addEventListener('click', resetAll);
  searchEl.addEventListener('input', () => { state.q = searchEl.value.trim(); syncUrl(); updateFilterUI(); render(); });
  document.addEventListener('click', closeMenus);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenus(); });
}
function resetAll(){ state.q = ''; searchEl.value = '';
  state.facets = {audit:new Set(), kind:new Set(), coll:new Set(), ci:new Set()}; closeMenus(); syncUrl(); updateFilterUI(); render(); }

function syncUrl(){
  const p = new URLSearchParams();
  if (state.view !== DEFAULT_VIEW) p.set('view', state.view);
  if (state.q) p.set('q', state.q);
  ['audit','kind','coll','ci'].forEach(g => { if (state.facets[g].size) p.set(g, [...state.facets[g]].join(',')); });
  if (state.view === 'all') p.set('sort', state.sort.col+':'+state.sort.dir);
  const h = p.toString();
  history.replaceState(null, '', h ? '#'+h : location.pathname + location.search);
}
function loadUrl(){
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get('view') && TAB_SPECS.some(v => v[0] === p.get('view'))) state.view = p.get('view');
  if (p.get('q')){ state.q = p.get('q'); searchEl.value = state.q; }
  ['audit','kind','coll','ci'].forEach(g => { if (p.get(g)) state.facets[g] = new Set(p.get(g).split(',')); });
  if (p.get('sort')){ const s = p.get('sort').split(':'); state.sort = {col:s[0], dir:s[1] || 'desc'}; }
}

renderStrip();
buildToolbar();
loadUrl();
updateTabs();
updateViewChrome();
updateFilterUI();
render();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
