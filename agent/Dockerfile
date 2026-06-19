FROM python:3.12-slim

# linux-perf provides the perf userspace; procps for basic process tooling.
# py-spy ships as a self-contained binary via pip (no build toolchain needed).
RUN apt-get update \
    && apt-get install -y --no-install-recommends linux-perf procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt py-spy==0.4.0
COPY agent ./agent

CMD ["python", "-m", "agent.main"]
