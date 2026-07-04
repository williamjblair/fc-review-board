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
        return "ab--unconditional", "machine: unconditional"
    if mv == "conditional":
        return "ab--conditional", "machine: conditional"
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
    head = ("<tr><th>PR</th><th>title</th><th>author</th><th>kind</th>"
            "<th>audit</th><th>open</th><th>idle</th><th>CI</th>"
            "<th>&check;</th><th>&pm;</th></tr>")
    return f'<table><thead>{head}</thead><tbody>{body}</tbody></table>'


def main() -> None:
    prs = load_prs()
    verdicts = load_verdicts()
    now = datetime.now(timezone.utc)
    buckets: dict[str, list[dict]] = {"review": [], "author": [], "draft": [], "approved": []}
    for p in prs:
        buckets[classify(p)].append(p)

    stmt_review = [p for p in buckets["review"] if is_statement(p)]
    oldest = max((days_since(p["createdAt"], now) for p in buckets["review"]), default=0)
    n_audited = sum(1 for p in buckets["review"]
                    if any(verdicts.get(k, {}).get("machine_verdict")
                           for k in problem_numbers(p)))
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")

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
        parts.append(f'<section><h2>{title} <span class="n">{len(group)}</span></h2>'
                     f'{table(group, now, verdicts, sort_idle=idle)}</section>')

    doc = TEMPLATE.format(
        stamp=stamp,
        total=len(prs),
        n_review=len(buckets["review"]),
        n_stmt=len(stmt_review),
        oldest=oldest,
        sections="\n".join(parts),
    )
    (HERE / "index.html").write_text(doc)
    print(f"wrote index.html - {len(prs)} PRs, "
          f"{len(buckets['review'])} ready for review "
          f"({len(stmt_review)} statements, {n_audited} with an audit verdict), "
          f"oldest waiting {oldest}d")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>formal-conjectures &middot; review queue</title>
<style>
:root {{
  --paper: oklch(97.5% 0.006 250); --card: oklch(99% 0.004 250);
  --ink0: oklch(28% 0.02 260); --ink1: oklch(45% 0.02 260); --ink2: oklch(62% 0.02 260);
  --rule: oklch(90% 0.01 255); --accent: oklch(52% 0.13 250);
  --ok: oklch(62% 0.13 150); --bad: oklch(60% 0.19 25); --run: oklch(75% 0.13 85);
  --stmt: oklch(52% 0.13 250); --infra: oklch(60% 0.02 260);
  --moss: oklch(58% 0.11 150); --brass: oklch(64% 0.11 75); --gold: oklch(74% 0.13 85);
  --stone: oklch(66% 0.015 260); --cinnabar: oklch(58% 0.19 25);
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--paper); color: var(--ink0);
  font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding: 40px 24px 80px; }}
header {{ margin-bottom: 28px; }}
h1 {{ font-size: 26px; font-weight: 600; letter-spacing: -.01em; margin: 0 0 4px; }}
.sub {{ color: var(--ink2); font-size: 13px; }}
.cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 22px 0 34px; }}
.card {{ background: var(--card); border: 1px solid var(--rule); border-radius: 12px; padding: 14px 16px; }}
.card .v {{ font-size: 26px; font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }}
.card .k {{ font-size: 12px; color: var(--ink2); margin-top: 2px; }}
section {{ margin: 30px 0; }}
h2 {{ font-size: 16px; font-weight: 600; margin: 0 0 10px; display: flex; align-items: baseline; gap: 8px; }}
h2 .n {{ font-size: 13px; color: var(--ink2); font-weight: 500; font-variant-numeric: tabular-nums; }}
.scroll {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; background: var(--card);
  border: 1px solid var(--rule); border-radius: 12px; overflow: hidden; }}
th {{ text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--ink2); font-weight: 600; padding: 9px 12px; border-bottom: 1px solid var(--rule); white-space: nowrap; }}
td {{ padding: 9px 12px; border-bottom: 1px solid var(--rule); font-size: 14px; }}
tr:last-child td {{ border-bottom: 0; }}
tbody tr:hover {{ background: oklch(96% 0.01 255); }}
.num a {{ color: var(--accent); text-decoration: none; font-variant-numeric: tabular-nums; font-weight: 600; }}
.ttl {{ max-width: 440px; }}
.ttl-t {{ display: inline-block; max-width: 440px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; vertical-align: bottom; }}
.who {{ color: var(--ink1); white-space: nowrap; }}
.mono {{ font-variant-numeric: tabular-nums; color: var(--ink1); text-align: right; white-space: nowrap; }}
.tag {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 600; white-space: nowrap; }}
.tag--statement {{ background: oklch(52% 0.13 250 / .12); color: var(--stmt); }}
.tag--infra {{ background: oklch(60% 0.02 260 / .12); color: var(--infra); }}
.audit {{ max-width: 220px; }}
.ab {{ display: inline-block; font-size: 11px; font-variant-numeric: tabular-nums; font-weight: 600;
  text-decoration: none; padding: 1px 6px; margin: 1px 3px 1px 0; border-radius: 5px;
  border: 1px solid transparent; }}
.ab--unconditional {{ background: oklch(58% 0.11 150 / .13); color: var(--moss); }}
.ab--conditional {{ background: oklch(64% 0.11 75 / .16); color: var(--brass); }}
.ab--unaudited, .ab--none {{ background: oklch(66% 0.015 260 / .12); color: var(--stone); }}
.ab--signed {{ background: oklch(58% 0.11 150 / .13); color: var(--moss); border-color: var(--gold);
  box-shadow: inset 0 0 0 1px oklch(74% 0.13 85 / .5); }}
.ab--variant {{ background: oklch(64% 0.11 75 / .16); color: var(--brass); border-color: var(--gold); }}
.ab--discrepancy {{ background: oklch(58% 0.19 25 / .14); color: var(--cinnabar); }}
.roll {{ font-size: 12px; color: var(--ink1); line-height: 2; }}
.roll b {{ color: var(--ink0); font-variant-numeric: tabular-nums; }}
.rc {{ display: inline-block; font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums;
  padding: 0 5px; border-radius: 5px; }}
.ci {{ display: inline-block; width: 9px; height: 9px; border-radius: 999px; }}
.ci--ok {{ background: var(--ok); }} .ci--bad {{ background: var(--bad); }}
.ci--run {{ background: var(--run); }} .ci--na {{ background: var(--rule); }}
.appr {{ color: var(--moss); font-weight: 600; }}
.appr-c {{ text-align: center; }}
.flag {{ display: inline-block; font-size: 10px; font-weight: 600; padding: 1px 6px; margin-left: 6px;
  border-radius: 5px; vertical-align: middle; text-transform: uppercase; letter-spacing: .03em; }}
.flag--ci {{ background: oklch(75% 0.13 85 / .16); color: oklch(52% 0.11 75); }}
.flag--conflict {{ background: oklch(60% 0.19 25 / .13); color: var(--cinnabar); }}
.legend {{ display: flex; flex-wrap: wrap; gap: 14px; margin: 4px 0 0; font-size: 12px; color: var(--ink2); }}
.legend span {{ display: inline-flex; align-items: center; gap: 5px; }}
.sw {{ width: 10px; height: 10px; border-radius: 3px; display: inline-block; border: 1px solid transparent; }}
.sw--moss {{ background: oklch(58% 0.11 150 / .5); }}
.sw--brass {{ background: oklch(64% 0.11 75 / .6); }}
.sw--stone {{ background: oklch(66% 0.015 260 / .4); }}
.sw--gold {{ background: oklch(58% 0.11 150 / .3); border-color: var(--gold); }}
footer {{ margin-top: 40px; color: var(--ink2); font-size: 12px; line-height: 1.7; }}
footer a {{ color: var(--ink1); }}
@media (max-width: 640px) {{ .cards {{ grid-template-columns: repeat(2, 1fr); }} }}
</style></head>
<body><div class="wrap">
<header>
  <h1>formal-conjectures &middot; review queue</h1>
  <div class="sub">A review dashboard for open PRs, in the spirit of mathlib's queueboard. Generated {stamp}.</div>
</header>
<div class="cards">
  <div class="card"><div class="v">{total}</div><div class="k">open PRs</div></div>
  <div class="card"><div class="v">{n_review}</div><div class="k">ready for review</div></div>
  <div class="card"><div class="v">{n_stmt}</div><div class="k">of those, statements</div></div>
  <div class="card"><div class="v">{oldest}d</div><div class="k">longest waiting</div></div>
</div>
{sections}
<div class="legend">
  <span><span class="sw sw--moss"></span> unconditional</span>
  <span><span class="sw sw--brass"></span> conditional</span>
  <span><span class="sw sw--stone"></span> not yet audited</span>
  <span><span class="sw sw--gold"></span> signed by a named reviewer</span>
</div>
<footer>
  The <strong>audit</strong> column joins each Erdos-problem PR to the public fidelity audit: whether the
  linked proof is unconditional, rests on a named assumption (conditional), or carries a signed reviewer
  verdict. It reports a fact; the merge decision is the maintainer's.<br>
  Ready for review = not draft, no changes requested, no merge conflict, CI not failing. The waiting groups
  sort by idle time; ready-for-review by how long each has been open. &check; counts approvals, &pm; is lines changed.<br>
  PR data via the GitHub API; problem-audit data via the
  <a href="https://erdos.constellate.science">Erdos frontier</a> snapshot. Not affiliated with the
  formal-conjectures maintainers.
</footer>
</div></body></html>
"""


if __name__ == "__main__":
    main()
