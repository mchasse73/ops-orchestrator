"""CLI slash commands — skill-defined shortcuts for common tasks.

Commands are declared in SKILL.md frontmatter under `commands:`:

    ---
    name: list-vm-skill
    commands:
      - name: list-vms
        description: Show all VMs across the cluster
        expands_to: "List all VMs in the cluster with their status and node assignment."
      - name: list-nodes
        description: Show all Proxmox nodes
        expands_to: "List all Proxmox cluster nodes."
    ---

The coordinator's CLI checks if the input starts with `/` and routes it:
  ops-agent /help              # built-in: list all commands
  ops-agent /list-vms          # expands to the text above
  ops-agent /list-vms --node prox2  # expands + appends extra args

This is a pure Python registry — no LLM calls. The command text is the task.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Command:
    """A single CLI shortcut."""
    name: str
    description: str
    expands_to: str
    skill_name: str  # which skill defined this


def load_commands(skills_dir: Path) -> dict[str, Command]:
    """Load all commands from skill SKILL.md files.

    Parses frontmatter for a `commands:` block like:
      commands:
        - name: list-vms
          description: Show all VMs
          expands_to: "List all VMs..."

    Returns {command_name: Command}.
    """
    commands = {}
    for skill_dir in skills_dir.glob("*/"):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        content = skill_md.read_text()
        # extract frontmatter (between --- ----)
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            continue
        frontmatter = match.group(1)
        # crude YAML parse for commands: list
        # find where commands: starts and capture until next top-level key or EOF
        cmd_start = frontmatter.find("commands:\n")
        if cmd_start == -1:
            continue
        cmd_start += len("commands:\n")
        # find the end of the commands block (next top-level key or EOF)
        rest = frontmatter[cmd_start:]
        next_key = re.search(r"^[a-z]", rest, re.MULTILINE)
        if next_key:
            cmd_text = rest[: next_key.start()]
        else:
            cmd_text = rest
        # parse each command block (lines starting with "  - name:")
        skill_name = skill_dir.name
        current_cmd = {}
        for line in cmd_text.split("\n"):
            if line.startswith("  - name:"):
                if current_cmd:
                    cmd = Command(
                        name=current_cmd["name"],
                        description=current_cmd.get("description", ""),
                        expands_to=current_cmd.get("expands_to", ""),
                        skill_name=skill_name,
                    )
                    commands[cmd.name] = cmd
                current_cmd = {"name": line.split(":", 1)[1].strip()}
            elif line.startswith("    description:"):
                current_cmd["description"] = line.split(":", 1)[1].strip()
            elif line.startswith("    expands_to:"):
                val = line.split(":", 1)[1].strip()
                # strip quotes if present
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                current_cmd["expands_to"] = val
        if current_cmd:
            cmd = Command(
                name=current_cmd["name"],
                description=current_cmd.get("description", ""),
                expands_to=current_cmd.get("expands_to", ""),
                skill_name=skill_name,
            )
            commands[cmd.name] = cmd
    return commands


def parse_command_line(input_str: str) -> tuple[str | None, str]:
    """Check if input is a command. Return (command_name, expanded_task) or (None, input_str)."""
    if not input_str.startswith("/"):
        return None, input_str
    # split on first space: /list-vms --node prox2 -> ["list-vms", "--node prox2"]
    parts = input_str[1:].split(None, 1)
    cmd_name = parts[0] if parts else ""
    extra_args = parts[1] if len(parts) > 1 else ""
    return cmd_name, extra_args


def help_text(commands: dict[str, Command]) -> str:
    """Format all commands as a help message."""
    if not commands:
        return "No commands available. Use the coordinator directly: ops-agent '<task>'"
    lines = ["Available commands:\n"]
    for name in sorted(commands.keys()):
        cmd = commands[name]
        lines.append(f"  /{name}")
        lines.append(f"    {cmd.description}")
        lines.append(f"    (from: {cmd.skill_name})\n")
    return "".join(lines)


def expand_command(cmd_name: str, commands: dict[str, Command], extra_args: str = "") -> str | None:
    """Expand a command name to its task text. Return None if not found."""
    if cmd_name not in commands:
        return None
    cmd = commands[cmd_name]
    task = cmd.expands_to
    if extra_args:
        task = f"{task} {extra_args}"
    return task
