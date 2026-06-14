import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NetGuard AI — Security Operations Center",
  description: "Real-time IoT Network Intrusion Detection System powered by a Two-Stage Hybrid AI pipeline with live SHAP explainability, D3 network topology, and RAG-grounded incident analysis.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Preconnect — resolve DNS + TLS before font fetch */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />

        {/*
          Three-font system for premium typography:

          Outfit    — Display/heading font. Geometric sans-serif with slightly rounded
                      terminals. Used for page titles, card headers, nav items, logo.
                      Gives the dashboard its premium, modern feel.

          Inter     — Body/data font. Optimized for readability at small sizes with
                      optical sizing (opsz axis). Used for descriptions, labels, feeds.

          JetBrains Mono — Monospace for code values, timestamps, metrics, IPs.

          display=swap — renders system fallback immediately, swaps when loaded.
        */}
        <link
          href="https://fonts.googleapis.com/css2?family=Outfit:wght@300..700&family=Inter:ital,opsz,wght@0,14..32,300..700;1,14..32,300..700&family=JetBrains+Mono:ital,wght@0,300..700;1,300..700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
