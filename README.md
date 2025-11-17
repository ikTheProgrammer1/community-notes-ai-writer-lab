# Community Notes AI Writer Lab

This repo is a small but real **“lab”** for experimenting with AI-generated
Community Notes on top of X's official APIs.

The goal is **not** to automate large-scale note submission.  
The goal is to give developers a safe, transparent environment to:

- Explore how AI models (like Grok / xAI) can help draft **concise, sourced, neutral** notes.
- Understand how notes are **generated, scored, normalized, and submitted**.
- Experiment in **`test_mode` only** before doing anything in production.
- Support the mission of Community Notes: **creating a better-informed world**.

---

## What this lab gives you

- A **pipeline** that:
  - Pulls posts eligible for Community Notes via X’s APIs.
  - Generates draft notes with Grok / xAI.
  - Pre-scores them with a claim/opinion score and URL checks.
  - Optionally rewrites weak notes.
  - Submits only strong notes in `test_mode`.
  - Stores every draft, rewrite, score, and submission in SQLite.

- A **dashboard** (FastAPI + Jinja2) to inspect per-writer metrics and recent
  notes.

- A **modular design** so you can swap in your own prompts, evaluators, or
  submission logic.

The goal is to make it easy for other developers to:

- Stand up their own Community Notes “writers” quickly.
- Understand exactly how notes are generated, scored, and submitted.
- Safely debug and iterate using `test_mode` before doing anything in
  production.

---

## Quick start

### 1. Install dependencies

Using your preferred PEP 621 tool, e.g. `uv` or `pip`:

- With `uv` (recommended):

  ```bash
  uv sync

	•	Or with pip (editable install):

pip install -e .



2. Configure environment

Set these environment variables for any process that will run the lab:

Required:
	•	LAB_DATABASE_URL – optional, default: sqlite:///./lab.sqlite3
	•	X_BEARER_TOKEN – your X API bearer token (used for some endpoints)
	•	X_COMMUNITY_NOTES_ELIGIBLE_URL – fully qualified URL for “eligible for Community Notes” posts, e.g.
https://api.x.com/2/notes/search/posts_eligible_for_notes
	•	X_COMMUNITY_NOTES_SUBMIT_URL – fully qualified URL for creating Community Notes, e.g.
https://api.x.com/2/notes
	•	GROK_API_KEY – API key for Grok / xAI (or XAI_API_KEY)

Optional:
	•	GROK_API_URL – default: https://api.x.ai/v1/chat/completions
	•	GROK_MODEL – default: grok-4-fast-reasoning

OAuth1 user-context credentials (preferred for Community Notes endpoints):
	•	X_API_KEY
	•	X_API_SECRET
	•	X_ACCESS_TOKEN
	•	X_ACCESS_TOKEN_SECRET

Lab tuning:
	•	LAB_MAX_NOTES_PER_WRITER_PER_RUN – hard cap per writer per run (default: 5)
	•	LAB_DEFAULT_SUBMIT_MIN_SCORE – default submit threshold (0.0–1.0, default: 0.75)
	•	LAB_DEFAULT_REWRITE_MIN_SCORE – default rewrite window lower bound (default: 0.4)

Debugging helpers:
	•	LAB_DEBUG_NOTE_TEXT=1 – print normalized/final note text before submission.

3. Initialise the database and seed writers

Run once to create the SQLite schema and example writers:
	•	Via the module entrypoint:

python -m note_writer_lab.cli init-db
# or
uv run python -m note_writer_lab.cli init-db


	•	Or via the top-level script:

python main.py init-db



This creates the DB (default lab.sqlite3) and seeds:
	•	Grok Conservative – high submit threshold, rewrite enabled.
	•	Grok Exploratory – slightly lower threshold, no rewrite.

4. Run a single lab cycle

To run the pipeline once for all enabled writers:

python main.py run-once
# or
python -m note_writer_lab.cli run-once
# or
uv run python -m note_writer_lab.cli run-once

For each writer, this will:
	•	Pull up to max_notes_per_run eligible posts from X.
	•	Generate draft notes with Grok.
	•	Score them (claim/opinion + URL checks).
	•	Optionally rewrite weak-but-promising notes.
	•	Submit only strong notes in test_mode.
	•	Log everything (tweets, notes, scores, submissions) into SQLite.

run-once is intentionally “one shot”. You can call it on a cron,
manually, or in your own loop.

5. Start the dashboard

To explore metrics and recent notes:

python main.py serve --host 127.0.0.1 --port 8000
# or
python -m note_writer_lab.cli serve --host 127.0.0.1 --port 8000
# or
uv run python -m note_writer_lab.cli serve --host 127.0.0.1 --port 8000

Then open http://127.0.0.1:8000:
	•	Writers overview:
	•	Admission metrics (last 50 test notes): high/low score %, URL pass %.
	•	Lab metrics: average score, % ≥ submit threshold, rewrites, total notes.
	•	Recent notes: draft/rewrite text with scores and tweet links.
	•	Writer detail:
	•	The same metrics plus a longer list of recent notes.

⸻

High-level architecture

The code is centered around the note_writer_lab package:
	•	config.py – environment-driven settings (DB URL, X/Grok creds, thresholds).
	•	db.py – SQLAlchemy engine + session helpers.
	•	models.py – SQLAlchemy models for:
	•	WriterConfig – per-writer prompts/thresholds.
	•	Tweet – tweets eligible for notes.
	•	Note – drafts and rewrites.
	•	NoteScore – claim/opinion scores + URL checks.
	•	Submission – attempts to submit notes to X.
	•	grok_client.py – minimal Grok / xAI chat client.
	•	evaluator.py – heuristic or external evaluator for notes.
	•	x_client.py – wrapper around X Community Notes endpoints.
	•	tags.py – chooses info.misleading_tags enum values using Grok.
	•	lab_runner.py – orchestrates the “lab” pipeline.
	•	metrics.py – aggregates metrics for the dashboard.
	•	web.py – FastAPI app + Jinja2 templates for the dashboard.
	•	cli.py – CLI for init-db, run-once, serve.

Dashboard templates live in note_writer_lab/templates/ and use simple HTML +
inline CSS so you can customize them freely.

⸻

Data model

The main tables are defined in note_writer_lab/models.py:
	•	WriterConfig
	•	Name, description.
	•	prompt, optional rewrite_prompt.
	•	rewrite_min_score, submit_min_score.
	•	max_notes_per_run, enabled.
	•	Relationships: notes, submissions.
	•	Tweet
	•	tweet_id, author info, text, language.
	•	tweet_created_at, collected_at.
	•	Relationships: notes, submissions.
	•	Note
	•	writer_id, tweet_id.
	•	stage – "draft" or "rewrite".
	•	text.
	•	Optional parent_note_id (for rewrites).
	•	Relationships: score (NoteScore), submissions (Submission).
	•	NoteScore
	•	note_id (1–1 with Note).
	•	claim_opinion_score (float 0.0–1.0).
	•	url_pass (bool).
	•	Optional raw_payload (e.g. from real evaluate_note).
	•	Submission
	•	note_id, writer_id, tweet_id.
	•	test_mode (bool).
	•	status – "submitted" or "failed".
	•	api_response – JSON from X on success.
	•	error_message – error description on failure.

⸻

Pipeline: what happens in a run-once

The pipeline is implemented in note_writer_lab/lab_runner.py.

For each enabled writer:
	1.	Fetch eligible tweets
XClient.fetch_eligible_tweets(max_results=...) calls:
	•	GET X_COMMUNITY_NOTES_ELIGIBLE_URL with test_mode=true.
	•	Returns a list of raw tweet objects.
	2.	Upsert tweets into DB
Each tweet is converted to a Tweet row if it doesn’t already exist.
	3.	Draft note with Grok
GrokClient.generate_note:
	•	Builds a user prompt from WriterConfig.prompt.
	•	Uses a system prompt that:
	•	Emphasizes concise, neutral, well-sourced notes.
	•	Requests a single plain-English paragraph, no markdown/headings/bullets/code blocks.
	•	Calls the Grok API and returns the draft note text.
	4.	Evaluate draft
	•	NoteEvaluator.evaluate:
	•	If the official communitynotes.evaluation.evaluate_note is available,
it can be used.
	•	Otherwise, a heuristic evaluator scores the note:
	•	Penalizes subjective language.
	•	Rewards URLs, numbers, quotes.
	•	Computes claim_opinion_score in [0.0, 1.0].
	•	Computes url_pass and URL counts.
	•	A NoteScore row is created.
	5.	Optional rewrite
	•	If the draft score is below submit_min_score but above
rewrite_min_score, the lab:
	•	Builds a rewrite prompt summarizing weaknesses.
	•	Calls GrokClient.rewrite_note to produce a rewrite.
	•	Evaluates and scores the rewrite.
	•	Keeps whichever note (draft vs rewrite) has the higher score.
	6.	Decide whether to submit
For the best note, the lab checks:
	•	claim_opinion_score ≥ writer.submit_min_score
	•	url_pass == True
	•	url_count > 0
If all pass, it proceeds to submission.
	7.	Choose misleading_tags
	•	tags.choose_misleading_tags(tweet, note):
	•	Calls Grok with a JSON-only prompt to select one or more tags from the
allowed misleading_tags enum discovered from /2/notes.
	•	Filters invalid tags and falls back to ["missing_important_context"]
on errors.
	8.	Normalize and validate note text
	•	XClient._normalize_note_text:
	•	Flattens multi-line markdown output into a single paragraph.
	•	Strips headings (### Claim, Claim:, Sources:).
	•	Strips bullets and numbered lists.
	•	Simplifies markdown links [label](https://example.com) into
label (https://example.com).
	•	Text is truncated to ≤280 characters, preserving the first URL when
possible.
	•	_validate_note_text_for_submission checks:
	•	1–280 characters.
	•	Single paragraph (no \n).
	•	Contains at least one https?:// URL.
	•	No obvious markdown headings/bullets or link syntax.
	•	If validation fails, the lab raises an error and records a "failed"
Submission with the error message.
	9.	Submit to /2/notes
	•	XClient.submit_note builds a payload like:

{
  "info": {
    "classification": "misinformed_or_potentially_misleading",
    "misleading_tags": ["missing_important_context"],
    "text": "<normalized note text>",
    "trustworthy_sources": true
  },
  "post_id": "<tweet id>",
  "test_mode": true
}


	•	Uses OAuth1 user-context auth to call X_COMMUNITY_NOTES_SUBMIT_URL.
	•	On success, stores the JSON response in Submission.api_response.
	•	On HTTP error, stores the error string and any response body in
Submission.error_message.

	10.	Record submission
	•	A Submission row is created with:
	•	status = "submitted" on success.
	•	status = "failed" on exceptions.

This entire flow runs once per enabled writer per run-once invocation.

⸻

Using the CLI

The CLI lives in note_writer_lab/cli.py and has three commands:
	•	init-db – create the DB and seed example writers.
	•	run-once – run a single lab cycle for all writers.
	•	serve – run the dashboard with Uvicorn.

Examples:

# Initialize DB
python -m note_writer_lab.cli init-db

# Run the lab pipeline once
python -m note_writer_lab.cli run-once

# Start the dashboard
python -m note_writer_lab.cli serve --host 127.0.0.1 --port 8000

You can also use the wrapper main.py:

python main.py init-db
python main.py run-once
python main.py serve --host 127.0.0.1 --port 8000

Or uv:

uv run python -m note_writer_lab.cli run-once
uv run python -m note_writer_lab.cli serve --host 127.0.0.1 --port 8000


⸻

Extending and customizing

Some common extension points:
	•	Custom prompts per writer
	•	Modify WriterConfig.prompt and rewrite_prompt in the DB via SQL or a
small admin script.
	•	The prompts already support string formatting with:
	•	{tweet_text}, {tweet_id}, {author_handle}.
	•	Plug in the official evaluator
	•	If you have X’s official communitynotes.evaluation.evaluate_note
available, NoteEvaluator will automatically try to load and use it.
	•	The heuristic is only a fallback; you can adapt _evaluate_with_external
to your local evaluator’s API.
	•	Adjust thresholds
	•	Per-writer: rewrite_min_score, submit_min_score, max_notes_per_run.
	•	Global defaults: LAB_MAX_NOTES_PER_WRITER_PER_RUN,
LAB_DEFAULT_SUBMIT_MIN_SCORE, LAB_DEFAULT_REWRITE_MIN_SCORE.
	•	Change how misleading tags are chosen
	•	note_writer_lab/tags.py currently uses Grok with a JSON contract.
	•	You can:
	•	Add simple rules before/after the LLM.
	•	Switch to a pure-heuristic approach if you prefer.
	•	Explore submission behavior
	•	The docs notes_integration_status.md, notes_submission_issue.md,
submit_note_payload_issue.md, and note_output_contract.md capture
the API behavior and debugging steps taken.
	•	They’re useful references if you want to experiment deeper with
/2/notes.

⸻

Notes and caveats
	•	The lab is designed to run in test_mode against /2/notes.
You should treat it as a safe experimentation harness, not a production system,
until you are comfortable with its behavior.
	•	The heuristic evaluator currently drives claim_opinion_score unless you
plug in the official evaluator.
	•	The output contract for note text is enforced both at the prompt level
(Grok prompts) and at the submission level (_normalize_note_text +
_validate_note_text_for_submission) to avoid sending markdown-heavy or
structurally invalid notes to the API.

If you are integrating this into your own tools or need to change deeper
behavior (DB schema, submission logic, etc.), the sections above should give
you a roadmap of which modules to adjust.

