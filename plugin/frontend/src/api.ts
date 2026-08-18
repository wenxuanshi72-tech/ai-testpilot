import axios from "axios";

export type Row = Record<string, unknown>;

export interface WorkspaceSnapshot {
  project: Row | null;
  prd: Row | null;
  analysis: { run: Row | null; batches: Row[] };
  requirements: Row[];
  test_forge: { run: Row | null; candidates: Row[]; revisions: Row[] };
  baseline: Row | null;
  execution: { api_runs: Row[]; ui_runs: Row[]; api_results: Row[]; ui_results: Row[] };
  evidence: { run: Row | null; records: Row[]; classifications: Row[] };
  bug: { record: Row | null; latest_status_event: Row | null; bundle: Row | null };
  report: Row | null;
  regression: Row | null;
  metrics: {
    requirements: number;
    candidates: number;
    snapshots: number;
    evidence: number;
    result_statuses: Record<string, number>;
  };
  meta: { source: string; provider_mode: string | null; environment_id: string | null };
}

const client = axios.create({ baseURL: "/api/v1", timeout: 10_000 });

export async function loadWorkspace(): Promise<WorkspaceSnapshot> {
  const response = await client.get<{ data: WorkspaceSnapshot }>("/workspace");
  return response.data.data;
}
