import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import * as api from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, loadWorkspace: vi.fn() };
});

const snapshot: api.WorkspaceSnapshot = {
  project: { project_id: "PRJ-1", name: "AI TestPilot" },
  prd: { title: "Login PRD", version_number: 1, content_hash: "abc" },
  analysis: {
    run: { status: "completed", provider: "deepseek", provider_mode: "real" },
    batches: [{ analysis_batch_id: "BAT-1", status: "completed" }],
  },
  requirements: [{ requirement_id: "REQ-1", review_status: "approved" }],
  test_forge: {
    run: { status: "completed" },
    candidates: [{ case_id: "TC-1", case_type: "api", decision: "approve" }],
    revisions: [],
  },
  baseline: { frozen_baseline_id: "FBL-1", status: "frozen", baseline_hash: "hash" },
  execution: {
    api_runs: [],
    ui_runs: [],
    api_results: [{ case_id: "TC-1", status: "PASS" }],
    ui_results: [{ case_id: "TC-2", status: "PASS" }],
  },
  evidence: {
    run: { status: "completed" },
    records: [{ consolidated_evidence_record_id: "EVD-1", case_id: "TC-1", evidence_hash: "hash" }],
    classifications: [{ case_id: "TC-1", classification_code: "seeded_product_bug" }],
  },
  bug: {
    record: {
      bug_id: "BUG-AUTH-001",
      bug_version: 1,
      severity: "high",
      priority: "high",
      status: "open",
      canonical_hash: "bughash",
    },
    latest_status_event: { to_status: "closed" },
    bundle: { json_path: "artifacts/bugs/bug.json", markdown_path: "artifacts/bugs/bug.md" },
  },
  report: { report_version: 1 },
  regression: {
    status: "completed",
    baseline_api_test_run_id: "RUN-OLD",
    baseline_ui_test_run_id: "UIR-OLD",
    regression_api_test_run_id: "RUN-NEW",
    regression_ui_test_run_id: "UIR-NEW",
    guard_pass_count: 7,
    guard_case_count: 7,
    trace_hash: "trace",
  },
  metrics: {
    requirements: 19,
    candidates: 46,
    snapshots: 10,
    evidence: 12,
    result_statuses: { PASS: 10 },
  },
  meta: { source: "plugin.db", provider_mode: "real", environment_id: "local-windows-demo" },
};

describe("quality exploration workspace", () => {
  beforeEach(() => {
    vi.mocked(api.loadWorkspace).mockResolvedValue(snapshot);
  });

  it.each([
    ["/mission-control", "Mission Control"],
    ["/prd-scanner", "PRD Scanner"],
    ["/requirements", "Requirement Constellation"],
    ["/test-forge", "Test Forge"],
    ["/execution", "Execution Arena"],
    ["/evidence", "Evidence Vault"],
    ["/bugs", "Bug Archive"],
    ["/quality", "Quality Observatory"],
    ["/regression", "Regression Portal"],
  ])("renders the deep-linked %s area", async (path, heading) => {
    window.history.pushState({}, "", path);
    render(<App />);
    expect(await screen.findByRole("heading", { name: heading })).toBeVisible();
  });

  it("exposes source-backed metrics and keyboard navigation", async () => {
    window.history.pushState({}, "", "/mission-control");
    render(<App />);
    expect(await screen.findByText("Formal requirements")).toBeVisible();
    expect(screen.getByText("19")).toBeVisible();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute(
      "href",
      "#main-content",
    );
  });

  it("shows a truthful error state and retry action", async () => {
    vi.mocked(api.loadWorkspace).mockRejectedValueOnce(new Error("offline"));
    render(<App />);
    expect(await screen.findByText("Workspace unavailable")).toBeVisible();
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
  });

  it("shows an empty state when no project exists", async () => {
    vi.mocked(api.loadWorkspace).mockResolvedValueOnce({ ...snapshot, project: null });
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText("No Plugin project data is available yet.")).toBeVisible(),
    );
  });
});
