#!/bin/sh
# the pinned CLI (2.1.x ships a native linux-x64 binary; no node needed at run time)
exec /opt/claude-cli/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe "$@"
