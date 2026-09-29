#!/usr/bin/env bash
# Usage: scripts/new_worktree.sh <Wave> <Agent> [base-ref]
# Creates ~/av-wt/w<Wave>-<Agent> on branch w<Wave>/<Agent> (from base-ref, default main),
# copies .env with AV_DATA_DIR pointing at the shared data folder, and links bin/ (OPA).
# AV_WT_ROOT overrides ~/av-wt.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <Wave> <Agent> [base-ref]" >&2
  exit 2
fi
wave=$1 agent=$2 base=${3:-main}
[[ $wave =~ ^[0-9]+$ && $agent =~ ^[A-Za-z0-9_-]+$ ]] || { echo "bad wave/agent: $wave $agent" >&2; exit 2; }

repo=$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)
wt_root=${AV_WT_ROOT:-$HOME/av-wt}
dest=$wt_root/w$wave-$agent
branch=w$wave/$agent

# The shared data folder: the caller's AV_DATA_DIR, else main's .env, else ~/av-data.
data=${AV_DATA_DIR:-}
if [[ -z $data && -f $repo/.env ]]; then
  data=$(grep -E '^AV_DATA_DIR=' "$repo/.env" | tail -1 | cut -d= -f2- || true)
fi
data=${data:-$HOME/av-data}
data=${data/#\~/$HOME}

if [[ -e $dest ]]; then
  echo "already exists: $dest" >&2
  exit 1
fi
mkdir -p "$wt_root" "$data"

if git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
  git -C "$repo" worktree add "$dest" "$branch"
else
  git -C "$repo" worktree add -b "$branch" "$dest" "$base"
fi

umask 077
if [[ -f $repo/.env ]]; then
  grep -v -E '^AV_DATA_DIR=' "$repo/.env" > "$dest/.env" || true
else
  : > "$dest/.env"
fi
echo "AV_DATA_DIR=$data" >> "$dest/.env"

# bin/ is git-ignored (the OPA binary from `make setup`); share main's copy.
if [[ -d $repo/bin && ! -e $dest/bin ]]; then
  ln -s "$repo/bin" "$dest/bin"
fi

echo "worktree: $dest"
echo "branch:   $branch"
echo "data dir: $data"
echo "next:     cd $dest && uv sync && claude"
