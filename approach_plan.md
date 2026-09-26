# Approach Plan — AI Code Review Coach
### IBM Bob 2.0 Hackathon (Sep 25–27, 2026)

> **Note to Bob:** This document defines *what* to build and *why*. You (Bob) own the architecture, tech stack choices, and implementation. Wherever this doc says "suggested," treat it as a recommendation to override if you find a better approach — especially on datasets (see Section 5).

---

## 1. Problem Statement

Code review is a major bottleneck in developer workflows — reviewers spend hours reading diffs, catching the same style/security/logic issues repeatedly, and PR authors wait hours-to-days for feedback. This project builds an AI-powered code review assistant that reduces manual review effort, catches issues earlier, and speeds up the path from PR opened → PR merged, directly matching the hackathon's "developer workflow" and "reduce manual effort, errors, and rework" goals.

Maps to the official use case: **"Intelligent code review and quality coach."**

---

## 2. Core Features

1. **PR Ingestion**
   - Accepts a GitHub PR URL (or repo + branch) as input.
   - Pulls the diff, list of changed files, and full file contents for changed files (not just the hunk — needed for context).

2. **Diff Analysis Engine**
   - Breaks the PR into per-file / per-hunk chunks.
   - Runs each chunk through IBM Bob with a review-specific prompt, checking for:
     - Security issues (SQL injection, XSS, hardcoded secrets/API keys, OWASP-referenced weak practices)
     - Logic errors / null pointer risks / race conditions
     - Code smells & maintainability issues
     - Style/convention violations (naming, formatting, structure)
     - Missing or weak test coverage for the change

3. **Severity-Tagged Review Comments**
   - Each finding gets a severity label (Blocker / Major / Minor / Nit) and a plain-English explanation of *why* it matters, not just *what's* wrong.
   - Comments are anchored to the specific line/hunk, like a human reviewer would leave them.

4. **PR Summary Generation**
   - Auto-generates a one-paragraph summary of what the PR does and a bullet list of key risks, for reviewers who want a fast overview before diving into line comments.

5. **Review Comment Posting**
   - Posts findings directly back as PR review comments (via GitHub API/MCP — see Section 4), so it slots into the existing GitHub review workflow rather than living in a separate dashboard the team has to remember to check.

6. **Dashboard / Results View**
   - A simple UI showing: overall risk score for the PR, breakdown of findings by category and severity, and a diff viewer with inline annotations.
   - This is the primary demo surface for judges.

7. **Convention-Aware Feedback (this is the differentiator)**
   - Instead of generic "this could be cleaner" AI feedback, comments are grounded in *this specific project's* actual conventions and past review history (see RAG section below). This is what separates a "quality coach" from a linter with an LLM wrapper.

8. **Stretch features (only if time allows, in priority order)**
   - One-click "apply suggested fix" for simple findings (formatting, null checks).
   - Historical trend view: "this type of issue has appeared in 6 of the last 20 PRs from this repo" — signals a recurring team weak spot.
   - Slack/Discord notification with PR summary once review completes.

---

## 3. How It Functions End-to-End (for the demo)

1. User pastes a GitHub PR link into the tool.
2. Tool fetches the diff + changed files.
3. For each changed hunk: retrieve relevant context (style guide snippet, similar past-reviewed code, relevant docs) → inject into the review prompt → Bob generates findings.
4. Findings are aggregated, deduplicated, and severity-ranked.
5. Summary + annotated diff shown in the dashboard.
6. On confirmation, findings are posted as real PR comments on GitHub (demo this on a controlled/sandbox repo, same safety approach TestForge Pro used at the May hackathon — simulate on other repos, real posting only on a designated demo repo).

---

## 4. Optional: RAG Pipeline (suggested, not required)

**Why:** Grounds review comments in the *actual* project's conventions instead of generic LLM opinions — this is the single biggest quality differentiator versus a plain "send diff to LLM" approach.

**Suggested corpus to embed:**
- The target repo's own style guide / CONTRIBUTING.md / linter config, if present.
- Past merged PRs' review comment threads from the same repo (real precedent — "we've asked for this exact fix before").
- A general code-review dataset for cold-start grounding when a repo has no history yet (see Section 5).

**Suggested flow:**
- Chunk + embed the corpus above into a vector store.
- On each diff hunk, retrieve top-k relevant snippets (style rule, similar past comment, etc.) and inject them into the review prompt as grounding context.
- This also lets the tool *cite* why it's flagging something ("per this repo's style guide, section X" / "similar issue was flagged in PR #42") — a nice visible feature for judges.

## 5. Optional: MCP Server Linking (suggested, not required)

**Why:** Turns this from a one-off script into something that lives inside the real GitHub review workflow.

**Suggested MCP usage:**
- **GitHub MCP server** — the core one. Use it to: fetch PR diffs and changed files, read repo file contents for context, read past PR review comment threads (for the RAG corpus above), and post review comments/PR reviews back to GitHub.
- **Filesystem MCP** (optional) — only needed if demoing against a locally cloned repo rather than pulling live from GitHub.
- **Notification MCP (Slack/Discord)** (optional, stretch) — post a PR-ready summary to a channel once review completes.

If Bob's environment already exposes a GitHub-connected MCP/tool, prefer that over a custom API integration to save build time.

---

## 6. Datasets

**Bob: please also independently search for additional or better-fitting datasets — the ones below are a starting point, not the final word. In particular, look for anything more recent, better license terms, or closer to whatever language/stack the demo repo ends up being in.**

1. **CodeReviewer dataset + model (Microsoft)** — the primary reference dataset for this project. Large-scale, multilingual (9 languages), real GitHub PR diffs paired with real review comments, plus a pretrained model for three sub-tasks: code change quality estimation, review comment generation, and code refinement.
   - Paper: https://arxiv.org/abs/2203.09095
   - Code + dataset: https://github.com/microsoft/CodeBERT/tree/master/CodeReviewer
   - Model card: https://huggingface.co/microsoft/codereviewer

2. **Methods2Test (Microsoft)** — 780,944 JUnit test ↔ focal method pairs from 91,385 Java GitHub repos. Useful if you build out the "missing test coverage" finding category.
   - Paper: https://arxiv.org/abs/2203.12776
   - Dataset: https://github.com/microsoft/methods2test
   - Smaller preprocessed version: https://huggingface.co/datasets/andstor/methods2test_small

3. **Live data (no dataset needed)** — for the actual demo, real-time PR diffs pulled from a real or sandbox GitHub repo via the GitHub API/MCP are more convincing to judges than static dataset examples. Use the datasets above for grounding/RAG and for any offline evaluation of finding quality, not as the demo's live input.

---

## 7. Competitive Note (why this angle, not the others)

From the May 2026 IBM Bob hackathon: onboarding-assistant and legacy-modernization projects placed 1st and 2nd and have several near-duplicate entries already, making them high-risk for this round. Code review had one entry (PRISM, 4th place) but is far less saturated. This plan intentionally targets that gap while staying within the official "Intelligent code review and quality coach" use case.
