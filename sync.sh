#!/usr/bin/env bash
#
# Produce snapshot.json for generate.py, using queueboard - the tool mathlib's
# review dashboard is built on - to do the fetching and the state classification.
#
# Two queries, deliberately:
#   basic_pr_info  (~1 rate-limit point each) for every open PR. Carries labels,
#                  CI rollup, files, diff size, reviews: everything the board
#                  needs except timings.
#   pr_info        (~5 points each) for every open PR. This one walks the
#                  timeline, which is what makes `total_queue_time` possible.
#
# A full cold run costs roughly 900 points and a few minutes, so there is no
# cache and no incremental sync to get wrong. Everything is refetched each run.
#
# Usage: QB_REF=master ./sync.sh   (expects gh, jq, uv on PATH)

set -euo pipefail

REPO="${QB_REPO:-google-deepmind/formal-conjectures}"
BASE="${QB_BASE:-main}"
OWNER="${REPO%%/*}"
NAME="${REPO##*/}"
WORK="${QB_WORK:-$PWD/.queueboard}"
CORE="$WORK/core"

mkdir -p "$WORK"

remaining () { gh api graphql -f query='{ rateLimit { remaining } }' --jq '.data.rateLimit.remaining' 2>/dev/null || echo 0; }

# Always start from a pristine upstream tree. The patches below are applied to
# a working copy, so a reused clone would already carry them from the previous
# run - the branch substitution would then match nothing and the check below
# would fire. Resetting also picks up upstream changes on a warm tree, which is
# the whole point of not forking.
if [ ! -d "$CORE/.git" ]; then
  echo "==> cloning queueboard-core"
  git clone --quiet --depth 1 ${QB_REF:+--branch "$QB_REF"} \
    https://github.com/leanprover-community/queueboard-core.git "$CORE"
else
  echo "==> refreshing queueboard-core"
  git -C "$CORE" fetch --quiet --depth 1 origin ${QB_REF:-HEAD}
  git -C "$CORE" reset --quiet --hard FETCH_HEAD
  git -C "$CORE" clean -qfd
fi
( cd "$CORE" && uv sync --quiet )

# queueboard hardcodes mathlib's default branch and PR URLs. Three constants;
# patched here rather than forked so the clone stays a clean upstream checkout.
#
# Each substitution is checked. If upstream ever renames or parameterises one
# of these, the pattern stops matching, and a silent no-op would leave the
# board looking for a branch this repository does not have - a green run with
# an empty review queue. Better to fail here and keep the last good deploy.
repoint () {  # description, pattern, replacement, file...
  local what="$1" from="$2" to="$3"; shift 3
  local f hits total=0
  for f in "$@"; do
    hits=$(grep -c -- "$from" "$f" || true)
    total=$(( total + hits ))
    [ "$hits" -gt 0 ] && sed -i.bak "s|$from|$to|g" "$f"
  done
  if [ "$total" -eq 0 ]; then
    echo "error: could not repoint $what." >&2
    echo "  Nothing in queueboard-core matched '$from'." >&2
    echo "  Upstream has probably changed; the patch in sync.sh needs updating." >&2
    exit 1
  fi
  echo "    $what: $total occurrence(s)"
}

echo "==> repointing queueboard at $REPO ($BASE)"
repoint "default branch" '"master"' "\"$BASE\"" \
  "$CORE/src/queueboard/compute_dashboard_prs.py" "$CORE/src/queueboard/dashboard.py"
repoint "repository URLs" "leanprover-community/mathlib4" "$REPO" \
  "$CORE/src/queueboard/compute_dashboard_prs.py" "$CORE/src/queueboard/dashboard_data.py"

# A patched tree that still mentions mathlib4 in the URL builders means a
# substitution half-applied; catch that too.
if grep -rq "leanprover-community/mathlib4" \
     "$CORE/src/queueboard/dashboard_data.py" 2>/dev/null; then
  echo "error: dashboard_data.py still points at mathlib4 after patching." >&2
  exit 1
fi

cd "$WORK"
: > stubborn_prs.txt
mkdir -p data processed_data
# Reviewer suggestions are a mathlib feature we do not use, but the pipeline
# insists the file exists.
[ -f reviewer-topics.json ] || echo '{}' > reviewer-topics.json

# GitHub 502s on individual PR queries often enough that one must not end the
# run. Retry with backoff; if a PR still will not come back, skip it and carry
# on - a board missing one row beats no board.
fetch_pr () {  # query-file, pr-number, destination
  local q="$1" n="$2" dest="$3" tmp attempt
  mkdir -p "$(dirname "$dest")"
  tmp="$(mktemp)"
  for attempt in 1 2 3 4 5; do
    if gh api graphql -f owner="$OWNER" -f repo="$NAME" -F prNumber="$n" \
         -F query=@"$q" > "$tmp" 2>/dev/null \
       && jq -e . "$tmp" >/dev/null 2>&1 \
       && ! jq -e 'has("errors")' "$tmp" >/dev/null 2>&1; then
      jq '.' "$tmp" > "$dest"; rm -f "$tmp"; return 0
    fi
    sleep $(( attempt * 4 ))
  done
  rm -f "$tmp"; return 1
}
export -f fetch_pr
export OWNER NAME

# 438 round trips at half a second each is four minutes of waiting on the
# network in series. GitHub is happy with modest concurrency, so fan out.
JOBS="${QB_JOBS:-8}"

fetch_all () {  # query-file, dest-pattern (%s -> PR number), list-file
  local q="$1" pat="$2" list="$3"
  QB_Q="$q" QB_PAT="$pat" xargs -P "$JOBS" -I{} bash -c \
    'dest=$(printf "$QB_PAT" "$1"); fetch_pr "$QB_Q" "$1" "$dest" || { rm -rf "$(dirname "$dest")"; echo "$1"; }' \
    _ {} < "$list"
}

# --- open PR listings, in the shape dashboard_data expects --------------------
query () {
  echo "query(\$endCursor: String) {
    search(query: \"repo:$REPO $1\", type: ISSUE, first: 25, after: \$endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes { ... on PullRequest {
        number url author { ... on User { login url } } title state updatedAt
        labels(first: 10, orderBy: {direction: DESC, field: CREATED_AT}) {
          nodes { name color url } } } }
    } }"
}
echo "==> listing open PRs"
gh api graphql --paginate --slurp -f query="$(query 'sort:updated-asc is:pr state:open -label:merge-conflict -label:blocked-by-other-PR')" \
  | jq '{"output": .}' > all-open-PRs-1.json
for f in all-open-PRs-2a all-open-PRs-2b all-open-PRs-3; do echo '{"output":[]}' > "$f.json"; done

jq -r '.output[].data.search.nodes[].number' all-open-PRs-1.json | sort -n > prs.txt
echo "    $(wc -l < prs.txt | tr -d ' ') open"

# --- pass 1: cheap metadata for every PR --------------------------------------
echo "==> basic metadata for every PR"
failed=$(fetch_all "$CORE/src/queueboard/queries/basic_pr_info.graphql" \
  "data/%s-basic/basic_pr_info.json" prs.txt)
[ -n "$failed" ] && echo "    unavailable: $(echo "$failed" | tr '\n' ' ')" >&2 || true

build () {
  # Chatty on stdout, and its warnings are about mathlib conventions we do not
  # follow, so stdout is dropped. stderr is kept: a real failure should be
  # visible in the log rather than swallowed.
  ( cd "$WORK"
    uv run --project "$CORE" python -m queueboard.process >/dev/null
    uv run --project "$CORE" python -m queueboard.dashboard_data \
      all-open-PRs-1.json all-open-PRs-2a.json all-open-PRs-2b.json all-open-PRs-3.json \
      >/dev/null )
}

# A first pass tells us who is on the review queue; only those need timings.
echo "==> classifying"
build
# Every open PR gets a timeline. Restricting this to the review queue left the
# waiting column empty for the author and draft buckets, which is half the
# board. In series that would have been unaffordable; in parallel it is seconds.
cp prs.txt queue.txt
echo "    $(wc -l < queue.txt | tr -d ' ') PRs need timings"

# --- pass 2: timelines for the rows people actually read -------------------------------
echo "==> timelines (rate budget: $(remaining))"
# One budget check for the whole pass rather than one per PR: with requests in
# flight concurrently there is no safe moment between them anyway. Each of
# these costs about five points.
need=$(( $(wc -l < queue.txt) * 5 + 200 ))
if [ "$(remaining)" -lt "$need" ]; then
  echo "    skipping: needs ~$need points, $(remaining) left." >&2
  echo "    The board still builds; these PRs fall back to age." >&2
else
  fetch_all "$CORE/src/queueboard/queries/pr_info.graphql" "data/%s/pr_info.json" queue.txt >/dev/null
  # Full data supersedes the basic record.
  while read -r n; do [ -f "data/$n/pr_info.json" ] && rm -rf "data/$n-basic"; done < queue.txt
fi

echo "==> rebuilding with timings"
build
cp api/snapshot.json "${QB_OUT:-$OLDPWD}/snapshot.json"
echo "==> wrote snapshot.json ($(jq '.prs | length' api/snapshot.json) PRs, budget left $(remaining))"
