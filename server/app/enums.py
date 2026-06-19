"""Enumerations and the legal task state-machine transitions."""
import enum


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"      # created, waiting for an agent to claim
    RUNNING = "RUNNING"      # agent claimed and is collecting
    UPLOADING = "UPLOADING"  # collection finished, agent is storing the artifact
    DONE = "DONE"            # artifact stored, ready for analysis
    FAILED = "FAILED"        # terminal failure (see status_reason / error_message)


class AnalysisStatus(str, enum.Enum):
    NONE = "NONE"        # collection not finished yet -> nothing to analyze
    PENDING = "PENDING"  # queued, waiting for the analyzer to pick it up
    RUNNING = "RUNNING"  # analyzer is generating the flamegraph / hotspots
    DONE = "DONE"
    FAILED = "FAILED"


class ProfilerType(str, enum.Enum):
    PERF = "perf"      # native CPU sampling via Linux perf
    PYSPY = "pyspy"    # Python language-level sampling via py-spy
    EBPF = "ebpf"      # kernel-level syscall latency via bpftrace (tracepoint probe)


# from-state -> set of allowed to-states. Terminal states have no outgoing edges.
ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.FAILED},
    TaskStatus.RUNNING: {TaskStatus.UPLOADING, TaskStatus.FAILED},
    TaskStatus.UPLOADING: {TaskStatus.DONE, TaskStatus.FAILED},
    TaskStatus.DONE: set(),
    TaskStatus.FAILED: set(),
}


class TaskMode(str, enum.Enum):
    ONESHOT = "oneshot"        # one capture -> one flamegraph
    CONTINUOUS = "continuous"  # resident low-frequency slices -> timeline + window replay


class AgentEventType(str, enum.Enum):
    REGISTER = "REGISTER"  # first time we ever saw this agent
    OFFLINE = "OFFLINE"    # missed heartbeats past the threshold
    RECOVER = "RECOVER"    # heartbeat resumed after being offline
