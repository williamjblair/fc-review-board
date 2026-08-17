# Open Formal Workflows

**Formal Conjectures · Review, Verification & Preservation**

A bounded review-evidence pilot plus review-queue dashboard for open pull requests on
[google-deepmind/formal-conjectures](https://github.com/google-deepmind/formal-conjectures),
in the spirit of mathlib's [queueboard](https://leanprover-community.github.io/queueboard/).
The default view follows the review, verification, and preservation loop in
[Formal Conjectures issue #4394](https://github.com/google-deepmind/formal-conjectures/issues/4394)
for one selected calibration case. The existing queue remains available so
maintainers can see what is ready for review, what is waiting on its author,
and what has been waiting longest.

**Live:** https://williamjblair.github.io/fc-review-board

Open Formal Workflows is the pilot program name; this deployment is scoped to
Formal Conjectures review, verification, and preservation. The repository name
and public URL remain `fc-review-board` for continuity.

This is a proof-of-concept and a neutral tool. It is not affiliated with the
formal-conjectures maintainers, and where and how a board like this should live
is their call.

Formal Conjectures remains canonical for declarations, PR state, CI, and
maintainer decisions. This board is an advisory projection. Its checks,
ReviewReport, queue labels, and external execution evidence cannot set approval,
merge acceptance, or mathematical truth. Vela/problems.science may later link
to the evidence, but it is not an authority input here.

## The bounded pilot

The selected case is public PR
[#4884](https://github.com/google-deepmind/formal-conjectures/pull/4884),
`Erdos427.erdos_427`. It is a useful negative calibration because the linked
proof declares a Shiu-theorem condition and the retained Comparator replay
ended with an invocation `error`. The typed result keeps result parsing
`not_attempted` and axiom policy `not_evaluated`; terminal text is retained by
hash but never converted into a failing property verdict.

The Pilot view collects, without merging their meanings:

- the exact FC PR head, source file, linked proof, audit core, and observation;
- a derived LeanEval-shaped multi-file profile with exact interface and tool pins;
- content-addressed preparation files, execution image, stdout, and stderr;
- typed audit and Comparator outcomes;
- a fresh GitHub head observation, rendered as current or stale; and
- an advisory ReviewReport whose maintainer disposition is always unfilled.

The Method view states the loop, non-goals, and what an independent pilot would
need to demonstrate. No reviewer buy-in, upstream adoption, partner status, or
Econlib integration is claimed.

## What it shows

PRs are grouped into approval-recorded / ready-for-review / waiting-on-author / draft.
Ready-for-review sorts by **waiting** time, not by age: a pull request that sat
with its author for two months and has been on the queue for a week ranks below
one that has waited a fortnight throughout. The author and draft groups sort by
idle time instead, and show `--` under waiting, since a statement that has never
been ready for review has no queue time to report.

Each row carries CI status, approval count, size, and small flags:

- **needs rebase** when a branch's checks predate a breaking change on `main`,
  naming which one. Two so far: `FormalConjectures.Util.ProblemImports` was
  deleted in July, and the `openClassical` linter was switched on in August. 245
  of the 279 open PRs predate one of them, and 213 of those still show a passing
  tick, earned against a `main` that has moved. Predating a change is not the
  same as being broken by it, and not a mark against the PR: of six sampled and
  rebuilt, three needed only the import swap, two also needed `open Classical`
  dropped, and one had real type errors.
- **CI *n* old** when the checks last ran a month or more ago, for the branches
  that predate nothing in particular.
- **already on main?** when every file a PR adds is already on the base branch,
  so the work may have landed another way. A prompt rather than a verdict: the
  data cannot tell an added file from one that was only appended to. It found
  #4071, #4072 and #4285.
- **the assignee**, when a PR has one. Sparse, because people rarely set one,
  which is the thing worth changing if several people start reviewing at once.
- merge conflicts, and PRs whose CI has not run at all (usually waiting on a
  maintainer to approve the workflow for a first-time contributor).
- an exact **PR audit** label when that pull request is one of the five frozen
  `formal-conjectures.pr-audit.v1` cases. The label comes from the same
  validated core and observation records used by the native summary, skill,
  evaluation packet, and Vela adapter, and links to the commit-pinned record.
  `clean`, `needs revision`, `inconclusive`, and `unavailable` remain distinct; none
  means approval, merge readiness, mathematical truth, or Repository authority.

Besides the queue there is a **Pick one up** view: the conjecture issues with no
missing prerequisites, oldest first, split into the ones nothing has started and
the ones an open pull request already claims. 96 of 540 are already claimed, and
nothing else surfaces that, since the site knows what problems exist and GitHub
knows what is in flight but nothing joins them.

There is deliberately no view of the problems themselves. The repository's own
site does that better, with an AMS-subject matrix and growth over time. This
board is about what is in flight.

Filters cover the source collection (Erdős, OEIS, Wikipedia, arXiv, papers and
the rest), whether a PR is a statement or infrastructure, CI state, and the
audit. Collection comes from the repo's own labels and covers 232 of the 290
open PRs, which is the useful axis if several people are reviewing and want to
work in an area they know.

The `ams-*` subject labels would be the better axis, but exactly one open PR
carries one: they get applied to issues rather than pull requests.

### The problem audit column (optional, off by default)

Set a `VERDICTS_URL` repository variable pointing at a `verdicts.json` and an
extra column appears, showing per problem whether a linked proof was found
unconditional, rests on a named assumption, or carries a signed verdict from a
named reviewer. It reports a fact next to the PR; the merge decision stays the
maintainer's.

With no such variable the board fetches nothing but GitHub, and the column, its
filter and the Fidelity view are not rendered. That is the default because a
review dashboard should not depend on a third-party service to draw a column,
and because most of what it would report is Erdős-specific: of 3503 statements
in the repository, 295 carry a `formal_proof` link at all, and 243 of those are
Erdős problems.

### The exact per-PR audit column

The hosted build checks out the public audit prototype at exact commit
`50fb575fadfc710f2da66cba1d3909429f9ba25e` and tree
`7213fa92375028e13797fc89f2cc300fc0568869`. `fc_pr_audit.py` verifies the
validator and schema bytes, validates all five core and observation records,
checks their pair bindings and roots, and emits a small closed projection. The
board joins that projection by native pull-request number. Unsupported or
drifted records fail the build rather than losing or reinterpreting a status.

This prototype is program-owned evidence on a contributor fork. It is not an
upstream Formal Conjectures installation or maintainer decision.

`review_report.py` builds and validates the reader-facing ReviewReport v1
profile used by the bounded pilot. It validates the same pinned
core/observation pair, preserves its
advisory synthesis byte-for-byte in meaning, and places current GitHub state in
a separate head-bound observation section. It never derives maintainer
disposition from the audit, CI, mergeability, or review state.

An optional `--comparator-json` attachment accepts only the typed
`formal-conjectures.comparator-outcome.v1` contract. The report binds its
canonical bytes by SHA-256 and keeps invocation, structured-result parsing,
and policy outcome separate. An invocation exception therefore remains
`error` / `not_evaluated`; terminal text can never become a policy failure.

Optional `--reviewer-attributions-json` evidence treats `human` and `ai` as
peer attributed reviewer kinds. Both must name the reviewer, method, exact
Git commit/path/hash inputs, scope, independence or shared dependencies, and
content-addressed results. Kind is not a quality score, and neither kind can
set maintainer disposition. The report uses source-owned Git provenance; it
does not add an attempt, session, or parallel memory system.

`pilot.py` validates the generated ReviewReport again at the file/render
boundary, binds it to the retained files under `pilot/`, and fails closed on
component drift, a mismatched #4884 identity, or any filled maintainer
disposition. The scheduled build refreshes the GitHub observation and rebuilds
this projection on every run.


## How it works

PR state comes from [queueboard](https://github.com/leanprover-community/queueboard-core),
the tool mathlib's own review dashboard is built on. `sync.sh` clones it,
repoints three mathlib-specific constants (default branch, and two hardcoded
mathlib4 URLs), runs its pipeline against formal-conjectures and writes
`snapshot.json`. The scheduled build also refreshes #4884's GitHub head,
rebuilds its ReviewReport from the exact audit checkout and retained typed
Comparator outcome, and validates the pilot component bindings. `generate.py`
reads those projections plus the optional audit feed and writes a single
self-contained `index.html`.

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

A GitHub Action (`.github/workflows/board.yml`) does this on a schedule and
deploys to GitHub Pages. The cron asks for hourly; GitHub spaces scheduled runs
out under load, so in practice it lands every two to three hours, and Pages
takes several more minutes to serve the result.

## Run it locally

Needs `gh` (authenticated), `jq` and [`uv`](https://docs.astral.sh/uv/).

```bash
./sync.sh                      # writes snapshot.json (a few minutes)
python3 generate.py            # writes index.html
python3 -m http.server         # then open http://localhost:8000
```

`sync.sh` keeps its working tree in `.queueboard/`, so a second run reuses the
clone. `generate.py` on its own is instant once `snapshot.json` exists.

## Configuration

The optional problem-audit feed is absent by default. Set `VERDICTS_URL` in the
environment (or as a repository variable in the Action) to a compatible
`verdicts.json` to enable it. The exact per-PR audit projection has no moving
configuration: its public source commit, tree, validator, schemas, and fixture
roots are reviewed pins in `fc_pr_audit.py` and the workflow.

## Attribution

PR state and queue timings come from
[queueboard](https://github.com/leanprover-community/queueboard-core), by Johan
Commelin, Michael Rothgang and Bryan Gin-ge Chen, used unmodified apart from
three repointed constants.
