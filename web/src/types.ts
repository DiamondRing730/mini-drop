export interface Agent {
  id: string;
  hostname: string;
  ip_addr: string;
  agent_version: string;
  online: boolean;
  last_heartbeat: string | null;
  self_stats: Record<string, number>;
}

export interface Transition {
  from_status: string | null;
  to_status: string;
  reason: string;
  created_at: string;
}

export interface AgentEvent {
  event_type: string;
  detail: string;
  created_at: string;
}

export interface TaskSummary {
  tid: string;
  name: string;
  target_pid: number;
  profiler_type: string;
  status: string;
  status_reason: string;
  analysis_status: string;
  agent_id: string | null;
  created_at: string;
}

export interface TaskDetail extends TaskSummary {
  duration_sec: number;
  frequency_hz: number;
  analysis_reason: string;
  error_message: string;
  result_files: Record<string, string>;
  begin_time: string | null;
  end_time: string | null;
  transitions: Transition[];
}

export interface TopN {
  total_samples: number;
  unique_stacks: number;
  top: { func: string; self: number; self_pct: number }[];
}

export interface EbpfDist {
  kind: string;
  unit: string;
  total_events: number;
  latency_us: { bucket: string; count: number }[];
  by_comm: { comm: string; count: number }[];
}
