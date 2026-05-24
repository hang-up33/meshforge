#!/usr/bin/env bash
# Run Codex reviewer agent against the current branch's diff vs base.
# Usage: scripts/codex-review.sh [base_branch]
#   base_branch defaults to "main".
# Output: .codex/reviews/review-<timestamp>.md (path printed to stdout).

set -euo pipefail

base="${1:-main}"
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

out_dir=".codex/reviews"
mkdir -p "$out_dir"
ts="$(date +%Y%m%d-%H%M%S)"
branch="$(git rev-parse --abbrev-ref HEAD)"
safe_branch="${branch//\//_}"
out="$out_dir/review-${safe_branch}-${ts}.md"
diff_file="$(mktemp -t codex-review-diff.XXXXXX)"
trap 'rm -f "$diff_file"' EXIT

git fetch --quiet origin "$base" 2>/dev/null || true
merge_base="$(git merge-base "origin/$base" HEAD 2>/dev/null || git merge-base "$base" HEAD)"
git diff "$merge_base"...HEAD > "$diff_file"

if [[ ! -s "$diff_file" ]]; then
  echo "No diff between $base ($merge_base) and HEAD ($branch). Nothing to review." >&2
  exit 0
fi

if ! command -v codex >/dev/null 2>&1; then
  cat >&2 <<'MSG'
codex CLI not found in PATH.
Install per https://developers.openai.com/codex/cli (e.g. `brew install codex` if available),
then re-run this script.
MSG
  exit 2
fi

prompt_file="$(mktemp -t codex-review-prompt.XXXXXX)"
trap 'rm -f "$diff_file" "$prompt_file"' EXIT

{
  echo "Review the following diff (branch '$branch' vs '$base') as the 'reviewer' agent."
  echo "Read AGENTS.md and README.md for project context — meshforge is in a strict step-by-step build mode."
  echo
  echo "=== DIFF (base=$merge_base) ==="
  cat "$diff_file"
} > "$prompt_file"

codex exec \
  --agent reviewer \
  --color never \
  -C "$repo_root" \
  -o "$out" \
  - < "$prompt_file"

echo "$out"
