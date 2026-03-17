---
name: Parallel Work Mode
trigger: /run_parallel
category: workflow
tags: workflow, git, worktree, parallel
---

Set up and manage parallel development using git worktrees. This enables multiple AI agents or work streams to execute tasks simultaneously without conflicts.

## Inputs

- `action` (required): setup, status, merge, cleanup
- `tasks` (optional): Comma-separated task identifiers for setup
- `prefix` (optional): Branch prefix (default: "task")

## Workflow

### Phase 1: Planning
1. Break down the work into independent, small tasks
2. Each task should be completable in isolation
3. Define clear boundaries and interfaces between tasks

### Phase 2: Setup
1. For each task, create a worktree:
   ```bash
   git worktree add ../project-task-<name> -b task/<name>
   ```
2. This creates:
   ```
   ~/project/                 # Main worktree (main branch)
   ~/project-task-task1/      # Worktree for task1
   ~/project-task-task2/      # Worktree for task2
   ~/project-task-task3/      # Worktree for task3
   ```
3. Each worktree is a full copy on its own branch

### Phase 3: Parallel Execution
- Multiple AI agents can work simultaneously
- Each agent works in their assigned worktree
- No merge conflicts during development
- Agents can work on different parts of the codebase

### Phase 4: Integration
1. Check status: `git worktree list` and `git status` in each worktree
2. Review each completed task
3. Merge back: `git merge task/<name>` for each completed task
4. Resolve any conflicts
5. Clean up worktrees

## Steps

### For Setup Action
1. Confirm task breakdown with user
2. For each task, run `git worktree add ../$(basename $PWD)-task-<name> -b task/<name>`
3. Report created worktrees and their paths
4. Provide instructions for working in each worktree

### For Status Action
1. Run `git worktree list` to see all worktrees
2. Check `git status` in each worktree directory
3. Report which tasks are clean vs have changes
4. Identify any tasks ready for merge

### For Merge Action
1. Verify each worktree is clean (`git status` in each)
2. From main worktree, run `git merge task/<name>` for each branch
3. Report merge results
4. Handle any conflicts

### For Cleanup Action
1. Run `git worktree list` to see all worktrees
2. Remove completed worktrees: `git worktree remove ../project-task-<name>`
3. Optionally delete merged branches: `git branch -d task/<name>`

## Examples

- Setup parallel work: "/run_parallel action=setup tasks=auth,api,frontend"
- Check progress: "/run_parallel action=status"
- Merge completed: "/run_parallel action=merge"
- Clean up: "/run_parallel action=cleanup"

## Best Practices

1. **Keep tasks small** - Each task should be 1-2 hours of work
2. **Define interfaces first** - Agree on function signatures, API contracts
3. **Test in isolation** - Each task should be testable independently
4. **Communicate dependencies** - If task B needs task A, note it
5. **Regular status checks** - Run status before starting each session
