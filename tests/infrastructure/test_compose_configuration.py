"""Static contracts for runtime configuration shared across services."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_runtime_keys_are_upgrade_fallbacks_only():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert (
        "PARALLEL_SLOTS=${ATLAS_PARALLEL_SLOTS:-${PARALLEL_SLOTS:-4}}"
        in compose
    )
    assert (
        "KV_CACHE_TYPE_K=${ATLAS_KV_TYPE_K:-${KV_CACHE_TYPE_K:-f16}}"
        in compose
    )
    assert (
        "KV_CACHE_TYPE_V=${ATLAS_KV_TYPE_V:-${KV_CACHE_TYPE_V:-f16}}"
        in compose
    )
    assert (
        "ATLAS_PARALLEL_SLOTS=${ATLAS_PARALLEL_SLOTS:-${PARALLEL_SLOTS:-4}}"
        in compose
    )
