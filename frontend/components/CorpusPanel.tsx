"use client";

import React, { useState, useEffect } from "react";
import { getCorpusStatus, triggerCorpusBuild } from "@/lib/api";
import { CorpusStatus } from "@/lib/types";
import { Database, RefreshCw, CheckCircle, AlertCircle } from "lucide-react";

interface CorpusPanelProps {
  repoOwner?: string;
  repoName?: string;
}

export default function CorpusPanel({ repoOwner, repoName }: CorpusPanelProps) {
  const [corpus, setCorpus] = useState<CorpusStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [buildMsg, setBuildMsg] = useState<string | null>(null);

  const loadStatus = () => {
    setLoading(true);
    getCorpusStatus(repoOwner, repoName)
      .then((data) => setCorpus(data))
      .catch((err) => console.error("Corpus status failed:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadStatus();
  }, [repoOwner, repoName]);

  const handleBuild = async () => {
    if (!repoOwner || !repoName) return;
    setBuilding(true);
    setBuildMsg(null);
    try {
      const res = await triggerCorpusBuild(repoOwner, repoName, false);
      setBuildMsg(`Indexed ${res.style_chunks || 0} style chunks & ${res.history_chunks || 0} history items in ${res.duration_s || 0}s`);
      loadStatus();
    } catch (err: any) {
      setBuildMsg(`Build error: ${err.message}`);
    } finally {
      setBuilding(false);
    }
  };

  return (
    <div className="card" style={{ marginTop: "2rem" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "0.85rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Database size={18} color="var(--accent-purple)" />
          <h3 style={{ fontSize: "0.95rem", fontWeight: 600 }}>RAG Knowledge Corpus Status</h3>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {repoOwner && repoName && (
            <button
              type="button"
              onClick={handleBuild}
              disabled={building}
              className="btn btn-secondary"
              style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem" }}
            >
              <RefreshCw size={12} className={building ? "spinner" : ""} />
              <span>{building ? "Indexing..." : `Index ${repoOwner}/${repoName}`}</span>
            </button>
          )}

          <button
            type="button"
            onClick={loadStatus}
            disabled={loading}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
            }}
            title="Refresh status"
          >
            <RefreshCw size={14} className={loading ? "spinner" : ""} />
          </button>
        </div>
      </div>

      {buildMsg && (
        <div
          style={{
            fontSize: "0.8rem",
            padding: "0.4rem 0.75rem",
            borderRadius: "4px",
            marginBottom: "0.75rem",
            backgroundColor: "rgba(88, 166, 255, 0.15)",
            color: "var(--accent-blue)",
            border: "1px solid rgba(88, 166, 255, 0.3)",
          }}
        >
          {buildMsg}
        </div>
      )}

      {corpus ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "0.75rem" }}>
          {/* Cold start overall indicator */}
          <div
            style={{
              padding: "0.6rem 0.75rem",
              borderRadius: "6px",
              backgroundColor: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
            }}
          >
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
              COLD-START DATASETS
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem", fontWeight: 600 }}>
              {corpus.cold_start_loaded ? (
                <>
                  <CheckCircle size={14} color="#3fb950" />
                  <span style={{ color: "#3fb950" }}>Ready</span>
                </>
              ) : (
                <>
                  <AlertCircle size={14} color="#f85149" />
                  <span style={{ color: "#f85149" }}>Not Loaded</span>
                </>
              )}
            </div>
          </div>

          {/* Individual collections */}
          {Object.entries(corpus.collections || {}).map(([key, col]) => (
            <div
              key={key}
              style={{
                padding: "0.6rem 0.75rem",
                borderRadius: "6px",
                backgroundColor: "var(--bg-primary)",
                border: "1px solid var(--border-color)",
              }}
            >
              <div
                style={{
                  fontSize: "0.7rem",
                  color: "var(--text-muted)",
                  marginBottom: "0.2rem",
                  textOverflow: "ellipsis",
                  overflow: "hidden",
                  whiteSpace: "nowrap",
                }}
                title={key}
              >
                {key.replace("cold_start_", "").toUpperCase()}
              </div>
              <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)" }}>
                {col.count ?? 0} <span style={{ fontSize: "0.7rem", fontWeight: 400, color: "var(--text-muted)" }}>chunks</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Loading corpus metrics...</div>
      )}
    </div>
  );
}
