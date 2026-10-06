# ADR 0007 — Document parsing and OCR

## Context
Inputs:
- digital PDFs (invoices, repair estimates),
- scanned forms (handwritten claim reports),
- medical reports,
- photos.

The languages are German and Slovak. The output is structured fields with per-field confidence and the source location (page and bounding box), so a handler can verify each value with one click.

## Options

| Option | Pros | Cons |
|---|---|---|
| A. Azure AI Document Intelligence | Strong OCR including handwriting; layout and tables; EU region; bounding boxes | Per-page cost; prebuilt models only cover generic invoices |
| B. Open-source parsing (Docling, Unstructured) + Tesseract | Free; runs locally | Weaker on handwriting and poor scans |
| C. Multimodal LLM directly on page images | One step; handles odd layouts | Expensive per page; no reliable coordinates; harder to verify; hallucination risk on numbers |
| **D. Layered: layout/OCR first (A or B) → LLM extraction on text+layout → vision LLM only as fallback** | Cheap path for clean docs; coordinates for verification; LLM does what it is good at (mapping to schema) | More pipeline steps |

## Decision
**Option D.**
1. Digital PDFs → text layer via `pypdf` (implemented; local, free). Docling stays the candidate when tables and layout coordinates are needed for source highlighting in the CRM.
2. Scans and handwriting → Azure Document Intelligence (EU).
3. LLM maps text plus layout to the Pydantic schema for that document type, citing source spans.
4. Validators check the extracted values: IBAN checksum, dates within the policy period, totals equal the sum of the lines, policy number exists via MCP.
5. Fields that fail validation or have low confidence trigger a vision-LLM re-read. If they still fail, the case goes to human review with the field highlighted.

## Implementation status
- **Done:** text layer (pypdf), LLM extraction with verbatim evidence quotes, and deterministic validators (`src/aip/agents/validators.py`): IBAN checksum, line items = total, event date vs. claim and policy period, policy number match, document total vs. claimed amount, and grounding (every evidence quote must occur in the document).
- **Not wired yet:** OCR for scans. A document without a text layer escalates the claim to a human instead of guessing.
- **Not wired yet:** bounding boxes. Evidence is a verbatim quote for now, not page coordinates.

## Why
- Deterministic validators catch the most damaging LLM errors (wrong amounts, swapped dates) for free.
- Source coordinates make human review fast, which is what actually reduces handling time.
- Cost scales with document difficulty, not with volume.

## Consequences
- The OCR output is cached by file hash (ADR 0005 L4).
- Per-field metrics are tracked per document type and per language (ADR 0011).

## Revisit when
Vision models become cheap and reliable enough on numbers that step 5 matches step 1–3 quality at lower total cost. That is measured in the evals, not assumed.
