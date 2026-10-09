# AI Learning Companion

Portable macOS Codex plugin. Python standard library only; preserve the pinned teach FORMAT files, original invocation policy, and all bundled license notices.

- Source: `plugins/ai-learning-companion/`; user data and config are outside this repository.
- Formal answers happen in Codex. Browser practice and reading are not mastery evidence.
- Run `python3 -m unittest discover -s tests -v`; actual Chrome rendering needs `RUN_RENDER_INTEGRATION=1`.
- Build `python3 scripts/build_release.py`. Never package user Vaults, state, configuration, chat logs, or `.git/`.
- Only mark diagrams verified after rendering and visually inspecting them.
- Preserve human note edits and idempotent quiz/sync behavior.
