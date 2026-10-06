import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { switchHandler } from "@/lib/actions";
import { currentHandler, HANDLERS } from "@/lib/handler";

export const metadata: Metadata = {
  title: "Claims Workbench",
  description: "Handler CRM for the Agentic Insurance Platform",
};

export default async function CrmLayout({ children }: { children: ReactNode }) {
  const handler = await currentHandler();
  return (
    <>
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1500px] items-center gap-6 px-4 py-3">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-indigo-600 text-sm text-white">
              C
            </span>
            Claims Workbench
          </Link>
          <nav className="flex gap-1 text-sm">
            <Link href="/" className="rounded-md px-3 py-1.5 hover:bg-slate-100">
              Dashboard
            </Link>
            <Link href="/claims" className="rounded-md px-3 py-1.5 hover:bg-slate-100">
              Review queue
            </Link>
            <Link href="/claims?status=all" className="rounded-md px-3 py-1.5 hover:bg-slate-100">
              All claims
            </Link>
            <Link href="/portal" className="rounded-md px-3 py-1.5 text-slate-500 hover:bg-slate-100">
              Customer portal ↗
            </Link>
          </nav>
          <form action={switchHandler} className="ml-auto flex items-center gap-2 text-sm">
            <label htmlFor="handler" className="text-slate-500">
              Signed in as
            </label>
            <select
              id="handler"
              name="handler"
              defaultValue={handler}
              className="rounded-md border border-slate-300 bg-white px-2 py-1"
            >
              {HANDLERS.map((h) => (
                <option key={h}>{h}</option>
              ))}
            </select>
            <button className="rounded-md border border-slate-300 px-2 py-1 hover:bg-slate-100">
              Switch
            </button>
            <span className="hidden text-xs text-slate-400 lg:inline">dev identity · Entra ID in prod</span>
          </form>
        </div>
      </header>
      <main className="mx-auto max-w-[1500px] px-4 py-6">{children}</main>
    </>
  );
}
