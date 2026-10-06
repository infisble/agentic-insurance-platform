import Link from "next/link";

import { Card, QueueBadge, Stat, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";

const QUEUES = ["fraud_review", "senior", "standard", "fast_track"];

function pct(v: number | null) {
  return v === null ? "–" : `${Math.round(v * 100)} %`;
}

export default async function Dashboard() {
  const [o, jobs] = await Promise.all([api.overview(), api.jobStats()]);
  const awaiting = o.claims_by_status["AWAITING_REVIEW"] ?? 0;
  const reviewed = o.agents.reduce((n, a) => n + a.reviewed, 0);
  const overridden = o.agents.reduce((n, a) => n + a.edited + a.rejected, 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-sm text-slate-500">
          Agents propose, handlers decide. Every accept, edit or reject below is a quality signal
          for the agents.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Awaiting review" value={awaiting} hint="claims prepared by agents" />
        <Stat
          label="Override rate"
          value={pct(reviewed ? overridden / reviewed : null)}
          hint={`${reviewed} agent drafts reviewed by handlers`}
        />
        <Stat
          label="Agent cost"
          value={`$${Number(o.total_agent_cost_usd).toFixed(4)}`}
          hint="all runs, list prices"
        />
        <Stat
          label="Agent failures"
          value={o.agents.reduce((n, a) => n + a.failed, 0)}
          hint="escalated to a human"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Review queue" className="lg:col-span-1">
          <ul className="divide-y divide-slate-100">
            {QUEUES.map((q) => (
              <li key={q}>
                <Link
                  href={`/claims?queue=${q}`}
                  className="flex items-center justify-between py-2 hover:text-indigo-700"
                >
                  <QueueBadge queue={q} />
                  <span className="tabular-nums font-medium">{o.review_queue[q] ?? 0}</span>
                </Link>
              </li>
            ))}
          </ul>
          <h3 className="mt-4 mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Agent job queue
          </h3>
          <p className="text-sm tabular-nums text-slate-700">
            {jobs.queued} queued · {jobs.running} running · {jobs.done} done ·{" "}
            <span className={jobs.dead ? "font-medium text-rose-700" : ""}>{jobs.dead} dead</span>
          </p>
          <h3 className="mt-4 mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Claims by status
          </h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(o.claims_by_status).map(([s, n]) => (
              <span key={s} className="flex items-center gap-1 text-sm">
                <StatusBadge status={s} /> <span className="tabular-nums">{n}</span>
              </span>
            ))}
          </div>
        </Card>

        <Card title="Agent quality and cost" className="lg:col-span-2">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="pb-2">Agent</th>
                  <th className="pb-2 text-right">Runs</th>
                  <th className="pb-2 text-right">Failed</th>
                  <th className="pb-2 text-right">Avg cost</th>
                  <th className="pb-2 text-right">Avg latency</th>
                  <th className="pb-2 text-right">Reviewed</th>
                  <th className="pb-2 text-right">Accept / Edit / Reject</th>
                  <th className="pb-2 text-right">Override rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {o.agents.map((a) => (
                  <tr key={a.agent}>
                    <td className="py-2 font-mono text-xs">{a.agent}</td>
                    <td className="py-2 text-right tabular-nums">{a.runs}</td>
                    <td className="py-2 text-right tabular-nums">{a.failed}</td>
                    <td className="py-2 text-right tabular-nums">${Number(a.avg_cost_usd).toFixed(4)}</td>
                    <td className="py-2 text-right tabular-nums">{(a.avg_latency_ms / 1000).toFixed(1)} s</td>
                    <td className="py-2 text-right tabular-nums">{a.reviewed}</td>
                    <td className="py-2 text-right tabular-nums">
                      {a.accepted} / {a.edited} / {a.rejected}
                    </td>
                    <td className="py-2 text-right font-medium tabular-nums">{pct(a.override_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 className="mt-5 mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Fields handlers correct most (extraction)
          </h3>
          {o.most_corrected_fields.length === 0 ? (
            <p className="text-sm text-slate-500">No corrections yet.</p>
          ) : (
            <ul className="flex flex-wrap gap-2 text-sm">
              {o.most_corrected_fields.map(([f, n]) => (
                <li key={f} className="rounded-md bg-slate-100 px-2 py-1 font-mono text-xs">
                  {f} × {n}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 text-xs text-slate-500">
            Corrected cases are candidates for the golden dataset (ADR 0011): the eval set grows from
            real misses.
          </p>
        </Card>
      </div>
    </div>
  );
}
