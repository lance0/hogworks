"""Validate the shared Agent Skills metadata (requires PyYAML)."""

import re
from pathlib import Path

import yaml


def validate(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
    if not match:
        raise ValueError("missing YAML frontmatter delimiters")
    data = yaml.safe_load(match[1])
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    name = data.get("name")
    if (not isinstance(name, str) or len(name) > 64
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
            or name != path.parent.name):
        raise ValueError("name must match its directory and use 1–64 lowercase letters, digits or single hyphens")
    description = data.get("description")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ValueError("description must be a non-empty string of at most 1024 characters")
    if not text[match.end():].strip():
        raise ValueError("missing skill instructions")


if __name__ == "__main__":
    directories = sorted(p for p in Path("skills").iterdir() if p.is_dir())
    if not directories:
        raise SystemExit("No skill directories found")
    failed = False
    for directory in directories:
        path = directory / "SKILL.md"
        try:
            validate(path)
        except (OSError, ValueError, yaml.YAMLError) as error:
            print(f"FAIL {path}: {error}")
            failed = True
        else:
            print(f"PASS {path}")
    raise SystemExit(1 if failed else 0)
