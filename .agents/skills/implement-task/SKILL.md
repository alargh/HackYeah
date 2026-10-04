---
name: implement-task
description: Implement a named task from a repository specification, including relevant validation and execution records. Use when the user asks to implement or continue a specification task.
---

# Implement a Specification Task

Read the applicable repository instructions, `.ai/RULES.md`, `.ai/ARCHITECTURE.md`, `.ai/WORKFLOW.md` when present, and the complete specification and selected task.
Use the task's goal, dependencies, scope, validation, and completion conditions as the implementation contract.

Check that implementation is authorized by the specification or the user's current or earlier instruction.
If the user explicitly authorizes implementation of a draft task, record that authorization and proceed.
Ask only when a missing decision or incomplete dependency prevents useful, correct work.
Work on the requested task or tasks; do not start unrelated tasks.

1. Inspect the worktree, branch, relevant files, and existing validation commands.
2. Follow the specification's branch choice when supplied and safe, preserving unrelated changes.
   Do not invent a branch requirement for work that does not need one.
3. State the intended scope briefly and implement the smallest complete change.
4. Run validation appropriate to the actual stack and acceptance criteria.
   Verify observable behavior, and report unavailable checks honestly.
5. Review the diff for unintended changes and update architecture or decision records when the task changes them.
6. Create commits only when requested or already authorized.
   Group coherent changes together, including their tests and relevant documentation.
7. Update the task's `Execution result` with actual files, validation outcomes, deviations, remaining work, and commit hashes when applicable.
   Mark it complete only when `Done when` is satisfied.

Do not infer authorization for paid operations, publishing, or deployment from permission to edit local code.
Run long jobs when they are needed and already authorized; otherwise record prerequisites and exact commands for the remaining work.

Report the implemented outcome, validation, material limitations, and next step.
