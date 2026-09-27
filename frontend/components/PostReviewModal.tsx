"use client";

import React, { useState } from "react";
import { postReviewComments } from "@/lib/api";
import { PostReviewResponse } from "@/lib/types";
import { Send, CheckCircle2, AlertTriangle, X } from "lucide-react";

interface PostReviewModalProps {
  reviewId: string;
  prUrl: string;
  findingsCount: number;
}

export default function PostReviewModal({
  reviewId,
  prUrl,
  findingsCount,
}: PostReviewModalProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<PostReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handlePost = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await postReviewComments(reviewId, dryRun);
      setResult(res);
    } catch (err: any) {
      setError(err.message || "Failed to post review");
    } finally {
      setSubmitting(false);
    }
  };

  const close = () => {
    setIsOpen(false);
    setResult(null);
    setError(null);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="btn btn-primary"
      >
        <Send size={15} />
        <span>Post Review to GitHub</span>
      </button>

      {isOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            backgroundColor: "rgba(0, 0, 0, 0.7)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            backdropFilter: "blur(4px)",
          }}
        >
          <div
            className="card"
            style={{
              width: "100%",
              maxWidth: 520,
              backgroundColor: "var(--bg-secondary)",
              border: "1px solid var(--border-color)",
              boxShadow: "0 8px 32px rgba(0, 0, 0, 0.5)",
              position: "relative",
            }}
          >
            {/* Header */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "1rem",
                borderBottom: "1px solid var(--border-color)",
                paddingBottom: "0.75rem",
              }}
            >
              <h3 style={{ fontSize: "1.05rem", fontWeight: 600 }}>Post Review to GitHub</h3>
              <button
                type="button"
                onClick={close}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Success state */}
            {result ? (
              <div>
                <div
                  style={{
                    padding: "0.85rem",
                    borderRadius: "6px",
                    backgroundColor: "rgba(63, 185, 80, 0.15)",
                    border: "1px solid rgba(63, 185, 80, 0.4)",
                    color: "#3fb950",
                    marginBottom: "1rem",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "0.6rem",
                  }}
                >
                  <CheckCircle2 size={18} style={{ flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                      {result.dry_run ? "Simulated Review Successful" : "Review Posted!"}
                    </div>
                    <div style={{ fontSize: "0.8rem", marginTop: 2, color: "var(--text-primary)" }}>
                      {result.message}
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <button type="button" onClick={close} className="btn btn-secondary">
                    Close
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                  PRISM will submit your automated review with <strong>{findingsCount} finding(s)</strong> anchored to the specific lines in the PR diff.
                </p>

                {/* Dry run checkbox */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "0.6rem",
                    padding: "0.75rem",
                    borderRadius: "6px",
                    backgroundColor: "var(--bg-tertiary)",
                    border: "1px solid var(--border-color)",
                    marginBottom: "1.25rem",
                  }}
                >
                  <input
                    type="checkbox"
                    id="dryRunToggle"
                    checked={dryRun}
                    onChange={(e) => setDryRun(e.target.checked)}
                    style={{ marginTop: 3, cursor: "pointer" }}
                  />
                  <label htmlFor="dryRunToggle" style={{ fontSize: "0.85rem", cursor: "pointer" }}>
                    <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>Dry Run (Simulation)</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      Validate findings and comments payload without writing actual comments to the live GitHub PR.
                    </div>
                  </label>
                </div>

                {error && (
                  <div
                    style={{
                      padding: "0.65rem 0.85rem",
                      borderRadius: "6px",
                      backgroundColor: "rgba(248, 81, 73, 0.15)",
                      border: "1px solid rgba(248, 81, 73, 0.4)",
                      color: "#f85149",
                      fontSize: "0.8rem",
                      marginBottom: "1rem",
                    }}
                  >
                    {error}
                  </div>
                )}

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button type="button" onClick={close} className="btn btn-secondary">
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handlePost}
                    disabled={submitting}
                    className="btn btn-primary"
                  >
                    {submitting ? "Posting..." : dryRun ? "Run Simulation" : "Confirm & Post"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
