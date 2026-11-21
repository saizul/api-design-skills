import json
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import validate_skills as vs  # noqa: E402

GOOD_SKILL = """---
name: demo-skill
description: Does a demo thing. Use when the user asks for a demo.
metadata:
  author: Test
  version: "0.1.0"
---

# Demo

## When to use
- demos

## When not to use
- real work

## Workflow
1. Run `scripts/demo.py` and read [the guide](references/guide.md#top).

## Output
- text
"""


@pytest.fixture
def repo(tmp_path):
    skill = tmp_path / "skills" / "demo-skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "references").mkdir()
    (skill / "SKILL.md").write_text(GOOD_SKILL)
    (skill / "references" / "guide.md").write_text("# Guide\n")
    (skill / "scripts" / "demo.py").write_text(
        "import argparse\nargparse.ArgumentParser(description='demo').parse_args()\n"
    )
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "owner": {"name": "Test"},
                "plugins": [{"name": "demo", "source": "./", "skills": ["./skills/demo-skill"]}],
            }
        )
    )
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "demo", "version": "0.1.0", "description": "d", "author": {"name": "Test"}})
    )
    return tmp_path


def test_this_repository_is_valid():
    assert vs.validate(ROOT) == []


def test_fixture_repo_is_valid(repo):
    assert vs.validate(repo) == []


def edit(repo, old, new):
    path = repo / "skills" / "demo-skill" / "SKILL.md"
    path.write_text(path.read_text().replace(old, new))


@pytest.mark.parametrize(
    "old,new,expected",
    [
        ("name: demo-skill", "name: Demo_Skill", "must be lowercase"),
        ("name: demo-skill", "name: other-skill", "does not match folder"),
        ("name: demo-skill", "name: demo--skill", "must be lowercase"),
        ("name: demo-skill", "name: " + "a" * 65, "max 64"),
        ("Does a demo thing. Use when the user asks for a demo.", "x" * 1100, "max 1024"),
        ("Does a demo thing. Use when the user asks for a demo.", "Does a demo thing.", "when to use"),
        ("## When not to use", "## Notes", "missing section '## When not to use'"),
        ("## Output", "## Result", "missing section '## Output'"),
        ("references/guide.md#top", "references/missing.md", "referenced file not found: references/missing.md"),
        ("`scripts/demo.py`", "`scripts/nope.py`", "referenced file not found: scripts/nope.py"),
        ('version: "0.1.0"', "version: 0.1", "metadata must map strings"),
        ("metadata:", "colour: blue\nmetadata:", "unknown frontmatter field"),
    ],
)
def test_skill_problems(repo, old, new, expected):
    edit(repo, old, new)
    problems = vs.validate(repo)
    assert any(expected in p for p in problems), problems


def test_missing_frontmatter(repo):
    (repo / "skills" / "demo-skill" / "SKILL.md").write_text("# no frontmatter\n")
    assert any("frontmatter" in p for p in vs.validate(repo))


def test_too_long(repo):
    edit(repo, "## Output", "\n" * 450 + "## Output")
    assert any("max 400" in p for p in vs.validate(repo))


def test_broken_script_help(repo):
    (repo / "skills" / "demo-skill" / "scripts" / "demo.py").write_text("raise SystemExit(3)\n")
    assert any("--help failed" in p for p in vs.validate(repo))
    assert vs.validate(repo, run_scripts=False) == []


def test_marketplace_must_list_every_skill(repo):
    shutil.copytree(repo / "skills" / "demo-skill", repo / "skills" / "second-skill")
    edit_path = repo / "skills" / "second-skill" / "SKILL.md"
    edit_path.write_text(edit_path.read_text().replace("name: demo-skill", "name: second-skill"))
    assert any("skills not listed: second-skill" in p for p in vs.validate(repo))


def test_marketplace_problems(repo):
    path = repo / ".claude-plugin" / "marketplace.json"
    data = json.loads(path.read_text())
    data["plugins"][0]["skills"].append("./skills/ghost")
    data["plugins"][0]["source"] = "../elsewhere"
    del data["owner"]
    path.write_text(json.dumps(data))
    problems = "\n".join(vs.validate(repo))
    assert "owner.name is required" in problems
    assert "must start with ./" in problems
    assert "ghost" in problems
    path.write_text("{broken")
    assert any("marketplace.json" in p for p in vs.validate(repo))


def test_plugin_name_must_match_entry(repo):
    path = repo / ".claude-plugin" / "plugin.json"
    path.write_text(json.dumps({"name": "different", "version": "1", "description": "d", "author": {"name": "T"}}))
    assert any("does not match a marketplace entry" in p for p in vs.validate(repo))


def test_simple_yaml_fallback():
    data = vs._simple_yaml('name: x\ndescription: "a: b"\nmetadata:\n  author: Me\n  version: "1"\n')
    assert data == {"name": "x", "description": "a: b", "metadata": {"author": "Me", "version": "1"}}


def test_cli(repo):
    ok = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "validate_skills.py"), str(repo)], capture_output=True, text=True
    )
    assert ok.returncode == 0 and "OK: 1 skills" in ok.stdout
    edit(repo, "## Output", "## Nope")
    bad = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "validate_skills.py"), str(repo), "--format", "json"],
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1 and json.loads(bad.stdout)["ok"] is False
