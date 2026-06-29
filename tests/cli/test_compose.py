"""Public policy tests for backend-aware Compose command construction."""

import pathlib

import pytest

from atlas.cli import compose


def _root(tmp_path: pathlib.Path) -> str:
    for name in (
        "docker-compose.yml",
        "docker-compose.macos.yml",
        "docker-compose.rocm.yml",
        "docker-compose.vulkan.yml",
    ):
        (tmp_path / name).write_text("services: {}\n")
    return str(tmp_path)


@pytest.mark.parametrize(
    ("backend", "expected"),
    [
        ("cuda", []),
        ("metal", ["-f", "docker-compose.yml", "-f",
                   "docker-compose.macos.yml"]),
        ("rocm", ["-f", "docker-compose.yml", "-f",
                  "docker-compose.rocm.yml"]),
        ("vulkan", ["-f", "docker-compose.yml", "-f",
                    "docker-compose.vulkan.yml"]),
    ],
)
def test_backend_selects_expected_compose_files(tmp_path, backend, expected):
    assert compose.file_args(_root(tmp_path), backend=backend,
                             environ={}) == expected


def test_shell_environment_wins_over_dotenv_values(tmp_path):
    root = _root(tmp_path)
    (tmp_path / ".env").write_text("ATLAS_BACKEND=rocm\n")
    assert compose.resolve_backend(
        root,
        values={"ATLAS_BACKEND": "vulkan"},
        environ={"ATLAS_BACKEND": "metal"},
    ) == "metal"


def test_command_places_overlay_before_operation(tmp_path):
    root = _root(tmp_path)
    cmd = compose.command(root, ["up", "-d", "atlas-proxy"],
                          backend="metal", environ={})
    assert cmd == [
        "docker", "compose", "-f", "docker-compose.yml", "-f",
        "docker-compose.macos.yml", "up", "-d", "atlas-proxy",
    ]


def test_missing_required_overlay_fails_before_docker(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    with pytest.raises(FileNotFoundError, match="docker-compose.macos.yml"):
        compose.command(str(tmp_path), ["up", "-d"], backend="metal",
                        environ={})
