#!/usr/bin/env bash
# Extract commits in a git range with their Azure DevOps PR and work item ids.
# Usage: collect-changes.sh <range>     e.g. collect-changes.sh "release/v1.29..release/v1.30"
# Output (TSV): sha  date  author  subject  pr_ids  work_item_ids   (ids comma-separated)
set -euo pipefail

range="${1:?usage: collect-changes.sh <previous>..<release>}"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "error: not inside a git repository" >&2; exit 1
fi

# Validate both ends of the range so a typo fails loudly instead of returning nothing.
for ref in "${range%%..*}" "${range##*..}"; do
  [ -z "$ref" ] && continue
  git rev-parse --verify --quiet "$ref^{commit}" >/dev/null \
    || { echo "error: ref not found: $ref (try: git fetch --all --tags)" >&2; exit 1; }
done

printf 'sha\tdate\tauthor\tsubject\tpr_ids\twork_item_ids\n'

# Records separated by \x1e, fields by \x1f, so multi-line bodies survive.
git log "$range" --format='%H%x1f%as%x1f%an%x1f%s%x1f%B%x1e' |
awk 'BEGIN { RS = "\x1e"; FS = "\x1f" }
NF >= 5 {
  sha = $1; sub(/^\n+/, "", sha)
  subject = $4; gsub(/\t/, " ", subject)
  msg = $4 "\n" $5

  prs = ""; seen_pr = ""
  s = msg
  while (match(s, /Merged PR [0-9]+/)) {
    id = substr(s, RSTART + 10, RLENGTH - 10)
    if (index("," seen_pr ",", "," id ",") == 0) { seen_pr = seen_pr (seen_pr ? "," : "") id }
    s = substr(s, RSTART + RLENGTH)
  }
  prs = seen_pr

  wis = ""
  s = msg
  while (match(s, /(AB)?#[0-9]+/)) {
    tok = substr(s, RSTART, RLENGTH); sub(/^(AB)?#/, "", tok)
    if (index("," prs ",", "," tok ",") == 0 && index("," wis ",", "," tok ",") == 0)
      wis = wis (wis ? "," : "") tok
    s = substr(s, RSTART + RLENGTH)
  }

  printf "%s\t%s\t%s\t%s\t%s\t%s\n", sha, $2, $3, subject, prs, wis
}'
