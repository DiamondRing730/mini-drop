import type { Agent, AgentEvent, EbpfDist, TaskDetail, TaskSummary, TopN } from "./types";

const BASE = "/api/v1";

async function j<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) {
    throw new Error(`${r.status} ${await r.text()}`);
  }
  return (await r.json()) as T;
}

export interface CreateTaskBody {
  name?: string;
  target_pid: number;
  duration_sec: number;
  frequency_hz: number;
  profiler_type: string;
  agent_id?: string | null;
}

export const api = {
  listAgents: () => j<Agent[]>(`${BASE}/agents`),
  getAgentEvents: (id: string) => j<AgentEvent[]>(`${BASE}/agents/${id}/events`),
  listTasks: () => j<TaskSummary[]>(`${BASE}/tasks`),
  getTask: (tid: string) => j<TaskDetail>(`${BASE}/tasks/${tid}`),
  createTask: (body: CreateTaskBody) =>
    j<{ tid: string }>(`${BASE}/tasks`, { method: "POST", body: JSON.stringify(body) }),
  deleteTask: (tid: string) => j<unknown>(`${BASE}/tasks/${tid}`, { method: "DELETE" }),
  artifactUrl: (tid: string, name: string) => `${BASE}/tasks/${tid}/artifacts/${name}`,
  getTopN: (tid: string, name: string) => j<TopN>(`${BASE}/tasks/${tid}/artifacts/${name}`),
  getEbpf: (tid: string, name: string) => j<EbpfDist>(`${BASE}/tasks/${tid}/artifacts/${name}`),
};
