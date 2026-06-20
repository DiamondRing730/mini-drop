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

export interface TimelineEntry {
  start_ts: number;
  end_ts: number;
  samples: number;
}

export interface TaskSummary {
  tid: string;
  name: string;
  target_pid: number;
  profiler_type: string;
  mode: string;
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

export interface AttributionFinding {
  function: string;
  self_pct: number;
  evidence: string;
  recommendation: string;
}

export interface AttributionCheck {
  function: string;
  claimed_self_pct: number | null;
  actual_self_pct: number | null;
  verdict: "pass" | "fail";
  note: string;
}

export type AttributionEngine = "offline" | "deepseek";

export interface Attribution {
  tid: string;
  engine: AttributionEngine | "heuristic"; // heuristic is accepted for older saved artifacts
  model: string | null;
  summary: string;
  findings: AttributionFinding[];
  tool_trace: { tool: string; input: Record<string, unknown> }[];
  verification: {
    total_findings: number;
    verified: number;
    failed: number;
    pass_rate: number;
    tolerance_pct: number;
    checks: AttributionCheck[];
  };
}
