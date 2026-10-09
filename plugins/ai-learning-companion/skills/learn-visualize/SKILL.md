---
name: learn-visualize
description: Create and verify Mermaid or SVG diagrams for an active AI learning topic, including evidence-linked learning roadmaps and concept geometry. Use for requested or useful learning visuals, rather than general UI design or automatic course startup.
---

# Learning Visuals

Create a small diagram that makes the actual relationship or geometry clearer. Read [the visual contract](../../references/visual-contract.md), then [the tool interface](../../references/tool-interface.md) for the renderer and publication commands.

1. Resolve the topic workspace and inspect `assets/` before creating a new component. If no topic was selected, obtain it rather than publishing into an arbitrary directory.
2. Brief one available maker with the essential concept, source/evidence links, and output purpose. Read [the Mermaid maker prompt](../../agents/mermaid-maker.md) for relationships or [the SVG maker prompt](../../agents/svg-maker.md) for geometry. Pass the prompt and necessary context to a Codex subagent. These files do not register a pi runtime or select a model. If delegation is unavailable, follow the same author/render/inspect contract in the main agent.
3. Run `python3 <plugin-root>/scripts/learning_tools.py --root <data-root> render --kind mermaid|svg --input SOURCE --output-dir TOPIC_ASSETS --stem NAME` using the actual paths. Inspect the resulting PNG for meaning and layout. Only then run `diagram-verify --manifest RESULT.json --note CHECK`. Return the source and the checked rendition; state any rendering or inspection limitation.
4. Link the figure from the lesson and Obsidian note. A roadmap's learning status comes from learner evidence, not the maker's subject-matter verification. Do not reveal a pending answer or mark untested concepts confirmed.

This skill supplies diagrams and requested visual assets. It does not activate `teach`, invent a mission, change the course's teaching method, or infer mastery.
