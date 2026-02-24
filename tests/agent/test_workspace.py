"""Tests for workspace creation functionality."""

import tempfile
from pathlib import Path

import pytest

from nanocrew.config.migration import (
    ensure_agent_workspace,
    ensure_workspaces_structure,
    get_main_workspace,
)


@pytest.fixture
def temp_workspace_dir():
    """Create a temporary directory for workspace tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_ensure_agent_workspace_creates_structure(temp_workspace_dir):
    """Test ensure_agent_workspace creates complete directory structure."""
    workspace = temp_workspace_dir / "test_agent"

    # Ensure workspace
    ensure_agent_workspace(workspace, "test_agent")

    # Check directories exist
    assert workspace.exists()
    assert (workspace / "memory").exists()
    assert (workspace / "skills").exists()


def test_ensure_agent_workspace_creates_template_files(temp_workspace_dir):
    """Test ensure_agent_workspace creates template files."""
    workspace = temp_workspace_dir / "my_agent"

    ensure_agent_workspace(workspace, "my_agent")

    # Check template files exist
    assert (workspace / "AGENTS.md").exists()
    assert (workspace / "SOUL.md").exists()
    assert (workspace / "USER.md").exists()

    # Check content includes agent name
    agents_md = (workspace / "AGENTS.md").read_text()
    assert "my_agent" in agents_md

    soul_md = (workspace / "SOUL.md").read_text()
    assert "my_agent" in soul_md


def test_ensure_agent_workspace_creates_memory_files(temp_workspace_dir):
    """Test ensure_agent_workspace creates memory files."""
    workspace = temp_workspace_dir / "agent_with_memory"

    ensure_agent_workspace(workspace, "agent_with_memory")

    # Check memory files exist
    memory_dir = workspace / "memory"
    assert memory_dir.exists()
    assert (memory_dir / "MEMORY.md").exists()
    assert (memory_dir / "HISTORY.md").exists()


def test_ensure_agent_workspace_idempotent(temp_workspace_dir):
    """Test ensure_agent_workspace is idempotent (safe to run multiple times)."""
    workspace = temp_workspace_dir / "idempotent_agent"

    # Run twice
    ensure_agent_workspace(workspace, "idempotent_agent")
    first_agents_md = (workspace / "AGENTS.md").read_text()

    ensure_agent_workspace(workspace, "idempotent_agent")
    second_agents_md = (workspace / "AGENTS.md").read_text()

    # Content should be the same
    assert first_agents_md == second_agents_md


def test_ensure_agent_workspace_different_agents(temp_workspace_dir):
    """Test creating workspaces for different agents."""
    backend_ws = temp_workspace_dir / "backend"
    product_ws = temp_workspace_dir / "product"

    ensure_agent_workspace(backend_ws, "backend")
    ensure_agent_workspace(product_ws, "product")

    # Each has its own name in content
    backend_soul = (backend_ws / "SOUL.md").read_text()
    product_soul = (product_ws / "SOUL.md").read_text()

    assert "backend" in backend_soul
    assert "product" in product_soul
    assert "product" not in backend_soul
    assert "backend" not in product_soul


def test_ensure_workspaces_structure(temp_workspace_dir):
    """Test ensure_workspaces_structure creates main workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        main = tmp_path / "workspaces" / "main"

        # Patch _get_data_dir to use temp directory
        import nanocrew.config.migration as migration

        original_get_data_dir = migration._get_data_dir
        migration._get_data_dir = lambda: tmp_path

        try:
            result = ensure_workspaces_structure()

            assert result == main
            assert main.exists()
            assert (main / ".sessions").exists()
            assert (main / "memory").exists()
            assert (main / "skills").exists()
        finally:
            migration._get_data_dir = original_get_data_dir


def test_get_main_workspace(temp_workspace_dir):
    """Test get_main_workspace returns correct path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        import nanocrew.config.migration as migration

        original_get_data_dir = migration._get_data_dir
        migration._get_data_dir = lambda: tmp_path

        try:
            main = get_main_workspace()

            assert main == tmp_path / "workspaces" / "main"
            assert main.exists()
        finally:
            migration._get_data_dir = original_get_data_dir
