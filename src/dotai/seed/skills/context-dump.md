---
name: Context Dump
trigger: /run_context
category: workflow
tags: context, onboarding, sync
---

Generate a comprehensive context dump for starting a new AI session or onboarding.

## Inputs

- `project` (required): Project name to generate context for
- `include` (optional): Comma-separated extras (git-log, open-issues, recent-prs)
- `days` (optional): How many days of history to include (default: 7)

## Steps

1. Load project knowledge:
   - Read `~/.ai/rules.md` and `<project>/.ai/rules.md`
   - Run `dotai primer --project <project>` for structured context
2. Get current git state:
   - `git branch --show-current` for current branch
   - `git log --oneline -10` for recent commits
   - `git status --short` for uncommitted changes
   - `git branch --sort=-committerdate | head -5` for recent branches
3. If include=git-log:
   - `git log --oneline --since="N days ago"` to summarize recent commits
   - Identify what areas of code changed most
4. If include=open-issues:
   - `gh issue list --state open --limit 10` (if GitHub CLI available)
   - Summarize current priorities
5. If include=recent-prs:
   - `gh pr list --state merged --limit 10` for recently merged PRs
   - Note any patterns or decisions made
6. Compile into a structured context document:
   - Project overview
   - Current state
   - Recent activity
   - Known issues/learnings
   - Active work streams
7. Output in markdown format suitable for pasting into AI context

## Examples

- Quick context: "/run_context project=documaker"
- Full sync: "/run_context project=documaker include=git-log,open-issues days=14"
- Morning standup prep: "Run /run_context to catch up on what happened"
