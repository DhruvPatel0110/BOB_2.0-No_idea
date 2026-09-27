"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { getSystemHealth } from "@/lib/api";
import { HealthStatus } from "@/lib/types";
import { ShieldCheck, Activity, Terminal } from "lucide-react";

export default function Navbar() {
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    getSystemHealth()
      .then((data) => setHealth(data))
      .catch(() => setHealth(null));
  }, []);

  return (
    <header
      style={{
        borderBottom: "1px solid var(--border-color)",
        backgroundColor: "var(--bg-secondary)",
        padding: "0.85rem 0",
        marginBottom: "1.5rem",
      }}
    >
      <div
        className="container"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <Link
            href="/"
            style={{
              fontSize: "1.25rem",
              fontWeight: 700,
              color: "var(--text-primary)",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <ShieldCheck size={24} color="#58a6ff" />
            <span>PRISM</span>
            <span
              style={{
                fontSize: "0.75rem",
                color: "var(--text-secondary)",
                fontWeight: 400,
                border: "1px solid var(--border-color)",
                padding: "0.1rem 0.4rem",
                borderRadius: "4px",
              }}
            >
              AI Code Review Coach
            </span>
          </Link>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "1.25rem" }}>
          <Link
            href="/"
            style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}
          >
            Dashboard
          </Link>

          <a
            href={`${process.env.NEXT_PUBLIC_API_URL || "https://prism-backend-8yq3.onrender.com"}/docs`}
            target="_blank"
            rel="noreferrer"
            style={{
              fontSize: "0.875rem",
              color: "var(--text-secondary)",
              display: "flex",
              alignItems: "center",
              gap: "0.3rem",
            }}
          >
            <Terminal size={14} />
            <span>API Docs</span>
          </a>

          {/* Health Pill */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              fontSize: "0.75rem",
              padding: "0.2rem 0.6rem",
              borderRadius: "20px",
              backgroundColor: health?.all_ok
                ? "rgba(63, 185, 80, 0.15)"
                : "rgba(248, 81, 73, 0.15)",
              color: health?.all_ok ? "#3fb950" : "#f85149",
              border: `1px solid ${
                health?.all_ok ? "rgba(63, 185, 80, 0.4)" : "rgba(248, 81, 73, 0.4)"
              }`,
            }}
            title={
              health
                ? `Ollama: ${health.ollama.ok ? "Ready" : "Offline"}, ChromaDB: ${
                    health.chromadb.ok ? "Ready" : "Error"
                  }, GitHub: ${health.github.ok ? "Ready" : "Error"}`
                : "Checking backend health..."
            }
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                backgroundColor: health?.all_ok ? "#3fb950" : "#f85149",
              }}
            />
            <span>{health?.all_ok ? "All Systems Operational" : "Backend Offline / Degraded"}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
