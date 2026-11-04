#!/bin/sh
# SessionStart hook: the acuminator MCP server is launched with uvx, so when uv
# is missing the server shows as "disconnected" with no explanation. Put the
# reason and the fix into context instead. Always exits 0: a missing tool must
# not block the session.
if command -v uvx >/dev/null 2>&1; then
  exit 0
fi
# printf is a shell builtin: no dependency on PATH for the message itself.
printf '%s\n' \
  '[acuminator plugin] uv is not installed, so the acuminator MCP server (uvx) cannot start and its tools are unavailable. Ask the user to install it and restart Claude Code:' \
  '  winget install astral-sh.uv' \
  'Alternative without winget: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
exit 0
