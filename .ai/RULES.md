# Project Rules

## Scope and authorization

- Follow explicit user requirements and existing session authorization.
- Use a specification for work that benefits from agreed scope, dependencies, or acceptance criteria.
  Do not require one for a direct, bounded request.
- For specification tasks, respect `Allowed files`, `Do not touch`, dependencies, and `Done when`.
  If essential work falls outside that scope, update the plan within existing authorization or explain the decision needed before proceeding.
- Inspect the worktree before editing and preserve unrelated changes.
- Do not silently replace a selected design, expand the product, or mark unverified work complete.

## Shared and private material

`AGENTS.md`, `.agents/skills/`, and `.ai/` are shared template and project documentation suitable for version control.
Specifications, decisions, and research notes remain shareable unless explicitly designated private.

Keep credentials, personal workstation settings, temporary files, and generated artifacts out of commits.
Add ignore patterns for actual tools and outputs as they are introduced rather than copying exclusions from another project.
Do not exclude source assets or documentation merely because of their file format.

## Evidence and decisions

- Use the user's current requirements and recorded decisions for intended behavior.
- Use implementation and observable behavior for claims about the current system.
- Use reproducible outputs for measured results and authoritative sources for external facts.
- Label assumptions, missing evidence, and open questions.
  Never invent test outcomes, metrics, citations, or commands that were executed.
- Record lasting design choices in `.ai/decisions/` and investigation evidence in `.ai/research/` when useful.
- Update `.ai/ARCHITECTURE.md` when the actual structure or selected technologies change.

## Validation and handoff

- Validate the behavior changed by the task with checks appropriate to its impact and stack.
- Record commands actually run, outcomes, and any unavailable checks.
- Use manual verification when it is the meaningful check for a documentation or presentation change.
- Account for prerequisites and authorization before running costly or externally affecting operations.
  There is no blanket restriction on a particular runtime, processor, or type of experiment.
- Create coherent commits when authorized.
  Include related implementation, tests, and documentation together rather than forcing one file per commit.
- Prepare concrete work before requesting any additional authorization genuinely required to push, publish, or deploy.
- Describe actual changes and relevant validation in PRs, including template or workflow changes when those are in scope.
