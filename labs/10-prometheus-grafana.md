# Lab 10 – Prometheus & Grafana

## Goal

Monitor the Ubuntu VM with Prometheus and visualize the metrics in Grafana.

## Architecture

```
node_exporter ──► Prometheus ──► Grafana
(VM metrics)      (stores time series)   (dashboards)
```

- **node_exporter** exposes host metrics: CPU, memory, disk, network, filesystem.
- **Prometheus** scrapes (pulls) these metrics every 15 seconds and stores them as time series.
- **Grafana** queries Prometheus and shows the data in dashboards.

## Files

Located in `projects/monitoring/`.

`docker-compose.yml`:

```yaml
services:
  prometheus:
    image: prom/prometheus
    ports: ["9090:9090"]
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
  node-exporter:
    image: prom/node-exporter
    pid: host
    volumes:
      - /:/host:ro,rslave
    command: --path.rootfs=/host
  grafana:
    image: grafana/grafana
    ports: ["3000:3000"]
```

`prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: node
    static_configs:
      - targets: ["node-exporter:9100"]
```

## Steps

### 1. Start the stack

```bash
cd ~/devops-lab/projects/monitoring
docker compose up -d
docker compose ps
```

All three containers must be `running`.

### 2. Verify Prometheus

Open `http://192.168.178.110:9090`.

- **Status → Targets:** the `node` target must be **UP**.
- In the query field, try:

```promql
up
node_load1
100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

The last query shows CPU usage in percent.

### 3. Log in to Grafana

Open `http://192.168.178.110:3000`, log in with `admin` / `admin` and set a new password.

### 4. Add Prometheus as a data source

**Connections → Data sources → Add data source → Prometheus**

- URL: `http://prometheus:9090`
- **Save & test** must succeed.

Grafana reaches Prometheus by its container name, because both run in the same Docker network.

### 5. Import a dashboard

**Dashboards → New → Import**, enter ID **1860** ("Node Exporter Full"), select the Prometheus data source, import.

### 6. Generate load and watch it

```bash
# CPU load for 60 seconds
timeout 60 sh -c 'while :; do :; done' &

# Temporary 1 GB file on disk
fallocate -l 1G /tmp/testfile && sleep 60 && rm /tmp/testfile
```

Watch CPU and filesystem panels change in Grafana.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Target `node` is DOWN | node-exporter not running or wrong target name | `docker compose ps`, check `prometheus.yml` |
| Grafana data source test fails | Used `localhost` instead of container name | URL must be `http://prometheus:9090` |
| Page does not open from Windows | Port blocked or wrong IP | `curl http://localhost:9090` inside the VM, check `ufw status` |
| Changes in `prometheus.yml` ignored | Prometheus reads config only at start | `docker compose restart prometheus` |

## Cleanup

```bash
docker compose down        # stop, keep nothing (no volumes defined)
```

## What I learned

-

## Next

- AI Lab 11 extends this setup with GPU, vLLM and LiteLLM metrics.
- Phase 1 of the AIOps agent uses this stack as its telemetry source.