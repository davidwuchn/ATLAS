package main

import (
	"strings"
	"testing"
)

func TestTracebackSteerNamesFixSite(t *testing.T) {
	ctx := &AgentContext{WorkingDir: "/workspace"}
	out := "Traceback (most recent call last):\n" +
		"  File \"/workspace/_agenttest/app.py\", line 14, in get_item\n" +
		"    return jsonify(items[item_id + 1])\n" +
		"IndexError: list index out of range\n"
	steer := tracebackSteer(ctx, out)
	for _, want := range []string{"get_item", "line 14", "IndexError", "function:get_item"} {
		if !strings.Contains(steer, want) {
			t.Errorf("steer missing %q:\n%s", want, steer)
		}
	}
}

func TestTracebackSteerNoTraceback(t *testing.T) {
	ctx := &AgentContext{WorkingDir: "/workspace"}
	if s := tracebackSteer(ctx, "Total inventory value: $237\n"); s != "" {
		t.Errorf("expected empty steer for non-traceback output, got: %s", s)
	}
}

// The deepest frame is usually stdlib; the fix site is the deepest PROJECT
// frame (the user line that called into the library).
func TestTracebackSteerSkipsStdlib(t *testing.T) {
	ctx := &AgentContext{WorkingDir: "/workspace"}
	out := "Traceback (most recent call last):\n" +
		"  File \"/workspace/app.py\", line 5, in main\n" +
		"    data = json.loads(raw)\n" +
		"  File \"/usr/lib/python3.9/json/__init__.py\", line 346, in loads\n" +
		"    return _default_decoder.decode(s)\n" +
		"ValueError: Expecting value\n"
	steer := tracebackSteer(ctx, out)
	if !strings.Contains(steer, "app.py") || !strings.Contains(steer, "function:main") {
		t.Errorf("should pick project frame app.py:main, got: %s", steer)
	}
	if strings.Contains(steer, "json/__init__") {
		t.Errorf("should NOT point at stdlib, got: %s", steer)
	}
}
