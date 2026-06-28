package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func withInferenceURL(t *testing.T, url string) {
	t.Helper()
	previous := inferenceURL
	inferenceURL = url
	t.Cleanup(func() {
		inferenceURL = previous
	})
}

func TestPassthroughPreservesRequestURI(t *testing.T) {
	var gotMethod string
	var gotRequestURI string
	var gotBody string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotRequestURI = r.URL.RequestURI()
		body, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatalf("read upstream body: %v", err)
		}
		gotBody = string(body)
		w.Header().Set("X-Upstream", "seen")
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte("ok"))
	}))
	t.Cleanup(upstream.Close)
	withInferenceURL(t, upstream.URL)

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions?stream=true&n=2", strings.NewReader("payload"))
	req.Header.Set("X-Client", "atlas-test")
	rec := httptest.NewRecorder()

	newProxyMux().ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("status = %d, want %d; body=%q", rec.Code, http.StatusAccepted, rec.Body.String())
	}
	if gotMethod != http.MethodPost {
		t.Fatalf("method = %q, want %q", gotMethod, http.MethodPost)
	}
	if gotRequestURI != "/v1/chat/completions?stream=true&n=2" {
		t.Fatalf("request URI = %q", gotRequestURI)
	}
	if gotBody != "payload" {
		t.Fatalf("body = %q", gotBody)
	}
	if rec.Header().Get("X-Upstream") != "seen" {
		t.Fatalf("upstream header was not copied")
	}
}

func TestPassthroughRejectsOversizedBody(t *testing.T) {
	upstreamCalled := false
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamCalled = true
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(upstream.Close)
	withInferenceURL(t, upstream.URL)

	handler := http.MaxBytesHandler(newProxyMux(), 1)
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader("too large"))
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("status = %d, want %d; body=%q", rec.Code, http.StatusRequestEntityTooLarge, rec.Body.String())
	}
	if upstreamCalled {
		t.Fatalf("oversized request reached upstream")
	}
}
