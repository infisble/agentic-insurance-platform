# ADR 0011 — Evaluation of non-deterministic components

## Context
Prompts, models, retrieval settings and tool descriptions change often. Each change can silently degrade quality. We need evidence before release and monitoring after.

## Options

| Option | Pros | Cons |
|---|---|---|
| A. Manual spot checks | Cheap | Not repeatable; regressions slip through |
| B. LLM-as-judge for everything | Scales; works for free text | Judge bias and drift; weak for numbers and fields |
| **C. Layered: deterministic metrics where possible, LLM-judge only for free text, both on a versioned golden dataset, run in CI with gates** | Repeatable; cheap for structured tasks; honest about where judges are needed | Dataset curation effort |

## Decision
**Option C.**

**Golden dataset (versioned in repo, synthetic, no real PII)**

| Set | Size |
|---|---|
| Documents per type × language (DE/SK) | ≥ 15 each, with labelled fields |
| Claims with labelled triage class and route | ≥ 60 |
| Coverage questions with expected verdict and required clause IDs | ≥ 40 |
| Adversarial cases (prompt injection in documents, contradictory amounts, missing pages) | ≥ 20 |

**Metrics per component**

| Component | Metric | Gate (initial) |
|---|---|---|
| Extraction | per-field exact/normalised match; critical fields (amount, IBAN, dates) separately | critical ≥ 98%, overall ≥ 92% |
| Triage | accuracy, confusion matrix, cost of misroute | ≥ 90%, no fraud→simple misroutes |
| Retrieval | recall@5 of required clauses | ≥ 90% |
| Coverage | verdict accuracy, citation correctness, correct abstention | ≥ 90%, 0 uncited answers |
| Letters / summaries | LLM-judge rubric (faithfulness, completeness, tone), calibrated against 30 human ratings | ≥ 4/5 mean faithfulness |
| All | cost per case, p95 latency | no regression > 15% |

**Statistical honesty**
- The sets are small, so gates must not react to noise.
  - With 60 triage cases, a 90% accuracy has a 95% confidence interval of roughly ±7.5 points.
  - With 15 documents of one type, a single error drops "98%" to 93%.
- Therefore:
  - **Pooling:** field-level metrics are pooled across all documents of all types (hundreds of field instances), and per-type numbers are reported but not gated.
  - **Confidence intervals:** every metric is reported with a bootstrap 95% CI.
  - **Regression rule:** a regression fails CI only when the new score is below the baseline's CI lower bound, or when any **critical-case** test (fraud misroute, wrong payout amount, uncited coverage answer) fails. Critical cases are hard asserts, not averages.
  - **Variance runs:** a nightly job runs the suite 3× with the response cache bypassed (ADR 0005) to measure run-to-run variance.
- The sets grow from production overrides, so the intervals narrow over time.

**Process**
- **CI:** runs the eval suite on every pull request touching `prompts/`, `agents/`, `retrieval/` or model routing. It posts a diff table and fails on gate violations.
- **Release notes:** every prompt version carries its eval scores.
- **Online feedback:** human overrides in production (ADR 0010) are reviewed weekly. Representative failures are added to the golden set, which grows from real misses.

## Implementation status (phase 2)
**What exists**
- **Runner:** `python -m aip.evals extraction --extractor baseline|llm [--gate]`. The report is written to `evals/reports/`.
- **Golden set:** generated deterministically (seed 2026, ~160 documents) as SK/DE invoices, repair estimates, claim forms and **free-text customer e-mails**, with labelled fields and injected anomalies.
- **Metrics:**
  - per-field and critical-field accuracy, with bootstrap 95% CIs over documents;
  - slices by language, document type and layout;
  - anomaly detection rate and false alarms on clean documents;
  - PII masking recall;
  - cost and latency.

**Measured baseline (regex extractor, seed 2026)**

| Layout | Critical-field accuracy |
|---|---|
| Forms | 100% |
| Free-text e-mails | 25% |

The free-text e-mails are the slice where an LLM has to justify its cost. The LLM run needs an API key and has not been recorded in this repository yet.

**Masking recall is 87–89%.** The misses are names of third parties (e.g. the other driver), which need NER (ADR 0012). The number is reported, not hidden.

**CI:** runs the baseline eval as a harness smoke test, and the gated LLM eval only on PRs that touch agents, the LLM layer or the document generator, when a key is configured.

**Not yet:** triage and summary evals; nightly variance runs.

## Why
- Structured outputs deserve structured metrics. Using an LLM judge where exact match works only adds noise.
- Gates turn "the prompt feels better" into a reviewable engineering change.
- Adversarial cases matter because claims documents are untrusted input.

## Consequences
- Eval runs use the L2 response cache (ADR 0005), so re-running unchanged cases is free.
- Thresholds are owned with the business: a misroute of a fraud case costs more than a typo in a summary, and the gates reflect that.

## Revisit when
Production override data shows the golden set no longer represents real traffic. Then re-sample it.
