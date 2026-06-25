"""Tests for the Haiku worker delegation."""
from ops_agent.worker import DELEGATABLE_PREFIXES, is_delegatable


def test_is_delegatable_list_tools():
    """list_* tools are delegatable (read-only)."""
    assert is_delegatable("proxmox__list_nodes")
    assert is_delegatable("proxmox__list_vms")
    assert is_delegatable("dynu__list_records")


def test_is_delegatable_get_tools():
    """get_* tools are delegatable."""
    assert is_delegatable("proxmox__get_vm_config")
    assert is_delegatable("proxmox__get_vm_status")


def test_is_delegatable_status_tools():
    """status tools are delegatable."""
    assert is_delegatable("proxmox__status")


def test_is_delegatable_next_free():
    """next_free_* tools are delegatable."""
    assert is_delegatable("proxmox__next_free_vmid")


def test_is_delegatable_mutating_tools():
    """Mutating tools (add_, delete_, set_, start_) are NOT delegatable."""
    assert not is_delegatable("proxmox__clone_template")
    assert not is_delegatable("proxmox__set_vm_config")
    assert not is_delegatable("proxmox__add_disk")
    assert not is_delegatable("proxmox__start_vm")
    assert not is_delegatable("dynu__add_a_record")
    assert not is_delegatable("dynu__delete_record")


def test_is_delegatable_unknown_tools():
    """Unknown tool names are not delegatable."""
    assert not is_delegatable("proxmox__unknown_operation")
    assert not is_delegatable("custom__tool")


def test_delegatable_prefixes():
    """DELEGATABLE_PREFIXES is non-empty and contains expected patterns."""
    assert "list_" in DELEGATABLE_PREFIXES
    assert "get_" in DELEGATABLE_PREFIXES
    assert "status" in DELEGATABLE_PREFIXES
