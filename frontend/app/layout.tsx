import type { Metadata } from "next";
import React from "react";

export const metadata: Metadata = {
  title: "InvoiceAI Review",
  description: "Human review for AI-extracted invoices"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body style={{ margin: 0, fontFamily: "Inter, system-ui, sans-serif", background: "#f5f7fb", color: "#172033" }}>{children}</body></html>;
}
