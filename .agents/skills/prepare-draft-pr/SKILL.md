---
name: prepare-draft-pr
description: Prepare an English draft pull request title and description from repository changes and validation evidence. Use when the user asks to prepare PR text or create a draft pull request.
---

# Prepare a Draft Pull Request

Read the applicable repository instructions and PR template.
Use `.ai/templates/pr-description.md` when there is no repository-specific PR template.
Read the related specification when available, but describe the final implementation rather than copying the plan.

1. Inspect the worktree, current branch, intended base, and actual diff or commit range.
   Resolve the base from repository configuration or the user's request instead of assuming its name.
2. Review validation evidence and distinguish successful checks, skipped checks, and remaining limitations.
3. Write a concise English title and description that explain the problem, resulting behavior, and relevant validation.
4. Include workflow or documentation changes when they are part of the actual diff.
   Remove empty template sections and avoid unrelated planning history.
5. If the request is only for PR text, deliver that text without creating a PR.
6. If the user requested a draft PR, check remote branch availability directly.
   Use existing push authorization if available; if the branch is not published and no push is authorized, finish the PR text and explain the remaining prerequisite.
7. Create the draft PR only when that action was requested or already authorized.

Preparing or creating a draft PR does not authorize marking it ready, merging, or deploying.
Finish with the title and description or the created draft PR link, plus any material remaining prerequisite.
