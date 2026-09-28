# PDF Sentinel

A runnable Python application for reviewing differences between a reference PDF and a candidate PDF. It includes the comparison engine, web interface, durable job processing, reports, deployment files, example documents, regression tests, and reproducible benchmarks. No LLM decides whether the documents differ. Optional Surya OCR supplies extraction evidence only.

## Start the application

With Docker Desktop or Docker Engine and Compose installed:

```sh
docker compose up --build
```

Open **http://localhost:8000**. Choose **Try the included example PDFs**, then **Compare PDFs**, or upload your own files. The example contains changed amounts, a changed payment deadline, a negation, a font-size change, a reordered page and a metadata change.

The default deployment listens on localhost, starts a durable local worker, and keeps its database and files in a named volume. First build downloads Python dependencies. Stop with `docker compose down`; this preserves data. Do not add `--volumes` unless you intend to delete that data.

Default retention is **30 days** for terminal jobs and unreferenced documents. To change settings, copy `.env.example` to `.env`; set `RETENTION_DAYS=0` for indefinite retention. Set `AUTH_TOKEN` to a long random value if access protection is needed. The key is entered in the application sign-in dialog.

### Run directly on Linux

Python 3.12 and a writable working directory are required. Linux is the validated platform; use Docker on Windows. Process limits and file locks use POSIX APIs.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

The local database and files go to `./data`. Environment variables must be exported for native runs; `.env` is read by Compose, not implicitly by Python. Node is unnecessary for the application. `npm run dev` is a separately labelled, read-only visual QA preview of recorded results, not a substitute for the Python server.

## What is implemented

| Area | Behavior |
| --- | --- |
| Uploads | Two independently resumable 8 MiB chunk streams; offset checks; PDF header and parser validation; configurable byte/page limits; content hashes |
| Page alignment | Exact occurrence-aware matching, text/render fingerprints, global assignment, additions, removals, duplicate ambiguity and relative reordering |
| Text and semantics | Native character boxes, word edits, line context, paragraphs as extracted lines/blocks, numeric/unit rules, negation and obligation checks; semantic score independent of literal similarity |
| Typography | Family/name, size, flags, color, opacity, rotation, writing mode, measured glyph spacing, heuristic underline/strike-through; embedded program descriptors and subset normalization |
| Visual and layout | Bounded RGB rendering, small permitted registration, thresholded pixel masks, connected regions, heatmaps, SSIM diagnostic, page geometry, text movement/reflow, vectors and image geometry |
| Images and logos | Decoded image digests, encoding/compression evidence, position/transform/size/colorspace/mask checks; separate comparison of operator-selected logo regions |
| Tables | Native table/cell structure and values, per-cell locations; optional OCR HTML tables with table-level geometry |
| PDF internals | Metadata/XMP, outlines, layers, attachments, bounded canonical resources, forms, annotations, links and operator inventory |
| Correlation | Related native/text/visual observations attached to primary findings; repeated header/footer edits grouped without hiding occurrences |
| Scoring | Eleven configurable dimensions, five profiles, configurable severities, N/A for unassessed dimensions, visible effective weights and score contributions |
| Viewer | Side by side, overlay, difference mask, blink and heatmap; paired navigation, zoom and scroll; matching finding selection and exact-region highlights; filtering/search and lowest-score sorting |
| Dashboard | Match summary, dimension bars, difference donut, severity chart, page chart, coverage warnings, history and processing measurements |
| Outputs | Summary PDF, complete detailed PDF volumes in ZIP, JSON, CSV, Excel, annotated reference PDF and annotated candidate PDF |
| Processing | Bounded subprocesses, local durable queue or Celery/Redis, SQLite or PostgreSQL, page checkpoints, cancellation/resume, retries, cache invalidation and time/memory/pixel limits |
| Operations | Access key/session cookie, same-origin write protection, audit log, automatic retention, optional S3-compatible document/report archives, container configurations |

Each finding includes what changed, reference/candidate values, pages and available bounding boxes, severity, evidence confidence, supporting signals and contribution to score loss. Findings without page coordinates, such as metadata, are explicitly document-level.

## How to review a comparison

1. Upload both PDFs or load the included example. An interrupted upload can be resumed by reselecting the same file in the same browser.
2. Select Strict, Standard, Content, Visual or Custom. Expand advanced settings to change DPI, tolerances, weights, category severities or logo regions.
3. Start comparison. Leave and reopen it from History; processing continues. Cancel and resume are available.
4. Review coverage notes before accepting the score. Sort page pairs by lowest match, or filter findings by category, severity, confidence or text.
5. Click a finding or highlight to select corresponding regions on both pages. The evidence panel preserves old/new values, context and correlated observations.
6. Download reports. `detailed-report.zip` includes the summary and every finding in bounded PDF volumes; it does not silently truncate long comparisons.

Logo region example (displayed page coordinates in PDF points, 72 points per inch):

```json
[{"label":"Company logo","page_a":1,"page_b":1,"bbox_a":[30,25,130,70],"bbox_b":[40,25,140,70]}]
```

Severity override example:

```json
{"FONT_SIZE_CHANGE":"major","TABLE_CELL_CHANGED":"critical"}
```

## OCR setup

Native PDFs work without model downloads. Scanned and hybrid pages are still visually compared when OCR is unavailable; text/semantic coverage is explicitly marked unavailable.

To enable extraction, install `requirements-ocr.txt` in the Python environment, run an operator-controlled **Surya 2** inference server, and set `SURYA_INFERENCE_URL=http://your-ocr-host:port/v1`. For Docker, also set `INSTALL_OCR=1` and rebuild. The server must be reachable from the worker container; container-local `localhost` does not refer to the host.

Follow the [Surya installation and inference instructions](https://github.com/datalab-to/surya) for the GPU/CPU backend. The adapter requires an explicitly configured endpoint and does not auto-start an inference server. Keep that endpoint on infrastructure you control. OCR model weights and server runtime are not included in this package. The actual Surya model was **not run** during this build; recognition uncertainty behavior was tested using controlled extraction evidence.

## Deployment and operation

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for PostgreSQL/Redis/Celery, S3, environment settings, retention, backup and recovery. Interactive API documentation is at `/docs` on the running server. See [docs/API.md](docs/API.md) for the upload and comparison lifecycle.

This is one shared, trusted workspace with an optional operator access key. It does not implement tenant isolation, SSO or role-based authorization. Use a TLS reverse proxy and organizational access controls before exposing it beyond a trusted environment. Container recipes are supplied; Docker was unavailable in the build environment, so those recipes have not been executed here.

## Validation and honest limits

Measured results and exact scope are in [docs/VALIDATION.md](docs/VALIDATION.md) and the accompanying JSON files. Tests include actual HTTP queue execution, report downloads, cancellation/resume and controlled expected differences. The capacity suite completed a 500-page native comparison and a separate approximately 1 GB upload/inspection test. These do not prove that every 1 GB scanned or complex PDF fits the same resource budget.

Match percentage describes agreement across assessed checks. It is **not detection accuracy**. Confidence values reflect rules or OCR evidence, not calibrated probabilities. The included synthetic category benchmark reports precision/recall/F1 only for its stated fixtures.

PDFs do not reliably encode authoring concepts or business meaning. Consequently:

- General paraphrase equivalence is unresolved when deterministic rules cannot decide. There is no general-purpose semantic model or domain ontology.
- Logo identity is supplied through known regions; the application does not reliably infer every logo automatically.
- Underlines, strike-through, headers/footers and table detection use geometry heuristics. Native character boxes are precise extraction coordinates, not proof of font intent. Scanned font identity and exact OCR character boxes are unavailable.
- Dynamic XFA behavior, cryptographic signature trust, arbitrary embedded scripts, full accessibility structure and every recursively reachable PDF object are not evaluated. Structural inspection is intentionally bounded. Password-required PDFs need a decrypted copy.
- A raster viewer synchronizes finding selection; it is not an editable PDF viewer and does not provide general text selection across both documents.
- Render caps may reduce effective DPI. Very complex pages may time out or fail; incomplete coverage is surfaced and failed pages can be retried. Large image decoding and report generation still require suitable disk/RAM.

## Develop and reproduce

```sh
pip install -r requirements-dev.txt
SENTINEL_DATA=./data/test START_WORKER=0 python -m pytest -q tests
python scripts/run_integration.py
python scripts/verify_live_api.py
python scripts/benchmark_detection.py
python scripts/benchmark_large.py --pages 500
# Optional: allocates approximately 1 GB of storage and uploads it through the API
python scripts/benchmark_large.py --large-file-bytes 1000000000
```

Tests use synthetic documents, never private user files. `scripts/make_examples.py` regenerates the example pair. `scripts/build_qa_fixture.py` refreshes recorded visual QA data from an integration run. The source requirement document is included in `docs/requirements-source.md`; this README distinguishes implemented behavior from inherent or unvalidated limits.

Dependency notices and source links are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
