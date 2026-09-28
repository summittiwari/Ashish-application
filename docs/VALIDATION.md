# Validation record

Built and measured on 25 September 2026 using Linux and Python 3.12. Results below are local observations, not promises for arbitrary documents or deployments.

## Functional checks

- 23 automated tests passed. See `test-results.txt` for the actual runner output.
- Cases cover identical documents, precise numeric edits, negation, typography/color/position, image-only coverage, rotated coordinates, page alignment, duplicate pages, forms, CSV injection, upload offset/resume/validation, authentication, cross-origin writes, rendering limits, retention protection, OCR uncertainty, spacing and explicit logo correlation.
- `scripts/verify_live_api.py` started the real HTTP server and its local durable queue, authenticated by session cookie, ran a comparison, downloaded all seven exports, resumed the job and confirmed all 3 page-result checkpoints retained their original modification times. It also cancelled a new job and successfully resumed it. See `live-api-validation.json`.
- The supplied three-page example produced 7 correlated primary findings. All seven generated exports are included in `sample-output/`.
- Browser review exercised paired selection and the evidence panel against a read-only fixture captured from real backend results. A screenshot is included as `viewer-review.jpg`. The actual HTTP backend was checked separately by the live API script; the fixture preview did not perform uploads/comparisons.
- Summary and detail PDFs were rendered and visually reviewed. Samples include severity/score charts and highlighted evidence crops.

## Controlled detection benchmark

`benchmark-detection.json` records 17 synthetic scenarios, with 16 true-positive category-count findings, 0 false-positive findings and 0 false-negative findings after correlation fixes. Precision: 100.0%; recall: 100.0%; F1: 1.000 **on these fixtures only**.

Ground truth and observed category counts are preserved per case. A match requires both category and multiplicity. This is a small developer-created suite, not an independently held-out accuracy evaluation. It does not measure localization IoU, arbitrary semantics, real OCR quality, diverse business templates or robust behavior across all PDF producers. The actual reference/candidate fixtures are included in `benchmark-fixtures/`, and the script regenerates them.

False-negative rate is FN/(TP+FN). False-discovery rate is FP/(TP+FP). A general false-positive rate FP/(FP+TN) is undefined because the universe of non-findings is not enumerable; the JSON states this and separately reports negative-document false-alarm rate. Do not relabel the document match score as detection accuracy.

## Capacity measurements

| Scenario | Measured result | Scope |
| --- | --- | --- |
| 500-page pair | 163.61 seconds including reports | Two sparse native PDFs, 72 DPI, 2 page workers, one planted numeric change |
| 500-page detections | 1 numeric change; 0 failed page pairs | The single intended value edit was detected once |
| Coordinator peak RSS | 162.66 MiB | Peak for that process, not total combined memory |
| Largest child peak RSS | 160.41 MiB | Maximum child process peak, not the sum of simultaneous children |
| Large file upload | 999,999,826 bytes in 10.39 seconds | Chunk upload, hash and inspection of a one-page PDF with a large inert stream |
| Large upload test process RSS | 415.55 MiB | Synthetic TestClient upload path; not a complete 1 GB comparison |

Exact records are `benchmark-500.json` and `benchmark-1000000000.json`. Complex vector pages, high-resolution decoded images and OCR can have much higher cost. No 1,000-page, adversarial image-bomb, sustained multi-user, real GPU OCR, or complete 1 GB comparison was measured. The benchmark script accepts other page counts for target-environment validation.

## Deployment verification boundary

A fresh virtual environment was installed from the hashed dependency lock. All 23 tests and the actual HTTP queue/cancel/resume script passed again in that environment. The clean test database and live queue database both returned `ok` from SQLite `PRAGMA integrity_check`.

One older shared scratch database returned `database disk image is malformed` after overlapping development tool sessions. The cause was not established; it is not included in this package. This was not reproduced in the separate live queue or clean-install databases. Keep backups and validate concurrency on the target filesystem; the distributed deployment uses PostgreSQL.

The local Python server, SQLite queue, subprocess pipeline, actual HTTP session, reports and resume behavior were exercised. PostgreSQL/Celery/Redis/S3 integration and Docker recipes are implemented/configured but were not exercised against real services here. Surya model inference was not run. Those are explicit target-environment acceptance checks, not fabricated passing results.

The optional Node/Vite project is only a static visual QA harness. Production functionality is in the Python application. There is no public hosted deployment in this deliverable.
