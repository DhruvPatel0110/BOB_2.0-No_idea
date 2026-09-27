import type { Metadata } from "next";
import Navbar from "@/components/Navbar";
import "./globals.css";

export const metadata: Metadata = {
  title: "PRISM — AI Code Review Coach",
  description:
    "Automated, grounded code reviews powered by Ollama, ChromaDB, and GitHub MCP.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        <main
          className="container"
          style={{
            minHeight: "calc(100vh - 180px)",
            paddingBottom: "3rem",
          }}
        >
          {children}
        </main>
        <footer
          style={{
            borderTop: "1px solid var(--border-color)",
            padding: "1.5rem 0",
            backgroundColor: "var(--bg-secondary)",
            color: "var(--text-muted)",
            fontSize: "0.8rem",
            textAlign: "center",
          }}
        >
          <div className="container">
            PRISM — Precision Review Intelligence & Style Mentor • Built for IBM-BOB
            Hackathon
          </div>
        </footer>
      </body>
    </html>
  );
}
