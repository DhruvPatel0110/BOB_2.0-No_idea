"use client";

import React, { useEffect, useState, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getReviewSession } from "@/lib/api";
import { ReviewSession, Finding, Severity, Category } from "@/lib/types";
import RiskScore from "@/components/RiskScore";
import FindingsSummary from "@/components/FindingsSummary";
import DiffViewer from "@/components/DiffViewer";
import PostReviewModal from "@/components/PostReviewModal";
import CorpusPanel from "@/components/CorpusPanel";
import {
  GitPullRequest,
  ExternalLink,
  ArrowLeft,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  FileCode,
  Download,
  AlertOctagon,
  Copy,
  Check,
  Search,
} from "lucide-react";

export default function ReviewDetailPage() {
  const params = useParams();
  const router = useRouter();
  const reviewId = params?.id as string;

  const [session, setSession] = useState<ReviewSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedSeverity, setSelectedSeverity] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [filterText, setFilterText] = useState("");
  const [activeTab, setActiveTab] = useState<"diff" | "list">("diff");
  const [copiedIndex, setCopiedIndex] = useState<string | null>(null);

  // Polling logic
  useEffect(() => {
    if (!reviewId) return;

    let timer: NodeJS.Timeout | null = null;
    let isSubscribed = true;

    const fetchSession = async () => {
      try {
        const data = await getReviewSession(reviewId);
        if (!isSubscribed) return;

        console.log(`[PRISM Poller] Review ${reviewId.slice(0, 8)}:`, {
          status: data.status,
          stage: data.progress?.stage,
          percent: `${data.progress?.percent ?? 0}%`,
          message: data.progress?.message,
          findings: data.result?.findings?.length ?? 0,
        });

        setSession(data);
        setLoading(false);

        // Continue polling if still processing
        if (data.status === "processing") {
          timer = setTimeout(fetchSession, 2000);
        } else if (data.status === "complete") {
          console.log("[PRISM Poller] Review complete! Loaded findings:", data.result?.findings);
        } else if (data.status === "failed") {
          console.error("[PRISM Poller] Review failed with error:", data.error);
        }
      } catch (err: any) {
        if (!isSubscribed) return;
        console.error("[PRISM Poller] Error fetching session:", err);
        setError(err.message || "Failed to load review session");
        setLoading(false);
      }
    };

    fetchSession();

    return () => {
      isSubscribed = false;
      if (timer) clearTimeout(timer);
    };
  }, [reviewId]);

  // Extract owner, repo, PR number from URL
  const prDetails = useMemo(() => {
    if (!session?.pr_url) return null;
    const match = session.pr_url.match(/github\.com\/([^\/]+)\/([^\/]+)\/pull\/(\d+)/);
    if (!match) return { owner: "", repo: "", number: "" };
    return {
      owner: match[1],
      repo: match[2],
      number: match[3],
    };
  }, [session?.pr_url]);

  // Filtered findings
  const allFindings = useMemo(() => session?.result?.findings || [], [session]);

  const filteredFindings = useMemo(() => {
    return allFindings.filter((f) => {
      if (selectedSeverity && f.severity !== selectedSeverity) return false;
      if (selectedCategory && f.category?.toLowerCase() !== selectedCategory.toLowerCase()) return false;
      if (filterText.trim()) {
        const q = filterText.toLowerCase();
        const fPath = f.file_path || (f as any).file || "";
        const matchesTitle = f.title?.toLowerCase().includes(q) || false;
        const matchesPath = fPath.toLowerCase().includes(q);
        const matchesExpl = f.explanation?.toLowerCase().includes(q) || false;
        if (!matchesTitle && !matchesPath && !matchesExpl) return false;
      }
      return true;
    });
  }, [allFindings, selectedSeverity, selectedCategory, filterText]);

  const copyCode = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(id);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const downloadJson = () => {
    if (!session?.result) return;
    const blob = new Blob([JSON.stringify(session.result, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `prism-review-${reviewId.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Initial Loading
  if (loading && !session) {
    return (
      <div style={{ textAlign: "center", padding: "4rem 0" }}>
        <RefreshCw size={32} className="spinner" style={{ color: "var(--accent-blue)", marginBottom: "1rem" }} />
        <h2 style={{ fontSize: "1.25rem", fontWeight: 600 }}>Loading Review Session...</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
          Connecting to PRISM API Engine...
        </p>
      </div>
    );
  }

  // Error fetching session
  if (error && !session) {
    return (
      <div className="card" style={{ maxWidth: 600, margin: "3rem auto", textAlign: "center", padding: "2rem" }}>
        <AlertTriangle size={36} color="#f85149" style={{ marginBottom: "1rem" }} />
        <h2 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.5rem" }}>Review Session Error</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginBottom: "1.5rem" }}>{error}</p>
        <Link href="/" className="btn btn-primary">
          <ArrowLeft size={16} />
          <span>Return to Dashboard</span>
        </Link>
      </div>
    );
  }

  if (!session) return null;

  return (
    <div>
      {/* Top Breadcrumb & Controls */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "1.25rem",
        }}
      >
        <Link
          href="/"
          className="btn btn-secondary"
          style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem" }}
        >
          <ArrowLeft size={14} />
          <span>Dashboard</span>
        </Link>

        {session.status === "complete" && session.result && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <button
              type="button"
              onClick={downloadJson}
              className="btn btn-secondary"
              style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem" }}
              title="Download findings as JSON"
            >
              <Download size={14} />
              <span>Export JSON</span>
            </button>

            <PostReviewModal
              reviewId={reviewId}
              prUrl={session.pr_url}
              findingsCount={session.result.findings.length}
            />
          </div>
        )}
      </div>

      {/* PR Header Bar */}
      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem" }}>
              <GitPullRequest size={20} color="var(--accent-blue)" />
              <h1 style={{ fontSize: "1.3rem", fontWeight: 700 }}>
                {session.result?.pr_meta?.title || `Pull Request #${prDetails?.number || "Review"}`}
              </h1>
              <a
                href={session.pr_url}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.25rem",
                  fontSize: "0.75rem",
                  marginLeft: "0.5rem",
                }}
              >
                <span>View on GitHub</span>
                <ExternalLink size={12} />
              </a>
            </div>

            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "1rem", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
              <span>
                Repository: <strong>{prDetails?.owner}/{prDetails?.repo}</strong>
              </span>
              {session.result?.pr_meta?.author && (
                <span>
                  Author: <strong>@{session.result.pr_meta.author}</strong>
                </span>
              )}
              {session.result?.duration_s !== undefined && (
                <span>
                  Analysis time: <strong>{session.result.duration_s.toFixed(1)}s</strong>
                </span>
              )}
            </div>
          </div>

          <div>
            {session.status === "complete" && (
              <span
                className="badge"
                style={{
                  backgroundColor: "rgba(63, 185, 80, 0.15)",
                  color: "#3fb950",
                  border: "1px solid rgba(63, 185, 80, 0.4)",
                  padding: "0.3rem 0.75rem",
                }}
              >
                <CheckCircle2 size={13} style={{ marginRight: 4 }} />
                Analysis Complete
              </span>
            )}
            {session.status === "processing" && (
              <span
                className="badge"
                style={{
                  backgroundColor: "rgba(88, 166, 255, 0.15)",
                  color: "#58a6ff",
                  border: "1px solid rgba(88, 166, 255, 0.4)",
                  padding: "0.3rem 0.75rem",
                }}
              >
                <RefreshCw size={12} className="spinner" style={{ marginRight: 4 }} />
                Reviewing PR In Progress
              </span>
            )}
            {session.status === "failed" && (
              <span className="badge badge-blocker" style={{ padding: "0.3rem 0.75rem" }}>
                Analysis Failed
              </span>
            )}
          </div>
        </div>
      </div>

      {/* STATE 1: PROCESSING */}
      {session.status === "processing" && (
        <div className="card" style={{ padding: "2.5rem 1.5rem", textAlign: "center" }}>
          <RefreshCw size={42} className="spinner" style={{ color: "var(--accent-blue)", marginBottom: "1rem" }} />
          <h2 style={{ fontSize: "1.3rem", fontWeight: 700, marginBottom: "0.5rem" }}>
            PRISM AI Engine is Analyzing Pull Request
          </h2>

          {/* Current Sub-State Stage Pill */}
          <div style={{ margin: "0.6rem 0 1rem 0" }}>
            <span
              className="badge"
              style={{
                backgroundColor: "rgba(88, 166, 255, 0.2)",
                color: "#79c0ff",
                border: "1px solid rgba(88, 166, 255, 0.4)",
                padding: "0.3rem 0.85rem",
                fontSize: "0.8rem",
                letterSpacing: "0.8px",
              }}
            >
              STAGE: {session.progress?.stage?.toUpperCase() || "PROCESSING"}
            </span>
          </div>

          <p
            style={{
              color: "var(--text-primary)",
              fontSize: "0.95rem",
              fontWeight: 500,
              maxWidth: 680,
              margin: "0 auto 1.5rem auto",
              lineHeight: 1.5,
            }}
          >
            {session.progress?.message || "Running automated AST chunking, RAG context retrieval, and local Ollama analysis..."}
          </p>

          {/* Progress bar with percentage */}
          <div style={{ maxWidth: 500, margin: "0 auto" }}>
            <div
              style={{
                width: "100%",
                height: 10,
                backgroundColor: "var(--bg-tertiary)",
                borderRadius: 6,
                overflow: "hidden",
                border: "1px solid var(--border-color)",
              }}
            >
              <div
                style={{
                  width: `${session.progress?.percent || 15}%`,
                  height: "100%",
                  backgroundColor: "var(--accent-blue)",
                  transition: "width 0.5s ease",
                }}
              />
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginTop: "0.5rem",
                fontSize: "0.75rem",
                color: "var(--text-muted)",
              }}
            >
              <span>Active Stage: {session.progress?.stage || "processing"}</span>
              <strong style={{ color: "var(--accent-blue)" }}>{session.progress?.percent || 15}%</strong>
            </div>
          </div>

          <div style={{ marginTop: "1.25rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
            Polling backend every 2s • Check browser console (F12) for detailed live updates
          </div>
        </div>
      )}

      {/* STATE 2: FAILED */}
      {session.status === "failed" && (
        <div className="card" style={{ border: "1px solid #f85149", padding: "2rem" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: "1rem" }}>
            <AlertTriangle size={28} color="#f85149" style={{ flexShrink: 0 }} />
            <div>
              <h2 style={{ fontSize: "1.15rem", fontWeight: 600, color: "#ff7b72", marginBottom: "0.5rem" }}>
                Analysis Encountered an Error
              </h2>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: "1rem" }}>
                {session.error || session.progress?.message || "An unknown error occurred during PR review processing."}
              </p>

              {/* Graceful Error Guidance (Phase 9) */}
              {(session.error?.toLowerCase().includes("ollama") ||
                session.error?.toLowerCase().includes("11434") ||
                session.error?.toLowerCase().includes("connection refused")) && (
                <div
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    padding: "0.85rem 1rem",
                    borderRadius: "6px",
                    marginBottom: "1.25rem",
                    borderLeft: "3px solid #d29922",
                    fontSize: "0.82rem",
                  }}
                >
                  <strong style={{ color: "#d29922" }}>Troubleshooting Ollama:</strong>
                  <div style={{ marginTop: 4, color: "var(--text-primary)" }}>
                    Ensure the local Ollama daemon is active (`ollama serve`) and the generation model is pulled (`ollama pull granite3-dense:2b`).
                  </div>
                </div>
              )}

              {(session.error?.toLowerCase().includes("github_token") ||
                session.error?.toLowerCase().includes("401") ||
                session.error?.toLowerCase().includes("token")) && (
                <div
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    padding: "0.85rem 1rem",
                    borderRadius: "6px",
                    marginBottom: "1.25rem",
                    borderLeft: "3px solid #d29922",
                    fontSize: "0.82rem",
                  }}
                >
                  <strong style={{ color: "#d29922" }}>Troubleshooting GitHub Token:</strong>
                  <div style={{ marginTop: 4, color: "var(--text-primary)" }}>
                    Verify that `GITHUB_TOKEN` is set in your `.env` file with `repo` and `write:discussion` permissions.
                  </div>
                </div>
              )}

              {(session.error?.toLowerCase().includes("diff is empty") ||
                session.error?.toLowerCase().includes("404")) && (
                <div
                  style={{
                    backgroundColor: "var(--bg-tertiary)",
                    padding: "0.85rem 1rem",
                    borderRadius: "6px",
                    marginBottom: "1.25rem",
                    borderLeft: "3px solid #d29922",
                    fontSize: "0.82rem",
                  }}
                >
                  <strong style={{ color: "#d29922" }}>Troubleshooting PR URL:</strong>
                  <div style={{ marginTop: 4, color: "var(--text-primary)" }}>
                    Ensure the Pull Request exists, is accessible with your GitHub Token, and contains modified files.
                  </div>
                </div>
              )}

              <div style={{ display: "flex", gap: "0.75rem" }}>
                <Link href="/" className="btn btn-secondary">
                  Back to Dashboard
                </Link>
                <button
                  type="button"
                  onClick={() => router.push("/review/demo-pr-1")}
                  className="btn btn-primary"
                >
                  ⚡ Try Staged Demo PR Instead
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STATE 3: COMPLETE */}
      {session.status === "complete" && session.result && (
        <div>
          {/* Top Section: Risk Score + Executive Summary */}
          <div className="grid-2" style={{ marginBottom: "1.5rem" }}>
            <RiskScore score={session.result.risk_score} />

            <div className="card" style={{ margin: 0, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
              <div>
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: "0.4rem" }}>
                  EXECUTIVE SUMMARY
                </div>
                <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: "0.75rem" }}>
                  {session.result.summary || "No executive summary generated."}
                </p>

                {/* Key Risks */}
                {session.result.key_risks && session.result.key_risks.length > 0 && (
                  <div>
                    <div style={{ fontSize: "0.75rem", color: "#f85149", fontWeight: 600, marginBottom: "0.3rem" }}>
                      KEY RISKS DETECTED:
                    </div>
                    <ul style={{ margin: 0, paddingLeft: "1.2rem", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                      {session.result.key_risks.map((risk, idx) => (
                        <li key={idx} style={{ marginBottom: "0.2rem" }}>
                          {risk}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              <div style={{ marginTop: "0.75rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Hunks reviewed: <strong>{session.result.hunk_count || 1}</strong> • Total findings: <strong>{allFindings.length}</strong>
              </div>
            </div>
          </div>

          {/* Findings Filter Bar */}
          <div className="card" style={{ marginBottom: "1.5rem" }}>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "1rem",
                marginBottom: "1rem",
              }}
            >
              <FindingsSummary
                findings={allFindings}
                selectedSeverity={selectedSeverity}
                onSelectSeverity={setSelectedSeverity}
                selectedCategory={selectedCategory}
                onSelectCategory={setSelectedCategory}
              />

              {/* Text Search */}
              <div style={{ minWidth: 220 }}>
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.4rem", fontWeight: 600 }}>
                  SEARCH FINDINGS
                </div>
                <div style={{ position: "relative" }}>
                  <input
                    type="text"
                    placeholder="Search file, title, or fix..."
                    className="input"
                    value={filterText}
                    onChange={(e) => setFilterText(e.target.value)}
                    style={{ fontSize: "0.8rem", padding: "0.35rem 0.65rem 0.35rem 1.85rem" }}
                  />
                  <Search
                    size={13}
                    style={{ position: "absolute", left: "0.6rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}
                  />
                </div>
              </div>
            </div>

            {/* View Mode Toggle: Diff Viewer vs Findings List */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                borderTop: "1px solid var(--border-color)",
                paddingTop: "0.75rem",
              }}
            >
              <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                Showing <strong>{filteredFindings.length}</strong> of <strong>{allFindings.length}</strong> finding(s)
                {(selectedSeverity || selectedCategory || filterText) && (
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedSeverity(null);
                      setSelectedCategory(null);
                      setFilterText("");
                    }}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "var(--accent-blue)",
                      marginLeft: "0.75rem",
                      cursor: "pointer",
                      fontSize: "0.8rem",
                    }}
                  >
                    Reset filters
                  </button>
                )}
              </div>

              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  type="button"
                  onClick={() => setActiveTab("diff")}
                  className={`btn ${activeTab === "diff" ? "btn-primary" : "btn-secondary"}`}
                  style={{ fontSize: "0.75rem", padding: "0.3rem 0.65rem" }}
                >
                  Interactive Diff View
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("list")}
                  className={`btn ${activeTab === "list" ? "btn-primary" : "btn-secondary"}`}
                  style={{ fontSize: "0.75rem", padding: "0.3rem 0.65rem" }}
                >
                  Findings List ({filteredFindings.length})
                </button>
              </div>
            </div>
          </div>

          {/* MAIN VIEW CONTENT: Tab 1 (Diff) or Tab 2 (List) */}
          {activeTab === "diff" ? (
            <div style={{ marginBottom: "2rem" }}>
              <DiffViewer
                diffText={session.result.diff_text || ""}
                findings={filteredFindings}
              />
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginBottom: "2rem" }}>
              {filteredFindings.length === 0 ? (
                <div className="card" style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
                  No findings match the current active filters.
                </div>
              ) : (
                filteredFindings.map((finding, idx) => {
                  const cardId = `finding-list-${idx}`;
                  let badgeClass = "badge-nit";
                  if (finding.severity === "Blocker") badgeClass = "badge-blocker";
                  if (finding.severity === "Major") badgeClass = "badge-major";
                  if (finding.severity === "Minor") badgeClass = "badge-minor";

                  return (
                    <div key={idx} className="card" style={{ marginBottom: 0 }}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          justifyContent: "space-between",
                          marginBottom: "0.6rem",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                          <span className={`badge ${badgeClass}`}>{finding.severity}</span>
                          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>
                            {finding.category}
                          </span>
                          <h3 style={{ fontSize: "0.95rem", fontWeight: 600 }}>{finding.title}</h3>
                        </div>

                        {finding.citation && (
                          <span className="badge badge-citation">Citation: {finding.citation}</span>
                        )}
                      </div>

                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.4rem",
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.75rem",
                          color: "var(--accent-blue)",
                          marginBottom: "0.6rem",
                        }}
                      >
                        <FileCode size={13} />
                        <span>
                          {finding.file_path || (finding as any).file || "code"}:L{finding.line_start}
                          {finding.line_end !== finding.line_start ? `-${finding.line_end}` : ""}
                        </span>
                      </div>

                      <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: "0.75rem" }}>
                        {finding.explanation}
                      </p>

                      {(finding.suggested_fix || (finding as any).suggestion) && (
                        <div
                          style={{
                            padding: "0.6rem 0.85rem",
                            backgroundColor: "var(--bg-primary)",
                            borderRadius: "6px",
                            border: "1px solid var(--border-color)",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              marginBottom: "0.3rem",
                            }}
                          >
                            <span style={{ fontSize: "0.7rem", color: "var(--accent-green)", fontWeight: 600 }}>
                              SUGGESTED REFACTOR
                            </span>
                            <button
                              type="button"
                              onClick={() => copyCode(finding.suggested_fix || (finding as any).suggestion || "", cardId)}
                              style={{
                                background: "transparent",
                                border: "none",
                                color: "var(--text-muted)",
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                gap: "0.25rem",
                                fontSize: "0.7rem",
                              }}
                            >
                              {copiedIndex === cardId ? (
                                <>
                                  <Check size={12} color="#3fb950" />
                                  <span style={{ color: "#3fb950" }}>Copied</span>
                                </>
                              ) : (
                                <>
                                  <Copy size={12} />
                                  <span>Copy</span>
                                </>
                              )}
                            </button>
                          </div>
                          <pre
                            style={{
                              margin: 0,
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.8rem",
                              color: "#e6edf3",
                              overflowX: "auto",
                            }}
                          >
                            <code>{finding.suggested_fix || (finding as any).suggestion}</code>
                          </pre>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* Repo Knowledge Corpus Panel */}
          <CorpusPanel repoOwner={prDetails?.owner} repoName={prDetails?.repo} />
        </div>
      )}
    </div>
  );
}
