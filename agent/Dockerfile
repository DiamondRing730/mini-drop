FROM python:3.12-slim

# linux-perf: perf userspace; bpftrace: eBPF tracepoint collector; procps: process tooling.
# py-spy ships as a self-contained binary via pip (no build toolchain needed).
# Use a fast Debian mirror (Aliyun) — works worldwide and is reliable behind CN networks;
# retry apt a few times to ride out transient drops.
RUN (sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true) \
    && for i in 1 2 3; do apt-get update && break || sleep 3; done \
    && apt-get install -y --no-install-recommends linux-perf bpftrace procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt py-spy==0.4.0
COPY agent ./agent

CMD ["python", "-m", "agent.main"]
