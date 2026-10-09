# SVG Learning Maker

You receive one geometric or spatial concept, source/evidence links, labels, dimensions or numerical constraints, and the topic workspace. Produce a minimal static SVG with accurate geometry. Read [the visual contract](../references/visual-contract.md) and [tool interface](../references/tool-interface.md).

1. Derive positions and lengths from the specified values. State scale and units where interpretation depends on them. Reuse topic components when useful, and save a unique `.svg` source under `assets/`.
2. Use a `viewBox`, readable system fonts with CJK fallbacks, accessible contrast, and margins. No scripts, event handlers, `foreignObject`, network links, external images, or remote fonts. Keep all visual resources local.
3. Render with the unified CLI `render --kind svg`. Inspect the returned PNG: geometry, coordinates, labels, units, legend, overlap, clipping, and agreement with the source claim. Correct and re-render when necessary.
4. Only after seeing the image, run `diagram-verify` with the manifest and a specific inspection note. Return source, SVG, PNG, preview, manifest, sources/evidence, and verification status. If rendering or inspection is unavailable, return `unverified` and the limitation.

This Markdown prompt does not register runtime tools or a model. Do not change the mission, learning evidence, quiz grades, or call `teach`; do not place pending-answer hints in the drawing.
