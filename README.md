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
Ready-for-review sorts by **waiting** time, not by age: a pull request that sat
with its author for two months and has been on the queue for a week ranks below
one that has waited a fortnight throughout. The author and draft groups sort by
idle time instead, and show `--` under waiting, since a statement that has never
been ready for review has no queue time to report.

Each row carries CI status, approval count, size, and small flags:

- **CI *n* old** when the checks last ran a month or more ago. A passing tick is
  only as good as the `main` it ran against, and 111 of the open PRs currently
  import a module that was deleted in July while still showing green. The flag
  reports the age and leaves the judgement to the reviewer.
- **the assignee**, when a PR has one. Sparse, because people rarely set one,
  which is the thing worth changing if several people start reviewing at once.
- merge conflicts, and PRs whose CI has not run at all (usually waiting on a
  maintainer to approve the workflow for a first-time contributor).

Filters cover the source collection (Erdős, OEIS, Wikipedia, arXiv, papers and
the rest), whether a PR is a statement or infrastructure, CI state, and the
audit. Collection comes from the repo's own labels and covers 232 of the 290
open PRs, which is the useful axis if several people are reviewing and want to
work in an area they know.

The `ams-*` subject labels would be the better axis, but exactly one open PR
carries one: they get applied to issues rather than pull requests.

### The audit column

For PRs that touch `FormalConjectures/ErdosProblems/<N>.lean`, the board joins
each problem to the public [Erdős fidelity audit](https://erdos.constellate.science)
and shows, per problem, whether the linked proof was found unconditional, rests
on a named assumption (conditional), or carries a signed verdict from a named
reviewer. It reports a fact next to the PR; the merge decision stays the
maintainer's. A PR touching many problems is summarised as a count breakdown
rather than a long list of badges.

## How it works

PR state comes from [queueboard](https://github.com/leanprover-community/queueboard-core),
the tool mathlib's own review dashboard is built on. `sync.sh` clones it,
repoints three mathlib-specific constants (default branch, and two hardcoded
mathlib4 URLs), runs its pipeline against formal-conjectures and writes
`snapshot.json`. `generate.py` reads that plus the audit feed and writes a
single self-contained `index.html`.

Leaning on queueboard means the parts that break when GitHub changes a response
shape, or when the repository adopts a new label, are maintained upstream. What
lives here is the part nobody upstream would maintain: the audit join, the
statement/infra split, and the page itself.

It also brings **waiting** - the time a PR has actually spent on the review
queue, reconstructed from its timeline, excluding spells when the ball was in
the author's court. That is a fairer ranking than age, and it is what the ready
-for-review table sorts on. PRs whose timeline could not be reconstructed show
`--` and fall back to age.

`sync.sh` is deliberately stateless: no cached PR data, nothing to go stale or
need repairing. It uses two queries - a cheap one (~1 rate-limit point) for
every open PR, and an expensive one (~5 points) only for PRs on the review
queue, since only those need timings. Fetches run eight at a time, since
several hundred half-second round trips in series is most of a slow run. A full
run is around 600 of the 5000 hourly points and about a minute. If the budget will not cover the timings it skips
them and the board still builds, with those PRs falling back to age.

A GitHub Action (`.github/workflows/board.yml`) does this hourly and deploys to
GitHub Pages.

## Run it locally

Needs `gh` (authenticated), `jq` and [`uv`](https://docs.astral.sh/uv/).

```bash
curl -sfL https://erdos.constellate.science/verdicts.json -o verdicts.json
./sync.sh                      # writes snapshot.json (a few minutes)
python3 generate.py            # writes index.html
python3 -m http.server         # then open http://localhost:8000
```

`sync.sh` keeps its working tree in `.queueboard/`, so a second run reuses the
clone. `generate.py` on its own is instant once `snapshot.json` exists.

## Configuration

The audit feed URL defaults to the Erdős frontier snapshot and is overridable
via the `VERDICTS_URL` environment variable (or a `VERDICTS_URL` repository
variable in the Action). Point it at any compatible `verdicts.json`, or at an
empty feed to drop the audit column entirely.

## Attribution

PR state and queue timings come from
[queueboard](https://github.com/leanprover-community/queueboard-core), by Johan
Commelin, Michael Rothgang and Bryan Gin-ge Chen, used unmodified apart from
three repointed constants. Problem-audit data comes from the
[Erdős frontier](https://erdos.constellate.science) snapshot.
