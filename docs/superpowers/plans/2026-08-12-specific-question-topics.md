# Specific Question Topics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace broad subject labels with concrete question topics and make the result/PDF wording useful and accurate.

**Architecture:** The school catalog remains the source of truth for a question's topic. The validator blocks broad subject names; scoring uses the resulting concrete topics. The Mini App distinguishes a repeat recommendation from a supported topic-level conclusion, and the report renders frozen expected answers independently of a missing user answer.

**Tech Stack:** Python 3.11, Pydantic, pytest, TypeScript, React, Vitest, ReportLab.

## Global Constraints

- Preserve all project text as UTF-8 without BOM.
- Never expose `correct` in public catalog payloads.
- Do not modify existing completed attempt snapshots.
- Use test-first RED/GREEN cycles for production behavior.

---

### Task 1: Block broad subject labels in the catalog

**Files:**
- Modify: `scripts/validate_school.py`
- Modify: `tests/test_validate_school.py`

- [ ] Write a failing validator test with `topic = "Математика"` that expects `ERROR topic_too_broad`.
- [ ] Run the focused pytest test and observe the failure.
- [ ] Add a fixed set of prohibited broad labels and emit one deterministic error per offending question.
- [ ] Run the focused validator tests and confirm green.

### Task 2: Add concrete topics to every catalog question

**Files:**
- Modify: `school/diagnostics/*.json`
- Test: `scripts/validate_school.py`

- [ ] Create the 178-question topic map from question identifiers to a specific school skill.
- [ ] Apply the map only to current broad-topic questions.
- [ ] Run the school validator and confirm zero broad labels and all assets resolve.

### Task 3: Make result wording proportional to evidence

**Files:**
- Modify: `miniapp/app/result-flow-model.ts`
- Modify: `miniapp/app/result-flow-model.test.ts`
- Modify: `miniapp/app/result-flow.tsx`

- [ ] Write a failing unit test for one-question weak evidence returning `Стоит повторить тему «…»`.
- [ ] Run the focused Vitest test and observe the failure.
- [ ] Add a pure evidence-aware topic recommendation helper and consume it in the result screen.
- [ ] Rename the partial-diagnostic copy to `Что вошло в диагностику`.
- [ ] Run focused and full Mini App tests.

### Task 4: Preserve correct answers in reports

**Files:**
- Modify: `backend/diagnostic/report.py`
- Modify: `backend/diagnostic/report_layout.py`
- Modify: `tests/test_report.py`

- [ ] Write a failing PDF test with missing `user_answer` and a known `expected_answer`.
- [ ] Run the focused pytest test and observe the failure.
- [ ] Ensure report generation uses only `Не отвечено` for the user column, preserves the frozen expected value in the correct-answer column, and renders only stored verified learning text rather than a URL.
- [ ] Render a representative PDF, extract text, and inspect page images.
- [ ] Run relevant Python report/API tests.

### Task 5: Release and verify

**Files:**
- No new source files.

- [ ] Run school validation, Python tests, Mini App unit tests and production build.
- [ ] Build one full deployment package, back up the live release, deploy backend/Mini App/catalog/assets together, and check health plus a public question asset.
- [ ] Commit only the catalog, validator, UI/PDF changes, tests and this approved spec/plan.
