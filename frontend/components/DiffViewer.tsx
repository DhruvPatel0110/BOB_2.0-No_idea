"use client";

import React, { useState, useMemo } from "react";
import { Finding } from "@/lib/types";
import { FileCode, AlertOctagon, ChevronDown, ChevronRight, Copy, Check } from "lucide-react";

interface DiffViewerProps {
  diffText: string;
  findings: Finding[];
}

interface ParsedLine {
  type: "header" | "add" | "del" | "context";
  content: string;
  oldLineNumber?: number;
  newLineNumber?: number;
  finding?: Finding;
}

interface ParsedFile {
  path: string;
  lines: ParsedLine[];
}

export default function DiffViewer({ diffText, findings }: DiffViewerProps) {
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});
  const [copiedIndex, setCopiedIndex] = useState<string | null>(null);

  const toggleCard = (id: string) => {
    setExpandedCards((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const copyCode = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(id);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  // Parse raw unified diff into structured file & lines
  const parsedFiles = useMemo(() => {
    if (!diffText) return [];

    const lines = diffText.split("\n");
    const files: ParsedFile[] = [];
    let currentFile: ParsedFile | null = null;
    let oldLine = 0;
    let newLine = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // New file boundary
      if (line.startsWith("diff --git") || line.startsWith("--- a/")) {
        const match = line.match(/(?:b\/|--- a\/)(.+)$/);
        const path = match ? match[1].replace(/^[ab]\//, "") : "unknown_file";
        currentFile = { path, lines: [] };
        files.push(currentFile);
        continue;
      }

      if (line.startsWith("+++ b/")) {
        if (currentFile) {
          currentFile.path = line.replace("+++ b/", "");
        }
        continue;
      }

      // Hunk header: @@ -old,len +new,len @@
      if (line.startsWith("@@")) {
        const hunkMatch = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
        if (hunkMatch) {
          oldLine = parseInt(hunkMatch[1], 10);
          newLine = parseInt(hunkMatch[2], 10);
        }
        if (currentFile) {
          currentFile.lines.push({
            type: "header",
            content: line,
          });
        }
        continue;
      }

      if (!currentFile) {
        // Fallback for single file diff without standard git headers
        currentFile = { path: "Diff View", lines: [] };
        files.push(currentFile);
      }

      let type: ParsedLine["type"] = "context";
      let oNum: number | undefined = undefined;
      let nNum: number | undefined = undefined;

      if (line.startsWith("+")) {
        type = "add";
        nNum = newLine++;
      } else if (line.startsWith("-")) {
        type = "del";
        oNum = oldLine++;
      } else {
        type = "context";
        oNum = oldLine++;
        nNum = newLine++;
      }

      // Check if this line is anchored to any finding
      const lineFinding = findings.find((f) => {
        const fp = f.file_path || (f as any).file || "";
        const cp = currentFile?.path || "";
        const fileMatches =
          !fp || !cp
            ? true
            : fp === cp || cp.endsWith(fp) || fp.endsWith(cp);
        return (
          fileMatches &&
          ((f.line_start === nNum && nNum !== undefined) ||
            (f.line_start === oNum && oNum !== undefined))
        );
      });

      currentFile.lines.push({
        type,
        content: line,
        oldLineNumber: oNum,
        newLineNumber: nNum,
        finding: lineFinding,
      });
    }

    return files;
  }, [diffText, findings]);

  if (!parsedFiles.length) {
    return (
      <div className="card" style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>
        No diff content available for review.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {parsedFiles.map((file, fileIdx) => {
        const fileFindings = findings.filter((f) => {
          const fp = f.file_path || (f as any).file || "";
          const cp = file.path || "";
          return !fp || !cp ? true : fp === cp || cp.endsWith(fp) || fp.endsWith(cp);
        });

        return (
          <div key={fileIdx} className="diff-container">
            {/* File Header */}
            <div className="diff-file-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <FileCode size={16} color="var(--accent-blue)" />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem" }}>{file.path}</span>
              </div>
              <div>
                {fileFindings.length > 0 ? (
                  <span
                    className="badge badge-blocker"
                    style={{ fontSize: "0.7rem", padding: "0.15rem 0.5rem" }}
                  >
                    {fileFindings.length} Issue{fileFindings.length > 1 ? "s" : ""} Found
                  </span>
                ) : (
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Clean file</span>
                )}
              </div>
            </div>

            {/* Diff Lines */}
            <div style={{ padding: "0.5rem 0" }}>
              {file.lines.map((ln, lnIdx) => {
                const hasFinding = !!ln.finding;
                const cardKey = `finding-${fileIdx}-${lnIdx}`;
                const isExpanded = expandedCards[cardKey] ?? hasFinding; // default open for findings

                let lineClass = "";
                if (ln.type === "add") lineClass = "diff-line-add";
                if (ln.type === "del") lineClass = "diff-line-del";
                if (ln.type === "header") lineClass = "diff-line-hunk";
                if (hasFinding) lineClass += " diff-has-finding";

                return (
                  <React.Fragment key={lnIdx}>
                    <div className={`diff-line ${lineClass}`}>
                      {/* Old Line # */}
                      <span className="diff-line-num">{ln.oldLineNumber ?? ""}</span>
                      {/* New Line # */}
                      <span className="diff-line-num">{ln.newLineNumber ?? ""}</span>

                      {/* Content */}
                      <div style={{ flex: 1, paddingRight: "0.5rem" }}>
                        {ln.content}

                        {/* Inline Finding Indicator */}
                        {hasFinding && (
                          <button
                            type="button"
                            onClick={() => toggleCard(cardKey)}
                            style={{
                              marginLeft: "0.75rem",
                              background: "rgba(248, 81, 73, 0.2)",
                              border: "1px solid #ff7b72",
                              borderRadius: "4px",
                              color: "#ff7b72",
                              fontSize: "0.7rem",
                              padding: "0.1rem 0.4rem",
                              cursor: "pointer",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.25rem",
                              verticalAlign: "middle",
                            }}
                          >
                            <AlertOctagon size={12} />
                            <span>
                              [{ln.finding?.severity}] {ln.finding?.title}
                            </span>
                            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Inline Expandable Finding Card */}
                    {hasFinding && isExpanded && ln.finding && (
                      <div className="diff-finding-card">
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            marginBottom: "0.5rem",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <span
                              className={`badge ${
                                ln.finding.severity === "Blocker"
                                  ? "badge-blocker"
                                  : ln.finding.severity === "Major"
                                  ? "badge-major"
                                  : "badge-minor"
                              }`}
                            >
                              {ln.finding.severity}
                            </span>
                            <span style={{ fontWeight: 600, fontSize: "0.9rem", color: "var(--text-primary)" }}>
                              {ln.finding.title}
                            </span>
                          </div>

                          {/* Citation Tag */}
                          {ln.finding.citation && (
                            <span className="badge badge-citation" title="Grounding reference retrieved via PRISM RAG">
                              Citation: {ln.finding.citation}
                            </span>
                          )}
                        </div>

                        {/* Explanation */}
                        <p
                          style={{
                            fontSize: "0.85rem",
                            color: "var(--text-secondary)",
                            lineHeight: 1.45,
                            marginBottom: "0.6rem",
                          }}
                        >
                          {ln.finding.explanation}
                        </p>

                        {/* Suggested Fix */}
                        {ln.finding.suggested_fix && (
                          <div
                            style={{
                              marginTop: "0.5rem",
                              padding: "0.5rem 0.75rem",
                              backgroundColor: "var(--bg-primary)",
                              borderRadius: "4px",
                              border: "1px solid var(--border-color)",
                            }}
                          >
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                marginBottom: "0.25rem",
                              }}
                            >
                              <span style={{ fontSize: "0.7rem", color: "var(--accent-green)", fontWeight: 600 }}>
                                SUGGESTED FIX
                              </span>
                              <button
                                type="button"
                                onClick={() => copyCode(ln.finding?.suggested_fix || "", cardKey)}
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
                                {copiedIndex === cardKey ? (
                                  <>
                                    <Check size={12} color="#3fb950" />
                                    <span style={{ color: "#3fb950" }}>Copied!</span>
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
                              <code>{ln.finding.suggested_fix}</code>
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
