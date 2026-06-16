package main

import "testing"

// Threshold resolution: per-model values from the lens response win; absent
// thresholds fall back to the package constants (older lenses).
func TestLensThresholdResolution(t *testing.T) {
	// No thresholds bundled → fall back to constants.
	var bare lensPerStepResult
	if got := bare.lowThreshold(); got != lensLowScoreThreshold {
		t.Errorf("bare low = %v, want fallback %v", got, lensLowScoreThreshold)
	}
	if got := bare.severeThreshold(); got != lensSevereThreshold {
		t.Errorf("bare severe = %v, want fallback %v", got, lensSevereThreshold)
	}
	// Per-model thresholds present → use them.
	withT := lensPerStepResult{Thresholds: &lensThresholds{OffRails: 0.6, Low: 0.45, Severe: 0.3}}
	if got := withT.lowThreshold(); got != 0.45 {
		t.Errorf("per-model low = %v, want 0.45", got)
	}
	if got := withT.severeThreshold(); got != 0.3 {
		t.Errorf("per-model severe = %v, want 0.3", got)
	}
}

// The Gemma case: writes score ~0.40, which never trips the Qwen-calibrated
// default (0.15) — so the intervention was silent. With the model's own
// thresholds (low=0.45), the same scores correctly trigger the regression.
func TestAgentLensRegressionUsesPerModelThresholds(t *testing.T) {
	gemmaScores := []float64{0.40, 0.39}

	// Default (Qwen-scale) thresholds: 0.40 is above 0.15 → no intervention.
	if _, fired := agentLensRegression(gemmaScores, lensLowScoreThreshold, lensSevereThreshold); fired {
		t.Errorf("default thresholds should NOT fire on Gemma-scale scores (~0.4)")
	}

	// Gemma-calibrated thresholds (low=0.45): two consecutive sub-0.45 writes
	// are a regression on this model's scale → fires.
	if _, fired := agentLensRegression(gemmaScores, 0.45, 0.30); !fired {
		t.Errorf("model-calibrated thresholds should fire on a 0.40/0.39 run")
	}
}

// Severe single-write short-circuit also honors the per-model severe value.
func TestAgentLensRegressionSevereIsPerModel(t *testing.T) {
	// One write at 0.32. Below a model severe of 0.35 → immediate fire.
	if _, fired := agentLensRegression([]float64{0.32}, 0.45, 0.35); !fired {
		t.Errorf("single write below per-model severe should fire")
	}
	// Same score under the default severe (0.05) → no fire (needs the run).
	if _, fired := agentLensRegression([]float64{0.32}, lensLowScoreThreshold, lensSevereThreshold); fired {
		t.Errorf("single 0.32 write should not fire under default severe=0.05")
	}
}
