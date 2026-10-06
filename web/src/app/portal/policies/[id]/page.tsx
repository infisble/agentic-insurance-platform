import Link from "next/link";
import { notFound } from "next/navigation";

import { Field, inputClass, Money, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { CUSTOMER_STATUS, perilLabel, PRODUCTS } from "@/lib/catalog";
import { ownsPolicy } from "@/lib/portal";
import { reportClaim } from "@/lib/portal-actions";

export default async function PolicyPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const { notice, error } = await searchParams;
  if (!(await ownsPolicy(id))) notFound();
  const [policy, claims] = await Promise.all([api.policy(id), api.policyClaims(id)]);
  const product = PRODUCTS[policy.product_code];
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-6">
      <div>
        <Link href="/portal" className="text-xs text-slate-500 hover:text-teal-700">
          ← My policies
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">{product.name}</h1>
        <p className="text-sm text-slate-500">
          Policy <span className="font-mono">{policy.number}</span> · {policy.status.toLowerCase()} ·{" "}
          {policy.start_date} – {policy.end_date} · <Money value={policy.gross_premium} /> / year ·
          conditions {policy.conditions_version}
        </p>
      </div>

      <Notice notice={notice} error={error} />

      <div className="grid gap-6 lg:grid-cols-5">
        <form
          action={reportClaim}
          className="space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 lg:col-span-3"
        >
          <h2 className="font-semibold">Report a claim</h2>
          <input type="hidden" name="policyId" value={policy.id} />
          <div className="grid grid-cols-2 gap-4">
            <Field label="What happened?">
              <select name="peril" className={inputClass}>
                {product.perils.map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="When?">
              <input
                name="event_date"
                type="date"
                required
                max={today}
                defaultValue={today}
                className={inputClass}
              />
            </Field>
          </div>
          <Field label="Amount you claim (€)">
            <input
              name="claimed_amount"
              type="number"
              min={0.01}
              step={0.01}
              required
              className={inputClass}
            />
          </Field>
          <Field label="Describe what happened">
            <textarea name="description" required rows={4} maxLength={5000} className={inputClass} />
          </Field>
          <Field label="Documents" hint="Invoice, repair estimate or police report. PDF or text, up to 20 MB.">
            <input
              name="file"
              type="file"
              multiple
              accept="application/pdf,text/plain"
              className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-teal-50 file:px-3 file:py-2 file:text-teal-700"
            />
          </Field>
          <button className="rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700">
            Submit claim
          </button>
        </form>

        <section className="space-y-3 lg:col-span-2">
          <h2 className="font-semibold">Claims on this policy</h2>
          {claims.length === 0 ? (
            <p className="text-sm text-slate-500">None so far.</p>
          ) : (
            <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
              {claims.map((c) => (
                <li key={c.id}>
                  <Link href={`/portal/claims/${c.id}`} className="block px-4 py-3 hover:bg-teal-50/50">
                    <div className="flex justify-between text-sm">
                      <span className="font-mono text-xs">{c.number}</span>
                      <span className="text-xs font-medium text-teal-700">
                        {CUSTOMER_STATUS[c.status]?.label ?? c.status}
                      </span>
                    </div>
                    <div className="text-xs text-slate-500">
                      {perilLabel(c.peril)} · {c.event_date} · <Money value={c.claimed_amount} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
