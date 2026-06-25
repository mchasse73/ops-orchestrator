"""Tests for the commands registry and CLI routing."""
import tempfile
from pathlib import Path

from ops_agent.commands import (
    Command,
    expand_command,
    help_text,
    load_commands,
    parse_command_line,
)


def test_parse_command_line_command():
    """Parse a command line starting with /."""
    cmd, extra = parse_command_line("/list-vms --node prox2")
    assert cmd == "list-vms"
    assert extra == "--node prox2"


def test_parse_command_line_no_command():
    """Parse a regular task (no /)."""
    cmd, extra = parse_command_line("list all VMs")
    assert cmd is None
    assert extra == "list all VMs"


def test_parse_command_line_commands():
    """Parse /commands."""
    cmd, extra = parse_command_line("/commands")
    assert cmd == "commands"
    assert extra == ""


def test_expand_command_exists():
    """Expand a known command."""
    commands = {
        "list-vms": Command(
            name="list-vms",
            description="Show VMs",
            expands_to="List all VMs in the cluster",
            skill_name="test-skill",
        )
    }
    result = expand_command("list-vms", commands)
    assert result == "List all VMs in the cluster"


def test_expand_command_with_args():
    """Expand a command and append extra args."""
    commands = {
        "list-vms": Command(
            name="list-vms",
            description="Show VMs",
            expands_to="List all VMs in the cluster",
            skill_name="test-skill",
        )
    }
    result = expand_command("list-vms", commands, "--node prox2")
    assert result == "List all VMs in the cluster --node prox2"


def test_expand_command_not_found():
    """Expand a nonexistent command returns None."""
    commands = {}
    result = expand_command("unknown", commands)
    assert result is None


def test_help_text_empty():
    """Help text for empty command registry."""
    result = help_text({})
    assert "No commands available" in result


def test_help_text_with_commands():
    """Help text lists all commands."""
    commands = {
        "list-vms": Command(
            name="list-vms",
            description="Show all VMs",
            expands_to="...",
            skill_name="provision",
        ),
        "list-nodes": Command(
            name="list-nodes",
            description="Show all nodes",
            expands_to="...",
            skill_name="provision",
        ),
    }
    result = help_text(commands)
    assert "/list-nodes" in result
    assert "/list-vms" in result
    assert "Show all VMs" in result
    assert "(from: provision)" in result


def test_load_commands_from_skill():
    """Load commands from a SKILL.md file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "test-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: test-skill
description: A test skill
commands:
  - name: cmd1
    description: First command
    expands_to: "Do the first thing"
  - name: cmd2
    description: Second command
    expands_to: "Do the second thing"
---

# Skill body
Test content.
"""
        )
        commands = load_commands(Path(tmpdir))
        assert len(commands) == 2
        assert commands["cmd1"].name == "cmd1"
        assert commands["cmd1"].skill_name == "test-skill"
        assert commands["cmd2"].expands_to == "Do the second thing"


def test_load_commands_no_commands_key():
    """Load from a skill with no commands: key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "test-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: test-skill
description: A test skill
---

# Skill body
"""
        )
        commands = load_commands(Path(tmpdir))
        assert len(commands) == 0
