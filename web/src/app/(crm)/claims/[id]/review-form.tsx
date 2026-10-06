import { review } from "@/lib/actions";
import type { Review } from "@/lib/types";

// Handler feedback on one agent draft. Changing a prefilled field turns "accept" into an
// edit with per-field corrections (computed in the server action).
export function ReviewForm({
  claimId,
  kind,
  fields = [],
  existing,
}: {
  claimId: string;
  kind: "extraction" | "triage" | "summary";
  fields?: { name: string; label: string; value: string | null; options?: string[] }[];
  existing: Review[];
}) {
  const last = existing.filter((r) => r.kind === kind).at(-1);
  return (
    <details className="group mt-4 rounded-lg border border-dashed border-slate-300 bg-slate-50/60">
      <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-sm">
        <span className="font-medium text-slate-700">Your feedback on this draft</span>
        {last ? (
          <span className="text-xs text-slate-500">
            last: <b>{last.verdict}</b> by {last.reviewer}
          </span>
        ) : (
          <span className="text-xs text-indigo-600 group-open:hidden">open</span>
        )}
      </summary>
      <form action={review} className="space-y-3 border-t border-slate-200 p-3">
        <input type="hidden" name="claimId" value={claimId} />
        <input type="hidden" name="kind" value={kind} />
        {fields.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-2">
            {fields.map((f) => (
              <label key={f.name} className="text-xs text-slate-600">
                {f.label}
                <input type="hidden" name={`orig:${f.name}`} value={f.value ?? ""} />
                {f.options ? (
                  <select
                    name={`field:${f.name}`}
                    defaultValue={f.value ?? ""}
                    className="mt-0.5 w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
                  >
                    {f.options.map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    name={`field:${f.name}`}
                    defaultValue={f.value ?? ""}
                    className="mt-0.5 w-full rounded-md border border-slate-300 bg-white px-2 py-1 font-mono text-sm"
                  />
                )}
              </label>
            ))}
          </div>
        )}
        <textarea
          name="comment"
          rows={2}
          placeholder="What was wrong? (required for reject)"
          className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
        />
        <div className="flex flex-wrap gap-2">
          <button
            name="verdict"
            value="accept"
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
          >
            {fields.length ? "Accept / save corrections" : "Accept"}
          </button>
          <button
            name="verdict"
            value="reject"
            className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-rose-700 ring-1 ring-rose-200 hover:bg-rose-50"
          >
            Reject draft
          </button>
        </div>
      </form>
    </details>
  );
}
