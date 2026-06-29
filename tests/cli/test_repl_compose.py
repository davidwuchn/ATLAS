"""Compose lifecycle tests for the interactive CLI."""

from types import SimpleNamespace

from atlas.cli import repl


def _metal_root(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "docker-compose.macos.yml").write_text("services: {}\n")
    (tmp_path / ".env").write_text("ATLAS_BACKEND=metal\n")
    return str(tmp_path)


def test_workspace_recreate_keeps_macos_overlay(monkeypatch, tmp_path):
    root = _metal_root(tmp_path)
    calls = []

    def capture(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(repl.subprocess, "run", capture)
    monkeypatch.setattr(repl, "_check_url", lambda *args, **kwargs: True)
    assert repl._recreate_docker_proxy(root, str(tmp_path / "project")) is True
    assert calls[0][:6] == [
        "docker", "compose", "-f", "docker-compose.yml", "-f",
        "docker-compose.macos.yml",
    ]
    assert "llama-server" not in calls[0]


def test_compose_ownership_check_keeps_macos_overlay(monkeypatch, tmp_path):
    root = _metal_root(tmp_path)
    calls = []

    def capture(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="atlas-proxy\n", stderr="")

    monkeypatch.setattr(repl.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(repl.subprocess, "run", capture)
    assert repl._docker_compose_owns_proxy(root) is True
    assert "docker-compose.macos.yml" in calls[0]
