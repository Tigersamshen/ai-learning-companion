# Upstream provenance

This plugin includes a local adaptation of Matt Pocock's `teach` skill.

- Repository: https://github.com/mattpocock/skills
- Commit: `b0618bc436ad893b3c5e84e55fba86586d34a404`
- Path: `skills/productivity/teach/`
- Source: https://github.com/mattpocock/skills/tree/b0618bc436ad893b3c5e84e55fba86586d34a404/skills/productivity/teach
- License: MIT, Copyright (c) 2026 Matt Pocock. The original notice is retained in `LICENSE`.
- Download method: Codex skill-installer `install-skill-from-github.py`, with the explicit commit and local plugin `skills/` destination.

## Local changes

`skills/teach/TEACHING-GUIDE.md`, loaded by the short `skills/teach/SKILL.md` entry point, retains the upstream knowledge/skills/wisdom framework, mission and learning-record formats, short HTML lessons and references, reusable assets, resource citations, retrieval/spacing/interleaving, and community preferences. It adds bounded new-topic diagnosis, resumption for existing topics, local replanning when the goal changes, evidence-linked Mermaid roadmaps, and Codex-first quiz recording. Browser exercises remain informal practice unless evidence is subsequently assessed in Codex.

Two frontmatter fields, `disable-model-invocation` and `argument-hint`, were removed because the bundled Codex skill-creator validator does not support them. Explicit-only invocation is retained through the unchanged `agents/openai.yaml` policy `allow_implicit_invocation: false`; the skill name remains `teach`.

The four `*-FORMAT.md` files and `skills/teach/agents/openai.yaml` are unchanged. `learn-visualize`, `learn-notes`, the shared integration references, and the three role prompts are authored for this plugin. They do not automatically invoke `teach` or replace its teaching decisions. The upstream full plugin is not installed and is not configured to auto-update this fork.

The additional diagnosis and dependency-map workflow is informed by Amos Blomqvist's public explanation and learning system (https://github.com/amosblomqvist/learn). No code or skill text from that repository is bundled here. Personal claims about brain mechanisms are not treated as established scientific laws.

## Progressive loading for the actual host

A real explicit installed-skill `codex exec` run reported main prompt context limit truncation while the enhanced `SKILL.md` entry point was 18,425 bytes. The complete enhanced body has therefore been moved, byte-for-byte, into `skills/teach/TEACHING-GUIDE.md` in the same directory. The short entry point retains the original name/description and explicit-call intent, requires complete reads of the guide, tool interface, and quiz protocol before teaching or resuming, and repeats only the essential guards.

This is a packaging change for progressive loading. It removes no upstream framework or local teaching behaviour. FORMAT and integration links retain their directory-relative meaning. A separately running old-version fresh CLI had already read the complete original file; post-split host behaviour must be checked in a fresh installed context rather than inferred from that earlier run.

- Enhanced entry point before split SHA-256: `4b781618e336f8ca2ebf4081cf5432169f69fdb6e4ec1bb4004aafb1c592ca8d`
- Complete body / `TEACHING-GUIDE.md` SHA-256: `c9a9ab670a9ad7ba91f57812e53d4c1c3aeea9a13b5e2f77aa1c8e9e57366318`
- Short entry point size: 3,966 bytes.

## Original teach directory SHA-256

These hashes describe the downloaded files before local edits; all files except `SKILL.md` must continue to match them.

```json
{
  "GLOSSARY-FORMAT.md": "9b99859ec28437668130d8f2ce5a342938970f8a1ed4fd38c3eab4f4b5fff210",
  "LEARNING-RECORD-FORMAT.md": "701fa34b6748aa89e6c960ffb815257f481a7d77fb2900f9028f7edf3fdd6052",
  "MISSION-FORMAT.md": "8cacbb3c0644d3ae0ea4965564797099401a6930a23f7cf462918576587f2418",
  "RESOURCES-FORMAT.md": "e9cacf34026e11a8d1c8f9de88abe5bcbf654f4ebdb25cae8c0de0d5f48f44ec",
  "SKILL.md": "550482c2d674b085c9043b87bfdc14a8f2ec453c736119e7fcbb1e9332bffeba",
  "agents/openai.yaml": "5856f3ae8aec742f1499c640aecdd5f1d6af5fa210a7c6ec794de8263a6f733f"
}
```
