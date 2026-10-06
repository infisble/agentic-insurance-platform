# ADR 0013 — Frontend stack and authentication

## Context
Two web interfaces:
- **Customer portal:** quote, buy, report a claim, upload documents, chat with the Intake agent.
- **Handler CRM:** client 360 view, policies, claim queue, case view with agent suggestions (accept / edit / reject), source highlighting on documents.

Requirements:
- streaming chat,
- a PDF viewer with bounding-box highlights,
- role-based access.

## Options — frontend

| Option | Pros | Cons |
|---|---|---|
| A. Streamlit / Gradio | Fastest to build | Looks like a prototype; limited UX for a real CRM; weak authentication story |
| **B. Next.js (React) + Tailwind + shadcn/ui** | Production-grade UX; streaming; rich components (PDF.js, tables); one stack for both apps | More code than A |
| C. Angular | Common in enterprises | Slower to iterate for one developer |
| D. Low-code (Power Apps, Retool) | Quick internal tools | Hard to show engineering skill; licensing |

## Options — authentication

| Option | Pros | Cons |
|---|---|---|
| **A. Microsoft Entra ID (OIDC) for handlers, Entra External ID for customers** | Matches an enterprise Microsoft identity estate; managed MFA; roles as app roles | Azure-specific |
| B. Keycloak | Self-hosted, portable | Operating an IdP |
| C. Custom JWT | Simple | Security risk; not credible for an insurer |

## Decision
- **Frontend: Next.js** for both apps, in one monorepo with shared UI components.
- **Authentication: Entra ID**, with roles `handler`, `senior_handler` and `admin`.
- **Local development:** Keycloak in Docker Compose with the same OIDC contract, so no cloud tenant is needed for development.
- **Authorisation:** enforced in the core API, not in the UI. MCP servers run with a service identity and pass the acting user for audit.

## Implementation status (phase 3, part 1)
- **Handler CRM:** built in `web/` with Next.js 16 (App Router).
  - Server Components fetch from the core API.
  - Mutations are Server Actions that call the core API, so the UI cannot bypass the state machine; forms work without client JavaScript.
  - Pages: dashboard (queue sizes, agent cost, override rate per agent, most corrected fields), review queue, case view.
- **Case view:**
  - the source PDF sits next to the extracted fields with their evidence quotes;
  - validator issues are highlighted;
  - the deterministic coverage result is shown with clause references;
  - triage shows the queue the agent proposed next to the queue the rules set;
  - the case brief and draft reply;
  - accept / edit / reject feedback on every draft;
  - the decision panel;
  - audit trail and per-run token cost.
- **Customer portal** (`web/src/app/portal`, phase 3, part 2):
  - quote with the full premium breakdown from the core tariff engine (the portal never calculates a price);
  - buy (creates the party and issues the policy);
  - report a claim with documents; the upload puts the claim on the job queue (ADR 0004);
  - claim status in customer language (milestones, not internal states, no agent names or queues), refreshing itself while agents work;
  - answering a handler's information request, which sends the claim back through the agents.
- **Identity:** development stand-ins for now. Handlers pick a name stored in an httpOnly cookie; customers see only the policies bought in their browser (httpOnly cookie), and other claim ids return 404. Entra ID / Entra External ID (Keycloak locally) is next; the core API must then take the actor from the token, not from the request body.
- **Tests:** Playwright E2E for the handler journey and for the customer journey across both apps: quote → buy → claim → agents via the queue → handler requests information → customer answers → agents again (`web/e2e`).

## Why
- The CRM's value is in the review UX: highlighted source spans and one-click accept. That needs a real frontend.
- Identity is a solved problem. Using the enterprise IdP is the expected answer.

## Revisit when
The organisation has a mandated frontend framework or a design system to follow.
