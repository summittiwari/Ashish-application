# Operation and deployment

## Runtime settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `SENTINEL_DATA` | `./data` | Writable work directory; `/data` in containers |
| `DATABASE_URL` | SQLite within data | Set `postgresql+psycopg://...` for PostgreSQL |
| `QUEUE_BACKEND` | `local` | Set `celery` for Redis/Celery |
| `START_WORKER` | `1` | API starts the local worker; use `0` for external workers |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker |
| `AUTH_TOKEN` | empty | Shared operator access key; empty disables login |
| `MAX_UPLOAD_BYTES` | 1,073,741,824 | Per-file byte limit (1 GiB) |
| `MAX_PAGES` | 2,000 | Per-file page limit |
| `MAX_RENDER_PIXELS` | 16,000,000 | Maximum raster canvas pixels; effective DPI may fall |
| `PAGE_CONCURRENCY` | 2 | Concurrent isolated operations per job; range 1–8 |
| `PAGE_BATCH_SIZE` | 8 | Extraction pages per subprocess; range 1–32 |
| `PAGE_TIMEOUT_SECONDS` | 180 | Per-page extraction allowance; comparison allows twice this |
| `JOB_TIMEOUT_SECONDS` | 21,600 | Whole-job hard deadline |
| `WORKER_MEMORY_MB` | 4,096 | Address-space cap per isolated process, not total host RAM |
| `RETENTION_DAYS` | 30 | Hourly cleanup of terminal jobs and unreferenced documents; 0 disables |
| `SURYA_INFERENCE_URL` | empty | Explicit Surya 2 inference endpoint ending `/v1` |
| `S3_BUCKET` | empty | Optional archive destination; empty disables archive calls |
| `S3_ENDPOINT_URL` | AWS default | Set for an S3-compatible endpoint |
| `S3_PREFIX` | `pdf-sentinel` | Object key prefix |
| `S3_SSE` | empty | Optional server-side encryption mode |
| `AWS_DEFAULT_REGION` | `us-east-1` | Archive region |

Standard AWS credentials/environment/workload identity apply. Never commit `.env` or credentials. Archive errors are recorded as `archive_failed` audit events while local results remain usable. Uploaded originals and generated reports are copied to S3; active processing and job state still require the work volume and database. An S3 archive alone is not a full database backup.

## Local container

`docker compose up --build` starts one API and one durable queue runner in the same container. The queue runner owns a file lock, so API restarts cannot create concurrent local queue owners. A stale running job is requeued on restart. Page workers use separate processes and deadlines. The container runs as UID 10001 with a read-only root, no additional Linux capabilities, and an 8 GiB container memory limit.

Native parsers are isolated by process/resource limits, not by a separate VM or sandbox per document. For hostile inputs, apply infrastructure-level workload isolation and egress restrictions. The app does not execute embedded PDF JavaScript. Optional S3 and OCR require only their operator-configured endpoints.

## PostgreSQL, Redis and Celery

Copy `.env.example` to `.env`, set nonempty `AUTH_TOKEN` and a URL-safe alphanumeric `POSTGRES_PASSWORD`, then:

```sh
docker compose -f compose.distributed.yaml up --build -d
docker compose -f compose.distributed.yaml up -d --scale worker=2
```

The supplied stack initializes the schema, waits for PostgreSQL/Redis health, and runs API, workers and a single periodic scheduler. Each worker runs one comparison at a time, with bounded page subprocess concurrency inside each comparison. This distributes separate jobs across workers; pages within one job are scheduled by its coordinator, not fanned out as independent cross-host Celery tasks.

All API/worker/scheduler instances must share the same POSIX data filesystem with working advisory locks. The default named volume works on one Docker host. For multiple hosts, replace it with an appropriate shared filesystem. Independent local volumes on different hosts are not sufficient. Redis and PostgreSQL ports are not published. Put a TLS reverse proxy in front of the localhost-bound API as needed; configure forwarded headers only for trusted proxy addresses.

Celery uses late acknowledgement, a one-task prefetch and redelivery on worker loss. Duplicate job deliveries are serialized by the job lock. A failed/cancelled job may be resumed through the UI or API. Use one scheduler, not one per worker.

Docker, PostgreSQL, Redis, real S3 and real Surya were not available for integrated deployment testing in the build environment. Their adapters/configurations are supplied; validate this stack in the target infrastructure before operational acceptance. The native local queue was exercised over actual HTTP.

## Retention and backups

The local queue runner sweeps while idle, at most once per hour. The distributed scheduler submits an hourly retention task. Cleanup removes expired terminal jobs, their reports/checkpoints, and documents no remaining job references. Active/queued jobs retain their documents. Cache directories are removed only when no document references their hash. Old upload sessions and audit rows also expire. S3 archives are retained independently: configure bucket lifecycle rules to match your policy.

Preview or apply manually:

```sh
python -m app.maintenance --days 30
python -m app.maintenance --days 30 --apply
```

For a consistent full backup, stop intake and workers, then back up both the database and `SENTINEL_DATA`. For SQLite, include its WAL/SHM state or use SQLite's online backup facility. For PostgreSQL, use a coordinated database dump/snapshot with the same work-volume snapshot. Restore them together before starting workers. No automatic disaster-recovery system is claimed.

Retry an optional archive after correcting connectivity/credentials:

```sh
python -m app.storage document DOCUMENT_ID
python -m app.storage job JOB_ID
```

## Capacity planning and recovery

Provision disk for both originals, page extraction caches, masks/heatmaps, two annotated copies, reports and temporary files. File size alone does not predict decoded image memory. Concurrent 4 GiB address-space allowances are not a promise that the machine only needs 4 GiB RAM. Increase limits only after observing representative documents.

Extraction uses bounded batches, and rendered pages are never retained for the whole document. Alignment retains compact fingerprints and a global assignment matrix, which is quadratic in page count. The 2,000-page default bounds this work. Exact duplicate pages can remain ambiguous and are flagged.

Failed comparison pages retain an explicit failed status; other pages and reports are produced with incomplete coverage. Extraction failure stops the job with an error. A resume retries unfinished pages and reuses completed ones if the engine, OCR configuration, options and mapping still match. Changing any checkpoint input invalidates previous page results. Originals are not modified; annotations are written to copies.

The health endpoint checks API availability and reports OCR configuration presence; it does not prove the inference endpoint or every dependency is healthy. Review `/api/audit`, job errors and container logs for operational diagnosis. Access keys are never intentionally logged. Job and report contents can contain sensitive document text, so protect the data volume and archives accordingly.
