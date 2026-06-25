"""Skill registry + on-demand loader (progressive disclosure).

A skill is a folder under skills_dir containing SKILL.md with YAML frontmatter:

    ---
    name: dynu-dns
    description: Manage public DNS records on Dynu (add/update/delete A records).
    ---
    <full procedure the coordinator reads only when it loads the skill>

Only the (name, description) pairs sit in the coordinator's context by default;
the full body is injected on demand via load_skill().
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path


def _parse(md: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body). Tolerates a missing frontmatter block."""
    if md.startswith("---"):
        _, fm, body = md.split("---", 2)
        meta = {}
        for line in fm.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        return meta, body.strip()
    return {}, md.strip()


def load_skills(skills_dir: str | Path) -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    for skill_md in sorted(Path(skills_dir).glob("*/SKILL.md")):
        meta, body = _parse(skill_md.read_text())
        name = meta.get("name", skill_md.parent.name)
        skills[name] = Skill(
            name=name,
            description=meta.get("description", ""),
            body=body,
            path=skill_md,
        )
    return skills


def registry_block(skills: dict[str, Skill]) -> str:
    """The cheap, always-in-context list the coordinator sees."""
    lines = ["Available skills (call load_skill to read the full procedure):"]
    for s in skills.values():
        lines.append(f"  - {s.name}: {s.description}")
    return "\n".join(lines)
