---
name: Commit Helper
trigger: /run_commit
category: workflow
tags: git, commit, workflow
---

Analyze staged changes and generate a well-structured commit message following conventional commits.

## Inputs

- `type` (optional): Override commit type (feat, fix, refactor, docs, test, chore)
- `scope` (optional): Override scope
- `breaking` (optional): Mark as breaking change (true/false)

## Steps

1. Run `git status --short` to check current state
2. Run `git diff --cached --name-only` to see what's being committed
3. Run `git diff --cached --stat` to understand scope of changes
4. Run `git log --oneline -5` to match recent commit style
5. Analyze the changes:
   - What files were modified/added/deleted
   - What's the nature of the change (new feature, bug fix, refactor, etc.)
   - What's the scope (component, module, or area affected)
6. Generate commit message following format:
   ```
   <type>(<scope>): <short description>

   <detailed description if needed>

   <footer with references if applicable>
   ```
7. Common types:
   - feat: New feature
   - fix: Bug fix
   - refactor: Code change that neither fixes nor adds
   - docs: Documentation only
   - test: Adding/updating tests
   - chore: Maintenance tasks
8. Present the suggested message and ask for confirmation
9. If confirmed, execute the commit

## Examples

- Simple commit: "/run_commit"
- Override type: "/run_commit type=fix"
- Breaking change: "/run_commit breaking=true"
