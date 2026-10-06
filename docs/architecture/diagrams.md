# Architecture diagrams

All diagrams are Mermaid and render on GitHub. They describe the target architecture.
The [roadmap](../roadmap.md) shows which parts are already implemented.

## 1. System context

Who uses the platform and what it talks to.

```mermaid
flowchart LR
    customer([Customer<br/>SK / AT])
    handler([Claims handler])
    senior([Senior handler])
    auditor([Auditor / DPO])

    subgraph platform[Agentic Insurance Platform]
        portal[Customer portal]
        crm[Handler CRM]
        core[Core: policies · claims · billing]
        agents[Agent layer]
    end

    llm[(LLM provider<br/>Azure OpenAI EU)]
    ocr[(Azure Document<br/>Intelligence EU)]
    idp[(Entra ID)]
    bank[(Payment system)]

    customer --> portal
    handler --> crm
    senior --> crm
    auditor --> crm
    portal --> core
    crm --> core
    core --> agents
    agents --> llm
    agents --> ocr
    portal & crm --> idp
    core --> bank
```

## 2. Containers

Deployable units and backing services (ADR 0001, 0004, 0005, 0008).

```mermaid
flowchart TB
    subgraph web[Web]
        portal[Customer portal<br/>Next.js]
        crm[Handler CRM<br/>Next.js]
    end

    subgraph backend[Backend]
        core[Core API<br/>FastAPI · modular monolith<br/>party · product · tariff · policy · claims]
        workers[Agent workers<br/>Procrastinate · asyncio]
        mcp[MCP server<br/>policy · claims · docs · knowledge]
        gw[LLM gateway<br/>masking · routing · cache · cost]
    end

    subgraph data[Data]
        pg[(Postgres<br/>domain data · pgvector · job queue)]
        redis[(Redis<br/>cache only)]
        blob[(Blob storage<br/>documents)]
    end

    obs[Langfuse + App Insights]

    portal -->|REST| core
    crm -->|REST| core
    core -->|state change + job<br/>same transaction| pg
    workers -->|poll jobs| pg
    workers -->|MCP| mcp
    mcp -->|REST, service identity| core
    workers --> gw
    gw --> redis
    core --> redis
    workers --> blob
    core --> blob
    gw -.->|OTel| obs
    workers -.->|OTel| obs
    core -.->|OTel| obs
```

## 3. Claim lifecycle (state machine)

Implemented in `src/aip/core/claims/state_machine.py`. Edge labels show **who may perform the transition**.
No AGENT edge leads to `APPROVED`, `REJECTED` or `PAID`. A unit test enforces this invariant.

```mermaid
stateDiagram-v2
    [*] --> RECEIVED: customer / human / system
    RECEIVED --> EXTRACTED: agent / system
    EXTRACTED --> TRIAGED: agent / system
    TRIAGED --> COVERAGE_CHECKED: agent / system
    COVERAGE_CHECKED --> AWAITING_REVIEW: agent / system

    RECEIVED --> AWAITING_REVIEW: escalate (agent / system / human)
    EXTRACTED --> AWAITING_REVIEW: escalate
    TRIAGED --> AWAITING_REVIEW: escalate

    RECEIVED --> NEEDS_INFO: agent / human
    EXTRACTED --> NEEDS_INFO: agent / human
    TRIAGED --> NEEDS_INFO: agent / human
    COVERAGE_CHECKED --> NEEDS_INFO: agent / human
    AWAITING_REVIEW --> NEEDS_INFO: human
    NEEDS_INFO --> RECEIVED: customer / human / system

    AWAITING_REVIEW --> APPROVED: human only
    AWAITING_REVIEW --> REJECTED: human only
    APPROVED --> PAID: system (payment confirmed)
    PAID --> [*]
    REJECTED --> [*]
```

## 4. Claim processing sequence (target, phases 2–4)

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant P as Portal
    participant Core as Core API
    participant Q as Job queue (Postgres)
    participant W as Agent worker
    participant M as MCP server
    participant G as LLM gateway
    actor H as Handler (CRM)

    C->>P: Report claim + upload PDFs
    P->>Core: POST /claims
    Core->>Core: status=RECEIVED, audit event
    Core->>Q: enqueue extract(claim) [same tx]
    Q-->>W: job
    W->>M: get_document_text(doc)
    W->>G: extract(schema, masked text)
    G-->>W: fields + confidence (tokens)
    W->>M: update_claim_fields(draft)
    M->>Core: PATCH /claims/{id} + transition EXTRACTED
    Core->>Q: enqueue triage [same tx]
    Q-->>W: job
    W->>G: classify(peril, complexity, fraud signals)
    W->>M: transition TRIAGED (queue=...)
    Core->>Q: enqueue coverage
    Q-->>W: job
    W->>M: search_conditions(product, version, query)
    W->>M: get_policy_snapshot_at(event_date)
    W->>Core: POST /claims/{id}/coverage (deterministic engine)
    W->>M: transition COVERAGE_CHECKED → AWAITING_REVIEW + rationale
    H->>Core: open case: fields with source spans, coverage, rationale
    H->>Core: APPROVE (amount) / REJECT / NEEDS_INFO
    Core->>Core: audit event (actor=human)
```

## 5. Inside one agent step

ADR 0003: one bounded agent per state transition.

```mermaid
flowchart TD
    start([Job: claim, step]) --> load[Load claim + allowed tools<br/>for this agent]
    load --> loop{LLM call<br/>via gateway}
    loop -->|tool_use| allow{Tool in<br/>allow-list?<br/>server-side}
    allow -->|no| deny[Return error to model<br/>+ log security event]
    deny --> budget
    allow -->|yes| exec[Execute MCP tool]
    exec --> budget{Budget left?<br/>steps · tokens · time}
    budget -->|yes| loop
    budget -->|no| esc[Escalate:<br/>AWAITING_REVIEW]
    loop -->|final answer| val{Pydantic schema<br/>+ domain validators}
    val -->|invalid| retry{Retry once<br/>with errors}
    retry -->|still invalid| esc
    retry -->|ok| propose
    val -->|valid| propose[Propose transition<br/>+ rationale]
    propose --> done([Core applies transition<br/>if actor allowed])
```

## 6. Caching layers

ADR 0005.

```mermaid
flowchart LR
    agent[Agent] --> gw[LLM gateway]
    gw --> l2{L2 exact-match<br/>Redis<br/>key = task+prompt_v+model+masked input}
    l2 -->|hit| out[Masked output → re-identify<br/>with current claim mapping]
    l2 -->|miss| prov[Provider<br/>L1 prompt cache on static prefix]
    prov --> out
    doc[Uploaded file] --> h{L4 sha256<br/>seen?}
    h -->|yes| cached[Reuse OCR + embeddings]
    h -->|no| ocr[OCR + embed] --> cached
    mcp[MCP get_policy] --> l5{L5 Redis<br/>TTL 60 s<br/>evict on policy.changed}
    l5 -->|miss| core[Core API]
```

## 7. Data model (core)

Implemented in `src/aip/core/*/models.py`.

```mermaid
erDiagram
    PARTY ||--o{ POLICY : holds
    POLICY ||--o{ CLAIM : "has"
    CLAIM ||--o{ CLAIM_EVENT : "audit trail"

    PARTY {
        uuid id PK
        string kind "person | company"
        string first_name
        string last_name
        date birth_date
        string national_id "PII: rodné číslo"
        string email
        string country "SK | AT"
        string language "sk | de"
    }
    POLICY {
        uuid id PK
        string number UK
        string product_code "MOTOR_TPL | HOUSEHOLD"
        uuid holder_id FK
        string status "ACTIVE | CANCELLED | EXPIRED"
        date start_date
        date end_date
        string tariff_version
        string conditions_version
        json risk "risk factors used for pricing"
        decimal net_premium
        decimal tax
        decimal gross_premium
    }
    CLAIM {
        uuid id PK
        string number UK
        uuid policy_id FK
        string status
        string peril
        date event_date
        datetime reported_at
        decimal claimed_amount
        decimal payable_amount "from coverage engine"
        decimal approved_amount "set by human"
        json coverage "decision + reasons + clauses"
        int version "optimistic lock"
    }
    CLAIM_EVENT {
        uuid id PK
        uuid claim_id FK
        string from_status
        string to_status
        string actor_type "customer | human | agent | system"
        string actor_id
        string reason
        datetime at
    }
```

## 8. Deployment (Azure)

ADR 0009.

```mermaid
flowchart TB
    gh[GitHub Actions<br/>lint · tests · evals · build] -->|images| acr[(Container Registry)]
    tf[Terraform] -.provisions.-> rg

    subgraph rg[Resource group · West Europe]
        subgraph aca[Container Apps environment]
            core[core-api]
            workers[agent-workers<br/>KEDA: postgres scaler]
            mcp[mcp-server]
            portal[portal]
            crm[crm]
        end
        pg[(PostgreSQL Flexible Server<br/>pgvector · pg_trgm · unaccent)]
        redis[(Azure Managed Redis)]
        blob[(Blob Storage)]
        kv[(Key Vault)]
        aoai[(Azure OpenAI<br/>EU Data Zone)]
        di[(Document Intelligence)]
        ai[(App Insights)]
    end

    acr --> aca
    aca -->|managed identity| kv
    aca --> pg & redis & blob
    workers --> aoai & di
    aca -.-> ai
```
