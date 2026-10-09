# Learning visual contract

Read [tool-interface.md](./tool-interface.md) for rendering and publication. The main agent owns the teaching meaning; a maker owns authoring, rendering, visual inspection, and correction. Role prompts in `../agents/` are instructions to pass to an available Codex subagent, not automatically loaded agent registrations.

## Choose a representation

Use Mermaid for prerequisites, flows, sequences, states, and other nodes-and-edges relationships. Use SVG for geometry, vectors, coordinate plots, and deliberate spatial placement. Prefer prose, an equation, or a table when it already explains the idea.

A roadmap is a small directed graph of learning prerequisites. Aim for five to nine nodes, fewer for a narrow goal. Distinguish a sourced domain prerequisite from a suggested teaching order. Each confirmed node needs learner evidence; source verification establishes a claim, not mastery. The CLI supports `confirmed`, `pending`, and `unknown`. Explain untested versus uncertain in the accompanying prose rather than inventing extra status values. Use node `source_refs` for supporting claims; identify pedagogical choices as such.

## Brief and verify

Supply the topic workspace, one relationship or geometric idea, essential labels, sources/evidence, output purpose, and numerical constraints. Do not give a maker pending-quiz keys or request visual hints revealing an answer.

1. Save a uniquely named source in the topic's `assets/`, alongside reusable prior components. Preserve existing figures.
2. Run the unified CLI `render` command. Mermaid needs the renderer runtime declared by the companion implementation; Python's standard library orchestrates it and does not render Mermaid itself.
3. Inspect the returned PNG. Compare the pixels with the brief: arrows, claims, units, numerical positions, clipping, font size, and contrast. Correct and re-render when necessary. Compilation alone is not visual verification.
4. Only after actual inspection, run `diagram-verify` with the returned manifest and a specific check note. If rendering or inspection is unavailable, return `unverified` and the limitation. Do not mark it as checked or publish it as a verified teaching figure.
5. Return source, SVG, PNG, preview, manifest, inspection status, and linked sources/evidence. Use the inspected rendition in the HTML lesson and Obsidian note, keeping an editable source link. Resolve references relative to the output file.

Keep embedded resources local: no CDN scripts, remote fonts, or remote image references. Source citations may link to the web. For SVG, use a `viewBox`, readable scale, system-font CJK fallbacks, and margins. Keep it static: no scripts, event handlers, `foreignObject`, external resources, or network references. Correct false dependencies and distorted measurements even when the drawing looks attractive.
