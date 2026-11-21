# Contributing to api-design-skills

Thank you for helping! New skills, better advice, new lint rules, framework examples and
bug reports are all welcome.

- [Ways to contribute](#ways-to-contribute)
- [Good first issues](#good-first-issues)
- [Development setup](#development-setup)
- [Project layout](#project-layout)
- [Write a skill](#write-a-skill)
- [Write or change a script](#write-or-change-a-script)
- [Guidelines](#guidelines)
- [Pull request process](#pull-request-process)

## Ways to contribute

| Size | Idea |
| --- | --- |
| 10 minutes | Fix a typo, clarify a step, add an example prompt |
| 30 minutes | Add a fixture case and test for a lint rule, improve an error message |
| 1-2 hours | A new lint rule, a framework snippet, or one of the good first issues below |
| Larger | A new skill (open a "New skill proposal" issue first) |

Comment on an issue before you start so nobody else picks the same one.

## Good first issues

Each of these is self-contained and touches one or two files plus tests.

1. **`openapi-review`: enum casing rule.** Warn when one `enum` mixes `snake_case`,
   `camelCase` or `UPPER_CASE` values. Add the rule to `RULES`, a case to
   `tests/fixtures/bad.yaml` and a test in `tests/test_openapi_lint.py`.
2. **`openapi-review`: `summary` too long.** Warn when a summary is longer than 80
   characters or ends with a period (index pages truncate it).
3. **`api-security-review`: missing `maxLength` on header parameters.** Extend the
   `unbounded-string-parameter` check and add a fixture.
4. **`api-docs-writer`: Python examples.** Add `--lang python` that emits a `requests`
   snippet next to each curl command. Keep credentials as `os.environ["API_TOKEN"]`.
5. **`webhook-design`: Go snippet.** Add `assets/snippets/verify_webhook.go` for the
   Standard Webhooks and GitHub schemes, and a test that runs `go test` when Go is
   installed (skip otherwise), like the Node.js and PHP tests.
6. **`error-responses`: Spring Boot example.** Add a `ProblemDetail` /
   `@RestControllerAdvice` section to `references/implementations.md`.
7. **`pagination-filtering`: SQLAlchemy keyset example.** Add a short section with
   `tuple_(Order.created_at, Order.id) < (...)` to `references/strategies.md`.
8. **`api-changelog-deprecation`: `--format apache`.** Print `Header always set` lines,
   like the existing `--format nginx`.
9. **`problem_lint.py`: Content-Type check.** Accept an optional `--content-type` and
   report an error when it is not `application/problem+json`.
10. **Validator: description quality.** Warn when a description is shorter than 80
    characters (too vague to trigger reliably).

## Development setup

You need Python 3.11+ for development (the scripts themselves run on 3.9+). Node.js 18+
and PHP 8+ are optional; their snippet tests are skipped when they are missing.

```bash
git clone https://github.com/saizul/api-design-skills.git
cd api-design-skills
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

python tools/validate_skills.py     # frontmatter, sections, links, manifests
pytest                              # all script and validator tests
ruff check . && ruff format --check .
```

CI runs the same commands on Python 3.11, 3.12 and 3.13.

To try the plugin locally in Claude Code:

```bash
claude plugin validate .
claude plugin marketplace add ./
claude plugin install api-design-skills@api-design-skills
```

## Project layout

```
.claude-plugin/marketplace.json   marketplace + plugin entry listing every skill
.claude-plugin/plugin.json        plugin manifest (name, version, author)
skills/<name>/SKILL.md            the skill: frontmatter + workflow
skills/<name>/references/         long material, loaded on demand
skills/<name>/scripts/            deterministic CLI helpers (stdlib Python)
skills/<name>/assets/             templates and reference implementations
templates/skill/SKILL.md          start here for a new skill
tests/                            pytest suite; tests/fixtures/ holds OpenAPI specs
tools/validate_skills.py          repository validator (run in CI)
```

## Write a skill

1. Open a **New skill proposal** issue with the name, example prompts and a workflow
   outline. Check that no existing skill already covers it.
2. Copy the template: `cp -R templates/skill skills/<your-skill-name>`.
3. Fill in the frontmatter:
   - `name`: lowercase letters, digits and single hyphens, at most 64 characters, equal
     to the folder name.
   - `description`: at most 1024 characters. Say **what** it does and **when** to use it
     ("Use when the user ..."), with the words a developer would actually type.
4. Write the body. Required sections: `## When to use`, `## When not to use`,
   `## Workflow`, `## Output`. Keep it imperative and step by step, with decision points
   and exact commands. Stay under 400 lines; move long material to `references/` and link
   it with a relative path.
5. Add a script if a deterministic check would make the skill more reliable (see below).
6. Register the skill: add `./skills/<name>` to the `skills` list in
   `.claude-plugin/marketplace.json`, add a row to the README table and the AGENTS.md
   table, add it to the bug report dropdown, and add a CHANGELOG entry.
7. Run the validator and the tests.

## Write or change a script

- Python 3.9+ standard library only. PyYAML may be imported lazily to read YAML, with a
  clear error message when it is missing.
- `argparse` with a useful `--help`, `--format json`, and documented exit codes
  (0 clean, 1 findings, 2 usage/parse error).
- No network calls. Never print, log or write secrets; read them from an environment
  variable or a file.
- Tests in `tests/test_<script>.py` using fixture specs in `tests/fixtures/`. Cover the
  clean case, each finding, the CLI exit codes and `--format json`.
- If you change `load_spec`, `resolve` or `iter_operations`, change every copy; the
  shared-helper test checks they match.

## Guidelines

- Back normative advice with a source (RFC, OpenAPI specification, OWASP, official
  framework docs). Link it in `references/`.
- Prefer one clear default over a list of options; explain when to deviate.
- Examples must be runnable and must not contain real credentials. Use placeholders such
  as `$API_TOKEN` or obvious test values (`test-stripe-secret`).
- Keep the tone neutral and practical; no marketing language.

## Pull request process

1. Fork, create a branch, make the change with tests.
2. Run the validator, `pytest` and ruff.
3. Fill in the pull request template checklist.
4. A maintainer reviews within a few days. Small, focused pull requests are merged fastest.

By contributing you agree that your contributions are licensed under the MIT License.
