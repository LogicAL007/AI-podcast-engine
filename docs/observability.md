# Observability

**Prometheus collects metrics. It does not store logs.** Metrics are numbers over time (request
rate, latency, stage duration, failure count). Logs are text events. This project has both, in
different places:

| | Where | How to use it |
|---|---|---|
| Metrics | Prometheus, <http://localhost:9090> | PromQL queries below |
| Logs | JSON lines on each container's stdout | `docker compose logs -f ingest_publish` |

Searching logs across containers needs a log store such as Loki. It is not set up yet.

## What is measured

The API serves `/metrics` and each of the five stage workers serves it on port 9100 (stage metrics carry a `stage` label, so stages sharing a worker stay apart), both only on the compose
network. Prometheus scrapes them every 15 seconds
([monitoring/prometheus.yml](../monitoring/prometheus.yml)).

| Metric | Labels | Meaning |
|---|---|---|
| `podcast_http_requests_total` | `method`, `route`, `status` | API requests. `route` is the template (`/shows/{show_id}`), so ids do not create new series; paths that match no route share `unmatched`. |
| `podcast_http_request_duration_seconds` | `method`, `route` | API latency histogram |
| `podcast_stage_runs_total` | `stage`, `outcome` | Stage attempts, `success` or `failure`. A retried stage counts once per attempt. |
| `podcast_stage_duration_seconds` | `stage` | Stage attempt duration histogram (buckets 0.5 s to 10 min) |

Prometheus adds `up{job=...}` for every target, which is 0 when a container is down or has no
metrics endpoint.

Stage duration is the per-stage timing the PRD asks for. Summing the stages of one episode gives
the end-to-end time against the 10-minute target.

## Querying

Open <http://localhost:9090> and paste a query into the Graph tab.

```promql
# API: 95th percentile latency per route
histogram_quantile(0.95, sum by (le, route) (rate(podcast_http_request_duration_seconds_bucket[5m])))

# API: share of requests that are server errors
sum(rate(podcast_http_requests_total{status=~"5.."}[5m])) / sum(rate(podcast_http_requests_total[5m]))

# Pipeline: failed attempts per second, by stage
sum by (stage) (rate(podcast_stage_runs_total{outcome="failure"}[5m]))

# Pipeline: 95th percentile stage duration
histogram_quantile(0.95, sum by (le, stage) (rate(podcast_stage_duration_seconds_bucket[15m])))

# Anything that is down
up == 0
```

While the stage bodies are still unwritten, every ingest attempt fails with `NotImplementedError`,
so expect `outcome="failure"` for ingest.

## How it works

uvicorn runs several processes and Celery's prefork pool runs several more, and a normal Prometheus
client would report only whichever process answered the scrape. Compose sets
`PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus` (a tmpfs) so the processes share counters through files,
and [metrics.py](../src/podcast_engine/common/metrics.py) merges them on each scrape. The files vanish
when the container restarts, which Prometheus handles as a counter reset.

- The API middleware and `/metrics` route are in
  [api/observability.py](../src/podcast_engine/api/observability.py).
- Stage metrics are recorded in `stage_timer`
  ([timing.py](../src/podcast_engine/common/timing.py)), which already wraps every stage.
- Workers start the metrics server in [worker.py](../src/podcast_engine/worker.py).
- nginx returns 404 for `/api/metrics`, so the public web port does not expose metrics. Prometheus
  reaches the API directly on the internal network.

Prometheus keeps 15 days of data in the `prometheus_data` volume and listens only on
`127.0.0.1:9090`. It has no authentication, so do not publish that port.

## Adding a metric

Define it in `common/metrics.py` with a `Counter` or `Histogram` (avoid `Gauge` without choosing a
`multiprocess_mode`), record it where the event happens, and add a test that reads it back with
`REGISTRY.get_sample_value`. Keep label values to small fixed sets: never an episode or show id.

## Running outside Docker

Without `PROMETHEUS_MULTIPROC_DIR`, each process reports only its own numbers, so `--workers 2`
or a Celery worker run directly on your machine gives partial counts. Use the compose stack for
anything you want to read the metrics of.

## Not done yet

- **Log storage and search** (Loki or similar).
- **Dashboards** (Grafana).
- **Queue depth**: jobs waiting per stage, from a Redis exporter.
- **Alert rules** and Alertmanager.
- **Scheduler metrics**: the scheduler exposes none.
