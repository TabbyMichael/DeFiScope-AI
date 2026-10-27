import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DeFiScope AI",
  description:
    "DeFi protocol research, explainable risk scoring and automated monitoring",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-zinc-950 text-zinc-100">
        <header className="border-b border-zinc-800">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-lg font-semibold tracking-tight">
                DeFi<span className="text-emerald-400">Scope</span> AI
              </span>
              <span className="hidden text-xs text-zinc-500 sm:inline">
                research · risk · monitoring
              </span>
            </Link>
            <nav className="flex gap-4 text-sm text-zinc-300">
              <Link href="/" className="hover:text-white">
                Dashboard
              </Link>
              <Link href="/alerts" className="hover:text-white">
                Alerts
              </Link>
              <a
                href={(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/docs"}
                target="_blank"
                rel="noreferrer"
                className="text-zinc-400 hover:text-white"
              >
                API
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
          {children}
        </main>
        <footer className="border-t border-zinc-800 py-3">
          <div className="mx-auto max-w-6xl px-4 text-xs text-zinc-500">
            Data source: DefiLlama public API. Scores measure what TVL data can
            show — see{" "}
            <Link href="/about" className="underline hover:text-zinc-300">
              methodology &amp; limitations
            </Link>
            .
          </div>
        </footer>
      </body>
    </html>
  );
}
