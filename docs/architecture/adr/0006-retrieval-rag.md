# ADR 0006 — Retrieval / RAG for policy conditions

## Context
The Coverage agent must answer "is this event covered under this policy?" and **cite the exact clause** of the general insurance conditions (VPP / AVB).

The corpus:
- is small: tens of PDFs, thousands of clauses;
- is versioned: a policy is bound to the conditions version valid at inception;
- is written in Slovak and German.

## Options

| Option | Pros | Cons |
|---|---|---|
| **A. Postgres + pgvector (+ full-text search)** | Same DB as the core; filter by product and version in SQL; one backup and one residency story | Vector index tuning is on us; fine at this corpus size |
| B. Azure AI Search | Managed hybrid search, semantic ranker | Separate service and cost; data duplicated outside the core DB |
| C. Qdrant / Weaviate | Strong vector features | Extra component without benefit at this size |
| D. Pinecone | Fully managed | US-centric SaaS; residency and procurement friction |
| E. Long-context only (put the whole conditions PDF into the prompt) | No retrieval errors | Cost per call; weaker citations; does not scale across products |
| F. Elasticsearch / OpenSearch | Best-in-class BM25 and analyzers; kNN; hybrid queries | Separate JVM cluster to operate; data duplicated outside the core DB; the version and product filtering we need is equally easy in SQL |

## Decision
**Option A** with **hybrid retrieval**:
- **Search:** Postgres full-text search plus vector similarity, fused with reciprocal rank fusion.
- **Hard filter:** `product_id` and `conditions_version`, so the agent can only see the conditions that legally apply to this policy.
- **Chunking by legal structure** (article → paragraph → letter), not by token count. Each chunk keeps its clause ID for citation.
- **Abstention:** the agent must cite at least one retrieved clause or return `insufficient_information`. An answer without a citation fails validation.

### Language handling in full-text search
- **German:** Postgres ships a built-in `german` Snowball configuration, which we use.
- **Slovak:** there is **no built-in Slovak configuration**, and managed Postgres (Azure Flexible Server) does not allow installing custom Hunspell dictionary files. So:
  - **Lemmatisation in the application:** Slovak text is lemmatised with a Slovak NLP model (e.g. Stanza `sk`) at index time **and** at query time, and stored in a separate `tsvector` built with the `simple` configuration plus `unaccent`.
  - **Fuzzy matching:** `pg_trgm` trigram similarity catches typos and inflected forms the lemmatiser misses.
- Lexical recall on Slovak queries is tracked separately in the eval set (ADR 0011).

## Why
- **Correctness over cleverness.** Version filtering is a legal requirement, and SQL does it trivially.
- At this size, a dedicated vector DB adds operations without improving recall.
- Hybrid search matters because users and documents use exact terms ("spoluúčasť", "Selbstbehalt") that pure embeddings blur.

## Consequences
- Retrieval quality is evaluated separately from answer quality (recall@k on a labelled question set, ADR 0011).
- Option E (long context) is kept as a baseline in the evals to prove retrieval is worth its complexity.

## Revisit when
- The corpus grows to tens of thousands of documents,
- semantic ranking (B) shows a measurable recall gain on the eval set, or
- the organisation already operates Elasticsearch/OpenSearch with Slovak analyzers. Reusing it (F) then beats our app-side lemmatisation.
