# AGENTS.md

Instructions for AI coding agents (OpenAI Codex, Claude Code and others) working with
this repository, either **using** the skills in another project or **changing** them here.

## Using the skills

- Each folder in `skills/` is one Agent Skill. Read its `SKILL.md` when the user's task
  matches the `description` in its frontmatter, and follow the Workflow section in order.
- Paths in a `SKILL.md` (`scripts/...`, `references/...`, `assets/...`) are relative to
  that skill's folder. Run scripts with the full path, from the user's project directory:
  `python <skill-folder>/scripts/openapi_lint.py openapi.yaml`.
- Read `references/` files only when a step points to them.
- Scripts are read-only: they read local files, print a report and exit 0 (clean),
  1 (findings) or 2 (usage or parse error). Prefer `--format json` when you need to
  post-process findings.
- YAML specs need PyYAML. If it is missing, ask before installing it, or convert the
  spec to JSON.
- `webhook_signature.py` reads the secret from an environment variable or file. Never
  put a secret on the command line, in a file you create, or in your reply.
- Do not run active security tests against systems the user has not confirmed they own
  and are allowed to test.

### Installing for Codex

Codex loads skills from `.agents/skills/` in the repository (scanned from the current
directory up to the repository root) and from `$HOME/.agents/skills/` for the user:

```bash
mkdir -p ~/.agents/skills
cp -R skills/* ~/.agents/skills/
```

Restart Codex if a skill does not appear. See the
[Codex skills documentation](https://developers.openai.com/codex/skills) for current
details.

### Which skill for which request

| Request | Skill |
| --- | --- |
| Design endpoints, choose methods/status codes, versioning | `rest-api-design` |
| Review or lint an OpenAPI file | `openapi-review` |
| Error format, problem+json, error handler | `error-responses` |
| List endpoints, cursors, filters, sorting | `pagination-filtering` |
| Sending or receiving webhooks, signatures | `webhook-design` |
| Duplicate charges/orders on retry, Idempotency-Key | `idempotency-keys` |
| Security review, OWASP API Top 10, IDOR/BOLA | `api-security-review` |
| Removing or changing endpoints, Sunset/Deprecation headers, API changelog | `api-changelog-deprecation` |
| Docs and curl examples from OpenAPI | `api-docs-writer` |

## Changing this repository

- Layout: `skills/<name>/SKILL.md` plus optional `scripts/`, `references/`, `assets/`;
  tests and fixture specs in `tests/`; the validator in `tools/validate_skills.py`;
  Claude Code manifests in `.claude-plugin/`.
- Before finishing any change, run:

  ```bash
  pip install -r requirements-dev.txt
  python tools/validate_skills.py
  pytest
  ruff check . && ruff format --check .
  ```

- Scripts: Python 3.9+, standard library only (PyYAML optional, imported lazily), no
  network access, `--help`, `--format json`, documented exit codes, tests with fixtures.
- The OpenAPI helpers (`load_spec`, `resolve`, `iter_operations`) are copied into each
  script so skills install independently. Change all copies together;
  `tests/test_shared_helpers.py` fails if they drift.
- New skill: copy `templates/skill/SKILL.md`, keep it under 400 lines, add it to
  `.claude-plugin/marketplace.json` (`skills` list), the README table, the table above,
  the bug report template and `CHANGELOG.md`.
- Cite RFCs or official docs for normative advice. Do not invent header names, flags or
  status code semantics.
