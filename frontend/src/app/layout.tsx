import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { Header } from "@/components/Header";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "BriefPay",
  description: "Neighbours pool money for one shared project. Nobody is charged unless the goal is reached.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col">
        <AuthProvider>
          <Header />
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
          <footer className="mt-auto border-t border-slate-200/80 bg-white/60 py-6 backdrop-blur-sm text-xs text-slate-500">
            <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 sm:flex-row">
              <div className="flex items-center gap-2 font-medium text-slate-700">
                <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>BriefPay · Autonomous Assurance Protocol for Pooled Projects</span>
              </div>
              <div className="text-slate-500">
                Powered by PayPal Authorization Holds &amp; Gemini AI • No charges unless goal is achieved
              </div>
            </div>
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
