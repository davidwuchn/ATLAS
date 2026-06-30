"""Backend-aware Docker Compose command construction.

ATLAS has one base Compose file plus backend overlays.  Any CLI command that
mutates or inspects the deployment must select the same files that were used
to start it; otherwise a Metal host can accidentally resolve the CUDA
llama-server service from the base file.
"""

from __future__ import annotations

import os
import shlex
from typing import Dict, Iterable, List, Mapping, Optional


_OVERLAY_BY_BACKEND = {
    "metal": "docker-compose.macos.yml",
    "rocm": "docker-compose.rocm.yml",
    "vulkan": "docker-compose.vulkan.yml",
}


def read_env_file(atlas_root: str) -> Dict[str, str]:
    """Read the checkout's Compose ``.env`` without executing shell code."""
    values: Dict[str, str] = {}
    path = os.path.join(atlas_root, ".env")
    try:
        with open(path, encoding="utf-8-sig") as fh:
            for raw in fh:
                line = raw.strip()
                if line.startswith("export "):
                    line = line[len("export "):].lstrip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.lstrip()
                head, marker, _ = value.partition("#")
                if marker and head and head[-1] in " \t":
                    value = head
                values[key.strip()] = value.strip().strip("'\"")
    except OSError:
        # An unreadable optional .env is treated as absent; callers still
        # honor explicit process-environment values and built-in defaults.
        pass
    return values


def resolve_backend(
    atlas_root: str,
    values: Optional[Mapping[str, str]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Resolve backend with shell environment taking precedence over `.env`."""
    env = os.environ if environ is None else environ
    backend = env.get("ATLAS_BACKEND")
    if not backend and values is not None:
        backend = values.get("ATLAS_BACKEND")
    if not backend:
        backend = read_env_file(atlas_root).get("ATLAS_BACKEND")
    return backend.strip().lower() if backend else None


def file_args(
    atlas_root: str,
    backend: Optional[str] = None,
    values: Optional[Mapping[str, str]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> List[str]:
    """Return Compose ``-f`` arguments for the resolved backend.

    CUDA keeps Compose's default discovery so a developer's conventional
    ``docker-compose.override.yml`` still applies. Backends with an explicit
    ATLAS overlay name both files in merge order.
    """
    selected = backend or resolve_backend(atlas_root, values, environ)
    overlay = _OVERLAY_BY_BACKEND.get(selected or "")
    if not overlay:
        return []
    if not os.path.isfile(os.path.join(atlas_root, overlay)):
        raise FileNotFoundError(
            "ATLAS backend {!r} requires missing {}".format(selected, overlay)
        )
    return ["-f", "docker-compose.yml", "-f", overlay]


def command(
    atlas_root: str,
    args: Iterable[str],
    backend: Optional[str] = None,
    values: Optional[Mapping[str, str]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> List[str]:
    """Build a complete ``docker compose`` argv list."""
    return [
        "docker", "compose",
        *file_args(atlas_root, backend, values, environ),
        *list(args),
    ]


def format_command(
    atlas_root: str,
    args: Iterable[str],
    backend: Optional[str] = None,
    values: Optional[Mapping[str, str]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> str:
    """Return a shell-display form of :func:`command`."""
    return shlex.join(command(atlas_root, args, backend, values, environ))
