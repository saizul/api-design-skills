---
name: api-docs-writer
description: Generate human-friendly API reference docs and copy-paste curl examples from an OpenAPI 3.x spec, then write the parts a generator cannot - quickstart, authentication guide, error and pagination guides, and use-case recipes. Use when the user wants API documentation, a README or docs page for their API, curl examples for endpoints, or developer onboarding docs, and has (or can export) an openapi.yaml/openapi.json.
license: MIT
compatibility: Python 3.9+. YAML specs need PyYAML.
metadata:
  author: Saizul Amin
  version: "0.1.0"
---

# API docs writer

Generated reference docs are accurate but not enough. Readers need a quickstart that
works in five minutes, an auth guide, and recipes for common tasks. Generate the
reference, then write those.

Paths such as `scripts/...` and `references/...` are relative to this skill's folder (`${CLAUDE_SKILL_DIR}` in Claude Code). Run scripts from the user's project with that folder's path.

## When to use

- The user has an OpenAPI spec and wants Markdown docs, a docs page or curl examples.
- Onboarding docs for a new public or partner API.
- Refreshing docs after spec changes.

## When not to use

- Hosting an interactive portal (use Redoc, Scalar, Swagger UI or a docs platform; this
  skill's Markdown can sit next to it).
- No spec and no code to infer one from: design the API first (`rest-api-design`).

## Workflow

1. **Check the spec quality first** (missing summaries and examples produce poor docs):
   `python ../openapi-review/scripts/openapi_lint.py openapi.yaml` if that skill is
   installed, or review summaries, descriptions and examples by hand.
2. **Generate the reference:**

   ```bash
   python scripts/openapi_to_markdown.py openapi.yaml -o docs/api-reference.md
   python scripts/openapi_to_markdown.py openapi.yaml --base-url https://sandbox.example.com --tag Orders
   python scripts/openapi_to_markdown.py openapi.yaml --format json   # curl commands only
   ```

   Credentials appear as `$API_TOKEN`, `$API_KEY`, `$ACCESS_TOKEN` or
   `$API_USER:$API_PASSWORD`. Never replace them with real values.
3. **Verify the curl examples** against a sandbox or local server when one is available,
   using test credentials the user provides through environment variables. Fix the spec
   (not the generated Markdown) when an example is wrong, then regenerate.
4. **Write the guides** using [references/doc-templates.md](references/doc-templates.md):
   - Quickstart: get a key, first request, read the response, next steps.
   - Authentication: how to obtain, send, rotate and scope credentials.
   - Errors: the problem `type` catalog and how to handle each.
   - Pagination, rate limits, idempotency and webhooks, if the API has them.
   - Two or three recipes for the top use cases ("Create an order and take payment").
5. **Assemble** `docs/README.md` (index) linking the guides and the reference. Keep
   generated files marked as generated so people edit the spec instead.

## Writing rules

- Lead with what the reader wants to do, not with the system architecture.
- Every example must be runnable as written (with the env vars exported).
- Show the response next to each request; trim long payloads with a note.
- Use the same IDs and values across a recipe so the steps chain together.
- Second person, present tense, short sentences.

## Output

- `docs/api-reference.md` (generated) plus the guides as Markdown files.
- A list of spec fixes that would improve the generated docs.

## Example prompts

- "Generate Markdown docs with curl examples from our openapi.yaml."
- "Write a quickstart for our API."
- "Give me curl commands for every endpoint in this spec."
