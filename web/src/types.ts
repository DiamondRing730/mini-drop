export interface Agent {
  id: string;
  hostname: string;
  ip_addr: string;
  agent_version: string;
  online: boolean;
  last_heartbeat: string | null;
  self_stats: Record<string, number>;
  discovery: DiscoveredContainer[];
}

export interface DiscoveredProcess {
  pid: number;
  ppid: number;
  comm: string;
  args: string;
}

export interface DiscoveredContainer {
  id: string;
  name: string;
  image: string;
  processes: DiscoveredProcess[];
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
  stop_requested: boolean;
  created_at: string;
}

export interface TaskListResponse {
  items: TaskSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface Artifact {
  path: string;
  logical_name: string | null;
  size_bytes: number;
  content_type: string;
}

export interface TaskDetail extends TaskSummary {
  duration_sec: number;
  frequency_hz: number;
  slice_sec: number;
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

export interface ComparisonFunction {
  function: string;
  baseline_samples: number;
  candidate_samples: number;
  baseline_pct: number;
  candidate_pct: number;
  delta_pct: number;
  relative_change_pct: number | null;
  status: "improved" | "regressed" | "stable";
  baseline_aliases: string[];
  candidate_aliases: string[];
}

export interface PerformanceComparison {
  verdict: "hotspot_reduced" | "hotspot_increased" | "no_clear_change" | "no_data";
  summary: string;
  confidence: "high" | "medium" | "low";
  change_threshold_pct: number;
  primary_hotspot: ComparisonFunction | null;
  functions: ComparisonFunction[];
  counts: { improved: number; regressed: number; stable: number };
  limitations: string[];
  baseline: { tid: string; name: string; profiler_type: string; total_samples: number };
  candidate: { tid: string; name: string; profiler_type: string; total_samples: number };
  verification: {
    total: number;
    verified: number;
    failed: number;
    pass_rate: number;
    tolerance_pct: number;
    checks: Array<{
      function: string;
      verdict: "pass" | "fail";
      claimed: { baseline_pct: number; candidate_pct: number; delta_pct: number };
      actual: { baseline_pct: number; candidate_pct: number; delta_pct: number };
      note: string;
    }>;
  };
  artifacts: { report: string; diff_flamegraph: string };
}
