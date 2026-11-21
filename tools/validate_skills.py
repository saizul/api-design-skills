#!/usr/bin/env python3
"""Validate every skill in skills/ and the Claude Code plugin manifests.

Checks
  * each skills/<dir>/SKILL.md has YAML frontmatter with name and description
  * name: 1-64 chars, lowercase letters/digits/hyphens, no leading, trailing or
    double hyphen, equal to the folder name (Agent Skills specification)
  * description: 1-1024 chars; compatibility <= 500 chars; metadata is a string map
  * required body sections exist: When to use, When not to use, Workflow, Output
  * SKILL.md is under the line limit
  * files referenced from SKILL.md (Markdown links and `scripts/...`,
    `references/...`, `assets/...` paths) exist inside the skill folder
  * every script in scripts/ supports --help
  * .claude-plugin/marketplace.json and plugin.json are valid and the marketplace
    lists every skill folder (and nothing else)

Exit codes: 0 = valid, 1 = problems found, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
REQUIRED_SECTIONS = ("When to use", "When not to use", "Workflow", "Output")
MAX_SKILL_LINES = 400
ALLOWED_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
PATH_RE = re.compile(r"(?<![\w./-])((?:scripts|references|assets)/[\w./-]+)")


def parse_frontmatter(text: str) -> tuple[dict | None, str, str | None]:
    """Return (frontmatter, body, error). Uses PyYAML when available, else a small parser."""
    if not text.startswith("---\n"):
        return None, text, "SKILL.md must start with '---' frontmatter"
    end = text.find("\n---", 4)
    if end == -1:
        return None, text, "frontmatter is not closed with '---'"
    raw = text[4:end]
    body = text[end + 4 :].lstrip("\n")
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(raw)
    except ImportError:
        data = _simple_yaml(raw)
    except Exception as exc:  # yaml.YAMLError
        return None, body, f"invalid frontmatter YAML: {exc}"
    if not isinstance(data, dict):
        return None, body, "frontmatter must be a mapping"
    return data, body, None


def _simple_yaml(raw: str) -> dict:
    """Minimal fallback for 'key: value' and one nested string map (metadata)."""
    data: dict = {}
    current = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and current is not None:
            key, _, value = line.strip().partition(":")
            data[current][key.strip()] = value.strip().strip("\"'")
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value == "":
            data[key.strip()] = {}
            current = key.strip()
        else:
            data[key.strip()] = value.strip("\"'")
            current = None
    return data


def check_skill(skill_dir: Path, run_scripts: bool = True) -> list[str]:
    problems: list[str] = []
    where = f"skills/{skill_dir.name}"
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{where}: missing SKILL.md"]
    text = skill_md.read_text(encoding="utf-8")
    meta, body, error = parse_frontmatter(text)
    if error:
        return [f"{where}/SKILL.md: {error}"]

    unknown = set(meta) - ALLOWED_FIELDS
    if unknown:
        problems.append(f"{where}: unknown frontmatter field(s): {', '.join(sorted(unknown))}")

    name = meta.get("name")
    if not isinstance(name, str) or not name:
        problems.append(f"{where}: frontmatter 'name' is required")
    else:
        if len(name) > 64:
            problems.append(f"{where}: name is {len(name)} chars (max 64)")
        if not NAME_RE.match(name):
            problems.append(f"{where}: name '{name}' must be lowercase letters, digits and single hyphens")
        if name != skill_dir.name:
            problems.append(f"{where}: name '{name}' does not match folder '{skill_dir.name}'")

    desc = meta.get("description")
    if not isinstance(desc, str) or not desc.strip():
        problems.append(f"{where}: frontmatter 'description' is required")
    else:
        if len(desc) > 1024:
            problems.append(f"{where}: description is {len(desc)} chars (max 1024)")
        if not re.search(r"\b(use when|use it when|use for|when the user)\b", desc, re.I):
            problems.append(f"{where}: description should say when to use the skill ('Use when ...')")

    compat = meta.get("compatibility")
    if compat is not None and (not isinstance(compat, str) or not 1 <= len(compat) <= 500):
        problems.append(f"{where}: compatibility must be a string of 1-500 chars")
    metadata = meta.get("metadata")
    if metadata is not None and (
        not isinstance(metadata, dict) or not all(isinstance(v, str) for v in metadata.values())
    ):
        problems.append(f"{where}: metadata must map strings to strings (quote numbers)")

    headings = {h.strip().lower() for h in re.findall(r"^##\s+(.+)$", body, re.M)}
    for section in REQUIRED_SECTIONS:
        if section.lower() not in headings:
            problems.append(f"{where}: missing section '## {section}'")

    lines = text.count("\n") + 1
    if lines > MAX_SKILL_LINES:
        problems.append(f"{where}: SKILL.md has {lines} lines (max {MAX_SKILL_LINES}); move detail to references/")

    refs = set()
    for target in LINK_RE.findall(body):
        if re.match(r"^[a-z]+:", target) or target.startswith(("#", "/", "../")):
            continue
        refs.add(target.split("#", 1)[0])
    for target in PATH_RE.findall(body):
        refs.add(target.rstrip(".,:;)"))
    for ref in sorted(r for r in refs if r):
        if not (skill_dir / ref).exists():
            problems.append(f"{where}: referenced file not found: {ref}")

    if run_scripts:
        for script in sorted((skill_dir / "scripts").glob("*.py")):
            proc = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=30)
            if proc.returncode != 0 or "usage" not in proc.stdout.lower():
                problems.append(f"{where}: scripts/{script.name} --help failed")
    return problems


def check_manifests(root: Path, skill_names: list[str]) -> list[str]:
    problems: list[str] = []
    market_path = root / ".claude-plugin" / "marketplace.json"
    plugin_path = root / ".claude-plugin" / "plugin.json"
    try:
        market = json.loads(market_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f".claude-plugin/marketplace.json: {exc}"]
    for key in ("name", "owner", "plugins"):
        if key not in market:
            problems.append(f"marketplace.json: missing '{key}'")
    if not isinstance(market.get("owner"), dict) or not market.get("owner", {}).get("name"):
        problems.append("marketplace.json: owner.name is required")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", str(market.get("name", ""))):
        problems.append("marketplace.json: invalid marketplace name")

    listed: list[str] = []
    for i, plugin in enumerate(market.get("plugins") or []):
        if not plugin.get("name") or "source" not in plugin:
            problems.append(f"marketplace.json: plugins[{i}] needs name and source")
            continue
        source = plugin["source"]
        if isinstance(source, str):
            if not (source == "." or source.startswith("./")) or ".." in source:
                problems.append(f"marketplace.json: plugins[{i}].source must start with ./ and not contain ..")
            elif not (root / source).exists():
                problems.append(f"marketplace.json: plugins[{i}].source {source} does not exist")
        for entry in plugin.get("skills") or []:
            if not str(entry).startswith("./"):
                problems.append(f"marketplace.json: skill path {entry} must start with ./")
            path = (root / str(source) / str(entry)).resolve()
            if not (path / "SKILL.md").is_file():
                problems.append(f"marketplace.json: skill path {entry} has no SKILL.md")
            listed.append(Path(str(entry)).name)

    missing = sorted(set(skill_names) - set(listed))
    extra = sorted(set(listed) - set(skill_names))
    if missing:
        problems.append("marketplace.json: skills not listed: " + ", ".join(missing))
    if extra:
        problems.append("marketplace.json: listed skills that do not exist: " + ", ".join(extra))
    if len(listed) != len(set(listed)):
        problems.append("marketplace.json: a skill is listed twice")

    try:
        plugin_manifest = json.loads(plugin_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f".claude-plugin/plugin.json: {exc}")
    else:
        pname = plugin_manifest.get("name")
        if not pname or not NAME_RE.match(str(pname)):
            problems.append("plugin.json: name is required and must be kebab-case")
        entry_names = [p.get("name") for p in market.get("plugins") or []]
        if pname not in entry_names:
            problems.append(f"plugin.json: name '{pname}' does not match a marketplace entry name")
        for key in ("version", "description", "author"):
            if key not in plugin_manifest:
                problems.append(f"plugin.json: '{key}' is recommended")
    return problems


def validate(root: Path, run_scripts: bool = True) -> list[str]:
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return ["skills/ directory not found"]
    skill_dirs = sorted(p for p in skills_dir.iterdir() if p.is_dir() and not p.name.startswith("."))
    problems: list[str] = []
    for skill_dir in skill_dirs:
        problems.extend(check_skill(skill_dir, run_scripts))
    problems.extend(check_manifests(root, [p.name for p in skill_dirs]))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate skills/ and .claude-plugin manifests.")
    parser.add_argument(
        "root",
        nargs="?",
        default=str(Path(__file__).resolve().parent.parent),
        help="Repository root (default: this repo)",
    )
    parser.add_argument("--no-run", action="store_true", help="Do not run scripts with --help")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    root = Path(args.root)
    problems = validate(root, run_scripts=not args.no_run)
    count = len([p for p in (root / "skills").iterdir() if p.is_dir()]) if (root / "skills").is_dir() else 0
    if args.format == "json":
        print(json.dumps({"skills": count, "problems": problems, "ok": not problems}, indent=2))
    elif problems:
        for problem in problems:
            print(f"FAIL {problem}")
        print(f"\n{len(problems)} problem(s) in {count} skill(s)")
    else:
        print(f"OK: {count} skills valid, marketplace lists all of them")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
