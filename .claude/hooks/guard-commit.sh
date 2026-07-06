#!/usr/bin/env bash
# PreToolUse(Bash) guard: block commits with the wrong email, Claude attribution, or a direct push to main.
set -euo pipefail
cmd="${1:-}"
[ -z "$cmd" ] && cmd="$(cat)"
if ! echo "$cmd" | grep -qE "\\bgit\\b.*\\b(commit|push)\\b"; then exit 0; fi
if echo "$cmd" | grep -qiE "Co-Authored-By:\s*Claude|Generated with .*Claude|Anthropic"; then
  echo "BLOCKED: no Claude/Anthropic attribution in commits." >&2; exit 2
fi
if echo "$cmd" | grep -qiE "juraj@kapusansky\.dev"; then
  echo "BLOCKED: wrong commit email — use juraj.kapusansky@gmail.com." >&2; exit 2
fi
if echo "$cmd" | grep -qE "git push .*(origin )?(main|master)\b"; then
  echo "BLOCKED: no direct push to main — branch → PR → merge." >&2; exit 2
fi
exit 0
