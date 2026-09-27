/**
 * api.ts — HTTP client for PRISM backend REST API.
 */

import {
  ReviewSession,
  HealthStatus,
  CorpusStatus,
  PostReviewResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const method = options?.method || "GET";
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options?.headers || {}),
      },
    });

    if (!res.ok) {
      let errMessage = `HTTP ${res.status}`;
      try {
        const errData = await res.json();
        errMessage = errData.detail || errData.error || errMessage;
      } catch {
        // ignore
      }
      console.warn(`[PRISM API] ${method} ${url} failed ->`, errMessage);
      throw new Error(errMessage);
    }

    return res.json();
  } catch (err: any) {
    if (err.message?.includes("Failed to fetch")) {
      console.error(`[PRISM API] Connection error: Backend is unreachable at ${url}. Ensure FastAPI server is running on port 8000.`);
    }
    throw err;
  }
}

export async function submitReviewAnalysis(
  prUrl: string,
  postComments = false,
  languageHint?: string
): Promise<{ review_id: string; status: string; message: string }> {
  return fetchJson(`${API_BASE}/review/analyze`, {
    method: "POST",
    body: JSON.stringify({
      pr_url: prUrl,
      post_comments: postComments,
      language_hint: languageHint || null,
    }),
  });
}

export async function getReviewSession(reviewId: string): Promise<ReviewSession> {
  return fetchJson<ReviewSession>(`${API_BASE}/review/${reviewId}`);
}

export async function getAllReviews(): Promise<ReviewSession[]> {
  return fetchJson<ReviewSession[]>(`${API_BASE}/review`);
}

export async function postReviewComments(
  reviewId: string,
  dryRun = true
): Promise<PostReviewResponse> {
  return fetchJson<PostReviewResponse>(`${API_BASE}/review/${reviewId}/post`, {
    method: "POST",
    body: JSON.stringify({ dry_run: dryRun }),
  });
}

export async function getSystemHealth(): Promise<HealthStatus> {
  return fetchJson<HealthStatus>(`${API_BASE}/health`);
}

export async function getCorpusStatus(owner?: string, repo?: string): Promise<CorpusStatus> {
  const query = new URLSearchParams();
  if (owner) query.set("owner", owner);
  if (repo) query.set("repo", repo);
  const qStr = query.toString() ? `?${query.toString()}` : "";
  return fetchJson<CorpusStatus>(`${API_BASE}/corpus/status${qStr}`);
}

export async function triggerCorpusBuild(
  owner: string,
  repo: string,
  forceRebuild = false
): Promise<any> {
  return fetchJson(`${API_BASE}/corpus/build`, {
    method: "POST",
    body: JSON.stringify({
      owner,
      repo,
      force_rebuild: forceRebuild,
    }),
  });
}
