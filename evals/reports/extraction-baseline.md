# Extraction eval — baseline

- Generated: 2026-10-06 13:01 UTC, seed 2026, 163 documents, 0 errors
- Cost: $0.0000, mean latency 0 ms

| Metric | Value | Gate |
|---|---|---|
| Critical fields (policy_number, event_date, total_amount, iban) | 86.2% [81.6%–90.3%] (n=652) | ≥ 98% |
| All fields | 89.0% [85.3%–92.3%] (n=1630) | ≥ 92% |
| Line items exact | 81.0% [74.8%–86.5%] (n=163) | |
| Anomaly detection (validators on extracted data) | 86.7% [72.4%–96.8%] (n=30) | |
| False alarms on clean documents | 0.0% [0.0%–0.0%] (n=134) | |
| PII masking recall | 86.9% [84.9%–88.9%] (n=520) | |

## Critical fields by layout

| Layout | Critical-field accuracy |
|---|---|
| form | 100.0% [100.0%–100.0%] (n=532) |
| free-text e-mail | 25.0% [25.0%–25.0%] (n=120) |

## Per field

| Field | Accuracy |
|---|---|
| policy_number | 81.6% [75.5%–87.1%] (n=163) |
| event_date | 81.6% [75.5%–87.1%] (n=163) |
| total_amount | 81.6% [75.5%–87.1%] (n=163) |
| iban | 100.0% [100.0%–100.0%] (n=163) |
| claimant_name | 81.6% [75.5%–87.1%] (n=163) |
| issue_date | 81.6% [75.5%–87.1%] (n=163) |
| document_number | 100.0% [100.0%–100.0%] (n=163) |
| vendor_name | 100.0% [100.0%–100.0%] (n=163) |
| doc_type | 81.6% [75.5%–87.1%] (n=163) |
| language | 100.0% [100.0%–100.0%] (n=163) |

## By language / document type

| Slice | All-field accuracy |
|---|---|
| sk | 89.0% [84.3%–93.2%] (n=1150) |
| de | 88.8% [81.2%–95.0%] (n=480) |
| claim_form | 60.0% [52.0%–68.0%] (n=450) |
| invoice | 100.0% [100.0%–100.0%] (n=500) |
| repair_estimate | 100.0% [100.0%–100.0%] (n=680) |

## PII not masked (examples)

Known gap: names of people other than the policyholder need NER (ADR 0012).

- `Adam Höfer`
- `Alfréd Grznárová`
- `Aurelia Oberhofer`
- `Barbara Dusko`
- `Benjamin Kopf`
- `Blažej Franeková`
- `Boleslav Novotný`
- `Bonifác Capka`
- `Branislav Ďurišová`
- `Dagmara Mrázová`
