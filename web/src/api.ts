import type { Agent, AgentEvent, Artifact, Attribution, AttributionEngine, EbpfDist, TaskDetail, TaskListResponse, TimelineEntry, TopN } from "./types";

const BASE = "/api/v1";

async function j<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) {
    const text = await r.text();
    try {
      const data = JSON.parse(text);
      throw new Error(data.detail || `${r.status} ${text}`);
    } catch (e) {
      if (e instanceof SyntaxError) throw new Error(`${r.status} ${text}`);
      throw e;
    }
  }
  return (await r.json()) as T;
}

export interface CreateTaskBody {
  name?: string;
  target_pid: number;
  duration_sec: number;
  frequency_hz: number;
  profiler_type: string;
  mode?: string;
  slice_sec?: number;
  agent_id?: string | null;
}

export interface TaskListQuery {
  q?: string;
  status?: string;
  profiler_type?: string;
  page?: number;
  page_size?: number;
}

function queryString(params: TaskListQuery): string {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.status) qs.set("status", params.status);
  if (params.profiler_type) qs.set("profiler_type", params.profiler_type);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  const value = qs.toString();
  return value ? `?${value}` : "";
}

function encodeArtifactPath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

export const api = {
  listAgents: () => j<Agent[]>(`${BASE}/agents`),
  getAgentEvents: (id: string) => j<AgentEvent[]>(`${BASE}/agents/${id}/events`),
  listTasks: (params: TaskListQuery = {}) =>
    j<TaskListResponse>(`${BASE}/tasks${queryString(params)}`),
  getTask: (tid: string) => j<TaskDetail>(`${BASE}/tasks/${tid}`),
  createTask: (body: CreateTaskBody) =>
    j<{ tid: string }>(`${BASE}/tasks`, { method: "POST", body: JSON.stringify(body) }),
  deleteTask: (tid: string) => j<unknown>(`${BASE}/tasks/${tid}`, { method: "DELETE" }),
  retryTask: (tid: string) =>
    j<{ tid: string; source_tid: string }>(`${BASE}/tasks/${tid}/retry`, { method: "POST" }),
  listArtifacts: (tid: string) => j<Artifact[]>(`${BASE}/tasks/${tid}/artifacts`),
  artifactUrl: (tid: string, name: string, download = false) =>
    `${BASE}/tasks/${tid}/artifacts/${encodeArtifactPath(name)}${download ? "?download=true" : ""}`,
  getTopN: (tid: string, name: string) => j<TopN>(`${BASE}/tasks/${tid}/artifacts/${name}`),
  getEbpf: (tid: string, name: string) => j<EbpfDist>(`${BASE}/tasks/${tid}/artifacts/${name}`),
  getTimeline: (tid: string) => j<TimelineEntry[]>(`${BASE}/tasks/${tid}/timeline`),
  windowUrl: (tid: string, from: number, to: number) =>
    `${BASE}/tasks/${tid}/window?from=${from}&to=${to}`,
  // AI attribution: get the stored result if present, or run it on demand.
  getAttribution: (tid: string, name: string) => j<Attribution>(`${BASE}/tasks/${tid}/artifacts/${name}`),
  runAttribution: (tid: string, engine: AttributionEngine) =>
    j<Attribution>(`${BASE}/tasks/${tid}/attribution`, {
      method: "POST",
      body: JSON.stringify({ engine }),
    }),
};
