import Link from "next/link";
import { notFound } from "next/navigation";

import { AgentTag, Badge, Card, DecisionBadge, Money, QueueBadge, StatusBadge } from "@/components/ui";
import { decide } from "@/lib/actions";
import { api, CoreApiError } from "@/lib/api";
import type { Claim, ExtractedDocument, Issue } from "@/lib/types";

import { ReviewForm } from "./review-form";

const RECOMMENDATION: Record<string, string> = {
  approve: "bg-emerald-100 text-emerald-800",
  reject: "bg-rose-100 text-rose-800",
  request_information: "bg-sky-100 text-sky-800",
  refer_senior: "bg-violet-100 text-violet-800",
};

const FIELDS: [keyof ExtractedDocument, string][] = [
  ["policy_number", "Policy number"],
  ["claimant_name", "Claimant"],
  ["event_date", "Event date"],
  ["total_amount", "Total"],
  ["iban", "IBAN"],
  ["document_number", "Document no."],
  ["vendor_name", "Vendor"],
  ["issue_date", "Issued"],
];

async function load(id: string) {
  try {
    const claim = await api.claim(id);
    const [policy, documents, events, runs, reviews] = await Promise.all([
      api.policy(claim.policy_id),
      api.documents(id),
      api.events(id),
      api.runs(id),
      api.reviews(id),
    ]);
    return { claim, policy, documents, events, runs, reviews };
  } catch (e) {
    if (e instanceof CoreApiError && (e.status === 404 || e.status === 422)) notFound();
    throw e;
  }
}

export default async function ClaimPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { id } = await params;
  const { notice, error } = await searchParams;
  const { claim, policy, documents, events, runs, reviews } = await load(id);
  const cost = runs.reduce((n, r) => n + Number(r.cost_usd), 0);
  const issues = claim.extraction?.documents.flatMap((d) => d.issues) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/claims" className="text-xs text-slate-500 hover:text-indigo-700">
            ← Review queue
          </Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-2 text-xl font-semibold">
            <span className="font-mono">{claim.number}</span>
            <StatusBadge status={claim.status} />
            <QueueBadge queue={claim.queue} />
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {claim.peril.replace(/_/g, " ").toLowerCase()} · event {claim.event_date} · reported{" "}
            {claim.reported_at.slice(0, 10)} via {claim.channel} · policy{" "}
            <span className="font-mono">{policy.number}</span> ({policy.product_code},{" "}
            {policy.start_date} – {policy.end_date})
          </p>
        </div>
        <div className="grid grid-cols-3 gap-6 text-right">
          <div>
            <div className="text-xs text-slate-500">Claimed</div>
            <div className="text-lg font-semibold"><Money value={claim.claimed_amount} /></div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Payable (engine)</div>
            <div className="text-lg font-semibold"><Money value={claim.payable_amount} /></div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Agent cost</div>
            <div className="text-lg font-semibold tabular-nums">${cost.toFixed(4)}</div>
          </div>
        </div>
      </div>

      {notice && (
        <div className="rounded-lg bg-emerald-50 px-4 py-2 text-sm text-emerald-800 ring-1 ring-emerald-200">{notice}</div>
      )}
      {error && (
        <div className="rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-800 ring-1 ring-rose-200">{error}</div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        {/* Left: the source document, so every extracted value can be checked against it. */}
        <div className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          {documents.map((d) => (
            <Card
              key={d.id}
              title={d.filename}
              aside={
                <a href={`/files/${d.id}`} target="_blank" className="text-xs text-indigo-700 hover:underline">
                  open ↗
                </a>
              }
            >
              <iframe src={`/files/${d.id}`} title={d.filename} className="h-[72vh] w-full rounded-md border border-slate-200" />
            </Card>
          ))}
          {documents.length === 0 && <Card title="Documents">No documents attached.</Card>}
        </div>

        <div className="space-y-4">
          <Brief claim={claim} reviews={reviews} />
          <CoverageCard claim={claim} />
          <ExtractionCard claim={claim} issues={issues} reviews={reviews} />
          <TriageCard claim={claim} reviews={reviews} />
          {claim.status === "AWAITING_REVIEW" && <DecisionPanel claim={claim} />}

          <Card title="Activity">
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Audit trail</h3>
            <ol className="space-y-1.5 text-sm">
              {events.map((e) => (
                <li key={e.seq} className="flex gap-3">
                  <span className="w-36 shrink-0 tabular-nums text-xs text-slate-500">
                    {e.at.replace("T", " ").slice(0, 16)}
                  </span>
                  <span className="w-40 shrink-0"><StatusBadge status={e.to_status} /></span>
                  <span className="text-xs">
                    <span className="font-mono">{e.actor_type}:{e.actor_id}</span>
                    {e.reason && <span className="text-slate-500"> — {e.reason}</span>}
                  </span>
                </li>
              ))}
            </ol>
            <h3 className="mt-5 mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Agent runs</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-left text-slate-500">
                  <tr>
                    <th className="pb-1 pr-3">Agent</th>
                    <th className="pb-1 pr-3">Model</th>
                    <th className="pb-1 pr-3 text-right">Turns</th>
                    <th className="pb-1 pr-3 text-right">Tools</th>
                    <th className="pb-1 pr-3 text-right">Tokens in / out</th>
                    <th className="pb-1 pr-3 text-right">Cost</th>
                    <th className="pb-1 pr-3 text-right">Latency</th>
                    <th className="pb-1 pr-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {runs.map((r) => (
                    <tr key={r.id}>
                      <td className="py-1 pr-3 font-mono">{r.agent}@{r.agent_version}</td>
                      <td className="py-1 pr-3 font-mono">{r.model}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{r.turns}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{r.tool_calls}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">
                        {r.input_tokens.toLocaleString()} / {r.output_tokens.toLocaleString()}
                      </td>
                      <td className="py-1 pr-3 text-right tabular-nums">${Number(r.cost_usd).toFixed(4)}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{(r.latency_ms / 1000).toFixed(1)} s</td>
                      <td className="py-1 pr-3">
                        {r.status === "ok" ? (
                          <span className="text-emerald-700">ok{r.cache_hit ? " (cache)" : ""}</span>
                        ) : (
                          <span className="text-rose-700" title={r.error ?? ""}>failed</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Brief({ claim, reviews }: { claim: Claim; reviews: Awaited<ReturnType<typeof api.reviews>> }) {
  const s = claim.summary;
  if (!s) return <Card title="Case brief">No brief yet — the pipeline has not run for this claim.</Card>;
  return (
    <Card
      title="Case brief"
      aside={
        <span className="flex items-center gap-2">
          <Badge className={RECOMMENDATION[s.recommendation] ?? ""}>
            agent recommends: {s.recommendation.replace(/_/g, " ")}
          </Badge>
          <AgentTag by={s._by} />
        </span>
      }
    >
      <p className="text-sm leading-relaxed">{s.summary_sk}</p>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">Key facts</h3>
          <ul className="list-disc space-y-0.5 pl-4 text-sm">
            {s.key_facts.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </div>
        <div>
          <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">Open questions</h3>
          {s.open_questions.length ? (
            <ul className="list-disc space-y-0.5 pl-4 text-sm">
              {s.open_questions.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">None.</p>
          )}
        </div>
      </div>
      <p className="mt-3 text-sm"><span className="font-medium">Why: </span>{s.recommendation_rationale}</p>
      <h3 className="mt-3 mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
        Draft reply to customer (not sent)
      </h3>
      <textarea readOnly defaultValue={s.draft_customer_message} rows={3} className="w-full rounded-md border border-slate-200 bg-slate-50 p-2 text-sm" />
      <ReviewForm claimId={claim.id} kind="summary" existing={reviews} />
    </Card>
  );
}

function CoverageCard({ claim }: { claim: Claim }) {
  const c = claim.coverage;
  return (
    <Card
      title="Coverage (deterministic engine)"
      aside={<DecisionBadge decision={c?.decision} />}
    >
      {!c ? (
        <p className="text-sm text-slate-500">Not evaluated yet.</p>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {c.reasons.map((r, i) => (
            <li key={i} className="flex flex-wrap items-baseline justify-between gap-2">
              <span>{r.message}</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">{r.clause}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-slate-500">
        Rule-based and reproducible. Agents explain this result; they cannot change it.
      </p>
    </Card>
  );
}

function IssueList({ issues }: { issues: Issue[] }) {
  if (!issues.length) return <p className="text-sm text-emerald-700">All validators passed.</p>;
  return (
    <ul className="space-y-1">
      {issues.map((i, n) => (
        <li
          key={n}
          className={`rounded-md px-2 py-1 text-sm ${
            i.severity === "error" ? "bg-rose-50 text-rose-800" : "bg-amber-50 text-amber-800"
          }`}
        >
          <span className="font-mono text-[11px] uppercase">{i.severity}</span> {i.message}
        </li>
      ))}
    </ul>
  );
}

function ExtractionCard({
  claim,
  issues,
  reviews,
}: {
  claim: Claim;
  issues: Issue[];
  reviews: Awaited<ReturnType<typeof api.reviews>>;
}) {
  const e = claim.extraction;
  if (!e) return <Card title="Extracted data">Not extracted yet.</Card>;
  const first = e.documents[0]?.data;
  return (
    <Card title="Extracted data" aside={<AgentTag by={e._by} />}>
      <IssueList issues={issues} />
      {e.documents.map((d) => {
        const evidence = Object.fromEntries(d.data.evidence.map((ev) => [ev.field, ev]));
        const flagged = new Set(d.issues.map((i) => i.field));
        return (
          <div key={d.document_id} className="mt-3">
            <div className="mb-1 text-xs text-slate-500">
              {d.filename} · {d.data.doc_type.replace(/_/g, " ")} · {d.data.language}
            </div>
            <table className="w-full text-sm">
              <tbody className="divide-y divide-slate-100">
                {FIELDS.map(([key, label]) => {
                  const ev = evidence[key];
                  const value = d.data[key] as string | null;
                  return (
                    <tr key={key} className={flagged.has(key) ? "bg-rose-50/60" : ""}>
                      <td className="w-32 py-1.5 pr-2 text-xs text-slate-500">{label}</td>
                      <td className="py-1.5 pr-2 font-mono text-xs">
                        {value ?? <span className="text-slate-400">—</span>}
                      </td>
                      <td className="py-1.5 text-xs text-slate-500">
                        {ev && (
                          <span title={`confidence: ${ev.confidence}`}>
                            “{ev.quote}”{" "}
                            <span className={ev.confidence === "high" ? "text-emerald-600" : ev.confidence === "low" ? "text-rose-600" : "text-amber-600"}>
                              ●
                            </span>
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {d.data.line_items.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-xs">
                {d.data.line_items.map((li, n) => (
                  <li key={n} className="flex justify-between border-b border-dotted border-slate-200">
                    <span>{li.description}</span>
                    <Money value={li.amount} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
      {first && (
        <ReviewForm
          claimId={claim.id}
          kind="extraction"
          existing={reviews}
          fields={FIELDS.slice(0, 5).map(([key, label]) => ({
            name: key,
            label,
            value: (first[key] as string | null) ?? null,
          }))}
        />
      )}
    </Card>
  );
}

function TriageCard({ claim, reviews }: { claim: Claim; reviews: Awaited<ReturnType<typeof api.reviews>> }) {
  const t = claim.triage;
  if (!t) return <Card title="Triage">Not triaged yet.</Card>;
  return (
    <Card title="Triage" aside={<AgentTag by={t._by} />}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-500">Agent proposed</span>
        <QueueBadge queue={t.proposed_queue} />
        <span className="text-slate-400">→ rules set</span>
        <QueueBadge queue={t.final_queue} />
        <span className="text-slate-500">· complexity {t.complexity}</span>
        {!t.peril_matches_reported && <Badge className="bg-amber-100 text-amber-800">peril differs from report</Badge>}
      </div>
      {t.routing_overrides.length > 0 && (
        <ul className="mt-2 list-disc pl-4 text-xs text-violet-700">
          {t.routing_overrides.map((o, i) => <li key={i}>{o}</li>)}
        </ul>
      )}
      <p className="mt-2 text-sm">{t.rationale}</p>
      <div className="mt-2 grid gap-3 sm:grid-cols-2">
        <div>
          <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">Fraud signals</h3>
          {t.fraud_signals.length ? (
            <ul className="list-disc pl-4 text-sm text-rose-800">
              {t.fraud_signals.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">None found.</p>
          )}
        </div>
        <div>
          <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">Missing information</h3>
          {t.missing_information.length ? (
            <ul className="list-disc pl-4 text-sm">
              {t.missing_information.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">None.</p>
          )}
        </div>
      </div>
      <ReviewForm
        claimId={claim.id}
        kind="triage"
        existing={reviews}
        fields={[
          {
            name: "queue",
            label: "Correct queue",
            value: t.final_queue,
            options: ["fast_track", "standard", "senior", "fraud_review"],
          },
        ]}
      />
    </Card>
  );
}

function DecisionPanel({ claim }: { claim: Claim }) {
  const notCovered = claim.coverage?.decision === "NOT_COVERED";
  return (
    <Card title="Your decision" className="ring-2 ring-indigo-100">
      <div className="grid gap-4 md:grid-cols-3">
        <form action={decide} className="space-y-2 rounded-lg bg-emerald-50/60 p-3">
          <input type="hidden" name="claimId" value={claim.id} />
          <input type="hidden" name="decision" value="APPROVED" />
          <label className="block text-xs text-slate-600">
            Approved amount (€)
            <input
              name="amount"
              defaultValue={claim.payable_amount ?? ""}
              className="mt-0.5 w-full rounded-md border border-slate-300 bg-white px-2 py-1 font-mono text-sm"
            />
          </label>
          <input name="reason" placeholder="Note (optional)" className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm" />
          <button className="w-full rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700">
            Approve
          </button>
          {notCovered && <p className="text-xs text-rose-700">Engine says NOT COVERED — approving overrides it.</p>}
        </form>
        <form action={decide} className="space-y-2 rounded-lg bg-sky-50/60 p-3">
          <input type="hidden" name="claimId" value={claim.id} />
          <input type="hidden" name="decision" value="NEEDS_INFO" />
          <textarea name="reason" required rows={3} placeholder="What do you need from the customer?" className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm" />
          <button className="w-full rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700">
            Request information
          </button>
        </form>
        <form action={decide} className="space-y-2 rounded-lg bg-rose-50/60 p-3">
          <input type="hidden" name="claimId" value={claim.id} />
          <input type="hidden" name="decision" value="REJECTED" />
          <textarea name="reason" required rows={3} placeholder="Reason, with the clause" className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm" />
          <button className="w-full rounded-md bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-700">
            Reject
          </button>
        </form>
      </div>
      <p className="mt-3 text-xs text-slate-500">
        Decisions are recorded in the audit trail under your name. Payment happens only after the
        payment system confirms (state PAID, system actor).
      </p>
    </Card>
  );
}
