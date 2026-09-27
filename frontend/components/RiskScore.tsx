"use client";

import React from "react";

interface RiskScoreProps {
  score: number;
}

export default function RiskScore({ score }: RiskScoreProps) {
  const boundedScore = Math.max(0, Math.min(100, Math.round(score)));

  let color = "#3fb950"; // Green
  let label = "Low Risk";
  let description = "Changes look safe with low architectural and security impact.";

  if (boundedScore >= 50) {
    color = "#f85149"; // Red
    label = "High Risk";
    description = "Critical blocker/security flaws detected that require immediate attention.";
  } else if (boundedScore >= 20) {
    color = "#d29922"; // Yellow
    label = "Moderate Risk";
    description = "Noticeable issues or conventions flagged. Review carefully before merge.";
  }

  // SVG Circular Gauge calculations
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (boundedScore / 100) * circumference;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "1.5rem",
        padding: "1rem",
        backgroundColor: "var(--bg-tertiary)",
        borderRadius: "8px",
        border: "1px solid var(--border-color)",
      }}
    >
      <div style={{ position: "relative", width: 104, height: 104, flexShrink: 0 }}>
        <svg width="104" height="104" style={{ transform: "rotate(-90deg)" }}>
          {/* Background circle */}
          <circle
            cx="52"
            cy="52"
            r={radius}
            stroke="rgba(255, 255, 255, 0.1)"
            strokeWidth="8"
            fill="transparent"
          />
          {/* Progress circle */}
          <circle
            cx="52"
            cy="52"
            r={radius}
            stroke={color}
            strokeWidth="8"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            fill="transparent"
            style={{ transition: "stroke-dashoffset 0.8s ease" }}
          />
        </svg>

        {/* Center Text */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span style={{ fontSize: "1.6rem", fontWeight: 700, color: "var(--text-primary)" }}>
            {boundedScore}
          </span>
          <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginTop: "-4px" }}>
            / 100
          </span>
        </div>
      </div>

      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
          <span
            style={{
              padding: "0.15rem 0.5rem",
              borderRadius: "4px",
              backgroundColor: `${color}25`,
              color: color,
              fontWeight: 700,
              fontSize: "0.85rem",
              border: `1px solid ${color}60`,
            }}
          >
            {label}
          </span>
          <span style={{ fontSize: "0.9rem", fontWeight: 600 }}>Pull Request Risk Score</span>
        </div>
        <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.4 }}>
          {description}
        </p>
      </div>
    </div>
  );
}
