---
name: write-spec
description: Create an English specification for a feature, bug fix, maintenance change, research task, or documentation work. Use when the user wants to plan work and define implementation tasks before starting it.
---

# Write a Specification

Read the repository's `AGENTS.md`, `.ai/RULES.md`, `.ai/ARCHITECTURE.md`, `.ai/WORKFLOW.md`, and `.ai/specs/00-template.md` when present.
Inspect the relevant files and existing evidence before asking questions.
When the user asks for an interview to sharpen the plan, use the local `grill-me` skill and incorporate the agreed decisions into the specification.
If the repository has a different specification convention, follow it instead.

Create the specification under `.ai/specs/` with a descriptive English filename such as `YYYY-MM-DD-short-slug.md`.
Specifications are shared project documentation unless the user explicitly requests a local-only plan.

1. State the goal, observable success criteria, constraints, and exclusions.
2. Distinguish user requirements, verified facts, assumptions, and unresolved decisions.
3. Choose a descriptive work type without assuming a product domain or technology stack.
4. Split work into independently verifiable tasks sized for a focused session.
5. Give each task its scope, dependencies, concrete steps, validation, and completion conditions.
   Use exact file paths when known; use a bounded directory or discovery step when paths do not yet exist.
6. Record external dependencies, required access, costs, or long-running commands only when relevant.
7. Set the initial status to `Draft` unless the user has already explicitly authorized that specification's implementation.
   Record existing authorization rather than asking for it again.

Use `None` for an inapplicable field and label actual unknowns with a resolution step.
Do not invent requirements to fill the template.
Keep research spikes separate from implementation that depends on their results.
Do not implement product changes while the request is only to write a specification.

Finish with the specification path and any decisions that prevent implementation.
