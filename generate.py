#!/usr/bin/env python3
"""Render a review-queue dashboard for formal-conjectures open PRs.

In the spirit of mathlib's queueboard: it turns the open PRs into one
glance-able page so maintainers can see what is ready to review, what is
waiting on its author, and what has been waiting longest.

It also joins each Erdos-problem PR to the public Erdos fidelity audit
(https://erdos.constellate.science) and shows, per problem, whether the
linked proof was found unconditional, conditional, or signed by a named
reviewer. The audit surfaces a fact; the merge decision stays the
maintainer's.

    # PR data (the Action passes GITHUB_TOKEN; locally, gh's own auth):
    gh pr list -R google-deepmind/formal-conjectures --state open --limit 200 \
      --json number,title,author,labels,isDraft,createdAt,updatedAt,\
statusCheckRollup,reviewDecision,mergeStateStatus,latestReviews,\
additions,deletions,files > prs.json

    # Audit feed (the Action curls this before running):
    curl -sfL https://erdos.constellate.science/verdicts.json > verdicts.json

    python3 generate.py            # writes index.html
"""

from __future__ import annotations

import html
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


# Rollup order + short labels, keyed by badge class. Used both to bucket a
# many-problem PR into one compact summary and to order those counts.
ROLLUP = [("ab--signed", "signed"), ("ab--discrepancy", "unfaithful"),
          ("ab--variant", "variant"), ("ab--unconditional", "uncond"),
          ("ab--conditional", "cond"), ("ab--unaudited", "open"),
          ("ab--none", "off-list")]
ROLLUP_THRESHOLD = 8


def _assumptions(row: dict) -> str:
    """Readable form of the Prop hypotheses a conditional proof rests on:
    'hconv : Erdos94.ConvexPosition P' -> 'ConvexPosition P'."""
    labels = []
    for na in row.get("named_assumptions") or []:
        t = na.split(":", 1)[-1].strip()
        labels.append(re.sub(r"\bErdos\d+\.", "", t))
    return ", ".join(labels)


def audit_class(row: dict | None) -> tuple[str, str]:
    """Map an audit row to a (badge-class, tooltip-note). The base color comes
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


def audit_badge(n: int, row: dict | None) -> str:
    cls, note = audit_class(row)
    href = ERDOS_URL.format(n=n) if row is None else FINDING_URL.format(n=n)
    return (f'<a class="ab {cls}" href="{href}" '
            f'title="#{n}: {html.escape(note)}">{n}</a>')


def audit_rollup(nums: list[int], verdicts: dict[int, dict]) -> str:
    """One compact summary for a PR that touches many problems (batch syncs,
    version bumps). A stack of 30 badges is noise; the count breakdown is the
    signal a reviewer wants."""
    counts: dict[str, int] = {}
    for n in nums:
        cls = audit_class(verdicts.get(n))[0]
        counts[cls] = counts.get(cls, 0) + 1
    parts = [f'<span class="{cls} rc">{counts[cls]}</span>&thinsp;{label}'
             for cls, label in ROLLUP if counts.get(cls)]
    return (f'<span class="roll"><b>{len(nums)}</b> problems &middot; '
            + " &middot; ".join(parts) + '</span>')


def audit_cell(pr: dict, verdicts: dict[int, dict]) -> str:
    nums = problem_numbers(pr)
    if not nums:
        return '<td class="audit"></td>'
    if len(nums) <= ROLLUP_THRESHOLD:
        badges = "".join(audit_badge(n, verdicts.get(n)) for n in nums)
        return f'<td class="audit">{badges}</td>'
    return f'<td class="audit">{audit_rollup(nums, verdicts)}</td>'


# --- rendering ------------------------------------------------------------

def flags(pr: dict) -> str:
    out = []
    if not pr.get("isDraft") and ci_state(pr) == "none":
        out.append('<span class="flag flag--ci" title="CI has not run yet '
                   '(often waiting on a maintainer to approve the workflow)">CI pending</span>')
    if has_conflict(pr):
        out.append('<span class="flag flag--conflict" title="Merge conflict '
                   'with the base branch">conflict</span>')
    return "".join(out)


def row(pr: dict, now: datetime, verdicts: dict[int, dict]) -> str:
    n = pr["number"]
    age = days_since(pr["createdAt"], now)
    idle = days_since(pr["updatedAt"], now)
    ci = ci_state(pr)
    ci_dot = {"green": "ok", "failing": "bad", "running": "run", "none": "na"}[ci]
    kind = "statement" if is_statement(pr) else "infra"
    churn = (pr.get("additions", 0) or 0) + (pr.get("deletions", 0) or 0)
    appr = approvals(pr)
    appr_cell = f'<span class="appr">&check;{appr}</span>' if appr else ""
    login = (pr.get("author") or {}).get("login") or "ghost"
    return (
        f'<tr>'
        f'<td class="num"><a href="https://github.com/{REPO}/pull/{n}">#{n}</a></td>'
        f'<td class="ttl"><span class="ttl-t">{html.escape(pr["title"])}</span>{flags(pr)}</td>'
        f'<td class="who">{html.escape(login)}</td>'
        f'<td><span class="tag tag--{kind}">{kind}</span></td>'
        f'{audit_cell(pr, verdicts)}'
        f'<td class="mono">{age}d</td>'
        f'<td class="mono">{idle}d</td>'
        f'<td><span class="ci ci--{ci_dot}" title="{ci}"></span></td>'
        f'<td class="mono appr-c">{appr_cell}</td>'
        f'<td class="mono">{churn}</td>'
        f'</tr>')


def table(prs: list[dict], now: datetime, verdicts: dict[int, dict],
          *, sort_idle=False) -> str:
    key = (lambda p: -days_since(p["updatedAt"], now)) if sort_idle \
        else (lambda p: -days_since(p["createdAt"], now))
    body = "".join(row(p, now, verdicts) for p in sorted(prs, key=key))
    head = ('<tr><th scope="col">PR</th><th scope="col">title</th>'
            '<th scope="col">author</th><th scope="col">kind</th>'
            '<th scope="col">audit</th><th scope="col">open</th>'
            '<th scope="col">idle</th><th scope="col">CI</th>'
            '<th scope="col">&check;</th><th scope="col">&pm;</th></tr>')
    return (f'<div class="scroll"><table>'
            f'<thead>{head}</thead><tbody>{body}</tbody></table></div>')


# Highest-to-lowest so a PR's readout status is the most notable thing the
# audit found among its problems (a caution outranks good news).
SEVERITY = ["ab--discrepancy", "ab--conditional", "ab--variant",
            "ab--signed", "ab--unconditional"]


def pr_top_status(pr: dict, verdicts: dict[int, dict]) -> str | None:
    classes = {audit_class(verdicts.get(n))[0] for n in problem_numbers(pr)}
    for s in SEVERITY:
        if s in classes:
            return s
    return None


def stat(value, label: str, cls: str = "") -> str:
    sv = f'<span class="sv {cls}">{value}</span>' if cls else f'<span class="sv">{value}</span>'
    return f'<div class="stat">{sv} <span class="sl">{label}</span></div>'


def build_strip(prs, buckets, verdicts, now) -> str:
    n_stmt = sum(1 for p in buckets["review"] if is_statement(p))
    oldest = max((days_since(p["createdAt"], now) for p in buckets["review"]), default=0)
    queue = "".join([
        stat(len(prs), "open"),
        stat(len(buckets["review"]), "ready to review"),
        stat(n_stmt, "statements"),
        stat(f"{oldest}d", "oldest waiting"),
    ])
    strip = f'<div class="grp">{queue}</div>'
    if verdicts:  # fidelity readout, over the acted-on set (ready + approved)
        actionable = buckets["review"] + buckets["approved"]
        top = [pr_top_status(p, verdicts) for p in actionable]
        fidelity = "".join([
            stat(top.count("ab--signed"), "signed faithful", "sv--gold"),
            stat(top.count("ab--conditional") + top.count("ab--variant"),
                 "conditional", "sv--brass"),
            stat(top.count("ab--discrepancy"), "flagged", "sv--cinnabar"),
        ])
        strip += f'<div class="grp grp--audit">{fidelity}</div>'
    return f'<div class="strip">{strip}</div>'


def build_key(verdicts) -> str:
    if not verdicts:
        return ""
    items = [("kd--moss", "unconditional"), ("kd--brass", "conditional"),
             ("kd--stone", "not yet audited"), ("kd--gold", "signed by a reviewer"),
             ("kd--cinnabar", "flagged unfaithful")]
    keys = "".join(f'<span class="item"><span class="kd {c}"></span>{t}</span>'
                   for c, t in items)
    return (f'<div class="key" role="group" aria-label="Audit column key">'
            f'<span class="key-t">audit</span>{keys}</div>')


def main() -> None:
    prs = load_prs()
    verdicts = load_verdicts()
    now = datetime.now(timezone.utc)
    buckets: dict[str, list[dict]] = {"review": [], "author": [], "draft": [], "approved": []}
    for p in prs:
        buckets[classify(p)].append(p)

    sections = []
    if buckets["approved"]:
        sections.append(("Approved, ready to merge", buckets["approved"], False))
    sections.append(("Ready for review", buckets["review"], False))
    sections.append(("Waiting on the author", buckets["author"], True))
    sections.append(("Draft / work in progress", buckets["draft"], True))

    parts = []
    for title, group, idle in sections:
        if not group:
            continue
        parts.append(f'<section><div class="sec-h"><h2>{title}</h2>'
                     f'<span class="n">{len(group)}</span></div>'
                     f'{table(group, now, verdicts, sort_idle=idle)}</section>')

    doc = TEMPLATE.format(
        stamp=now.strftime("%Y-%m-%d %H:%M UTC"),
        strip=build_strip(prs, buckets, verdicts, now),
        key=build_key(verdicts),
        sections="\n".join(parts),
        fc_repo=FC_REPO_URL, fc_site=FC_SITE_URL, board_repo=BOARD_REPO_URL,
        frontier=FRONTIER_URL, method=METHOD_URL,
    )
    (HERE / "index.html").write_text(doc)
    n_stmt = sum(1 for p in buckets["review"] if is_statement(p))
    print(f"wrote index.html - {len(prs)} PRs, {len(buckets['review'])} ready "
          f"for review ({n_stmt} statements), oldest waiting "
          f"{max((days_since(p['createdAt'], now) for p in buckets['review']), default=0)}d")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>formal-conjectures &middot; review queue</title>
<style>
:root {{
  --paper: oklch(98.4% 0.004 265); --panel: oklch(96.4% 0.006 265); --card: oklch(99.4% 0.002 265);
  --ink0: oklch(27% 0.02 265); --ink1: oklch(44% 0.018 265); --ink2: oklch(57% 0.015 265);
  --rule: oklch(91% 0.008 265); --rule2: oklch(85% 0.012 265); --hover: oklch(27% 0.02 265);
  --accent: oklch(52% 0.13 255);
  --ok: oklch(60% 0.13 150); --bad: oklch(57% 0.2 25); --run: oklch(70% 0.14 78);
  --stmt: oklch(52% 0.13 255); --infra: oklch(55% 0.015 265);
  --moss: oklch(55% 0.11 150); --brass: oklch(56% 0.11 70); --gold: oklch(68% 0.13 85);
  --stone: oklch(60% 0.015 265); --cinnabar: oklch(55% 0.19 25);
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --paper: oklch(18.5% 0.02 265); --panel: oklch(23% 0.02 265); --card: oklch(21.5% 0.018 265);
    --ink0: oklch(92% 0.01 265); --ink1: oklch(75% 0.014 265); --ink2: oklch(60% 0.014 265);
    --rule: oklch(30% 0.015 265); --rule2: oklch(38% 0.018 265); --hover: oklch(92% 0.01 265);
    --accent: oklch(75% 0.12 255);
    --ok: oklch(72% 0.13 150); --bad: oklch(68% 0.19 25); --run: oklch(80% 0.13 78);
    --stmt: oklch(75% 0.12 255); --infra: oklch(66% 0.015 265);
    --moss: oklch(74% 0.12 150); --brass: oklch(77% 0.11 74); --gold: oklch(82% 0.12 85);
    --stone: oklch(68% 0.02 265); --cinnabar: oklch(71% 0.18 25);
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--paper); color: var(--ink0);
  font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased; }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding: 44px 24px 72px; }}
a {{ color: var(--accent); }}
:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }}

header {{ margin-bottom: 4px; }}
h1 {{ font-size: 23px; font-weight: 640; letter-spacing: -.015em; margin: 0 0 7px; }}
h1 .h1-sub {{ color: var(--ink2); font-weight: 460; }}
.lede {{ margin: 0; max-width: 64ch; color: var(--ink1); font-size: 14.5px; line-height: 1.55; }}
.meta {{ margin-top: 11px; font-size: 12.5px; color: var(--ink2); }}
.meta a {{ color: var(--ink1); text-decoration: none; border-bottom: 1px solid var(--rule2); }}
.meta a:hover {{ color: var(--accent); border-color: var(--accent); }}
.sep {{ margin: 0 8px; color: var(--rule2); }}

.strip {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px 26px;
  padding: 15px 18px; margin: 22px 0 12px; background: var(--panel);
  border: 1px solid var(--rule); border-radius: 12px; }}
.grp {{ display: flex; flex-wrap: wrap; gap: 10px 22px; align-items: baseline; }}
.grp--audit {{ position: relative; padding-left: 26px; }}
.grp--audit::before {{ content: ""; position: absolute; left: 0; top: 3px; bottom: 3px;
  width: 1px; background: var(--rule2); }}
.stat {{ display: flex; align-items: baseline; gap: 6px; }}
.sv {{ font-size: 19px; font-weight: 660; font-variant-numeric: tabular-nums;
  letter-spacing: -.01em; color: var(--ink0); }}
.sl {{ font-size: 12.5px; color: var(--ink2); }}
.sv--gold {{ color: color-mix(in oklab, var(--gold) 72%, var(--ink1)); }}
.sv--brass {{ color: var(--brass); }}
.sv--cinnabar {{ color: var(--cinnabar); }}

.key {{ display: flex; flex-wrap: wrap; align-items: center; gap: 7px 15px;
  margin: 0 2px 22px; font-size: 12px; color: var(--ink2); }}
.key-t {{ font-weight: 640; color: var(--ink1); text-transform: uppercase;
  letter-spacing: .06em; font-size: 10.5px; }}
.key .item {{ display: inline-flex; align-items: center; gap: 6px; }}
.kd {{ width: 11px; height: 11px; border-radius: 4px; display: inline-block; border: 1px solid transparent; }}
.kd--moss {{ background: color-mix(in oklab, var(--moss) 52%, transparent); }}
.kd--brass {{ background: color-mix(in oklab, var(--brass) 58%, transparent); }}
.kd--stone {{ background: color-mix(in oklab, var(--stone) 40%, transparent); }}
.kd--gold {{ background: color-mix(in oklab, var(--moss) 30%, transparent); border-color: var(--gold); }}
.kd--cinnabar {{ background: color-mix(in oklab, var(--cinnabar) 42%, transparent); }}

section {{ margin: 26px 0; }}
.sec-h {{ display: flex; align-items: baseline; gap: 8px; margin: 0 0 9px; }}
.sec-h h2 {{ font-size: 14px; font-weight: 640; margin: 0; letter-spacing: -.005em; }}
.sec-h .n {{ font-size: 12px; color: var(--ink2); font-weight: 500; font-variant-numeric: tabular-nums; }}
.scroll {{ overflow-x: auto; border: 1px solid var(--rule); border-radius: 12px; }}
table {{ width: 100%; border-collapse: collapse; background: var(--card); }}
th {{ text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--ink2); font-weight: 640; padding: 9px 12px; background: var(--panel);
  border-bottom: 1px solid var(--rule); white-space: nowrap; }}
td {{ padding: 9px 12px; border-bottom: 1px solid var(--rule); font-size: 14px; }}
tr:last-child td {{ border-bottom: 0; }}
tbody tr {{ transition: background .12s ease; }}
tbody tr:hover {{ background: color-mix(in oklab, var(--hover) 4%, transparent); }}
.num a {{ color: var(--accent); text-decoration: none; font-variant-numeric: tabular-nums; font-weight: 640; }}
.num a:hover {{ text-decoration: underline; }}
.ttl {{ max-width: 440px; }}
.ttl-t {{ display: inline-block; max-width: 440px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; vertical-align: bottom; color: var(--ink0); }}
.who {{ color: var(--ink1); white-space: nowrap; }}
.mono {{ font-variant-numeric: tabular-nums; color: var(--ink1); text-align: right; white-space: nowrap; }}
.tag {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 640; white-space: nowrap; }}
.tag--statement {{ background: color-mix(in oklab, var(--stmt) 12%, transparent); color: var(--stmt); }}
.tag--infra {{ background: color-mix(in oklab, var(--infra) 13%, transparent); color: var(--infra); }}
.audit {{ max-width: 220px; }}
.ab {{ display: inline-block; font-size: 11px; font-variant-numeric: tabular-nums; font-weight: 650;
  text-decoration: none; padding: 1px 6px; margin: 1px 3px 1px 0; border-radius: 5px;
  border: 1px solid transparent; }}
.ab:hover {{ filter: brightness(1.04) saturate(1.1); }}
.ab--unconditional {{ background: color-mix(in oklab, var(--moss) 14%, transparent); color: var(--moss); }}
.ab--conditional {{ background: color-mix(in oklab, var(--brass) 17%, transparent); color: var(--brass); }}
.ab--unaudited, .ab--none {{ background: color-mix(in oklab, var(--stone) 14%, transparent); color: var(--stone); }}
.ab--signed {{ background: color-mix(in oklab, var(--moss) 14%, transparent); color: var(--moss);
  border-color: var(--gold); box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--gold) 50%, transparent); }}
.ab--variant {{ background: color-mix(in oklab, var(--brass) 17%, transparent); color: var(--brass);
  border-color: var(--gold); }}
.ab--discrepancy {{ background: color-mix(in oklab, var(--cinnabar) 16%, transparent); color: var(--cinnabar); }}
.roll {{ font-size: 12px; color: var(--ink1); line-height: 1.9; }}
.roll b {{ color: var(--ink0); font-variant-numeric: tabular-nums; }}
.rc {{ display: inline-block; font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums;
  padding: 0 5px; border-radius: 5px; }}
.ci {{ display: inline-block; width: 9px; height: 9px; border-radius: 999px; }}
.ci--ok {{ background: var(--ok); }} .ci--bad {{ background: var(--bad); }}
.ci--run {{ background: var(--run); }} .ci--na {{ background: var(--rule2); }}
.appr {{ color: var(--moss); font-weight: 650; }}
.appr-c {{ text-align: center; }}
.flag {{ display: inline-block; font-size: 10px; font-weight: 650; padding: 1px 6px; margin-left: 6px;
  border-radius: 5px; vertical-align: middle; text-transform: uppercase; letter-spacing: .03em; }}
.flag--ci {{ background: color-mix(in oklab, var(--run) 18%, transparent);
  color: color-mix(in oklab, var(--run) 55%, var(--ink0)); }}
.flag--conflict {{ background: color-mix(in oklab, var(--cinnabar) 15%, transparent); color: var(--cinnabar); }}

footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--rule);
  color: var(--ink2); font-size: 12px; line-height: 1.75; }}
footer p {{ margin: 0 0 8px; max-width: 82ch; }}
footer a {{ color: var(--ink1); text-decoration: none; border-bottom: 1px solid var(--rule2); }}
footer a:hover {{ color: var(--accent); border-color: var(--accent); }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
</style></head>
<body><div class="wrap">
<header>
  <h1>formal-conjectures <span class="h1-sub">&middot; review queue</span></h1>
  <p class="lede">Open pull requests, oldest waiting first. The audit column shows what the fidelity
  check found for each linked proof; the merge decision stays the maintainer's.</p>
  <div class="meta">Updated {stamp} &middot; refreshes hourly<span class="sep">|</span><a href="{fc_repo}/pulls">pull requests</a><span class="sep">|</span><a href="{fc_site}">formal-conjectures</a><span class="sep">|</span><a href="{board_repo}">source</a></div>
</header>
{strip}
{key}
{sections}
<footer>
  <p><strong>The audit column</strong> joins each Erd&#337;s-problem PR to the public fidelity audit &mdash;
  whether the linked proof is machine-checked unconditional, rests on a named assumption, or carries a
  signed reviewer verdict. It reports a fact next to the PR; the merge decision is the maintainer's.
  <a href="{method}">How the audit works &rarr;</a></p>
  <p><strong>Ready for review</strong> = not draft, no changes requested, no merge conflict, CI not failing.
  The waiting groups sort by idle time; ready-for-review by how long each has been open. &check; counts
  approvals, &pm; is lines changed. &ldquo;CI pending&rdquo; marks PRs whose build has not run yet.</p>
  <p>PR data via the GitHub API. Problem-audit data via the <a href="{frontier}">Erd&#337;s frontier</a>
  snapshot. In the spirit of mathlib's queueboard. An independent tool, not affiliated with the
  formal-conjectures maintainers.</p>
</footer>
</div></body></html>
"""


if __name__ == "__main__":
    main()
