"""Claude Code PreToolUse hook for Bash: refuse heredocs that carry backslash escapes.

In this project's Git Bash, a heredoc body with \\n, \\t and similar does not reach Python, C or a
patch as written: escapes turned into real newlines and tabs inside generated C strings (xnu 2122,
Metal VBLUR 2026-11-24). Content with backslashes must be written to a file with the Write tool
(scratchpad), then the file is run or read. See AGENTS.md, first rule.
Exit 2 blocks the call and shows stderr to the agent.
"""
import json
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
command = (data.get('tool_input') or {}).get('command') or ''
if re.search(r'<<-?\s*[\'"]?[A-Za-z_]+', command) and re.search(r'\\\\|\\[ntr0xabfve"\']', command):
    sys.stderr.write(
        'BLOCKED by tools/hooks/heredoc-guard.py (AGENTS.md rule 1): this heredoc contains backslash '
        'escapes, and in Git Bash they get mangled before they reach Python/C/patches. Write the content '
        'to a file with the Write tool (scratchpad) and run or read that file instead.\n')
    sys.exit(2)
sys.exit(0)
