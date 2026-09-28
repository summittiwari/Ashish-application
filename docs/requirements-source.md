# Build an Enterprise-Grade PDF Comparison & Validation Platform

## 1. Objective

Build a production-grade Python-based application capable of performing extremely detailed comparison of two PDF documents.

This must NOT be a simple text-diff utility.

The application must compare PDFs across multiple independent dimensions:

1. Text / Content Comparison
2. Visual / Pixel Comparison
3. Typography / Font Comparison
4. Layout / Geometric Comparison
5. Image / Logo Comparison
6. Table Comparison
7. Structural Comparison
8. Semantic Comparison
9. Metadata Comparison
10. PDF Object Comparison
11. Form / Annotation Comparison
12. Header / Footer Comparison
13. Color Comparison
14. Page-Level Comparison
15. Document-Level Comparison

The application must identify:

> WHAT changed + WHERE it changed + OLD value + NEW value + TYPE of change + SEVERITY + CONFIDENCE + IMPACT ON MATCH SCORE.

The system should work primarily through Python libraries and deterministic comparison algorithms.

Do NOT use an LLM or generative AI for comparison.

Surya OCR may be used for OCR, layout detection, reading order and document-structure recognition.

---

# 2. Input

Provide a modern web interface containing:

### Reference Document

**PDF A — Baseline**

### Candidate Document

**PDF B — PDF Under Test**

Support:

- Native PDFs
- Scanned PDFs
- Mixed scanned/native PDFs
- Image-heavy PDFs
- Forms
- Reports
- Statements
- Invoices
- Brochures
- Generated PDFs
- Complex multi-column PDFs

Show:

- File name
- File size
- Page count
- PDF version
- Dimensions
- Orientation
- Encryption status
- Metadata
- Processing status

Provide a:

**COMPARE PDFs**

button.

---

# 3. Large PDF Architecture

The solution must be architected for very large PDFs.

Target:

- 1–10 pages
- 100+ pages
- 500+ pages
- 1,000+ pages where resources permit
- Hundreds of MB
- Target support for \~1 GB PDFs

Never load the complete PDF or all rendered pages into memory.

Implement:

- Streaming upload
- Chunked file handling
- Page batching
- Lazy page rendering
- Worker processes
- Background job queue
- Parallel comparison
- Configurable concurrency
- Temporary disk/object storage
- Checkpointing
- Resume capability
- Failed-page retry
- Progress persistence
- CPU/GPU resource controls
- Memory limits

Display progress such as:

`Pages compared: 247 / 500`

and individual stages:

`Extracting → OCR → Aligning → Text → Visual → Layout → Semantic → Metadata → Scoring → Report`

A large document must not cause the browser or API process to run out of memory.

---

# 4. Intelligent PDF Processing Pipeline

Before comparing anything, determine whether each page contains:

- Native searchable text
- Scanned image
- Hybrid content

For native PDFs, extract the PDF's actual objects whenever possible.

Do NOT OCR native text unnecessarily.

For scanned/image regions, use:

**Surya OCR**

Use Surya for:

- OCR
- Text-line detection
- Bounding boxes
- Layout detection
- Reading order
- Table detection/recognition
- Header detection
- Footer detection
- Picture detection
- Form detection
- Section/header recognition

Normalize all extracted information into a common internal document representation.

Example:

Document
→ Pages
→ Regions
→ Blocks
→ Lines
→ Words
→ Characters
→ Fonts
→ Images
→ Tables
→ Drawings
→ Metadata

Every element should contain its bounding box and relevant properties.

---

# 5. Page Alignment Engine

Do NOT blindly compare:

`PDF A page 1 → PDF B page 1`

Pages may have been inserted, deleted or reordered.

Create a page-alignment stage using multiple signals:

- Text similarity
- Text fingerprints
- Perceptual image hashes
- Layout signatures
- Header/footer patterns
- Page dimensions
- Key anchors
- Structural similarity

Generate mappings such as:

`A-001 → B-001`
`A-002 → B-002`
`A-003 → MISSING`
`A-004 → B-003`
`MISSING → B-004`

Detect:

- Added pages
- Deleted pages
- Reordered pages
- Duplicate pages
- Replaced pages

---

# 6. TEXT COMPARISON

Perform multiple levels of text comparison.

Compare:

### Character level

- Added character
- Deleted character
- Replaced character

### Word level

- Added word
- Deleted word
- Modified word
- Spelling change

### Sentence level

- Added sentence
- Deleted sentence
- Modified sentence
- Reordered sentence

### Paragraph level

- Added paragraph
- Deleted paragraph
- Modified paragraph
- Reordered paragraph

Detect whitespace separately from meaningful content changes.

Example:

Reference:

`Payment must be completed within 30 days.`

Candidate:

`Payment must be completed within 45 days.`

Result:

`TEXT_MODIFICATION`

Old:
`30`

New:
`45`

Highlight only the changed region.

Use bounding-box coordinates to map differences back to the PDF.

---

# 7. SEMANTIC COMPARISON

Literal text equality is insufficient.

Implement a separate semantic comparison layer.

It must distinguish between:

### Exact match

`Payment is due within 30 days.`

vs

`Payment is due within 30 days.`

### Formatting-only change

Same meaning and text, different font/layout.

### Paraphrase

`Payment must be made within thirty days.`

vs

`The payment should be completed within 30 days.`

### Meaning-changing modification

`Payment must be made within 30 days.`

vs

`Payment must be made within 60 days.`

### Contradiction / polarity change

`Refunds are permitted.`

vs

`Refunds are not permitted.`

### Numeric semantic change

Detect changes involving:

- Dates
- Currency
- Percentages
- Quantities
- Account/reference numbers
- Phone numbers
- Addresses
- Units
- Measurements

Semantic comparison must be reported separately from literal text similarity.

Do NOT hide literal differences simply because two sentences have similar embeddings.

Produce:

`Literal Text Score`
`Semantic Similarity Score`

Use deterministic NLP techniques and optionally local Sentence Transformer embeddings.

No generative LLM should be required.

---

# 8. TYPOGRAPHY COMPARISON

Compare typography at text-span level.

Detect changes in:

- Font family
- Font name
- Font subset
- Font size
- Font weight
- Bold
- Italic
- Underline
- Strike-through
- Superscript
- Subscript
- Character spacing
- Word spacing
- Line spacing
- Text color
- Text opacity
- Text rotation
- Writing direction

Example:

`Arial 11pt → Arial 12pt`

Report:

`FONT_SIZE_CHANGE`

Old: `11pt`

New: `12pt`

---

# 9. FONT EMBEDDING COMPARISON

Inspect embedded fonts.

Compare:

- Embedded fonts
- Missing fonts
- Font substitutions
- Font subsets
- Font encoding
- Font descriptor
- Font file properties

Where possible, inspect embedded font programs using FontTools.

Different subset prefixes should not automatically count as meaningful font changes if the underlying font is equivalent.

---

# 10. VISUAL / PIXEL COMPARISON

Render aligned pages at configurable resolution, e.g.:

- 150 DPI
- 200 DPI
- 300 DPI

Perform image registration/alignment before pixel comparison to prevent minor rendering offsets from generating thousands of false positives.

Use techniques such as:

- OpenCV
- SSIM
- Absolute pixel difference
- Edge comparison
- Contour analysis
- Morphological processing
- Perceptual hashing

Generate:

### Visual similarity score

Example:

`98.72%`

Generate a visual diff mask.

Highlight changed regions.

Avoid marking unchanged pixels.

---

# 11. VISUAL CHANGE CLASSIFICATION

Classify visual differences into:

- Text change
- Font change
- Image change
- Logo change
- Position change
- Alignment change
- Color change
- Background change
- Border change
- Shape change
- Line change
- Spacing change
- Unknown visual change

Do not report only:

`Pixels changed`

Explain the underlying detected difference whenever possible.

---

# 12. LAYOUT / GEOMETRY COMPARISON

Compare bounding boxes and document geometry.

Detect:

- X-position change
- Y-position change
- Width change
- Height change
- Element movement
- Alignment change
- Margin change
- Padding/spacing change
- Column change
- Section movement
- Text reflow
- Line wrapping change
- Reading-order change

Example:

`Logo moved 11 px right and 4 px down.`

Provide configurable tolerance.

Example:

`Position tolerance = ±2 px`

Changes inside tolerance may be classified as insignificant.

---

# 13. LOGO COMPARISON

Detect logos independently from generic images.

Compare:

- Presence
- Position
- Dimensions
- Aspect ratio
- Visual appearance
- Resolution
- Transparency
- Color
- Rotation

Detect:

`LOGO_MISSING`
`LOGO_ADDED`
`LOGO_MODIFIED`
`LOGO_MOVED`
`LOGO_RESIZED`

Use perceptual hashing and feature/image matching where appropriate.

---

# 14. IMAGE COMPARISON

Extract embedded images whenever possible.

Compare:

- Number of images
- Position
- Dimensions
- Resolution
- Image content
- Color
- Cropping
- Rotation
- Compression changes
- Transparency
- Replacement
- Missing/added images

Distinguish:

**Same image, different compression**

from

**Actual visual image change**

whenever possible.

---

# 15. COLOR COMPARISON

Compare:

- Text colors
- Background colors
- Fill colors
- Stroke colors
- Shape colors
- Image color differences

Support:

- RGB
- CMYK
- Grayscale

Normalize color spaces before comparison where appropriate.

Example:

`Heading color: #0057B8 → #0047A0`

---

# 16. TABLE COMPARISON

Detect and compare tables structurally.

Compare:

- Table existence
- Position
- Rows
- Columns
- Cell content
- Cell position
- Header rows
- Merged cells
- Borders
- Background
- Alignment
- Row height
- Column width

Report cell-level changes.

Example:

`Page 17 → Table 2 → Row 4 → Column 3`

Old:
`₹10,000`

New:
`₹12,000`

---

# 17. HEADER / FOOTER COMPARISON

Identify repeated headers and footers separately.

Compare:

- Header text
- Footer text
- Position
- Logo
- Page numbering
- Dates
- Document identifiers
- Confidentiality labels

Avoid reporting the same global header difference hundreds of times without summarization.

Example:

`Footer changed on pages 1–500`

Allow expansion to individual affected pages.

---

# 18. PAGE NUMBER COMPARISON

Detect:

- Missing page number
- Wrong page number
- Position change
- Font change
- Numbering-format change

Example:

`Page 09 → "9 of 50" changed to "9 / 50"`

---

# 19. METADATA COMPARISON

Compare PDF metadata independently from page content.

Include:

- Title
- Author
- Subject
- Keywords
- Creator
- Producer
- Creation date
- Modification date
- PDF version
- XMP metadata
- Custom metadata
- Encryption/security information where accessible

Report:

`METADATA_ADDED`
`METADATA_REMOVED`
`METADATA_CHANGED`

Do not let irrelevant volatile metadata automatically reduce the content accuracy score unless configured.

---

# 20. PDF STRUCTURAL / OBJECT COMPARISON

Inspect the internal PDF structure where practical.

Compare:

- Page tree
- Resources
- Fonts
- XObjects
- Images
- Content streams
- Annotations
- AcroForms
- Embedded files
- Bookmarks/outlines
- Named destinations
- Links
- Optional content/layers
- Attachments

Use pikepdf/qpdf-level inspection where appropriate.

Do NOT compare raw object numbers as meaningful content because equivalent PDFs can have different internal object IDs.

---

# 21. FORM COMPARISON

Compare AcroForm fields.

Detect:

- Added fields
- Deleted fields
- Field name change
- Field type change
- Position change
- Default-value change
- Current-value change
- Required/read-only flags
- Checkbox/radio state
- Dropdown options

---

# 22. ANNOTATION COMPARISON

Compare:

- Comments
- Highlights
- Notes
- Links
- Stamps
- Signatures where inspectable
- Drawing annotations

Report added, removed and changed annotations separately.

---

# 23. DRAWING / VECTOR COMPARISON

Compare vector elements:

- Lines
- Rectangles
- Curves
- Borders
- Fill
- Stroke
- Stroke width
- Position
- Dimensions

This is important because a visual difference may not exist as an image.

---

# 24. OCR DIFFERENCE HANDLING

OCR errors must NOT automatically be classified as document differences.

Use OCR confidence.

Example:

PDF A OCR:
`Invoice 1008`

PDF B OCR:
`Invoice 1O08`

Before declaring a difference, check:

- Native PDF text
- OCR confidence
- Bounding-box alignment
- Visual similarity
- Character ambiguity

Classify uncertain cases as:

`POSSIBLE_OCR_VARIANCE`

instead of definitive document changes.

---

# 25. DIFFERENCE TAXONOMY

Every detected difference must receive a structured category.

Examples:

`TEXT_ADDED`
`TEXT_REMOVED`
`TEXT_MODIFIED`
`SEMANTIC_CHANGE`
`NUMERIC_CHANGE`
`DATE_CHANGE`
`FONT_CHANGE`
`FONT_SIZE_CHANGE`
`COLOR_CHANGE`
`POSITION_CHANGE`
`LAYOUT_CHANGE`
`IMAGE_ADDED`
`IMAGE_REMOVED`
`IMAGE_CHANGED`
`LOGO_CHANGED`
`TABLE_CHANGED`
`METADATA_CHANGED`
`PAGE_ADDED`
`PAGE_REMOVED`
`PAGE_REORDERED`
`HEADER_CHANGED`
`FOOTER_CHANGED`
`FORM_CHANGED`
`ANNOTATION_CHANGED`
`VECTOR_CHANGED`
`VISUAL_CHANGE`
`OCR_UNCERTAINTY`

Every difference object should contain:

- difference\_id
- page\_a
- page\_b
- category
- subcategory
- severity
- confidence
- reference\_value
- candidate\_value
- reference\_bbox
- candidate\_bbox
- explanation
- score\_impact

---

# 26. SEVERITY

Classify differences:

### Critical

Examples:

- Missing page
- Important text removed
- Numeric/value change
- Major semantic change
- Logo missing
- Critical table value changed

### Major

Examples:

- Paragraph changed
- Image replaced
- Major layout shift
- Table structure changed

### Minor

Examples:

- Font size changed
- Small positioning difference
- Minor color difference

### Informational

Examples:

- Producer metadata changed
- Compression changed without visible impact

Severity rules must be configurable rather than hard-coded to one business domain.

---

# 27. MULTI-DIMENSIONAL ACCURACY / MATCH SCORE

Do NOT generate one unexplained percentage.

Calculate independent scores:

- Text Match %
- Semantic Match %
- Visual Match %
- Layout Match %
- Typography Match %
- Image Match %
- Logo Match %
- Table Match %
- Metadata Match %
- Structural Match %
- Form Match %

Then calculate:

## Overall Match Score

Example:

`Overall Match: 96.84%`

The weighting formula must be visible and configurable.

Example only:

Text: 25%
Visual: 20%
Layout: 15%
Typography: 10%
Images/Logos: 10%
Tables: 10%
Semantic: 5%
Metadata/Structure: 5%

Do not call this "accuracy" unless there is known ground truth.

In the UI/report, prefer:

**Overall Match Score**

Accuracy should be reserved for benchmark evaluation against manually labelled expected differences.

---

# 28. FALSE-POSITIVE CONTROL

Implement configurable tolerance rules for:

- Pixel differences
- Anti-aliasing
- Font rendering
- Coordinate movement
- Color differences
- OCR confidence
- Line wrapping
- Metadata
- Image compression
- DPI differences

Provide profiles:

### Strict

Pixel-perfect validation.

### Standard

Meaningful content and visual changes.

### Content Focused

Prioritize text/data/semantic changes.

### Visual Focused

Prioritize layout/design/rendering.

### Custom

User-defined tolerances and weights.

---

# 29. COMPARISON UI

After processing, display:

### Overall Match

`96.84%`

### Summary

`Pages: 500`
`Pages matched: 487`
`Pages with differences: 13`
`Critical: 2`
`Major: 4`
`Minor: 19`
`Informational: 8`

Provide filters for:

- Page
- Difference type
- Severity
- Confidence
- Text
- Visual
- Font
- Layout
- Image
- Logo
- Table
- Metadata
- Semantic

---

# 30. SIDE-BY-SIDE PDF VIEWER

Create:

`REFERENCE | CANDIDATE`

Synchronize:

- Page navigation
- Zoom
- Scroll
- Selection

Highlight corresponding differences on both documents.

Clicking a report difference should automatically navigate to and highlight the exact PDF region.

---

# 31. OVERLAY / DIFF VIEW

Provide:

### Side-by-Side

Original and candidate.

### Overlay

Documents superimposed.

### Difference

Only changed regions.

### Blink

Rapidly alternate A/B.

### Heatmap

Show concentration of differences.

---

# 32. HIGHLIGHTING

Use clear categories in the viewer/report:

- Removed
- Added
- Modified
- Moved
- Style changed
- Visual difference

Clicking a highlighted area must show:

**Difference Type:** Text Modification

**Reference:** 30 days

**Candidate:** 45 days

**Location:** Page 7, paragraph 3

**Confidence:** 100%

**Severity:** Critical

---

# 33. PAGE-LEVEL RESULT

Every page must have a comparison result.

Example:

`Page 001 — 100%`
`Page 002 — 99.6%`
`Page 003 — 91.2%`
`Page 004 — Missing`
`Page 005 — 100%`

Users must be able to sort by lowest match score first.

---

# 34. DASHBOARD & CHARTS

Generate graphical summaries.

Required:

### Overall Match Gauge

### Pie / Donut Chart

Difference distribution:

- Text
- Visual
- Font
- Layout
- Image
- Table
- Metadata
- Semantic
- Other

### Severity Chart

- Critical
- Major
- Minor
- Informational

### Page Difference Chart

Show difference count/match score by page.

For 500-page documents, allow navigation/filtering instead of trying to display every page label simultaneously.

---

# 35. PDF COMPARISON REPORT

Generate a professional downloadable PDF report.

Report structure:

## Executive Summary

- Reference document
- Candidate document
- Comparison date
- Pages compared
- Overall match score
- Total differences
- Critical differences
- Major differences
- Minor differences

## Match Score Breakdown

Charts for:

- Text
- Semantic
- Visual
- Layout
- Typography
- Images
- Tables
- Metadata

## Difference Distribution

Pie/donut chart.

## Severity Distribution

Chart.

## Page Comparison

Page-by-page score.

## Detailed Differences

For each difference:

- Page
- Category
- Severity
- Confidence
- Reference value
- Candidate value
- Description
- Screenshot/reference crop
- Screenshot/candidate crop
- Highlighted region

---

# 36. ANNOTATED PDF OUTPUT

In addition to the report, generate:

### Annotated Reference PDF

and/or

### Annotated Candidate PDF

Overlay detected difference boxes onto the relevant regions.

Do not permanently modify the uploaded originals.

---

# 37. EXPORTS

Support:

- PDF report
- JSON
- CSV
- Excel

JSON should expose the complete structured comparison result for integration with automated testing pipelines.

---

# 38. RECOMMENDED PYTHON TECHNOLOGY STACK

Evaluate the current stable versions and licensing before implementation.

Preferred starting stack:

### PDF parsing/rendering

- PyMuPDF
- pikepdf

### OCR / document layout

- Surya OCR

### Supplemental structured extraction

- pdfplumber where useful

### Images / vision

- OpenCV
- Pillow
- scikit-image

### Font inspection

- FontTools

### Text comparison

- Python difflib
- RapidFuzz

### Semantic comparison

- Sentence Transformers/local embeddings
- cosine similarity
- deterministic NLP rules

### Numerical/data comparison

- NumPy
- Pandas

### Report generation

- ReportLab

### API

- FastAPI

### Job processing

Choose based on deployment:

- Celery
- RQ
- Dramatiq

### Queue/cache

- Redis

### Database

- PostgreSQL

### Large file storage

- Local filesystem for development
- S3-compatible object storage for production

Do not introduce a library merely because it is popular.

Benchmark alternatives for:

- accuracy
- performance
- memory consumption
- licensing
- maintenance
- large-document behavior

before finalizing the dependency.

---

# 39. PROCESSING ARCHITECTURE

Implement approximately:

PDF A + PDF B
↓
File Validation
↓
PDF Inspection
↓
Page Inventory
↓
Native Content Extraction
↓
OCR only where required
↓
Layout/Structure Extraction
↓
Page Alignment
↓
Element Alignment
↓
┌─────────────────────────────┐
│ Text Comparison │
│ Semantic Comparison │
│ Typography Comparison │
│ Layout Comparison │
│ Visual Comparison │
│ Image/Logo Comparison │
│ Table Comparison │
│ Metadata Comparison │
│ Structural Comparison │
│ Form/Annotation Comparison │
└─────────────────────────────┘
↓
Difference Correlation
↓
False-Positive Suppression
↓
Severity Classification
↓
Scoring Engine
↓
Annotated PDFs
↓
Dashboard
↓
PDF / JSON / CSV / Excel Report

---

# 40. DIFFERENCE CORRELATION — CRITICAL REQUIREMENT

Do not report the same physical change independently five times.

Example:

Changing:

`30 → 45`

could trigger:

- Text diff
- Semantic diff
- Pixel diff
- Layout diff
- OCR diff

The correlation engine should understand these observations refer to one underlying change.

Create ONE primary difference:

`NUMERIC_TEXT_CHANGE`

and attach supporting signals:

`text=true`
`semantic=true`
`visual=true`

This is essential for producing an accurate, usable report.

---

# 41. PERFORMANCE

Instrument every stage.

Capture:

- File parsing time
- Page extraction time
- OCR time
- Rendering time
- Comparison time
- Report generation time
- Peak memory
- CPU utilization
- GPU utilization where applicable
- Pages/second

The system must allow administrators to tune:

- Worker count
- OCR batch size
- DPI
- Concurrent pages
- Memory limits
- GPU usage

---

# 42. CACHING

Cache expensive artifacts using content hashes.

Examples:

- Rendered page
- Extracted text
- OCR output
- Layout output
- Image hashes
- Semantic embeddings

If the same baseline PDF is compared against 20 candidate PDFs, the baseline should not need to be completely processed 20 times.

---

# 43. SECURITY

Implement:

- File-type validation
- PDF signature validation
- Upload size limits configurable by administrator
- Protection against malformed PDFs
- Processing timeout
- Isolated worker processing
- Filename sanitization
- Secure temporary storage
- Automatic cleanup
- Audit logging

Never trust PDF contents.

---

# 44. BENCHMARKING

Create a benchmark dataset containing controlled differences.

Examples:

- One changed character
- One changed number
- Font family change
- 1 pt font-size change
- 2 px movement
- Color change
- Missing logo
- Resized logo
- Replaced image
- Added paragraph
- Deleted paragraph
- Reordered page
- Missing page
- Table-cell change
- Metadata-only change
- Scanned-page OCR variation
- Same document generated by different PDF producers

For each test, maintain expected differences.

Calculate:

- Precision
- Recall
- F1 score
- False-positive rate
- False-negative rate

This benchmark is the appropriate place to use the term:

**Detection Accuracy**

Do not equate document similarity with detector accuracy.

---

# 45. TESTING

Implement:

### Unit tests

Each comparison algorithm independently.

### Integration tests

End-to-end PDF comparison.

### Regression tests

Known PDF pairs and expected differences.

### Performance tests

10 / 100 / 500 / 1000-page PDFs.

### Stress tests

Large file sizes.

### OCR tests

Scanned and multilingual PDFs.

### Golden-document tests

Known reference/candidate pairs with exact expected outputs.

---

# 46. FINAL QUALITY REQUIREMENT

The application must answer five questions for every meaningful difference:

### 1. WHAT changed?

Example:
`Invoice total changed`

### 2. WHERE?

Example:
`Page 18 → Table 2 → Row 5 → Column 4`

### 3. FROM WHAT TO WHAT?

Example:
`₹125,000 → ₹152,000`

### 4. HOW IMPORTANT IS IT?

Example:
`Critical`

### 5. HOW CERTAIN ARE WE?

Example:
`99.8% confidence`

Never produce only:

`PDFs are 96% similar.`

The final result must be explainable, traceable and visually verifiable.

---

# 47. DEVELOPMENT APPROACH

Do not attempt the entire platform in one implementation step.

Build vertically:

**Phase 1**
PDF ingestion + native text extraction + page rendering.

**Phase 2**
Page alignment + text diff + bounding-box highlighting.

**Phase 3**
Pixel/visual comparison + overlay viewer.

**Phase 4**
Typography + geometry + color comparison.

**Phase 5**
Images + logos + tables.

**Phase 6**
Surya OCR + scanned/hybrid documents.

**Phase 7**
Semantic + numeric/entity comparison.

**Phase 8**
Metadata + PDF structure + forms + annotations.

**Phase 9**
Difference correlation + scoring.

**Phase 10**
Dashboard + PDF/Excel/JSON reports.

**Phase 11**
Large-document distributed processing.

**Phase 12**
Benchmarking, tuning and false-positive reduction.

At the end of every phase:

1. Run automated tests.
2. Compare against golden PDFs.
3. Measure performance.
4. Record false positives.
5. Record false negatives.
6. Do not proceed until the phase is stable.

The finished product should behave as a **PDF QA and validation platform**, not merely a PDF text comparison utility.