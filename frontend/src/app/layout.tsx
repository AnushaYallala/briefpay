import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";
import { Header } from "@/components/Header";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "BriefPay",
  description: "Neighbours pool money for one shared project. Nobody is charged unless the goal is reached.",
  icons: {
    icon: "/favicon.svg",
  },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col">
        <AuthProvider>
          <Header />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 sm:px-6 lg:px-8 py-8 animate-fade-up">
            {children}
          </main>
          <footer className="mt-auto border-t border-slate-200/80 bg-white/70 py-6 backdrop-blur-sm text-xs text-slate-500">
            <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-3 px-4 sm:px-6 lg:px-8 sm:flex-row">
              <div className="flex items-center gap-2 font-medium text-slate-700">
                <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>BriefPay &bull; Autonomous Assurance Protocol for Pooled Projects</span>
              </div>
              <div className="flex items-center gap-4 text-slate-500">
                <Link href="/ledger?id=1" className="hover:text-sea-700 transition hover:underline">
                  Public Ledger
                </Link>
                <span>&bull;</span>
                <a
                  href="https://github.com/AnushaYallala/briefpay"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-sea-700 transition hover:underline"
                >
                  GitHub Repository
                </a>
              </div>
            </div>
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
