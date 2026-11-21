---
name: your-skill-name
description: One or two sentences saying WHAT the skill does and WHEN to use it. Name the triggers a developer would type (file names, terms, error messages). Use when the user ... Max 1024 characters.
license: MIT
compatibility: Python 3.9+ (delete this line if the skill has no scripts)
metadata:
  author: Your Name
  version: "0.1.0"
---

# Your skill title

One paragraph: the problem this solves and the result the agent produces.

## When to use

- Concrete situation 1 (what the user says or has open).
- Concrete situation 2.

## When not to use

- Neighbouring task that another skill or tool handles better (name it).

## Workflow

1. **Gather context.** What to look for in the repository or ask the user.
2. **Run the helper** (if any):

   ```bash
   python scripts/your_script.py INPUT --format json
   ```

   Exit 0 = clean, 1 = findings, 2 = usage or parse error.
3. **Decide.** Decision points with the default choice and when to deviate.
4. **Change or produce** the artefact. Details in [references/guide.md](references/guide.md).
5. **Verify.** Re-run the helper or tests and compare before/after.

## Output

1. What the agent must hand back, in what format (table, patch, file).
2. What it must not do (for example: never print secrets).

## Example prompts

- "A prompt that should trigger this skill."
- "Another one."
