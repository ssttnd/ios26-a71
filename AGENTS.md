# Working on ios-a71

**RULE 1, NO EXCEPTIONS: never put backslash escapes (`\n`, `\t`, `\\`, `\"` ...) in a shell heredoc or inline
`python -c` / `echo`.** In this Git Bash they are mangled on the way and land in C strings and patches as real
newlines and tabs (broke xnu 2122 and the Metal VBLUR edit on 2026-11-24). Write such content into a file with the
file-writing tool (scratchpad), then run or read that file. For Claude, `.claude/settings.json` runs
`tools/hooks/heredoc-guard.py`, which blocks these Bash calls; Codex and other agents have no guard, so obey this
rule by hand.

- Every new chat or session (Claude, ChatGPT/Codex) starts by turning on Remote Control for that chat. Do it once,
  only at the very start of a new chat, not again later in the same chat.
- Read `docs/WORKFLOW.md` (how to drive the phone, logs, flashing, packages, CI, the PC reboot-to-TWRP command)
  and keep it current when a procedure changes.
- Read `NOTES.md` before starting: current state, blockers, next action. Older Redmi history is in
  `docs/sweet-history-notes.md`; search it, do not read it in full.
- The user switches agents often. Update the handoff in `NOTES.md` after each milestone and before stopping:
  commits, CI run IDs, exact build and boot results, unfinished work. Separate observations from guesses.
- Work on Windows from this folder. Do not depend on WSL. The kernel builds in GitHub Actions.
- The phone boots iOS from its `boot` partition; there is no `fastboot boot`. Logs come over USB or from TWRP.
- Test images may be written to `boot` without asking, verified by hash, while debugging. Restore image:
  `backup/2026-11-06/boot.img`. Confirm every other destructive step first. Keep bootloaders, recovery, modem,
  persist and the backups intact.
- Do not start background jobs that open windows on the user's desktop.
- Keep device dumps, serial numbers, firmware and Apple files out of git.
