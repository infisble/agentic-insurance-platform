# ADR 0012 — PII handling and model governance

## Context
Claims contain:
- names, birth numbers (rodné číslo), addresses, IBANs, licence plates;
- health data (special category, GDPR Art. 9).

Regulatory frame:
- GDPR,
- the EU AI Act (insurance pricing for life and health is high-risk; claims support needs transparency and human oversight),
- DORA (ICT third-party risk).

## Options

| Option | Pros | Cons |
|---|---|---|
| A. Send raw documents to the model under the provider DPA | Best model accuracy | Maximum exposure; every log and cache becomes sensitive |
| **B. Pseudonymise before the model, re-identify after** | Model sees tokens, not direct identifiers; much smaller exposure in logs, caches and at the provider | Some accuracy cost; mapping store must be protected; pseudonymised data **is still personal data** under GDPR (Recital 26), so all GDPR obligations still apply downstream |
| C. Only self-hosted models | No third-party transfer | See ADR 0002 option D |

## Decision
**Option B.** Masking happens inside the LLM gateway:
- **Detection:** Microsoft Presidio as the framework, with:
  - **Pattern recognisers** with checksums for structured identifiers: rodné číslo, Austrian SVNR, IBAN, licence plates, policy numbers.
  - **Name, address and organisation NER:** German uses spaCy `de_core_news_lg`. **Slovak has no official spaCy pipeline**, so a multilingual transformer NER model (XLM-RoBERTa-based, fine-tuned for NER) is plugged into Presidio. Its recall on Slovak is measured, not assumed.
  - **Health data:** medical reports are not "anonymised" by removing names. The diagnosis itself is Art. 9 data, so medical documents are processed only on the EU, no-retention route regardless of masking.
- **Replacement:** each detected value becomes a consistent token (`<PERSON_1>`, `<IBAN_1>`).
- **Mapping store:** the token↔value mapping lives only in the core DB, per claim, encrypted.
- **Re-identification:** happens after validation, inside the core.
- **Extraction exception:** when a field's value *is* PII (e.g., IBAN), the model returns the token and the core resolves it. The model never needs to see the real value.

**Governance controls**

| Control | Rule |
|---|---|
| Model register | Every task has a recorded model, prompt version, owner, eval scores and intended use |
| No automated adverse decisions | Agents cannot reject or settle a claim. A human or an explicit rule does, with the agent's rationale shown |
| Transparency | Every AI-suggested field is marked in the CRM with its source span and confidence |
| Retention | Raw documents follow claims retention. LLM traces store masked content only, kept 90 days. Caches are tagged for erasure |
| Provider terms | EU processing, no training on inputs, zero or limited retention configured (ADR 0002) |
| Prompt injection | Document text is passed as data inside delimiters. Agents have least-privilege tools (ADR 0008). Adversarial evals run in CI (ADR 0011) |

## Implementation status (phase 2)
- **Done:** pseudonymisation in `src/aip/llm/masking.py`:
  - known values of the policyholder from the core (names, rodné číslo, e-mail, phone, street);
  - checksum-validated patterns (rodné číslo mod 11, IBAN mod 97), e-mail, phone, licence plate;
  - consistent tokens per case;
  - unmasking of tool arguments and final outputs.
- **PII leak tests:** a test asserts that the holder's name and rodné číslo never appear in any request sent to the model.
- **Measured gap:** masking recall is ~88% on the golden set. The misses are third-party names. Presidio with a multilingual NER model is still to do.
- **Data minimisation:** MCP tool results omit party PII, and the party API does not return `national_id`.

## Why
- Pseudonymisation reduces exposure in every downstream system (traces, caches, eval datasets) at a small accuracy cost, which is measured in the evals.
- It is a risk-reduction measure, **not** anonymisation. Retention, erasure and access controls still apply to all of those systems.
- Human oversight on adverse decisions is both a regulatory expectation and good product design for handlers.

## Consequences
- Masking recall is itself evaluated: a missed rodné číslo is a defect with its own test set.
- Data protection impact assessment (DPIA) notes are kept in `docs/governance/` alongside the code.

## Revisit when
Legal or the DPO approves a different processing basis, or a model task cannot reach the gate under masking. That would be escalated as a documented exception, not silently bypassed.
