import Link from "next/link";

import { Field, inputClass, Money, Notice } from "@/components/ui";
import { api, CoreApiError } from "@/lib/api";
import { DEDUCTIBLES, isProduct, PRODUCTS, REGIONS, type ProductCode } from "@/lib/catalog";
import { buyPolicy } from "@/lib/portal-actions";
import type { Premium } from "@/lib/types";

type Params = Record<string, string | string[] | undefined>;

const DEFAULTS: Record<ProductCode, Record<string, string>> = {
  MOTOR_TPL: { engine_kw: "85", holder_age: "35", region: "BA", bonus_malus_level: "0" },
  HOUSEHOLD: {
    sum_insured: "40000",
    property_type: "FLAT",
    region: "BA",
    flood_zone: "1",
    deductible: "100",
  },
};

function one(p: Params, key: string): string | undefined {
  const v = p[key];
  return typeof v === "string" ? v : undefined;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function riskFrom(product: ProductCode, v: Record<string, string>) {
  return product === "MOTOR_TPL"
    ? {
        product,
        engine_kw: Number(v.engine_kw),
        holder_age: Number(v.holder_age),
        region: v.region,
        bonus_malus_level: Number(v.bonus_malus_level),
      }
    : {
        product,
        sum_insured: v.sum_insured,
        property_type: v.property_type,
        region: v.region,
        flood_zone: Number(v.flood_zone),
        deductible: v.deductible,
      };
}

export default async function QuotePage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const requested = one(params, "product");
  const product: ProductCode = isProduct(requested) ? requested : "MOTOR_TPL";
  const values = Object.fromEntries(
    Object.entries(DEFAULTS[product]).map(([k, d]) => [k, one(params, k) ?? d]),
  );
  const startDate = one(params, "start_date") ?? today();
  const risk = riskFrom(product, values);

  // The price always comes from the core tariff engine; the portal never calculates it.
  let premium: Premium | null = null;
  let quoteError: string | null = null;
  if (one(params, "calc")) {
    try {
      premium = await api.quote({ risk, start_date: startDate });
    } catch (e) {
      if (!(e instanceof CoreApiError)) throw e;
      quoteError = e.status === 409 ? `This needs an underwriter: ${e.detail}` : e.detail;
    }
  }
  const quoteQuery = new URLSearchParams({
    product,
    ...values,
    start_date: startDate,
    calc: "1",
  }).toString();

  return (
    <div className="space-y-6">
      <div>
        <Link href="/portal" className="text-xs text-slate-500 hover:text-teal-700">
          ← My policies
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">Get a quote</h1>
      </div>

      <div className="flex flex-wrap gap-2">
        {(Object.keys(PRODUCTS) as ProductCode[]).map((code) => (
          <Link
            key={code}
            href={`/portal/quote?product=${code}`}
            className={`rounded-full px-4 py-1.5 text-sm ${
              code === product ? "bg-teal-600 text-white" : "bg-white ring-1 ring-slate-200 hover:bg-teal-50"
            }`}
          >
            {PRODUCTS[code].name}
          </Link>
        ))}
      </div>

      <Notice error={one(params, "error")} />

      <div className="grid gap-6 lg:grid-cols-2">
        <form className="space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <input type="hidden" name="product" value={product} />
          <input type="hidden" name="calc" value="1" />
          {product === "MOTOR_TPL" ? (
            <div className="grid grid-cols-2 gap-4">
              <Field label="Engine power (kW)">
                <input name="engine_kw" type="number" min={1} max={1000} required defaultValue={values.engine_kw} className={inputClass} />
              </Field>
              <Field label="Driver age">
                <input name="holder_age" type="number" min={18} max={110} required defaultValue={values.holder_age} className={inputClass} />
              </Field>
              <Field label="Bonus-malus level" hint="Claim-free years; negative after claims">
                <input name="bonus_malus_level" type="number" min={-3} max={10} required defaultValue={values.bonus_malus_level} className={inputClass} />
              </Field>
              <RegionSelect value={values.region} />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              <Field label="Sum insured (€)" hint="5 000 – 500 000 online">
                <input name="sum_insured" type="number" min={5000} step={100} required defaultValue={values.sum_insured} className={inputClass} />
              </Field>
              <Field label="Property">
                <select name="property_type" defaultValue={values.property_type} className={inputClass}>
                  <option value="FLAT">Flat</option>
                  <option value="HOUSE">House</option>
                </select>
              </Field>
              <RegionSelect value={values.region} />
              <Field label="Flood zone" hint="Zone 4: flood is excluded">
                <select name="flood_zone" defaultValue={values.flood_zone} className={inputClass}>
                  {[1, 2, 3, 4].map((z) => (
                    <option key={z}>{z}</option>
                  ))}
                </select>
              </Field>
              <Field label="Deductible (€)">
                <select name="deductible" defaultValue={values.deductible} className={inputClass}>
                  {DEDUCTIBLES.map((d) => (
                    <option key={d}>{d}</option>
                  ))}
                </select>
              </Field>
            </div>
          )}
          <Field label="Start date">
            <input name="start_date" type="date" required defaultValue={startDate} className={inputClass} />
          </Field>
          <button className="rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700">
            Calculate price
          </button>
        </form>

        <div className="space-y-4">
          {quoteError && <Notice error={quoteError} />}
          {premium ? (
            <>
              <PremiumCard premium={premium} />
              <BuyForm risk={JSON.stringify(risk)} startDate={startDate} quoteQuery={quoteQuery} />
            </>
          ) : (
            !quoteError && (
              <div className="rounded-2xl border border-dashed border-slate-300 p-6 text-sm text-slate-500">
                Fill in the details and calculate. You will see every factor that makes up the price.
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}

function RegionSelect({ value }: { value: string }) {
  return (
    <Field label="Region">
      <select name="region" defaultValue={value} className={inputClass}>
        {REGIONS.map(([code, name]) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
    </Field>
  );
}

function PremiumCard({ premium }: { premium: Premium }) {
  return (
    <section aria-label="Your price" className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">Your price</h2>
        <span className="text-2xl font-semibold text-teal-700">
          <Money value={premium.gross_premium} />
          <span className="text-sm font-normal text-slate-500"> / year</span>
        </span>
      </div>
      <table className="mt-4 w-full text-sm">
        <tbody className="divide-y divide-slate-100">
          <tr>
            <td className="py-1.5">Base premium</td>
            <td className="py-1.5 text-right">
              <Money value={premium.base} />
            </td>
          </tr>
          {premium.factors.map((f) => (
            <tr key={f.name}>
              <td className="py-1.5 text-slate-600">{f.explanation}</td>
              <td className="py-1.5 text-right tabular-nums">× {Number(f.value).toFixed(2)}</td>
            </tr>
          ))}
          <tr>
            <td className="py-1.5">Net premium</td>
            <td className="py-1.5 text-right">
              <Money value={premium.net_premium} />
            </td>
          </tr>
          <tr>
            <td className="py-1.5">Insurance tax</td>
            <td className="py-1.5 text-right">
              <Money value={premium.tax} />
            </td>
          </tr>
        </tbody>
      </table>
      <p className="mt-3 text-xs text-slate-400">Tariff {premium.tariff_version}</p>
    </section>
  );
}

function BuyForm({ risk, startDate, quoteQuery }: { risk: string; startDate: string; quoteQuery: string }) {
  return (
    <form action={buyPolicy} className="space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
      <h2 className="font-semibold">Buy this policy</h2>
      <input type="hidden" name="risk" value={risk} />
      <input type="hidden" name="start_date" value={startDate} />
      <input type="hidden" name="quote" value={quoteQuery} />
      <div className="grid grid-cols-2 gap-4">
        <Field label="First name">
          <input name="first_name" required autoComplete="given-name" className={inputClass} />
        </Field>
        <Field label="Last name">
          <input name="last_name" required autoComplete="family-name" className={inputClass} />
        </Field>
        <Field label="Date of birth">
          <input name="birth_date" type="date" autoComplete="bday" className={inputClass} />
        </Field>
        <Field label="E-mail">
          <input name="email" type="email" required autoComplete="email" className={inputClass} />
        </Field>
        <Field label="City">
          <input name="city" autoComplete="address-level2" className={inputClass} />
        </Field>
        <Field label="Country">
          <select name="country" defaultValue="SK" className={inputClass}>
            <option value="SK">Slovakia</option>
            <option value="AT">Austria</option>
          </select>
        </Field>
      </div>
      <Field label="Correspondence language">
        <select name="language" defaultValue="sk" className={inputClass}>
          <option value="sk">Slovak</option>
          <option value="de">German</option>
        </select>
      </Field>
      <button className="w-full rounded-lg bg-teal-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-teal-700">
        Buy policy
      </button>
    </form>
  );
}
