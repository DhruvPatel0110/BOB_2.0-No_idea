"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { submitReviewAnalysis, getAllReviews } from "@/lib/api";
import { ReviewSession } from "@/lib/types";
import CorpusPanel from "@/components/CorpusPanel";
import {
  Search,
  ArrowRight,
  GitPullRequest,
  CheckCircle2,
  Clock,
  AlertCircle,
  Sparkles,
  RefreshCw,
  ExternalLink,
} from "lucide-react";

export default function HomePage() {
  const router = useRouter();
  const [prUrl, setPrUrl] = useState("");
  const [languageHint, setLanguageHint] = useState("");
  const [postComments, setPostComments] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [recentReviews, setRecentReviews] = useState<ReviewSession[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(false);

  const loadRecentReviews = async () => {
    setLoadingRecent(true);
    try {
      const data = await getAllReviews();
      setRecentReviews(data);
    } catch (err: any) {
      console.warn("Could not load recent reviews:", err.message);
    } finally {
      setLoadingRecent(false);
    }
  };

  useEffect(() => {
    loadRecentReviews();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prUrl.trim()) {
      setError("Please enter a GitHub Pull Request URL");
      return;
    }

    if (!prUrl.includes("github.com") || !prUrl.includes("/pull/")) {
      setError("URL must be a valid GitHub Pull Request (e.g. https://github.com/owner/repo/pull/123)");
      return;
    }

    setSubmitting(true);
    setError(null);
    console.log("[PRISM Frontend] Submitting review analysis for:", prUrl.trim(), { postComments, languageHint });

    try {
      const res = await submitReviewAnalysis(prUrl.trim(), postComments, languageHint || undefined);
      console.log("[PRISM Frontend] Received review submission response:", res);
      if (res && res.review_id) {
        console.log(`[PRISM Frontend] Redirecting to /review/${res.review_id}`);
        router.push(`/review/${res.review_id}`);
      } else {
        setError("Failed to queue review session");
        setSubmitting(false);
      }
    } catch (err: any) {
      console.error("[PRISM Frontend] Submit review error:", err);
      setError(err.message || "Failed to submit PR for review");
      setSubmitting(false);
    }
  };

  const setPreset = (url: string) => {
    setPrUrl(url);
    setError(null);
  };

  return (
    <div>
      {/* Hero / Input Section */}
      <section style={{ margin: "2rem 0 2.5rem 0" }}>
        <div style={{ maxWidth: 840, margin: "0 auto", textAlign: "center" }}>
          <h1
            style={{
              fontSize: "2.25rem",
              fontWeight: 800,
              letterSpacing: "-0.5px",
              marginBottom: "0.75rem",
              background: "linear-gradient(90deg, #f0f6fc, #58a6ff)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Precision Review Intelligence & Style Mentor
          </h1>
          <p
            style={{
              fontSize: "1.05rem",
              color: "var(--text-secondary)",
              marginBottom: "2rem",
              lineHeight: 1.5,
            }}
          >
            Autonomous, RAG-grounded pull request code reviews powered by local Ollama LLMs and ChromaDB.
          </p>

          {/* Form Card */}
          <div className="card" style={{ padding: "1.75rem", textAlign: "left" }}>
            <form onSubmit={handleSubmit}>
              <label
                htmlFor="prUrlInput"
                style={{
                  display: "block",
                  fontSize: "0.85rem",
                  fontWeight: 600,
                  marginBottom: "0.5rem",
                  color: "var(--text-primary)",
                }}
              >
                GitHub Pull Request URL
              </label>

              <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem" }}>
                <input
                  id="prUrlInput"
                  type="url"
                  className="input"
                  placeholder="https://github.com/owner/repository/pull/123"
                  value={prUrl}
                  onChange={(e) => setPrUrl(e.target.value)}
                  disabled={submitting}
                  required
                />
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn btn-primary"
                  style={{ minWidth: 150 }}
                >
                  {submitting ? (
                    <>
                      <RefreshCw size={16} className="spinner" />
                      <span>Analyzing...</span>
                    </>
                  ) : (
                    <>
                      <span>Start Review</span>
                      <ArrowRight size={16} />
                    </>
                  )}
                </button>
              </div>

              {/* Advanced options */}
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "1rem",
                  paddingTop: "0.75rem",
                  borderTop: "1px solid var(--border-subtle)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <label
                    style={{
                      fontSize: "0.8rem",
                      color: "var(--text-secondary)",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.35rem",
                    }}
                  >
                    <span>Language Hint:</span>
                    <input
                      type="text"
                      placeholder="e.g. python, ts (optional)"
                      value={languageHint}
                      onChange={(e) => setLanguageHint(e.target.value)}
                      style={{
                        padding: "0.25rem 0.5rem",
                        fontSize: "0.75rem",
                        background: "var(--bg-primary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: "4px",
                        color: "var(--text-primary)",
                        width: 140,
                      }}
                    />
                  </label>
                </div>

                <label
                  style={{
                    fontSize: "0.8rem",
                    color: "var(--text-secondary)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.4rem",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={postComments}
                    onChange={(e) => setPostComments(e.target.checked)}
                  />
                  <span>Auto-post comments to PR upon completion</span>
                </label>
              </div>

              {error && (
                <div
                  style={{
                    marginTop: "1rem",
                    padding: "0.6rem 0.85rem",
                    backgroundColor: "rgba(248, 81, 73, 0.15)",
                    border: "1px solid rgba(248, 81, 73, 0.4)",
                    color: "#f85149",
                    borderRadius: "6px",
                    fontSize: "0.85rem",
                  }}
                >
                  {error}
                </div>
              )}
            </form>

            {/* Quick Presets */}
            <div style={{ marginTop: "1.25rem" }}>
              <div
                style={{
                  fontSize: "0.75rem",
                  color: "var(--text-muted)",
                  marginBottom: "0.5rem",
                  fontWeight: 600,
                  display: "flex",
                  alignItems: "center",
                  gap: "0.35rem",
                }}
              >
                <Sparkles size={12} color="var(--accent-yellow)" />
                <span>TRY A SAMPLE DEMO PR</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                <button
                  type="button"
                  onClick={() => setPreset("https://github.com/pallets/flask/pull/5000")}
                  className="btn btn-secondary"
                  style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem" }}
                >
                  <span>pallets/flask #5000</span>
                </button>
                <button
                  type="button"
                  onClick={() => setPreset("https://github.com/DhruvPatel0110/BOB_2.0-No_idea/pull/1")}
                  className="btn btn-secondary"
                  style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem" }}
                >
                  <span>DhruvPatel0110/BOB_2.0-No_idea #1</span>
                </button>
                <button
                  type="button"
                  onClick={() => setPreset("https://github.com/pallets/werkzeug/pull/2600")}
                  className="btn btn-secondary"
                  style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem" }}
                >
                  <span>pallets/werkzeug #2600</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Recent Reviews History Section */}
      <section style={{ marginBottom: "2.5rem" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "0.85rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Clock size={18} color="var(--accent-blue)" />
            <h2 style={{ fontSize: "1.1rem", fontWeight: 600 }}>Recent Reviews</h2>
          </div>
          <button
            type="button"
            onClick={loadRecentReviews}
            disabled={loadingRecent}
            className="btn btn-secondary"
            style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem" }}
          >
            <RefreshCw size={12} className={loadingRecent ? "spinner" : ""} />
            <span>Refresh</span>
          </button>
        </div>

        {recentReviews.length === 0 ? (
          <div
            className="card"
            style={{
              padding: "2rem",
              textAlign: "center",
              color: "var(--text-muted)",
              fontSize: "0.9rem",
            }}
          >
            No reviews analyzed yet in this session. Enter a GitHub PR URL above to get started!
          </div>
        ) : (
          <div
            className="card"
            style={{
              padding: 0,
              overflow: "hidden",
            }}
          >
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.85rem",
                textAlign: "left",
              }}
            >
              <thead>
                <tr
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    borderBottom: "1px solid var(--border-color)",
                    color: "var(--text-secondary)",
                    fontSize: "0.75rem",
                  }}
                >
                  <th style={{ padding: "0.6rem 1rem" }}>STATUS</th>
                  <th style={{ padding: "0.6rem 1rem" }}>PULL REQUEST</th>
                  <th style={{ padding: "0.6rem 1rem" }}>RISK SCORE</th>
                  <th style={{ padding: "0.6rem 1rem" }}>FINDINGS</th>
                  <th style={{ padding: "0.6rem 1rem" }}>CREATED</th>
                  <th style={{ padding: "0.6rem 1rem", textAlign: "right" }}>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {recentReviews.map((rev) => {
                  const findingsCount = rev.result?.findings?.length ?? 0;
                  const riskScore = rev.result?.risk_score;

                  return (
                    <tr
                      key={rev.review_id}
                      style={{
                        borderBottom: "1px solid var(--border-color)",
                      }}
                    >
                      {/* Status */}
                      <td style={{ padding: "0.75rem 1rem", whiteSpace: "nowrap" }}>
                        {rev.status === "complete" && (
                          <span
                            className="badge"
                            style={{
                              backgroundColor: "rgba(63, 185, 80, 0.15)",
                              color: "#3fb950",
                              border: "1px solid rgba(63, 185, 80, 0.3)",
                            }}
                          >
                            Complete
                          </span>
                        )}
                        {rev.status === "processing" && (
                          <span
                            className="badge"
                            style={{
                              backgroundColor: "rgba(88, 166, 255, 0.15)",
                              color: "#58a6ff",
                              border: "1px solid rgba(88, 166, 255, 0.3)",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.3rem",
                            }}
                          >
                            <RefreshCw size={10} className="spinner" />
                            Analyzing
                          </span>
                        )}
                        {rev.status === "failed" && (
                          <span
                            className="badge badge-blocker"
                          >
                            Failed
                          </span>
                        )}
                      </td>

                      {/* PR URL */}
                      <td style={{ padding: "0.75rem 1rem", maxWidth: 360, wordBreak: "break-all" }}>
                        <a
                          href={rev.pr_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.3rem",
                            fontFamily: "var(--font-mono)",
                            fontSize: "0.8rem",
                          }}
                        >
                          <GitPullRequest size={14} />
                          <span>{rev.pr_url.replace("https://github.com/", "")}</span>
                          <ExternalLink size={11} color="var(--text-muted)" />
                        </a>
                      </td>

                      {/* Risk Score */}
                      <td style={{ padding: "0.75rem 1rem" }}>
                        {riskScore !== undefined ? (
                          <span
                            style={{
                              fontWeight: 700,
                              color:
                                riskScore >= 50
                                  ? "#f85149"
                                  : riskScore >= 20
                                  ? "#d29922"
                                  : "#3fb950",
                            }}
                          >
                            {riskScore} / 100
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-muted)" }}>—</span>
                        )}
                      </td>

                      {/* Findings Count */}
                      <td style={{ padding: "0.75rem 1rem" }}>
                        {rev.status === "complete" ? (
                          <span>{findingsCount} issue{findingsCount === 1 ? "" : "s"}</span>
                        ) : (
                          <span style={{ color: "var(--text-muted)" }}>—</span>
                        )}
                      </td>

                      {/* Created */}
                      <td style={{ padding: "0.75rem 1rem", color: "var(--text-secondary)", fontSize: "0.75rem" }}>
                        {new Date(rev.created_at * 1000).toLocaleTimeString()}
                      </td>

                      {/* Action */}
                      <td style={{ padding: "0.75rem 1rem", textAlign: "right" }}>
                        <Link
                          href={`/review/${rev.review_id}`}
                          className="btn btn-outline-blue"
                          style={{ fontSize: "0.75rem", padding: "0.2rem 0.6rem" }}
                        >
                          View Review &rarr;
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Global Corpus Panel */}
      <CorpusPanel />
    </div>
  );
}
