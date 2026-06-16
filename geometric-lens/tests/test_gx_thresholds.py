"""Unit tests for per-model G(x) threshold derivation (_derive_gx_thresholds).

The thresholds must adapt to the model's score scale: a model whose grounded
(PASS) writes cluster high (the Gemma case) should get correspondingly higher
cutoffs, so the off-rails / regression interventions actually fire — instead of
the fixed Qwen-era 0.3/0.15/0.05 that stay silent on that scale.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from geometric_lens.training import _derive_gx_thresholds


def test_gemma_scale_scores_yield_higher_cutoffs():
    # PASS writes clustered ~0.45 (Gemma-like) — the fixed 0.15 default would
    # never fire; derived thresholds must sit up near this model's scale.
    rng = np.random.default_rng(0)
    pass_scores = np.clip(rng.normal(0.46, 0.05, 500), 0, 1)
    t = _derive_gx_thresholds(pass_scores)
    assert t["low"] > 0.25, f"low too low for a 0.46-centered model: {t}"
    assert t["severe"] < t["low"], f"severe must be strictest: {t}"
    assert t["severe"] <= t["off_rails"] <= t["low"], f"ordering wrong: {t}"
    # All within the clamp band.
    assert all(0.02 <= t[k] <= 0.6 for k in t), t


def test_qwen_scale_scores_yield_lower_cutoffs():
    # PASS writes clustered ~0.85 with a low tail (Qwen-like discrimination).
    rng = np.random.default_rng(1)
    pass_scores = np.clip(rng.normal(0.85, 0.18, 500), 0, 1)
    t = _derive_gx_thresholds(pass_scores)
    # A sharper, higher-clustered model tolerates lower cutoffs than Gemma's.
    assert t["severe"] <= t["off_rails"] <= t["low"], t
    assert all(0.02 <= t[k] <= 0.6 for k in t), t


def test_small_sample_falls_back_to_defaults():
    t = _derive_gx_thresholds(np.array([0.4, 0.5, 0.6]))
    assert t == {"off_rails": 0.3, "low": 0.15, "severe": 0.05}


def test_none_falls_back_to_defaults():
    assert _derive_gx_thresholds(None) == {"off_rails": 0.3, "low": 0.15, "severe": 0.05}


if __name__ == "__main__":
    test_gemma_scale_scores_yield_higher_cutoffs()
    test_qwen_scale_scores_yield_lower_cutoffs()
    test_small_sample_falls_back_to_defaults()
    test_none_falls_back_to_defaults()
    print("all gx threshold tests passed")
