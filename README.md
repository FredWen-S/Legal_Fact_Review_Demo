# LLM + RAG Legal Document Review Assistant

This project upgrades a rule-based lawyer document review demo into a stronger AI application that is suitable for a software engineering / AI tooling portfolio.

It reviews synthetic legal-style documents, runs deterministic checks, performs structured extraction with an optional LLM, retrieves matching synthetic knowledge-base records, compares extracted fields against retrieved knowledge, and exports review reports in HTML and Excel.

The current hardening focus is reliability and explainability: malformed LLM output falls back to the local mock extractor with a visible reason, and local RAG retrieval records match / no-match status instead of treating weak lexical hits as confirmed matches. Retrieval defaults to lexical search and can optionally use an embedding backend when a local embedding provider is configured.

## Project Background

Legal document review often mixes two very different tasks:

1. Deterministic QA
   - missing fields
   - date / amount / ID formatting
   - clause numbering
   - name consistency

2. Context-aware review
   - extracting key entities from messy text
   - finding the right client profile or standard template
   - checking whether a document aligns with internal standards

This demo keeps both layers separate on purpose:

- rules stay deterministic and explainable
- AI extraction is optional
- when no API key is configured, the app stays fully usable through deterministic mock extraction
- retrieval uses only local synthetic knowledge
- retrieval defaults to lexical scoring; optional embedding retrieval falls back to lexical when unavailable
- local review history and audit log store only lightweight metadata and event summaries
- privacy/redaction policy sanitizes storage metadata and adds privacy summaries to exports
- the app still works offline with mock extraction when no API key is configured

## Demo Data Disclaimer

Everything in this repository is synthetic.

- No real legal documents are included.
- No real client records are included.
- `kb/clients`, `kb/clauses`, and `kb/templates` contain fictional demo data only.
- Sample documents under `app/sample_data` are for demonstration and testing only.

This project is not legal advice and is not a production legal review system. It should remain a synthetic demo unless it receives substantial hardening, security review, privacy controls, and domain validation.

## What Changed

Compared with the earlier rule-based demo, this version adds:

- synthetic knowledge base under `kb/clients`, `kb/clauses`, and `kb/templates`
- structured extraction for:
  - parties
  - company names
  - credit codes
  - legal representatives
  - registered addresses
  - dates
  - amounts
  - contract IDs
  - statute citations (e.g. `《中华人民共和国民法典》第五百七十七条`, `民事诉讼法第一百二十二条`)
- statute citation cross-check against a local statute reference list (repealed laws, article numbers beyond the law's length, unknown laws)
- LLM-generated risk explanations for every finding, with a deterministic template fallback
- optional LLM extraction path with mock fallback
- lightweight local RAG-style retrieval
- issue schema with:
  - `severity`
  - `issue_type`
  - `original_text`
  - `suggested_text`
  - `evidence_source`
  - `explanation`
- richer HTML and Excel review exports

## Architecture

```text
Document (DOCX / PDF)
  -> parsers
  -> regex extraction
  -> structured extraction
       -> LLM if API key exists
       -> mock extractor otherwise
  -> local retrieval over synthetic KB
  -> deterministic validators
  -> RAG comparison validators
  -> statute citation cross-check
  -> issue aggregation (sorted by severity)
  -> risk explanations
       -> LLM if API key exists
       -> rule templates otherwise
  -> Streamlit UI + HTML/Excel/Word exports
```

### Main Flow

1. Parse a document into text chunks.
2. Extract deterministic fields with regex rules.
3. Extract structured entities with:
   - a remote LLM when configured
   - a local mock extractor otherwise
4. Retrieve:
   - the most relevant synthetic client profile
   - relevant synthetic templates
   - related standard clauses
5. Run checks:
   - deterministic document checks
   - source comparison checks
   - RAG comparison checks
   - statute citation checks against `kb/statutes`
6. Sort issues by severity and attach a risk explanation to each one (one batched LLM call, or templates offline).
7. Export issues plus extraction/retrieval context.

## Module Guide

### Core Review

- `app/review_engine.py`
  - main review pipeline
  - compatibility wrappers for older entry points
  - richer `ReviewResult` output with findings, structured extraction, and retrieved knowledge

### Parsing

- `app/parsers/docx_parser.py`
- `app/parsers/pdf_parser.py`
- `app/parsers/ocr_pdf_parser.py`

These convert uploaded files into chunked text for downstream review.

### Extraction

- `app/extractors/field_extractor.py`
  - deterministic regex extraction
- `app/extractors/llm_extractor.py`
  - structured extraction
  - optional LLM call
  - mock fallback when no API key is available
- `app/extractors/statute_extractor.py`
  - statute citation extraction with Chinese numeral parsing
  - ignores contract clause references such as `《技术服务合同》第三条`
- `app/extractors/external_review_fields.py`
  - builds the review workbench fields shown in UI and exports

### Retrieval

- `app/rag/retrieval.py`
  - loads local synthetic KB records
  - scores and retrieves relevant client / template / clause matches

### Validators

- `app/validators/format_rules.py`
  - placeholders, dates, amounts, IDs, formatting
- `app/validators/consistency_rules.py`
  - internal conflicts, party consistency, amount/date logic
- `app/validators/source_compare_rules.py`
  - base-info comparison and missing-field checks
- `app/validators/document_rules.py`
  - spelling variation checks
  - clause numbering checks
  - profile-based missing fields
- `app/validators/rag_rules.py`
  - compares extracted values with retrieved KB records
  - checks for missing standard clauses
- `app/validators/statute_rules.py`
  - `STATUTE_REPEALED`: cited law is repealed (e.g. 《合同法》, replaced by 《民法典》)
  - `STATUTE_ARTICLE_OUT_OF_RANGE`: article number exceeds the law's article count
  - `STATUTE_UNVERIFIED`: law is not in the local reference list

### LLM

- `app/llm/client.py`
  - shared OpenAI-compatible chat-completion client (JSON mode, stable fallback reason codes)
- `app/llm/risk_explainer.py`
  - sends the severity-sorted findings (up to 30) to the LLM in one request
  - validates the JSON response with Pydantic, ignores unknown `risk_id`s and text that claims a legal conclusion
  - falls back to per-risk-type template explanations when no API key is set or the call fails

### Reports

- `app/reports/html_report.py`
- `app/reports/excel_report.py`
- `app/reports/docx_report.py`
- `app/reports/package_export.py`

Exports include issues plus AI/RAG context for demoability.

### Synthetic Knowledge Base

- `kb/clients`
  - fictional client profiles
- `kb/clauses`
  - fictional standard clause entries
- `kb/templates`
  - fictional template metadata used for retrieval
- `kb/statutes`
  - public statute metadata (status, effective / repeal date, article count) used to cross-check citations; a small demo list, not a legal database

## Deterministic Checks Kept

The project still keeps deterministic checks for:

- spelling variation / near-duplicate company names
- missing fields
- amount format
- date format and date logic
- party name consistency
- clause numbering
- placeholders
- evidence references

## LLM Configuration

If no API key is configured, the app automatically uses mock extraction and template risk explanations.

When a key is configured, the LLM is used for two steps: structured extraction (including statute citations) and risk explanations. Each finding records `explanation_source` (`llm` or `mock`), and exports include a `Risk Explanation` column. Explanations are review hints, not legal conclusions; identifiers in them are masked in exports.

Supported environment variables:

```powershell
$env:LEGAL_LLM_API_KEY="..."
$env:LEGAL_LLM_BASE_URL="https://api.openai.com/v1"
$env:LEGAL_LLM_MODEL="gpt-4o-mini"
$env:LEGAL_LLM_TIMEOUT_SECONDS="30"
```

Fallback variables also supported:

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="gpt-4o-mini"
```

## How To Run

Requirements: Python 3.10-3.12 (Python 3.12 recommended). Python 3.9 and earlier are not supported because the code uses `X | None` type syntax at runtime, and Python 3.13 is not part of the supported delivery range.

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

### 2. Launch the Streamlit app

```powershell
streamlit run app/main.py
```

### 3. Open the local URL

Usually:

```text
http://localhost:8501
```

### 4. Demo flow

Use the sample cases in `app/sample_data/test_cases` or the sample files in `app/sample_data`.

Recommended demo:

1. Open the single review page.
2. Upload a synthetic document.
3. Optionally upload base info and evidence index for full review mode.
4. Run the review.
5. Inspect:
   - Issues
   - Structured Extraction
   - Retrieved Knowledge
   - Review Workbench
6. Export:
   - Excel review workbook
   - HTML review report
   - ZIP review package

## RAG Flow

The retrieval flow is intentionally lightweight and local. The default backend is lexical, so the demo remains offline and does not require model downloads.

1. Build a query from:
   - document text
   - extracted company names
   - credit codes
   - legal representatives
   - contract IDs
2. Search the synthetic KB with token overlap plus exact-match bonuses.
3. Return:
   - top client profile
   - top templates
   - related clauses
4. Compare extracted fields against retrieved records.
5. Emit issues such as:
   - client profile mismatch
   - spelling variation vs retrieved client name
   - missing standard clause
   - contract prefix mismatch

### Optional Embedding Retrieval

Embedding retrieval is an optional portfolio/demo enhancement, not a production legal search guarantee. It still searches only the synthetic local KB.

Default behavior:

```powershell
$env:RAG_RETRIEVAL_BACKEND="lexical"
```

Optional local embedding behavior:

```powershell
$env:RAG_RETRIEVAL_BACKEND="embedding"
$env:RAG_EMBEDDING_PROVIDER="local"
$env:RAG_EMBEDDING_MODEL="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
$env:RAG_MIN_SCORE="0.6"
```

The embedding provider is loaded lazily. If `sentence-transformers` is not installed, the model cannot load, or embedding computation fails, retrieval automatically falls back to lexical and records that fallback in `match_reason`.

Optional install:

```powershell
pip install sentence-transformers
```

Do not add real client or legal data to the KB for this demo.

## Local Review History / Audit Log

The app keeps a lightweight local SQLite history so the demo can show recent synthetic review runs and key UI events.

Stored history metadata includes file name, document hash, review mode, issue counts, severity distribution, LLM mode/fallback reason, retrieval backend, and retrieval status summary. Audit events include `run_review_started`, `run_review_succeeded`, `run_review_failed`, and prepared export events for Excel, HTML, Word, and ZIP.

The history/audit layer does not store full document text, full extracted text, full prompts, or full LLM responses. It is intended for local demo explainability only and is not a production compliance audit system.

## Privacy / Redaction Policy

The project includes a lightweight local privacy policy layer for demo hygiene:

- storage and audit metadata are sanitized before SQLite writes
- dangerous metadata keys such as `document_text`, `extracted_text`, `prompt`, `raw_response`, and `llm_response` are removed
- error messages are shortened and traceback bodies are not stored
- email, phone-like values, long ID-like numbers, and credit-code-like values are masked in storage/audit metadata
- exports include a privacy summary explaining the synthetic/local/demo boundary

Report redaction is not forced by default because the portfolio demo should remain readable with synthetic test issues. It can be enabled locally through `PrivacyPolicy(redact_report_sensitive_fields=True)` when generating reports in tests or integrations.

This is not a production privacy compliance system, DLP layer, or legal-document security product.

## Synthetic Demo / Evaluation Cases

The repository includes a repeatable synthetic demo case suite for portfolio demos, interview walkthroughs, and regression tests. All files are fictional and generated locally under `demo_cases/files`.

| case_id | Purpose |
| --- | --- |
| `clean_contract_pass` | Clean synthetic complaint with full-review inputs, matched client profile, and no high-risk findings. |
| `missing_required_fields` | Deterministic validation demo for missing fields and malformed amount text. |
| `client_profile_mismatch` | RAG comparison demo where retrieved synthetic client profile conflicts with document values. |
| `missing_standard_clause` | Template/clause retrieval demo for missing synthetic standard clauses. |
| `llm_fallback_privacy_export` | Offline mock LLM fallback plus export privacy-summary validation. |

Run the full demo case suite:

```powershell
python scripts/run_demo_cases.py
```

Run one case:

```powershell
python scripts/run_demo_cases.py --case client_profile_mismatch
```

Emit machine-readable output:

```powershell
python scripts/run_demo_cases.py --json
```

The runner reads `demo_cases/cases_manifest.json`, uses the normal workflow path, defaults to offline mock extraction and lexical retrieval, checks expected issue types and forbidden issue types, and verifies privacy summaries in exports.

These cases are for engineering regression and demo explainability. They are not legal advice and are not evidence of production legal-review accuracy.

## Tests

Run the focused verification suite:

```powershell
python -m pytest tests/test_extractors.py tests/test_validators.py tests/test_reports.py tests/test_manual_review.py tests/test_single_document_mode.py tests/test_llm_rag_pipeline.py tests/test_case_workspace.py tests/test_rule_config_center.py tests/test_docx_package_export.py tests/test_docx_annotation.py tests/test_single_review_workflow.py tests/test_embedding_retrieval.py tests/test_review_history.py tests/test_audit_log.py tests/test_redaction_policy.py tests/test_privacy_storage.py tests/test_privacy_exports.py tests/test_demo_cases.py tests/test_statute_references.py tests/test_risk_explainer.py -q
```

This focused suite covers deterministic extraction, validation rules, LLM fallback/schema behavior, local RAG no-match behavior, report exports, manual review records, case workspace behavior, rule configuration, DOCX package generation, lightweight history/audit storage, privacy/redaction behavior, and synthetic demo/evaluation cases.

## Resume Framing

This version is positioned as a local-first AI review assistant that combines:

- deterministic rule engines
- mockable LLM integration
- local RAG over synthetic internal knowledge
- local metadata-only review history and audit events
- lightweight privacy/redaction policy for storage and exports
- structured reporting
- offline demoability

That makes it much stronger for an AI tooling or full-stack engineering portfolio than a pure regex demo.

## Remaining Limits

- Retrieval defaults to lexical scoring; embedding retrieval is optional.
- Embedding retrieval is optional and falls back to lexical retrieval when unavailable.
- LLM extraction uses an OpenAI-compatible HTTP path but is not vendor-specific beyond that interface.
- LLM output is schema-validated, but the fallback path is still a demo safety mechanism rather than a legal-quality extraction guarantee.
- Clause coverage is based on a small synthetic KB.
- The statute reference list covers only a handful of laws and checks name, status and article count, not article content or amended article numbering.
- No authentication, redaction policy engine, or enterprise audit trail is implemented.
- Review History / Audit Log is metadata-only local demo instrumentation, not a production compliance trail.
- Privacy/redaction is a lightweight local demo safeguard, not a production DLP or compliance system.
- This is a demo assistant, not a production legal review platform.
