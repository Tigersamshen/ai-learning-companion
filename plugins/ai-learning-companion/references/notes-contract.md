# Notes and resumption contract

Read [tool-interface.md](./tool-interface.md) before using the CLI. Personal data belongs under the selected data root, not the plugin installation. Use the CLI for managed state and record writes; preserve user-authored Markdown.

## Keep records distinct

| Record | Purpose | Write when |
| --- | --- | --- |
| `sessions/` and companion state | Questions, attempts, explanations, activity, pending question, next position | A real session event happens |
| `learning-records/` | Non-trivial understanding, prior knowledge, corrected misconceptions, adopted mission changes | Evidence or clearly marked self-report exists |
| `学习路线.md`, `RESOURCES.md`, `GLOSSARY.md` | Teaching plan, trusted sources, understood vocabulary | The relevant claim or plan changes |

An activity log is not a learning record. Reading a lesson, opening HTML, browser clicks, or elapsed time does not independently establish mastery. Follow the [learning-record format](../skills/teach/LEARNING-RECORD-FORMAT.md) and [glossary format](../skills/teach/GLOSSARY-FORMAT.md), including evidence thresholds and supersession. Do not duplicate session transcripts as permanent understanding.

## Resume

Read the mission and relevant learning evidence, then inspect `status`. Resume a pending question with the same identity and order; finish an awaiting open-answer assessment before continuing. An unchanged goal follows the existing route. Uncertainty about the next prerequisite warrants a small targeted probe, not complete re-diagnosis. Show what is resumed without automatically activating `teach`.

A related scope change preserves valid evidence and revises only the affected branch through `route-set`. An unrelated goal gets its own topic. A clear user instruction to change the mission supplies confirmation; otherwise clarify before `mission-update --confirmed`. Preserve history and cross-link a superseding record when understanding changes.

## Obsidian and conflicts

The registered Vault stores missions, sources, learning records, sessions, and indices; machine state remains outside it. HTML lessons and reference sheets remain HTML. Do not assume Obsidian runs their JavaScript or that a note edit automatically sends a message to Codex.

Use `sync` for idempotent publication. A conflict means the user-edited file was preserved and a candidate exists under the state conflict directory. Read both versions, merge only intended changes, and save through `note-patch` with the exact current hash. Report an unfinished merge honestly. Retrying publication must not re-grade an answer or append duplicate events. Do not overwrite a note merely to rebuild an index.
