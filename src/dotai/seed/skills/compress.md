---
name: Compress Rules
trigger: /run_compress
role: reviewer
category: maintenance
allowed-tools: Read, Bash, Write
tags: rules, maintenance, context, compression
---

Compress dotai rules with semantic judgment while preserving every meaningful constraint.

## Gotchas

- Never weaken security, credential, destructive-operation, or production-safety boundaries
- Shorter is not better if an exception, alternative, scope, or failure mode is lost
- Never edit rule files directly; dotai must validate, back up, and apply proposals
- Never apply a proposal before showing the user the semantic summary and diff
- Treat estimated savings as directional, not a target that justifies unsafe deletion

## Steps

1. Run `dotai compress --json` and select review candidates with the highest context impact
2. Read each candidate's `source_path` and use its `original_sha256` unchanged in the proposal
3. Draft a shorter complete rule that preserves:
   - All prohibitions and mandatory actions
   - Scope and file-pattern behavior
   - Exceptions and escape hatches
   - Actionable alternatives
   - Security and data-loss safeguards
4. Compare the original and draft. Reject your own draft if it changes meaning or merely paraphrases without meaningful savings
5. Show the user:
   - Before/after estimated size
   - What was preserved
   - What was consolidated or removed
   - The complete diff
6. Ask `Apply this compression? [y/N]` for each rule. Default to No
7. For approved changes, write a version 1 proposal file:

```json
{
  "version": 1,
  "scope": "global",
  "changes": [
    {
      "rule_id": "example-rule",
      "source_path": "/absolute/path/to/example-rule.md",
      "original_sha256": "hash from dotai compress --json",
      "content": "complete proposed rule markdown"
    }
  ]
}
```

8. Run `dotai compress apply <proposal.json> --yes`. The `--yes` is allowed only because the user already approved the exact displayed diff
9. Remove the transient proposal file and run `dotai audit` to report actual savings

## Output

Report the backup path, changed rules, actual before/after context estimate, and any candidates the user declined.
