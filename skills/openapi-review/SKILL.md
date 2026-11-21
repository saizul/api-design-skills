---
name: openapi-review
description: Review and lint an OpenAPI 3.x (YAML or JSON) spec for missing descriptions, operationIds, error responses, examples, security requirements, undeclared path parameters and inconsistent naming, then propose concrete fixes. Use when the user shares an openapi.yaml/openapi.json/swagger file, asks to review, clean up or improve an API spec, or wants a spec quality gate in CI.
license: MIT
compatibility: Python 3.9+. YAML specs need PyYAML (pip install pyyaml); JSON specs need nothing.
metadata:
  author: Saizul Amin
  version: "0.1.0"
---

# OpenAPI review

Run a deterministic linter over an OpenAPI 3.x document, then add the judgement a
linter cannot: naming, resource modelling, and whether the docs answer a new
developer's questions.

Paths such as `scripts/...` and `references/...` are relative to this skill's folder (`${CLAUDE_SKILL_DIR}` in Claude Code). Run scripts from the user's project with that folder's path.

## When to use

- The user shares or points at `openapi.yaml`, `openapi.json` or a generated spec.
- Before publishing API docs, generating SDKs or freezing a version.
- Adding a spec quality check to CI.

## When not to use

- Swagger 2.0 files: convert first (`npx swagger2openapi swagger.json -o openapi.yaml`)
  or review by hand; the linter expects `openapi: 3.x`.
- Comparing two versions for breaking changes: use a diff tool such as `oasdiff`.
- Security-focused review: use `api-security-review` (it runs a separate scanner).

## Workflow

1. **Locate the spec.** Look for `openapi.*`, `swagger.*`, `api/*.yaml`, or a generated
   file (FastAPI serves `/openapi.json`; NestJS, springdoc and others can export one).
2. **Run the linter** (JSON output is easiest to post-process):

   ```bash
   python scripts/openapi_lint.py path/to/openapi.yaml
   python scripts/openapi_lint.py path/to/openapi.yaml --format json --fail-on warning
   python scripts/openapi_lint.py --list-rules
   ```

   Exit code 1 means findings at or above `--fail-on` (default `error`); 2 means the file
   could not be parsed. If PyYAML is missing, install it or convert the spec to JSON.
3. **Triage.** Fix `error` findings first (they break tooling: missing operationIds,
   undeclared path parameters, responses without descriptions). Then warnings. Treat
   `info` as suggestions. Rules are explained in
   [references/rules.md](references/rules.md).
4. **Review what the linter cannot see** using the manual checklist in
   [references/rules.md](references/rules.md#manual-review): resource naming, whether
   summaries say what an endpoint does in business terms, realistic examples, documented
   error `type`s, pagination and auth scopes.
5. **Fix or propose patches.** When editing the spec, keep the user's style (YAML
   indentation, key order). Prefer adding reusable `components` (`responses.NotFound`,
   `schemas.Problem`, `parameters.Limit`) over copying blocks. Show diffs for large files.
6. **Re-run the linter** and report the before/after counts.

## Output

1. A summary line: `N errors, N warnings, N info` before and after.
2. Findings grouped by severity with the location (`GET /orders/{id}`) and the fix.
3. Manual review notes the linter cannot detect.
4. Optional CI snippet:

   ```yaml
   - run: pip install pyyaml
   - run: python skills/openapi-review/scripts/openapi_lint.py openapi.yaml --fail-on error
   ```

## Example prompts

- "Review our openapi.yaml and fix the obvious gaps."
- "Why does our SDK generator fail on this spec?"
- "Add a spec lint step to CI that fails on missing operationIds."
