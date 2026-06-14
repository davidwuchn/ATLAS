package main

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
)

// Option 3 (issue #39 / Dmitri thesis): convert localization the model is bad
// at into the directed edit it is good at. When run_command surfaces a Python
// traceback, the deepest in-project frame names the exact fix site — so instead
// of leaving a weak model to "find the bug" (where it hallucinates symbols and
// edits the wrong function), the harness mechanically extracts file:line:
// function from the traceback and hands the model a directed instruction.
//
// Verified failure this addresses: a traceback pointing at draw():95 / get_item
// line N, after which the model edited an unrelated function. The stack frame IS
// the localization — no LLM reasoning required to read it.

var reTraceFrame = regexp.MustCompile(`File "([^"]+)", line (\d+), in (\S+)`)

// tracebackExclusion is the grammar-level counterpart to runBlockAfterTraceback.
// If the most recent tool result is a crashed run with a parseable traceback,
// it returns the run tools to ban from the next decision's GBNF tool-name enum
// plus a directed [system note]. The soft block returns an error the model can
// ignore (observed: it re-emitted run_command 6×); banning the tool name makes
// re-running *physically unemittable*, forcing the model to edit the named fix
// site. The restriction is scoped to one decision and clears once the model
// acts (the most recent tool result is then the edit, not the crash).
func tracebackExclusion(ctx *AgentContext) ([]string, string) {
	for i := len(ctx.Messages) - 1; i >= 0; i-- {
		m := ctx.Messages[i]
		if m.Role != "tool" {
			continue
		}
		if m.ToolName != "run_command" && m.ToolName != "run_background" {
			return nil, ""
		}
		var r struct {
			Data struct {
				Stdout string `json:"stdout"`
				Stderr string `json:"stderr"`
			} `json:"data"`
		}
		_ = json.Unmarshal([]byte(m.Content), &r)
		steer := tracebackSteer(ctx, r.Data.Stderr+"\n"+r.Data.Stdout)
		if steer == "" {
			return nil, ""
		}
		note := "[system note]: For this single decision, run_command and run_background are unavailable — the code is unchanged, so running it again only reproduces the crash. Make the edit now. " + steer
		return []string{"run_command", "run_background"}, note
	}
	return nil, ""
}

// runBlockAfterTraceback prevents the run-it-again loop. A weak model, handed a
// crash + a directed "fix function X" steer, often just re-emits the identical
// run_command instead of editing (observed: 6 identical runs, no edit). If the
// most recent tool result was a run that crashed with a traceback, block the
// next run and return the directed steer as the result — the code is unchanged,
// so re-running can only crash the same way. The block clears itself naturally:
// once the model edits, the most recent tool result is the edit, not the crash.
func runBlockAfterTraceback(ctx *AgentContext) *ToolResult {
	for i := len(ctx.Messages) - 1; i >= 0; i-- {
		m := ctx.Messages[i]
		if m.Role != "tool" {
			continue
		}
		if m.ToolName != "run_command" && m.ToolName != "run_background" {
			return nil // most recent tool wasn't a run (e.g. an edit) — don't block
		}
		var r struct {
			Data struct {
				Stdout string `json:"stdout"`
				Stderr string `json:"stderr"`
			} `json:"data"`
			Error string `json:"error"`
		}
		_ = json.Unmarshal([]byte(m.Content), &r)
		steer := tracebackSteer(ctx, r.Data.Stderr+"\n"+r.Data.Stdout)
		if steer == "" {
			return nil
		}
		return &ToolResult{Success: false, Error: "Re-running is blocked: the code is unchanged, so it will crash exactly the same way. Edit the code FIRST, then run. " + steer}
	}
	return nil
}

// tracebackSteer scans tool output for a Python traceback and returns a
// directed steer naming the exact fix site, or "" when there is no parseable
// in-project frame. ctx is used to read the offending line from disk
// (best-effort) so the steer can quote it.
func tracebackSteer(ctx *AgentContext, output string) string {
	if !strings.Contains(output, "Traceback (most recent call last)") {
		return ""
	}
	frames := reTraceFrame.FindAllStringSubmatch(output, -1)
	if len(frames) == 0 {
		return ""
	}

	// Walk frames outermost→deepest; keep the LAST one that's a project file
	// (skip stdlib / site-packages / <string> / <frozen ...> frames — the bug
	// is in the user's code, not the library it called).
	var file, fn string
	var lineNo int
	for _, f := range frames {
		p := f[1]
		if strings.Contains(p, "site-packages") || strings.Contains(p, "/usr/lib/") ||
			strings.Contains(p, "/lib/python") || strings.HasPrefix(p, "<") {
			continue
		}
		n, err := strconv.Atoi(f[2])
		if err != nil {
			continue
		}
		file, lineNo, fn = p, n, f[3]
	}
	if file == "" || lineNo == 0 {
		return ""
	}

	// Exception summary = last non-indented, non-"Traceback" line.
	exc := ""
	for _, l := range strings.Split(strings.TrimRight(output, "\n"), "\n") {
		if l == "" || strings.HasPrefix(l, " ") || strings.HasPrefix(l, "\t") ||
			strings.HasPrefix(l, "Traceback") {
			continue
		}
		exc = strings.TrimSpace(l)
	}

	// Best-effort: read the offending line so the steer can quote real bytes.
	exact := ""
	if data, err := os.ReadFile(resolveAgentPath(ctx, file)); err == nil {
		lines := strings.Split(string(data), "\n")
		if lineNo >= 1 && lineNo <= len(lines) {
			exact = strings.TrimSpace(lines[lineNo-1])
		}
	}

	rel := file
	if i := strings.Index(rel, "/workspace/"); i >= 0 {
		rel = rel[i+len("/workspace/"):]
	}

	var sb strings.Builder
	sb.WriteString("[system note]: The traceback points at the exact bug location — ")
	fmt.Fprintf(&sb, "%s line %d, in function `%s`", rel, lineNo, fn)
	if exc != "" {
		sb.WriteString(" (" + exc + ")")
	}
	sb.WriteString(". ")
	if exact != "" {
		fmt.Fprintf(&sb, "That line is: `%s`. ", exact)
	}
	// Directed instruction — name the one function to change; forbid the
	// failure modes we keep seeing (edit elsewhere, hardcode the value).
	if fn != "<module>" && fn != "" {
		fmt.Fprintf(&sb, "Fix the bug in `%s` — use ast_edit with selector `function:%s`. ", fn, fn)
	} else {
		fmt.Fprintf(&sb, "Fix the code at line %d. ", lineNo)
	}
	sb.WriteString("Do NOT edit any other function and do NOT hardcode a value to make the symptom go away — fix the actual logic at this location.")
	return sb.String()
}
