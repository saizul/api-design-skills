---
name: error-responses
description: Design and implement consistent HTTP API error responses using RFC 9457 Problem Details (application/problem+json) - problem type catalog, validation error shape, status code mapping, safe messages, plus ready-made handlers for Node/Express, Python/FastAPI/Flask and PHP/Laravel. Use when the user asks how to format API errors, wants consistent error handling, mentions problem+json or RFC 7807/9457, or when error payloads leak stack traces or differ between endpoints. Includes a linter for error bodies and OpenAPI error responses.
license: MIT
compatibility: Python 3.9+ for the linter. YAML specs need PyYAML.
metadata:
  author: Saizul Amin
  version: "0.1.0"
---

# Error responses (RFC 9457 problem details)

Give every error the same machine-readable shape so clients can branch on a stable
`type`, show a safe `title`/`detail`, and log an `instance` you can trace.

Paths such as `scripts/...` and `references/...` are relative to this skill's folder (`${CLAUDE_SKILL_DIR}` in Claude Code). Run scripts from the user's project with that folder's path.

## When to use

- Defining the error format for a new API, or unifying inconsistent errors.
- Implementing a global error handler / middleware.
- Reviewing captured error responses or the error section of an OpenAPI spec.

## When not to use

- GraphQL (errors live in the `errors` array of the response) or gRPC (status codes and
  `google.rpc.Status`).
- Choosing status codes in general: see `rest-api-design`.

## Workflow

1. **Inventory current errors.** Grep the handlers for how errors are returned
   (`res.status(`, `HTTPException`, `abort(`, `response()->json(`) and collect sample
   bodies. Note leaks: stack traces, SQL, file paths, internal hostnames.
2. **Define the problem type catalog** with
   [references/problem-details.md](references/problem-details.md): one row per error
   your clients must handle differently (`validation-error`, `insufficient-funds`,
   `rate-limited`). Each gets a stable `type` URI, a fixed `title`, a status, and any
   extension members. Use `about:blank` only when the status code says everything.
3. **Pick the validation error shape**: `errors: [{"detail": ..., "pointer": "#/items/0/qty"}]`
   (JSON Pointer, RFC 6901) as in RFC 9457's own examples.
4. **Implement one central handler** using the matching snippet in
   [references/implementations.md](references/implementations.md) (Express, FastAPI,
   Flask, Laravel, plain PHP). Rules: set `Content-Type: application/problem+json`; the
   body `status` equals the HTTP status; unknown exceptions become a generic 500 with a
   correlation ID and are logged server-side with the stack trace.
5. **Document it** in OpenAPI: a shared `components.schemas.Problem` and
   `components.responses` (`BadRequest`, `NotFound`, `Conflict`, `TooManyRequests`) with
   `application/problem+json` examples. Template:
   [assets/problem-components.yaml](assets/problem-components.yaml).
6. **Lint** captured bodies and the spec:

   ```bash
   python scripts/problem_lint.py doc error-samples/*.json --status 422
   python scripts/problem_lint.py spec openapi.yaml --format json
   ```

   Exit 1 means findings at or above `--fail-on` (default `error`).
7. **Test** each problem type: status, content type, `type` value, no internal details.

## Rules

- `type` is the contract; clients branch on it. Never change it for an existing error.
- `title` is fixed per `type`; put the occurrence-specific text in `detail`.
- `detail` is for humans; do not make clients parse it.
- Never include stack traces, SQL, exception class names or secrets. Log them with the
  `instance`/trace ID instead.
- Do not reveal whether a resource exists to callers who may not see it (return 404).
- Send `Retry-After` with 429 and 503. Send `WWW-Authenticate` with 401.

## Output

1. A problem type catalog table: `type | title | status | when | extension members`.
2. The handler code for the user's framework, wired in, with tests.
3. OpenAPI components for the errors.
4. Linter results before/after.

## Example prompts

- "Make all our Express API errors consistent and stop leaking stack traces."
- "What should a validation error response look like?"
- "Add problem+json error handling to this FastAPI app."
