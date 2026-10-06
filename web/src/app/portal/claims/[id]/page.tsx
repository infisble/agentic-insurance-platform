import Link from "next/link";
import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/portal";
import { Field, inputClass, Money, Notice } from "@/components/ui";
import { api, CoreApiError } from "@/lib/api";
import { CUSTOMER_STATUS, perilLabel, PROCESSING } from "@/lib/catalog";
import { ownsPolicy } from "@/lib/portal";
import { addDocuments } from "@/lib/portal-actions";
import type { ClaimEvent } from "@/lib/types";

// The customer sees milestones, not the internal pipeline: no queues, agent names or drafts.
const STEPS = [
  ["Submitted", ["RECEIVED"]],
  ["Documents checked", ["EXTRACTED", "TRIAGED", "COVERAGE_CHECKED"]],
  ["Handler review", ["AWAITING_REVIEW", "NEEDS_INFO"]],
  ["Decision", ["APPROVED", "REJECTED", "PAID"]],
] as const;

function stepIndex(status: string): number {
  return STEPS.findIndex(([, statuses]) => (statuses as readonly string[]).includes(status));
}

function lastReason(events: ClaimEvent[], status: string): string | null {
  return [...events].reverse().find((e) => e.to_status === status)?.reason ?? null;
}

function label(e: ClaimEvent): string {
  return CUSTOMER_STATUS[e.to_status]?.label ?? e.to_status;
}

async function load(id: string) {
  try {
    const claim = await api.claim(id);
    if (!(await ownsPolicy(claim.policy_id))) notFound();
    const [documents, events] = await Promise.all([api.documents(id), api.events(id)]);
    return { claim, documents, events };
  } catch (e) {
    if (e instanceof CoreApiError && (e.status === 404 || e.status === 422)) notFound();
    throw e;
  }
}

export default async function CustomerClaimPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const { notice, error } = await searchParams;
  const { claim, documents, events } = await load(id);
  const status = CUSTOMER_STATUS[claim.status] ?? { label: claim.status, text: "" };
  const current = stepIndex(claim.status);
  const canUpload = claim.status === "RECEIVED" || claim.status === "NEEDS_INFO";

  return (
    <div className="space-y-6">
      {PROCESSING.has(claim.status) && <AutoRefresh />}
      <div>
        <Link href={`/portal/policies/${claim.policy_id}`} className="text-xs text-slate-500 hover:text-teal-700">
          ← Policy
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">
          Claim <span className="font-mono">{claim.number}</span>
        </h1>
        <p className="text-sm text-slate-500">
          {perilLabel(claim.peril)} · {claim.event_date} · claimed <Money value={claim.claimed_amount} />
        </p>
      </div>

      <Notice notice={notice} error={error} />

      <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
        <div className="flex items-baseline justify-between gap-4">
          <h2 data-testid="claim-status" className="text-lg font-semibold text-teal-700">
            {status.label}
          </h2>
          {PROCESSING.has(claim.status) && <span className="text-xs text-slate-400">updating…</span>}
        </div>
        <p className="mt-1 text-sm text-slate-600">{status.text}</p>
        <ol className="mt-5 grid grid-cols-4 gap-2 text-xs">
          {STEPS.map(([label], i) => (
            <li key={label} className="space-y-1.5">
              <div className={`h-1.5 rounded-full ${i <= current ? "bg-teal-500" : "bg-slate-200"}`} />
              <div className={i <= current ? "font-medium text-slate-800" : "text-slate-400"}>{label}</div>
            </li>
          ))}
        </ol>
        {claim.status === "NEEDS_INFO" && (
          <p className="mt-4 rounded-lg bg-sky-50 p-3 text-sm text-sky-900">
            <span className="font-medium">What we need: </span>
            {lastReason(events, "NEEDS_INFO")}
          </p>
        )}
        {claim.status === "REJECTED" && (
          <p className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-900">{lastReason(events, "REJECTED")}</p>
        )}
        {(claim.status === "APPROVED" || claim.status === "PAID") && (
          <p className="mt-4 text-sm">
            Approved amount: <Money value={claim.approved_amount} />
          </p>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <h2 className="font-semibold">Your documents</h2>
          {documents.length === 0 ? (
            <p className="text-sm text-slate-500">No documents yet.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {documents.map((d) => (
                <li key={d.id}>
                  <a href={`/files/${d.id}`} target="_blank" className="text-teal-700 hover:underline">
                    {d.filename}
                  </a>
                </li>
              ))}
            </ul>
          )}
          {canUpload && (
            <form action={addDocuments} className="space-y-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
              <input type="hidden" name="claimId" value={claim.id} />
              <Field label={claim.status === "NEEDS_INFO" ? "Send the requested documents" : "Add documents"}>
                <input
                  name="file"
                  type="file"
                  multiple
                  required
                  accept="application/pdf,text/plain"
                  className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-teal-50 file:px-3 file:py-2 file:text-teal-700"
                />
              </Field>
              {claim.status === "NEEDS_INFO" && (
                <Field label="Message (optional)">
                  <input name="comment" maxLength={500} className={inputClass} />
                </Field>
              )}
              <button className="rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700">
                Upload
              </button>
            </form>
          )}
        </section>

        <section className="space-y-3">
          <h2 className="font-semibold">History</h2>
          <ol className="space-y-2 text-sm">
            {events
              .filter((e, i) => i === 0 || label(e) !== label(events[i - 1]))
              .map((e) => (
              <li key={e.seq} className="flex gap-3">
                <span className="w-32 shrink-0 tabular-nums text-xs text-slate-400">
                  {e.at.slice(0, 16).replace("T", " ")}
                </span>
                <span>{label(e)}</span>
              </li>
              ))}
          </ol>
        </section>
      </div>
    </div>
  );
}
