---
name: learn-notes
description: Capture evidence, inspect progress, resume pending quizzes, and maintain Obsidian notes for an active AI learning topic. Use for learning records and session continuity, rather than generic document editing, automatic course startup, or reminders.
---

# Learning Notes

Keep learner evidence and session history accurate across Codex chats and the registered Obsidian Vault. Read [the notes contract](../../references/notes-contract.md) and [the tool interface](../../references/tool-interface.md) before running the companion CLI.

1. Resolve the data root and topic; use `python3 <plugin-root>/scripts/learning_tools.py --root <data-root> status --topic TOPIC`. Read the mission and only the learning records and sessions relevant to the request. Machine state is outside the Vault. Do not edit it directly or assume this chat's working directory is the topic directory.
2. For resumption, report the existing position and pending question. Do not reshuffle, replace, answer, or teach past it. End the turn and wait for the user when a response is required. For answering and evaluation, follow [the quiz protocol](../../references/quiz-protocol.md). This skill can manage an already active session but does not automatically invoke `teach`.
3. For a learning record, follow [the original format](../teach/LEARNING-RECORD-FORMAT.md). Use `record-learning` with the actual evidence reference and concise summary. Mark prior knowledge as self-report. Put raw attempts and activity in sessions; HTML practice is not formal evidence. A corrected understanding can supersede an earlier record while retaining the original history.
4. For a related mission change, confirm ambiguous intent and use `mission-update --confirmed`; then update only the affected route through `route-set`. Keep valid records. A clear direct instruction to change the mission supplies confirmation. A different mission needs another topic workspace.
5. Run `sync` and inspect its result. Preserve manual edits on conflict; merge through `note-patch` with the current file hash rather than overwriting. Use `open` for a registered Vault note, preserving HTML lessons as HTML and linking assets relatively. Report an unfinished sync or merge accurately.

For revision, `review-list` supplies candidates; show their evidence and gaps. Start teaching only if the user explicitly invokes `teach`. Do not create recurring reminders from a one-time review request.
