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
      <body>
        <AuthProvider>
          <Header />
          <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
          <footer className="mx-auto max-w-5xl px-4 pb-8 text-xs text-gray-500">
            Sandbox demo: no real money moves. A pledge is only a hold at PayPal until the goal is reached.
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
