# API lifecycle

The running application exposes OpenAPI at `/openapi.json` and interactive documentation at `/docs`. All mutation requests require `X-Sentinel-Client: 1`. When configured, use `Authorization: Bearer ACCESS_KEY` or a session cookie from `POST /api/session` with `{"token":"ACCESS_KEY"}`. Cross-origin mutation requests are rejected.

| Method and path | Behavior |
| --- | --- |
| `GET /api/health` | API/configuration status, limits and OCR configuration presence |
| `GET /api/profiles` | Tolerance presets and default weights |
| `POST /api/uploads` | JSON `{name: "reference.pdf", size: 123}` returns upload ID and chunk size |
| `GET /api/uploads/{id}` | Current acknowledged byte offset for resume |
| `PUT /api/uploads/{id}?offset=N` | Raw bytes, up to 8 MiB; acknowledged offset returned; conflict is HTTP 409 |
| `POST /api/uploads/{id}/complete` | Require all declared bytes; validate and inspect PDF; return document ID |
| `GET /api/documents/{id}` | Document metadata/inspection |
| `GET /api/documents/{id}/pages/{page}.png?dpi=120` | Lazily render a 1-based page |
| `POST /api/jobs` | JSON `{reference: ID, candidate: ID, options: {profile: "standard"}}` |
| `GET /api/jobs` | Recent jobs, up to 100 |
| `GET /api/jobs/{id}` | Status, progress, options, summary and errors |
| `POST /api/jobs/{id}/cancel` | Request cancellation; completed checkpoints remain |
| `POST /api/jobs/{id}/resume` | Resume terminal job; active jobs return 409 |
| `GET /api/jobs/{id}/pages` | Paginated page pairs; `sort=score` puts lowest match first |
| `GET /api/jobs/{id}/differences` | Paginated findings with `category`, `severity`, `q`, `page_pair`, `min_confidence` |
| `GET /api/jobs/{id}/visual/{pair}/{mode}.png` | `mode=mask` or `heatmap`; pair is zero-based |
| `GET /api/jobs/{id}/exports/{name}` | Completed/partial jobs' exported files |
| `GET /api/audit` | Recent operational events |
| `POST /api/demo` | Register bundled synthetic examples |

Status values: `queued`, `running`, `complete`, `partial`, `failed`, `cancelled`. Check `summary.incomplete` even for a completed job: the process can complete while some analysis dimensions remain unavailable, such as OCR on a scan. `partial` specifically indicates failed page comparisons.

Pages/differences accept `offset=0&limit=100` (limit up to 200). Document pages are 1-based. `page_pair` and result `idx` are zero-based. `idx=-1` is document-level evidence, such as metadata. Bounding boxes are `[x0,y0,x1,y1]` in displayed PDF page points after page rotation, with the top-left as origin. Null coordinates mean the finding is not localizable to a page region.

Allowed export names: `report.pdf`, `detailed-report.zip`, `result.json`, `differences.csv`, `comparison.xlsx`, `annotated-a.pdf`, `annotated-b.pdf`. JSON includes schema version, summary, pages and all findings. CSV/Excel escape formula-like strings. PDF detail volumes contain all findings and available visual crops.

Options are validated by `app.config.Options`; see `/openapi.json` and source for exact fields. `Options.from_input` merges profile defaults with explicit values. Supply all eleven dimension names if overriding the weights dictionary. A positive total weight is required. Severity overrides map category names to `critical`, `major`, `minor` or `informational`.

An offset is committed only after bytes are flushed to disk. On an interrupted chunk, query the acknowledged offset and resend from there. Completed upload IDs return the existing document record if finalized again. To resume in the web UI, reselect the same file; the browser retains upload-session metadata, not a full in-memory copy of the file.
