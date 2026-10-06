# Web: Claims Workbench and customer portal

One Next.js 16 app with two faces:

- **Claims Workbench** (`/`): the CRM for claims handlers. It has the review queue and the case view, with the source PDF next to what the agents extracted. Handlers give accept/edit/reject feedback on every agent draft and make the decision (approve / request information / reject). Every handler verdict feeds the agent quality metrics on the dashboard (override rate, most corrected fields), next to the job queue status.
- **Customer portal** (`/portal`): get a quote with the full premium breakdown, buy a policy, and report a claim with documents. The claim status page follows the claim while the agents work on it, and lets the customer answer a handler's information request.

Server Components fetch from the core API; mutations are Server Actions that call the core API,
so handlers are bound by the same state machine and validation rules as agents.

```bash
# terminal 1: core API with demo data (fresh DB, mock claims, offline agents) + queue worker
python -m aip.demo                 # from the repository root

# terminal 2
cd web
npm install
npm run dev                        # http://localhost:3000 (CRM), /portal (customer portal)
```

`CORE_API_URL` (default `http://localhost:8000`) points the app at the core API.

## E2E tests

```bash
npx playwright install chromium    # once
npx playwright test                # starts its own core API (:8100) and app (:3100)
```

Screenshots of the main screens are written to `e2e/screenshots/`.

Identity is a development stand-in (handler picker in the header). Production uses Entra ID
(ADR 0013), and the core API derives the actor from the token.
