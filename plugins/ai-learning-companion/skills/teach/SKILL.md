---
name: teach
description: Teach the user a new skill or concept, within this workspace.
---

# Teach: Codex entry point

Use this skill only when the user explicitly selects `teach`. Other companion skills must not automatically invoke it. This is a stateful teaching workspace over multiple sessions, using the user's language.

## Load the complete instructions first

**Before any new lesson, diagnosis, planning, review, or resumption, read all three files in full:**

1. [TEACHING-GUIDE.md](./TEACHING-GUIDE.md): the complete enhanced teaching workflow, upstream knowledge/skills/wisdom framework, HTML lessons and references, source quality, learning records, and original FORMAT links.
2. [Tool interface](../../references/tool-interface.md): current CLI commands, schemas, paths, state transitions, and conflict handling.
3. [Quiz protocol](../../references/quiz-protocol.md): public/private question handling, waiting, submission, evaluation, and evidence.

If a read is truncated, read the remaining sections before acting. This short entry point is a loader and a guard list, not a substitute for the guide. The full teaching content is preserved there; do not invent a different workflow from this summary.

## Resolve the topic and inspect state

Verify the active Codex topic workspace or an absolute topic directory explicitly supplied by the user: `<data-root>/学习笔记库/主题/<topic-id>/`. A shell-only `cd` does not change the chat workspace. Resolve data root through the interface, then use `status --topic TOPIC` and read mission, relevant learning evidence, preferences, and route before choosing the next step. Machine state belongs outside the Vault and is written through the CLI.

Use `python3 <plugin-root>/scripts/learning_tools.py --root <data-root> <command>` with actual paths and file arguments for bodies. Initialize a missing topic only once its real ID, title, mission, and success criteria are known.

## Essential guards

- New topics: at most six startup diagnostic questions, one at a time. The user may shorten or skip. Stop at the budget even if all answers are correct; retain the confirmed lower bound and unknown upper boundary. Finish diagnosis and persist a small sourced route before first teaching.
- Pending question: preserve its ID and option order, display only the public payload, **end this turn and wait for the actual answer**. Do not reveal the key, guess a response, replace the question, or teach past it. Finish an awaiting open-answer assessment before continuing.
- Existing topics: resume their position; do not reset startup diagnosis. Use one or two local prerequisite checks with question `phase: review` when needed. Related goal changes update only affected branches and preserve evidence; confirm ambiguous mission changes. Unrelated missions use separate topics.
- Codex is the formal answer entry point. Objective grading uses stable IDs; open answers use the declared rubric and recorded evaluator. Keep wrong, unknown, cancelled, pending, and awaiting evaluation distinct. HTML practice, reading a page, self-reported knowledge, or one correct choice does not automatically establish mastery. Sessions are not learning records.
- Retain the upstream short HTML lesson/reference and reusable-assets framework. Teach from trusted sources; explain scope and motivated connections. Use learner evidence for confirmed route nodes and sources for concept claims, as specified in the full guide.
- For a new or changed route, render through learn-visualize, **actually inspect the PNG**, then use `diagram-verify` and `route-visual`. Rendering success alone is not verification. Preserve sources/errors and report unverified output when inspection cannot finish.
- Protect manual notes and history. Inspect sync conflicts and merge using the current hash; never overwrite user content, edit machine state directly, or fabricate evidence. Supporting skills do not start teach automatically.
