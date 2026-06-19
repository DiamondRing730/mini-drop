FROM python:3.12-slim

# Pure-Python analyzer: no perf/perl needed (stackcollapse + flamegraph are reimplemented).
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY analyzer ./analyzer

CMD ["python", "-m", "analyzer.main"]
