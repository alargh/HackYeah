import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tutorly",
  description: "Understand mathematics, don't just solve it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-[1600px] items-center gap-3 px-4 py-3">
            <Link href="/" className="text-lg font-bold tracking-tight">
              <span className="text-lens-600">Tutorly</span>
            </Link>
            <span className="hidden text-sm text-slate-500 sm:inline">Understand mathematics, don&apos;t just solve it.</span>
          </div>
        </header>
        <main className="mx-auto max-w-[1600px] px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
