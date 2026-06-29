"""Model onboarding tests for backend-specific inference lifecycles."""

from atlas.cli.commands import onboard


def test_metal_onboarding_never_starts_cuda_container(monkeypatch, tmp_path):
    monkeypatch.setattr(onboard, "_serving_this", lambda url, model: (False, False))

    def unexpected_run(*args, **kwargs):
        raise AssertionError("Metal onboarding must not invoke docker compose")

    monkeypatch.setattr(onboard, "_run", unexpected_run)
    ready, detail = onboard._arch_supported(
        str(tmp_path), {"ATLAS_BACKEND": "metal"}, "model.gguf",
        start=True, color=False,
    )
    assert ready is False
    assert "atlas-llama-macos.sh" in detail
    assert "will not start the CUDA container" in detail


def test_nonmetal_log_inspection_uses_backend_overlay(monkeypatch, tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "docker-compose.rocm.yml").write_text("services: {}\n")
    monkeypatch.setattr(onboard, "_serving_this", lambda url, model: (False, False))
    calls = []

    def capture(cmd, **kwargs):
        calls.append(cmd)
        return 0, "", ""

    monkeypatch.setattr(onboard, "_run", capture)
    ready, _ = onboard._arch_supported(
        str(tmp_path), {"ATLAS_BACKEND": "rocm"}, "model.gguf",
        start=False, color=False,
    )
    assert ready is False
    assert calls == [[
        "docker", "compose", "-f", "docker-compose.yml", "-f",
        "docker-compose.rocm.yml", "logs", "--tail=200", "llama-server",
    ]]
