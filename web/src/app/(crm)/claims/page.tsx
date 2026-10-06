import Link from "next/link";

import { DecisionBadge, Money, QueueBadge, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";

const QUEUE_ORDER: Record<string, number> = { fraud_review: 0, senior: 1, standard: 2, fast_track: 3 };
const QUEUES = ["all", "fraud_review", "senior", "standard", "fast_track"];

export default async function ClaimsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const status = typeof params.status === "string" ? params.status : "AWAITING_REVIEW";
  const queue = typeof params.queue === "string" ? params.queue : "all";

  let claims = await api.claims(status === "all" ? undefined : status);
  if (queue !== "all") claims = claims.filter((c) => c.queue === queue);
  claims.sort(
    (a, b) =>
      (QUEUE_ORDER[a.queue ?? ""] ?? 9) - (QUEUE_ORDER[b.queue ?? ""] ?? 9) ||
      a.reported_at.localeCompare(b.reported_at),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">
            {status === "all" ? "All claims" : "Review queue"}
          </h1>
          <p className="text-sm text-slate-500">
            {claims.length} claims · sorted by queue priority, oldest first
          </p>
        </div>
        <div className="flex flex-wrap gap-1 text-sm">
          {QUEUES.map((q) => (
            <Link
              key={q}
              href={`/claims?status=${status}&queue=${q}`}
              className={`rounded-md px-3 py-1.5 ${
                q === queue ? "bg-indigo-600 text-white" : "bg-white ring-1 ring-slate-200 hover:bg-slate-100"
              }`}
            >
              {q.replace(/_/g, " ")}
            </Link>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Claim</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Queue</th>
              <th className="px-4 py-3">Peril</th>
              <th className="px-4 py-3">Event</th>
              <th className="px-4 py-3 text-right">Claimed</th>
              <th className="px-4 py-3 text-right">Payable</th>
              <th className="px-4 py-3">Coverage</th>
              <th className="px-4 py-3">Agent recommends</th>
              <th className="px-4 py-3 text-right">Issues</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {claims.map((c) => {
              const issues = c.extraction?.documents.flatMap((d) => d.issues) ?? [];
              const errors = issues.filter((i) => i.severity === "error").length;
              return (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5">
                    <Link href={`/claims/${c.id}`} className="font-mono text-xs font-medium text-indigo-700 hover:underline">
                      {c.number}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5"><StatusBadge status={c.status} /></td>
                  <td className="px-4 py-2.5"><QueueBadge queue={c.queue} /></td>
                  <td className="px-4 py-2.5 text-xs">{c.peril.replace(/_/g, " ").toLowerCase()}</td>
                  <td className="px-4 py-2.5 tabular-nums text-xs">{c.event_date}</td>
                  <td className="px-4 py-2.5 text-right"><Money value={c.claimed_amount} /></td>
                  <td className="px-4 py-2.5 text-right"><Money value={c.payable_amount} /></td>
                  <td className="px-4 py-2.5"><DecisionBadge decision={c.coverage?.decision} /></td>
                  <td className="px-4 py-2.5 text-xs">{c.summary?.recommendation?.replace(/_/g, " ") ?? "–"}</td>
                  <td className="px-4 py-2.5 text-right text-xs tabular-nums">
                    {issues.length === 0 ? (
                      <span className="text-slate-400">0</span>
                    ) : (
                      <span className={errors ? "font-medium text-rose-700" : "text-amber-700"}>
                        {issues.length}
                        {errors ? ` (${errors} err)` : ""}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
            {claims.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-10 text-center text-slate-500">
                  Nothing here. Run the pipeline: <code>python -m aip.agents process --all</code>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
