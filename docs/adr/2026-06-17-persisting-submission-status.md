```
Title: Persisting submission status
Owner: Will May
Collaborator(s):
Created on: 2026-06-17
Status: Draft
Finalised on:
```

## Overview

A submission's status had always been calculated dynamically each time it was read. This ADR covers the decision to persist it to a column on the `Submission` model and read that column directly, prompted by a production incident in which dynamic calculation made Deliver's "list submissions" page fall over under load.

## What is the current state?

Status is stored in a non-nullable `Submission.status` enum column, added as nullable in migration `062`, backfilled, then made `NOT NULL` in `063`. The `status` property on `SubmissionHelper` now proxies the stored column instead of recomputing.

All writes go through `SubmissionHelper`, which recomputes via `_calculate_submission_status()` and persists on every state-changing action (answer add/edit/remove, and key submission events such as completing a form or certifying). The helper's docstring already held this responsibility: any change to a submission should go through it.

Deliver's list-submissions route now reads `Submission.status` directly through a single column-projected query rather than building a helper per submission. `_calculate_submission_status()` still exists but runs only on writes and via the recompute command. `AllSubmissionsHelper`, which previously loaded every submission in full for this page, is no longer used by the list view (it remains in use by the CSV/JSON export endpoint).

Persistence was introduced in [PR #1681](https://github.com/communitiesuk/funding-service/pull/1681) (`c1feabb`, 2026-06-03), reading from the column in [PR #1687](https://github.com/communitiesuk/funding-service/pull/1687), with a follow-up query optimisation in [PR #1691](https://github.com/communitiesuk/funding-service/pull/1691).

## Why are we changing?

Calculating status on read was CPU-intensive: per submission it looped over every form and walked all components, evaluating visibility conditions and answer-completeness. The old list endpoint did this for every row, on top of `AllSubmissionsHelper` eagerly loading each submission's full data and related entities.

On 2026-06-01 the Local Regeneration Fund report - 206 submissions, each with over 100 questions - caused the list-submissions page to take over two minutes to load. A single long-running request tied up a whole instance for its full duration, so responses slowed and timed out across all users of Deliver and Access Grant Funding. The page was temporarily disabled for reports with over 100 submissions while the fix was built. Persisting status removes the per-read recomputation cost.

## What are the key risks to manage or mitigate?

### Drift between stored and computed status

This is the central trade-off. Dynamic calculation was derived from source data at read time and so could never drift; a stored column can diverge from what `_calculate_submission_status()` would produce.

Two mitigations exist in the code, the second only partial. First, event-driven writes: every mutation routes through SubmissionHelper, which recomputes and persists on each answer change and key event, keeping the column in sync. Second, a recompute command (refresh-status-for-multi-submissions, evolved from the original backfill command) that reloads submissions, recomputes, and writes the result back, preserving updated_at_utc and defaulting to a dry run. It covers only reports that allow multiple submissions, so single-submission reports rely on the event-driven writes alone.

The residual risk is that there is no automatic periodic reconciliation - correction relies on the event-driven writes, plus the manually-run command for multi-submission reports only. If any status-affecting state could change without going through SubmissionHelper, the column could silently drift. That no such path exists has not been exhaustively verified, and is worth confirming.
