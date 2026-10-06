import Link from "next/link";

import { Money } from "@/components/ui";
import { api, CoreApiError } from "@/lib/api";
import { PRODUCTS, type ProductCode } from "@/lib/catalog";
import { myPolicyIds } from "@/lib/portal";
import type { Policy } from "@/lib/types";

async function myPolicies(): Promise<Policy[]> {
  const ids = await myPolicyIds();
  const found = await Promise.all(
    ids.map((id) =>
      api.policy(id).catch((e) => {
        if (e instanceof CoreApiError && e.status === 404) return null; // e.g. demo DB was reset
        throw e;
      }),
    ),
  );
  return found.filter((p): p is Policy => p !== null);
}

export default async function PortalHome() {
  const policies = await myPolicies();
  return (
    <div className="space-y-10">
      <section className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Insurance that explains itself</h1>
        <p className="max-w-2xl text-slate-600">
          See exactly how your price is calculated, buy online in a minute, and report a claim with
          your documents. We read them straight away; a claims handler makes every decision.
        </p>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        {(Object.keys(PRODUCTS) as ProductCode[]).map((code) => (
          <div key={code} className="flex flex-col rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-lg font-semibold">{PRODUCTS[code].name}</h2>
            <p className="mt-1 flex-1 text-sm text-slate-600">{PRODUCTS[code].tagline}</p>
            <Link
              href={`/portal/quote?product=${code}`}
              className="mt-4 inline-flex w-fit rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700"
            >
              Get a quote
            </Link>
          </div>
        ))}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">My policies</h2>
        {policies.length === 0 ? (
          <p className="text-sm text-slate-500">No policies in this browser yet. Get a quote to start.</p>
        ) : (
          <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
            {policies.map((p) => (
              <li key={p.id}>
                <Link href={`/portal/policies/${p.id}`} className="flex items-center gap-4 px-5 py-4 hover:bg-teal-50/50">
                  <div className="flex-1">
                    <div className="font-medium">{PRODUCTS[p.product_code].name}</div>
                    <div className="font-mono text-xs text-slate-500">{p.number}</div>
                  </div>
                  <div className="text-right text-sm">
                    <Money value={p.gross_premium} /> / year
                    <div className="text-xs text-slate-500">
                      {p.start_date} – {p.end_date}
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
