## What does this pull request do?

<!-- One or two sentences. Link the issue: "Closes #123". -->

## Type

- [ ] New skill
- [ ] Improvement to an existing skill (advice, references, examples)
- [ ] Script change or new lint rule
- [ ] Bug fix
- [ ] Documentation or repository tooling

## Checklist

- [ ] `python tools/validate_skills.py` passes
- [ ] `pytest` passes and new script behaviour has tests with fixture specs in `tests/fixtures/`
- [ ] `ruff check . && ruff format --check .` passes
- [ ] SKILL.md stays under 400 lines; long material is in `references/`
- [ ] Scripts use only the standard library (PyYAML optional for YAML input), support
      `--help` and `--format json`, make no network calls and never print secrets
- [ ] New skills are listed in `.claude-plugin/marketplace.json` and the README skills table
- [ ] Advice cites the RFC, spec or official documentation it follows
- [ ] CHANGELOG.md updated under "Unreleased"
