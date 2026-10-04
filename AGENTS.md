# Project Agent Instructions

This repository contains Tutorly, an AI-powered mathematical explanation system (see `README.md`),
built on the hackathon agent-workflow template.
The selected stack and components are recorded in `.ai/ARCHITECTURE.md` and `IMPLEMENTATION_PLAN.md`.
Runtime AI is Gemini; do not add a runtime dependency on another LLM provider.

Before project work, read `.ai/RULES.md`, `.ai/ARCHITECTURE.md`, and `.ai/WORKFLOW.md`.
For specification work, also read the relevant specification and requested tasks.

## Working conventions

- Follow the user's requested scope and existing authorization.
  Planning is useful for substantial work, but a specification is not required for every direct request.
- Write shared agent instructions, specifications, decision records, branch names, commit messages, and PR text in English unless the user requests otherwise.
  Conversation and product content may use the language appropriate to the user or audience.
- Preserve unrelated user changes and report actual evidence for completion.
- Keep the shared template files available in Git.
  Do not classify `AGENTS.md`, `.ai/`, or `.agents/` as private workstation state.
- Choose validation from the implemented stack and task requirements.
  Do not assume a framework, runtime, provider, dataset, or evaluation method.
- Respect existing authorization for Git and external actions; do not add mandatory approval steps to routine local work.

## Skill routing

- Interview the user to sharpen a plan or design when requested: `grill-me`.
- Plan work and define tasks: `write-spec`.
- Change an existing plan: `edit-spec`.
- Implement requested specification tasks: `implement-task`.
- Prepare PR text or create a requested draft PR: `prepare-draft-pr`.

Use the skills under `.agents/skills/` when the request fits them.
The workflow details and lifecycle are defined in `.ai/WORKFLOW.md`.
