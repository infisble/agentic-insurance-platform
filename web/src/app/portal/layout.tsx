import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "My Insurance",
  description: "Get a quote, buy a policy and report a claim online",
};

export default function PortalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-teal-50 to-slate-50">
      <header className="border-b border-teal-100 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
          <Link href="/portal" className="flex items-center gap-2 font-semibold">
            <span className="grid h-7 w-7 place-items-center rounded-full bg-teal-600 text-sm text-white">
              ✓
            </span>
            My Insurance
          </Link>
          <nav className="flex gap-1 text-sm">
            <Link href="/portal" className="rounded-md px-3 py-1.5 hover:bg-teal-50">
              My policies
            </Link>
            <Link href="/portal/quote" className="rounded-md px-3 py-1.5 hover:bg-teal-50">
              Get a quote
            </Link>
          </nav>
          <Link href="/" className="ml-auto text-xs text-slate-400 hover:text-slate-600">
            Staff: Claims Workbench →
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
      <footer className="mx-auto max-w-5xl px-4 pb-8 text-xs text-slate-400">
        Demo portal. All products, prices and documents are fictional. Every claim decision is made by
        a person; software only prepares the case.
      </footer>
    </div>
  );
}
