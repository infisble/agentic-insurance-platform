import type { ReactNode } from "react";

const STATUS_STYLE: Record<string, string> = {
  RECEIVED: "bg-slate-100 text-slate-700",
  EXTRACTED: "bg-slate-100 text-slate-700",
  TRIAGED: "bg-slate-100 text-slate-700",
  COVERAGE_CHECKED: "bg-slate-100 text-slate-700",
  AWAITING_REVIEW: "bg-amber-100 text-amber-800",
  NEEDS_INFO: "bg-sky-100 text-sky-800",
  APPROVED: "bg-emerald-100 text-emerald-800",
  PAID: "bg-emerald-200 text-emerald-900",
  REJECTED: "bg-rose-100 text-rose-800",
};

const QUEUE_STYLE: Record<string, string> = {
  fast_track: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  standard: "bg-slate-50 text-slate-700 ring-slate-200",
  senior: "bg-violet-50 text-violet-700 ring-violet-200",
  fraud_review: "bg-rose-50 text-rose-700 ring-rose-200",
};

const DECISION_STYLE: Record<string, string> = {
  COVERED: "bg-emerald-100 text-emerald-800",
  NOT_COVERED: "bg-rose-100 text-rose-800",
  REFER: "bg-amber-100 text-amber-800",
};

export function Badge({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${className}`}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <Badge className={STATUS_STYLE[status] ?? "bg-slate-100"}>{status.replace(/_/g, " ")}</Badge>;
}

export function QueueBadge({ queue }: { queue: string | null }) {
  if (!queue) return <span className="text-slate-400">–</span>;
  return (
    <Badge className={`ring-1 ring-inset ${QUEUE_STYLE[queue] ?? ""}`}>
      {queue.replace(/_/g, " ")}
    </Badge>
  );
}

export function DecisionBadge({ decision }: { decision: string | undefined }) {
  if (!decision) return <span className="text-slate-400">–</span>;
  return <Badge className={DECISION_STYLE[decision] ?? ""}>{decision.replace(/_/g, " ")}</Badge>;
}

export function Money({ value }: { value: string | number | null | undefined }) {
  if (value === null || value === undefined || value === "") return <span className="text-slate-400">–</span>;
  const n = Number(value);
  return (
    <span className="tabular-nums">
      {n.toLocaleString("sk-SK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €
    </span>
  );
}

export function Card({
  title,
  aside,
  children,
  className = "",
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          {aside}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function AgentTag({ by }: { by?: string }) {
  if (!by) return null;
  return (
    <span className="rounded bg-indigo-50 px-1.5 py-0.5 font-mono text-[11px] text-indigo-700">
      {by.replace(/^agent:/, "")}
    </span>
  );
}

export function Notice({ notice, error }: { notice?: unknown; error?: unknown }) {
  return (
    <>
      {typeof notice === "string" && (
        <div role="status" className="rounded-lg bg-emerald-50 px-4 py-2 text-sm text-emerald-800 ring-1 ring-emerald-200">
          {notice}
        </div>
      )}
      {typeof error === "string" && (
        <div role="alert" className="rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-800 ring-1 ring-rose-200">
          {error}
        </div>
      )}
    </>
  );
}

export const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100";

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}
