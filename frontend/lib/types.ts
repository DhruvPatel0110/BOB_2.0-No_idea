/**
 * types.ts — TypeScript interfaces for PRISM Frontend.
 * Aligned with backend Pydantic models.
 */

export type Severity = "Blocker" | "Major" | "Minor" | "Nit";
export type Category = "security" | "logic" | "maintainability" | "style" | "tests";

export interface Finding {
  id?: string;
  severity: Severity;
  category: Category;
  title: string;
  file_path?: string;
  file?: string;
  line_start: number;
  line_end: number;
  explanation: string;
  suggested_fix?: string | null;
  suggestion?: string | null;
  citation?: string | null;
}

export interface PRMetadata {
  title?: string;
  author?: string;
  base?: string;
  head?: string;
  files?: string[];
  number?: number;
  url?: string;
  [key: string]: any;
}

export interface ReviewResult {
  pr_url: string;
  risk_score: number;
  summary: string;
  key_risks?: string[];
  findings: Finding[];
  findings_by_severity?: Record<string, number>;
  findings_by_category?: Record<string, number>;
  hunk_count?: number;
  pr_meta?: PRMetadata;
  diff_text?: string;
  file_contents?: Record<string, string>;
  duration_s?: number;
  [key: string]: any;
}

export interface ReviewProgress {
  stage: string;
  message: string;
  percent?: number;
}

export interface ReviewSession {
  review_id: string;
  status: "processing" | "complete" | "failed";
  pr_url: string;
  created_at: number;
  completed_at?: number | null;
  progress?: ReviewProgress | null;
  result?: ReviewResult | null;
  error?: string | null;
}

export interface HealthStatus {
  all_ok: boolean;
  ollama: {
    ok: boolean;
    reachable?: boolean;
    gen_model?: string;
    embed_model?: string;
    error?: string | null;
  };
  chromadb: {
    ok: boolean;
    path?: string;
    error?: string | null;
  };
  github: {
    ok: boolean;
    authenticated_as?: string;
    error?: string | null;
  };
}

export interface CollectionStat {
  name: string;
  count: number;
  ok: boolean;
  error?: string | null;
}

export interface CorpusStatus {
  collections: Record<string, CollectionStat>;
  cold_start_loaded: boolean;
  persist_dir: string;
}

export interface PostReviewResponse {
  status: string;
  dry_run: boolean;
  pr_url: string;
  findings_count: number;
  message: string;
}
