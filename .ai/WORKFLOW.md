# Specification-Driven Workflow

## Choosing a workflow

Use specifications for work that needs an agreed outcome, several steps, or coordination across sessions.
Handle direct, bounded requests without creating a specification unless the user asks for one.
Templates describe the workflow and do not authorize any particular product or implementation.

## Specification lifecycle

Specifications live in `.ai/specs/` and normally use `YYYY-MM-DD-short-slug.md` filenames.
The work type is descriptive, such as `feature`, `bugfix`, `maintenance`, `research`, or `documentation`.
Use another type when it better describes the requested work.

| Status | Meaning |
| --- | --- |
| `Draft` | Proposed scope; research and planning may proceed |
| `Approved` | The user has authorized the recorded scope |
| `In Progress` | Authorized work has started |
| `Blocked` | A specific dependency or decision prevents remaining work |
| `Implemented` | All required tasks and acceptance checks are complete |
| `Abandoned` | The plan was cancelled or replaced |

Record approval under `Authorization`, including its scope and the user's instruction.
Explicit permission to implement a draft task supplies authorization for that task; do not ask for the same permission again.
An agent may update lifecycle status to reflect actual authorization and progress, but must not invent approval or extend its scope.
Task-level authorization can coexist with draft, unapproved tasks elsewhere in a specification.
For partial authorization, record which tasks are approved instead of marking the entire specification approved.
When previously approved scope changes, identify what new work still needs authorization.

## Planning and refinement

When the user requests an interview to sharpen a plan or design, use `grill-me` before writing or refining the specification.
Record the agreed decisions and remaining unknowns in the relevant project records.

1. Inspect the relevant repository context and known requirements.
2. Use `.ai/specs/00-template.md` to state the goal, constraints, observable success criteria, and exclusions.
3. Split work into focused, verifiable tasks with clear dependencies.
4. Resolve blocking unknowns through a bounded investigation or a user decision.
5. Use `.ai/decisions/00-template.md` for lasting choices and `.ai/research/00-template.md` for investigation evidence when useful.

Do not fill unknown requirements with invented technologies or product ideas.
Use `None` for inapplicable fields and an explicit resolution step for actual unknowns.

## Task execution

1. Read the full specification and requested tasks, then check scope, dependencies, and authorization.
2. Inspect the current branch and worktree, preserving unrelated changes.
3. Follow the planned branch when applicable and safe.
   A branch or PR may be `None` for work that does not need one.
4. Implement the requested tasks and validate their observable outcomes.
5. Review the diff and record actual files, validation, deviations, and remaining work in `Execution result`.
6. Mark a task complete only when its `Done when` conditions are satisfied.
7. Update the architecture map or decision records when the implementation changes them.

One focused task is a useful default, not a mandatory limit when the user requests several tasks or a complete feature.
Run longer validation or external actions within existing authorization; otherwise record the precise prerequisite or remaining command.

## Git and PR handoff

Shared workflow files and project records may be committed with relevant changes.
Create commits or push when requested or already authorized, grouping coherent changes together.
Use concise English branch and commit names, following repository conventions when they exist.

Prepare PR text from the actual diff, validation, and material limitations.
Use the repository PR template or `.ai/templates/pr-description.md` as a fallback.
Check the remote branch directly instead of requiring the user to repeat a push confirmation.
Create a draft PR when requested or already authorized; marking it ready, merging, or deploying requires the corresponding authorization.
