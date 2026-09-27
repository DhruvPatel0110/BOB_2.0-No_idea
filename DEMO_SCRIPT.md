# 🎤 PRISM — Hackathon Live Demo Script (Judge-Ready)
### IBM Bob 2.0 Hackathon: Intelligent Code Review & Quality Coach

---

## 🎯 60-Second Elevator Pitch (Start with this)

> *"Hi judges, this is **PRISM** — our Precision Review Intelligence & Style Mentor.
> 
> Code reviews are currently a major bottleneck in engineering teams: senior engineers spend hours catching repetitive security flaws, null-pointer risks, and style deviations, while authors wait days for feedback.
> 
> Existing AI review tools are essentially just generic linters with an LLM wrapper that say 'consider adding null checks here'. 
> 
> **PRISM is different**: it is an autonomous **Quality Coach** grounded in the specific repository’s own conventions, `CONTRIBUTING.md` guidelines, and past merged PR history using local RAG and IBM Granite. And instead of living in an isolated silo, PRISM posts line-anchored review comments directly back to the GitHub Pull Request diff."*

---

## 🎬 Live 5-Step Demo Sequence (2 to 3 minutes)

### Step 1: Open Dashboard & Show System Status
- Open your browser to: **`http://localhost:3000`**
- **Point out to judges**:
  - Top Navbar: **"All Systems Operational"** badge (verifying local Ollama, ChromaDB, and GitHub API are all green).
  - Bottom panel: **Corpus Status** showing active indexed collections (`cold_start_owasp`, `cold_start_smells`, `style_dhruvpatel0110_bob_2_0-no_idea`).

### Step 2: Launch the Review
You have two great ways to present depending on demo time:
- **Option A (Instant / Fast Pitch)**:
  - Click the green button: **`⚡ View Staged Demo PR`**
  - Instantly loads the review for `DhruvPatel0110/BOB_2.0-No_idea/pull/1` with zero waiting time!
- **Option B (Live Analysis from scratch)**:
  - Click the preset `DhruvPatel0110/BOB_2.0-No_idea #1` and click **"Start Review"**.
  - Show the live progress bar and stages:
    1. *Fetching PR metadata & diff*
    2. *Syntax chunking*
    3. *RAG context retrieval*
    4. *Granite 2B generation*
    5. *PR Executive Summary & Risk Scoring*

### Step 3: Walk Through the Dashboard
- **PR Header**: Title, author, repository link, duration.
- **Risk Score Gauge**: Circular color-coded score (Green < 20, Yellow 20–50, Red > 50).
- **Executive Summary Card**:
  - One-paragraph plain English summary of what the PR does.
  - Bulleted list of top risks.
- **Severity Breakdown & Category Distribution**:
  - Highlight the tally: Blockers, Majors, Minors, Nits.

### Step 4: The "WOW" Moment — Convention-Aware RAG Citations
- Scroll down to the **Findings** or switch to the **Diff Viewer** tab.
- **Click on Finding #1 (Blocker - Raw SQL String Interpolation)**:
  - Show the explanation of why it's a security vulnerability.
  - Show the suggested fix block.
  - **HIGHLIGHT THE CITATION**:
    > **Citation:** `CONTRIBUTING.md §1.1 | OWASP A03:2021`
  - *Say to judges:* *"Notice how PRISM didn't just guess — it specifically cited Section 1.1 of this repository's CONTRIBUTING.md and OWASP Top-10 standards. That's our ChromaDB RAG grounding in action."*
- **Click on Finding #2 (Major - Unsafe Nested Dictionary Access)**:
  - Show citation: `CONTRIBUTING.md §2.1`

### Step 5: Live GitHub Comment Posting (The Closer)
- Click the blue **"Post Review to GitHub"** button at the top right of the review page.
- In the modal dialog:
  - Toggle **Dry Run** off (or run simulation first).
  - Click **"Confirm & Post"**.
  - Watch the green success confirmation: *"Successfully posted formal PR review to GitHub!"*
- Open the live GitHub Pull Request:
  👉 **[https://github.com/DhruvPatel0110/BOB_2.0-No_idea/pull/1](https://github.com/DhruvPatel0110/BOB_2.0-No_idea/pull/1)**
- **Show the judges the real GitHub review**:
  - The formal review appears in the PR timeline.
  - Both comments are anchored directly to Line 4 of `demo_sample.py` with the severity badges, suggestions, and citation tags!

---

## 💡 Key Judge Questions & Answers

**Q1: What models are you running?**  
> *"We run everything 100% locally and privately using Ollama: `granite3-dense:2b` for review generation, and `nomic-embed-text` for vector embeddings into ChromaDB."*

**Q2: What prevents the tool from hallucinating line numbers?**  
> *"Our Phase 8 diff position mapper parses the git unified diff into exact line-to-position lookup tables. If an LLM suggests a line slightly out of bounds, our line-snapping algorithm automatically clamps it to the nearest valid line in the diff hunk, preventing GitHub API 422 errors."*

**Q3: How does it get smarter over time?**  
> *"We implemented an incremental learning feedback hook in Phase 8: whenever PRISM posts review comments or when PRs are merged, those review comments are embedded and indexed back into the repository's history collection in ChromaDB, so future PR reviews can cite them as team precedent."*

**Q4: Is it safe? What if someone posts on a production repo?**  
> *"We implemented an explicit demo repository safety gate. Live posting (`dry_run: false`) is strictly restricted to designated demo repositories configured in `.env`. Any attempts to post to external public repositories like `pallets/flask` are blocked with a safe simulation mode."*
