# formal-conjectures review board

A review-queue dashboard for the open pull requests on
[google-deepmind/formal-conjectures](https://github.com/google-deepmind/formal-conjectures),
in the spirit of mathlib's [queueboard](https://leanprover-community.github.io/queueboard/).
It turns the open PRs into one page so maintainers can see what is ready to
review, what is waiting on its author, and what has been waiting longest.

**Live:** https://williamjblair.github.io/fc-review-board

This is a proof-of-concept and a neutral tool. It is not affiliated with the
formal-conjectures maintainers, and where and how a board like this should live
is their call.

## What it shows

PRs are grouped into approved / ready-for-review / waiting-on-author / draft.
Ready-for-review sorts by how long each has been open; the waiting groups sort
by idle time. Each row carries CI status, approval count, size, and small flags
for merge conflicts and PRs whose CI has not run yet (often waiting on a
maintainer to approve the workflow).

### The audit column

For PRs that touch `FormalConjectures/ErdosProblems/<N>.lean`, the board joins
each problem to the public [Erdős fidelity audit](https://erdos.constellate.science)
and shows, per problem, whether the linked proof was found unconditional, rests
on a named assumption (conditional), or carries a signed verdict from a named
reviewer. It reports a fact next to the PR; the merge decision stays the
maintainer's. A PR touching many problems is summarised as a count breakdown
rather than a long list of badges.

## How it works

`generate.py` reads two inputs and writes a single self-contained `index.html`:

- open PRs, via `gh pr list` (the GitHub API);
- the audit feed, a `verdicts.json` snapshot (configurable, see below).

No server, no database, no client-side fetching. A GitHub Action
(`.github/workflows/board.yml`) regenerates the page hourly and deploys it to
GitHub Pages.

## Run it locally

```bash
gh pr list -R google-deepmind/formal-conjectures --state open --limit 200 \
  --json number,title,author,labels,isDraft,createdAt,updatedAt,statusCheckRollup,reviewDecision,mergeStateStatus,latestReviews,additions,deletions,files \
  > prs.json
curl -sfL https://erdos.constellate.science/verdicts.json -o verdicts.json
python3 generate.py            # writes index.html
python3 -m http.server         # then open http://localhost:8000
```

`generate.py` uses a local `prs.json` / `verdicts.json` when present and
fetches them otherwise, so re-running is cheap.

## Configuration

The audit feed URL defaults to the Erdős frontier snapshot and is overridable
via the `VERDICTS_URL` environment variable (or a `VERDICTS_URL` repository
variable in the Action). Point it at any compatible `verdicts.json`, or at an
empty feed to drop the audit column entirely.

## Attribution

PR data comes from the GitHub API. Problem-audit data comes from the
[Erdős frontier](https://erdos.constellate.science) snapshot. The queue design
follows mathlib's queueboard.
