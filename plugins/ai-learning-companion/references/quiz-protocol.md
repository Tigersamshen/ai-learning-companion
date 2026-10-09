# Codex quiz protocol

Use this for diagnostic questions, recall, and practice recorded through Codex. Read [tool-interface.md](./tool-interface.md) for the actual CLI schema. Use file arguments for JSON bodies; never splice user text into shell commands.

## Ask, wait, grade

1. Run `status --topic TOPIC`. If a question is pending, display that existing public question with its persisted option order. Do not create another one, reshuffle it, or reveal its key. If an open answer awaits evaluation, assess that answer before continuing.
2. Prepare a unique question ID and stable option IDs. Test one concept, state its scope, and include `source_refs`. For an objective question, provide `correct` and `explanation` in the input JSON. For an open question, provide the `rubric` before collecting the answer. Give each distractor one plausible misconception; match option length, grammatical shape, and specificity. Do not make the correct claim uniquely detailed.
3. Run `quiz-create --topic TOPIC --file QUESTION.json`. Show only its public output, with the actual persisted option order. Do not display the input JSON, key, or explanation. Store input files containing keys outside the Vault. Normal display hides answers; local files and tool parameters remain inspectable.
4. **End the assistant turn and wait for a real user answer.** Silence, time passing, and a preference popup are not answers. Resolve a displayed number through the persisted order into an option ID. Clarify an ambiguous reply instead of grading a guess.
5. Submit the actual answer using `quiz-submit --topic TOPIC --quiz ID --attempt ATTEMPT --answer ANSWER.json`. Use stable IDs for selections. Explicit unknown and cancellation use the distinct flags in the interface. Reuse the same attempt ID for a retry; do not generate a second attempt to work around an interrupted write.
6. An open answer returns `awaiting_evaluation`: read its original rubric and record the actual reasoning and evaluator with `quiz-assess`. Do not invent a model name; use the runtime identity if known, or state that evaluation identity is unavailable rather than fabricating a record. Describe this as an LLM assessment, not deterministic truth.
7. After actual submission and any required assessment, show feedback and choose the next teaching move. A cancelled question earns neither correctness nor mastery. On diagnostic cancellation, offer to end diagnosis rather than automatically replacing questions indefinitely.

## Evidence boundary

`correct`, `wrong`, `dont_know`, `cancelled`, `awaiting_evaluation`, and a still-pending question are distinct. Tool failure is a tooling limitation, never a learner outcome. A correct choice alone does not prove transfer or long-term retention.

Raw questions, attempts, feedback, and diagnosis observations belong in session records. Use `record-learning` only when the [learning-record contract](../skills/teach/LEARNING-RECORD-FORMAT.md) is met. Link demonstrated understanding to graded questions, and retain the self-report label for prior knowledge. Supersede earlier false understanding instead of erasing it.

Browser quizzes are informal practice with immediate feedback. Browser clicks, local storage, and page opening do not become formal evidence. If the user reports a browser result in Codex, assess a relevant response there and record that evidence source. This plugin does not import browser quiz results.
