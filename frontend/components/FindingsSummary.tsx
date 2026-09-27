"use client";

import React from "react";
import { Finding, Severity, Category } from "@/lib/types";
import { ShieldAlert, AlertTriangle, Info, CheckCircle2 } from "lucide-react";

interface FindingsSummaryProps {
  findings: Finding[];
  selectedSeverity: string | null;
  onSelectSeverity: (s: string | null) => void;
  selectedCategory: string | null;
  onSelectCategory: (c: string | null) => void;
}

export default function FindingsSummary({
  findings,
  selectedSeverity,
  onSelectSeverity,
  selectedCategory,
  onSelectCategory,
}: FindingsSummaryProps) {
  const countsBySeverity: Record<Severity, number> = {
    Blocker: 0,
    Major: 0,
    Minor: 0,
    Nit: 0,
  };

  const countsByCategory: Record<Category, number> = {
    security: 0,
    logic: 0,
    maintainability: 0,
    style: 0,
    tests: 0,
  };

  for (const f of findings) {
    if (countsBySeverity[f.severity] !== undefined) {
      countsBySeverity[f.severity]++;
    }
    const cat = f.category?.toLowerCase() as Category;
    if (countsByCategory[cat] !== undefined) {
      countsByCategory[cat]++;
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* Severities */}
      <div>
        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.4rem", fontWeight: 600 }}>
          FILTER BY SEVERITY
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          {(["Blocker", "Major", "Minor", "Nit"] as Severity[]).map((sev) => {
            const count = countsBySeverity[sev];
            const isSelected = selectedSeverity === sev;

            let badgeClass = "badge-nit";
            if (sev === "Blocker") badgeClass = "badge-blocker";
            if (sev === "Major") badgeClass = "badge-major";
            if (sev === "Minor") badgeClass = "badge-minor";

            return (
              <button
                key={sev}
                type="button"
                onClick={() => onSelectSeverity(isSelected ? null : sev)}
                className={`badge ${badgeClass}`}
                style={{
                  cursor: "pointer",
                  padding: "0.3rem 0.75rem",
                  fontSize: "0.8rem",
                  outline: isSelected ? "2px solid #ffffff" : "none",
                  boxShadow: isSelected ? "0 0 8px rgba(255,255,255,0.4)" : "none",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                }}
              >
                <span>{sev}</span>
                <span style={{ opacity: 0.85, fontWeight: 700 }}>({count})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Categories */}
      <div>
        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.4rem", fontWeight: 600 }}>
          FILTER BY CATEGORY
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          {(["security", "logic", "maintainability", "style", "tests"] as Category[]).map((cat) => {
            const count = countsByCategory[cat];
            const isSelected = selectedCategory === cat;

            return (
              <button
                key={cat}
                type="button"
                onClick={() => onSelectCategory(isSelected ? null : cat)}
                style={{
                  cursor: "pointer",
                  padding: "0.25rem 0.65rem",
                  fontSize: "0.75rem",
                  borderRadius: "6px",
                  border: isSelected ? "1px solid var(--accent-blue)" : "1px solid var(--border-color)",
                  backgroundColor: isSelected ? "rgba(88, 166, 255, 0.2)" : "var(--bg-tertiary)",
                  color: isSelected ? "var(--accent-blue)" : "var(--text-secondary)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  textTransform: "capitalize",
                }}
              >
                <span>{cat}</span>
                <span style={{ opacity: 0.75, fontWeight: 600 }}>({count})</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
