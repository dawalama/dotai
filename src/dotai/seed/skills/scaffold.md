---
name: Scaffold
trigger: /run_scaffold
category: scaffolding
allowed-tools: Read, Write, Glob, Bash
tags: generate, boilerplate, new
---

Generate boilerplate for a new module, component, or service by following existing project patterns.

## Gotchas

- Never invent conventions — always derive patterns from existing code in the project
- Check for code generators already in the project (plop, hygen, nx generate) before writing files manually
- New files need to be registered/exported — check for barrel files (index.ts), route registrations, or DI containers

## Inputs

- `type` (required): What to scaffold (component, service, api-route, model, test, module)
- `name` (required): Name for the new entity
- `path` (optional): Where to create it (defaults to conventional location)

## Steps

1. Search the project for existing examples of the requested type using Glob and Grep
2. Identify the dominant pattern: file structure, naming convention, imports, exports
3. Check for existing generators (package.json scripts, Makefile targets, plop/hygen configs)
4. If a generator exists, use it. Otherwise, create files following the discovered pattern
5. Register the new entity in any barrel files, route configs, or dependency injection containers
6. Output the list of created files

## Examples

- New React component: "/run_scaffold type=component name=UserProfile"
- New API route: "/run_scaffold type=api-route name=payments"
