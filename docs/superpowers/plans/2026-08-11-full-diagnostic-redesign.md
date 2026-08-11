# Full Diagnostic Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved Training Radar Mini App and Premium Workbook PDF, backed by one immutable post-completion review snapshot with user answers, expected answers, explanations, forecast, and route.

**Architecture:** Completion resolves every question into a private `review_snapshot` stored inside the existing `report_snapshot` JSONB. A new authenticated post-completion endpoint exposes a filtered display contract to the attempt owner, while the PDF generator consumes the same frozen snapshot and frozen assets. The Next.js page remains the attempt-state controller but delegates navigation, question, and result stages to focused presentational modules.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, asyncpg, ReportLab, svglib, pytest, Next.js 16, React 19, TypeScript 5.9, Vitest, Playwright, PostgreSQL 16.

## Global Constraints

- Preserve every existing uncommitted change; inspect the relevant diff before editing and stage only task-owned hunks.
- Treat every project text file as UTF-8 and preserve existing Cyrillic exactly.
- Keep `correct` and `explanation` out of bootstrap, public diagnostic types, public assets, and pre-completion HTML.
- Permit `expected_answer` in TypeScript only in the authenticated post-completion review response approved in the design.
- Keep Telegram authentication, session-scope validation, optimistic revision, tombstones, lease/retry delivery, and the eight-attempt delivery limit unchanged.
- Build old and new reports from persisted snapshots; never reconstruct a legacy result from the current catalog.
- Store new review data inside existing `report_snapshot`; do not add a database column or destructive migration.
- Keep each generated PDF below 25 MiB and each Mini App API request/response bounded by existing catalog and answer limits.
- Do not add runtime AI generation or a new external service.
- Do not commit `.superpowers/`, `.playwright-cli/`, `output/`, secrets, deployment-local files, or unrelated user changes.
- After any school content or brand change, run `scripts/validate_school.py` and `scripts/check_brand_isolation.py`.

## File Structure

### Backend domain and API

- `backend/diagnostic/review.py` — answer formatting, fallback guidance, immutable review snapshot construction, and public post-completion filtering.
- `backend/diagnostic/catalog.py` — optional bounded `explanation` and public exclusion.
- `backend/diagnostic/scoring.py` — public `is_answer_correct()` used by both scoring and review.
- `backend/diagnostic/api/sessions.py` — snapshot persistence and `/session/review` route.
- `backend/diagnostic/db/attempts.py` — private owner-scoped read of `report_snapshot`.

### PDF

- `backend/diagnostic/report_layout.py` — Premium Workbook theme, styles, summary/review/route flowable factories, and page chrome.
- `backend/diagnostic/report.py` — frozen snapshot/assets validation and report orchestration.
- `backend/diagnostic/assets/fonts/` — Forum and Manrope files plus OFL license texts.

### Mini App

- `miniapp/app/navigation-screens.tsx` — welcome, mode, and subject screens.
- `miniapp/app/question-screen.tsx` — question renderer and four answer formats.
- `miniapp/app/result-flow.tsx` — result, review, forecast, and personal route screens.
- `miniapp/app/result-flow-model.ts` — pure forecast, route, PDF-status, and review helpers.
- `miniapp/app/page.tsx` — attempt/network state controller and stage transitions.
- `miniapp/app/api.ts`, `miniapp/app/types.ts` — post-completion review contract.
- `miniapp/app/globals.css` — Training Radar tokens, responsive layout, focus, and reduced motion.

### Tests and documentation

- `tests/test_review.py` — domain formatting and guidance behavior.
- Existing backend/API/PDF/config tests — persistence, privacy, ownership, legacy behavior, and rendering.
- `miniapp/app/result-flow-model.test.ts` and existing Mini App tests — pure result-flow behavior and public boundary.
- `docs/CONTENT_FORMAT.md` and importer tests — optional explanation contract.

---

### Task 1: Review domain and optional catalog explanations

**Files:**
- Create: `backend/diagnostic/review.py`
- Create: `tests/test_review.py`
- Modify: `backend/diagnostic/catalog.py:71-216,234-347`
- Modify: `backend/diagnostic/scoring.py:45-96`
- Modify: `tests/test_catalog.py:1-120`
- Modify: `tests/fixtures/sample-school/diagnostics/demo-math.json:8-13`

**Interfaces:**
- Consumes: existing `Question`, `AnswerValue` JSON shapes, and option/item labels.
- Produces: `is_answer_correct(question: Question, answer: Any) -> bool`, `format_answer(question: Question, answer: Any) -> str`, `build_review_snapshot(questions: Sequence[Question], answers: Mapping[str, Any]) -> list[dict[str, Any]]`, and `public_review_items(report_snapshot: Mapping[str, Any]) -> list[dict[str, Any]] | None`.

- [ ] **Step 1: Write failing catalog and review tests**

```python
# tests/test_review.py
from pathlib import Path

from diagnostic.catalog import load_catalog
from diagnostic.review import build_review_snapshot, public_review_items
from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests" / "fixtures" / "sample-school"


def test_review_snapshot_formats_every_question_type():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    questions = catalog.get("demo-math").questions
    snapshot = build_review_snapshot(
        questions,
        {"q1": "1", "q2": ["1", "2"], "q3": {"a": "1", "b": "2"}, "q4": "41"},
    )

    assert [item["question_id"] for item in snapshot] == ["q1", "q2", "q3", "q4"]
    assert snapshot[0]["user_answer"] == "3"
    assert snapshot[0]["expected_answer"] == "4"
    assert snapshot[2]["expected_answer"] == "2 + 2: 4; 3 + 3: 6"
    assert snapshot[3]["expected_answer"] == "42"
    assert all(item["is_correct"] is False for item in snapshot)


def test_individual_explanation_wins_and_public_review_drops_raw_values():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    questions = catalog.get("demo-math").questions
    snapshot = build_review_snapshot(questions, {"q1": "2", "q2": ["1", "3"], "q3": {"a": "2", "b": "1"}, "q4": "42"})
    payload = public_review_items({"review_snapshot": snapshot})

    assert payload is not None
    assert payload[0]["guidance_kind"] == "individual"
    assert payload[0]["guidance"] == "Сложите два и два: получится четыре."
    assert "expected_value" not in payload[0]
    assert "user_value" not in payload[0]
```

```python
# tests/test_catalog.py
def test_public_catalog_omits_explanation_and_correct():
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    payload = catalog.public_payload("secret")
    serialized = json.dumps(payload, ensure_ascii=False)
    assert '"correct"' not in serialized
    assert '"explanation"' not in serialized
```

- [ ] **Step 2: Run the new tests and verify the missing model/module failures**

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q tests/test_review.py tests/test_catalog.py -k "review or explanation"
```

Expected: collection fails because `diagnostic.review` and `QuestionBase.explanation` do not exist.

- [ ] **Step 3: Expose one scoring predicate and add the bounded private field**

```python
# backend/diagnostic/scoring.py
def is_answer_correct(question: Question, answer: Any) -> bool:
    if isinstance(question, SingleQuestion):
        return isinstance(answer, str) and answer == question.correct
    if isinstance(question, MultipleQuestion):
        return isinstance(answer, list) and sorted(answer) == sorted(question.correct)
    if isinstance(question, MatchingQuestion):
        return isinstance(answer, dict) and answer == question.correct
    normalized_answer = _normalize_decimal(answer)
    return normalized_answer is not None and any(
        normalized_answer == _normalize_decimal(variant) for variant in question.correct
    )
```

Replace the internal call in `score_answers()` with `is_answer_correct()`.

```python
# backend/diagnostic/catalog.py, QuestionBase
explanation: str | None = Field(default=None, min_length=1, max_length=2000)

@field_validator("explanation")
@classmethod
def validate_explanation(cls, value: str | None) -> str | None:
    return _validate_prompt_text(value) if value is not None else None
```

Change both public serializers to exclude the set `{"correct", "explanation"}`.

- [ ] **Step 4: Implement deterministic formatting and honest guidance**

```python
# backend/diagnostic/review.py
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from diagnostic.catalog import InputQuestion, MatchingQuestion, MultipleQuestion, Question, SingleQuestion
from diagnostic.scoring import is_answer_correct


def format_answer(question: Question, answer: Any) -> str:
    if answer is None:
        return "Не отвечено"
    options = {option.id: option.label for option in getattr(question, "options", ())}
    if isinstance(question, SingleQuestion):
        return options.get(str(answer), str(answer))
    if isinstance(question, MultipleQuestion):
        values = answer if isinstance(answer, list) else []
        return ", ".join(options.get(str(value), str(value)) for value in values) or "Не отвечено"
    if isinstance(question, MatchingQuestion):
        values = answer if isinstance(answer, Mapping) else {}
        return "; ".join(
            f"{item.label}: {options.get(str(values.get(item.id, '')), 'Не отвечено')}"
            for item in question.items
        )
    if isinstance(question, InputQuestion) and isinstance(answer, (list, tuple)):
        return " / ".join(str(value) for value in answer)
    return str(answer)


def expected_value(question: Question) -> Any:
    return deepcopy(question.correct)


def fallback_guidance(question: Question, expected_answer: str) -> str:
    if isinstance(question, MultipleQuestion):
        return f"Проверьте каждый вариант по теме «{question.topic}» отдельно и перенесите весь набор: {expected_answer}."
    if isinstance(question, MatchingQuestion):
        return f"Сопоставляйте строки по одной и сохраняйте исходный порядок. Правильная схема: {expected_answer}."
    if isinstance(question, SingleQuestion):
        return f"Примените правило темы «{question.topic}», исключите противоречащие условию варианты и выберите: {expected_answer}."
    return f"Решите задание по алгоритму темы «{question.topic}» и перенесите только итоговое значение: {expected_answer}."
```

`build_review_snapshot()` must include raw `user_value`/`expected_value` privately and display-only `user_answer`/`expected_answer`, plus `guidance_kind` equal to `individual` or `fallback`. `public_review_items()` must return `None` when no list exists and otherwise whitelist only `question_id`, `number`, `type`, `topic`, `title`, `prompt`, `asset`, `assets`, `is_correct`, `user_answer`, `expected_answer`, `guidance`, and `guidance_kind`.

- [ ] **Step 5: Add one individual fixture explanation and rerun the domain tests**

```json
{"id":"q1","type":"single","topic":"Вычисления","title":"Задание 1","prompt":"Чему равно 2 + 2?","explanation":"Сложите два и два: получится четыре.","options":[{"id":"1","label":"3"},{"id":"2","label":"4"}],"correct":"2"}
```

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q tests/test_review.py tests/test_catalog.py tests/test_scoring.py
```

Expected: all selected tests pass.

- [ ] **Step 6: Review and commit only Task 1 hunks**

```powershell
rtk git diff -- backend/diagnostic/review.py backend/diagnostic/catalog.py backend/diagnostic/scoring.py tests/test_review.py tests/test_catalog.py tests/fixtures/sample-school/diagnostics/demo-math.json
rtk git add backend/diagnostic/review.py tests/test_review.py
rtk git add -p -- backend/diagnostic/catalog.py backend/diagnostic/scoring.py tests/test_catalog.py tests/fixtures/sample-school/diagnostics/demo-math.json
rtk proxy git -c core.excludesFile=NUL diff --cached --check
rtk git commit -m "Add immutable diagnostic review domain"
```

### Task 2: Persist and serve owner-scoped post-completion reviews

**Files:**
- Modify: `backend/diagnostic/api/sessions.py:32-104,143-171,230-451`
- Modify: `backend/diagnostic/db/attempts.py:13-25,555-609`
- Modify: `tests/test_api_sessions.py:344-409`
- Modify: `tests/test_attempts_db.py:1-100,300-330`

**Interfaces:**
- Consumes: `build_review_snapshot()` and `public_review_items()` from Task 1.
- Produces: `attempts.get_review_attempt(attempt_id: str, user_id: int)`, `POST /api/diagnostics/session/review`, and response `{ok, available, items, pdf_status}`.

- [ ] **Step 1: Write failing completion and review endpoint tests**

```python
from diagnostic.api import sessions


def test_completion_freezes_review_snapshot(monkeypatch):
    stored = {}

    async def complete_attempt(completion):
        stored["snapshot"] = completion.report_snapshot
        return {
            "attempt_id": completion.attempt_id,
            "diagnostic_id": completion.diagnostic_id,
            "mode": completion.mode,
            "status": "completed",
            "pdf_status": "pending",
            "result_snapshot": completion.result_snapshot,
        }

    client = make_client(monkeypatch, complete_attempt=complete_attempt)
    response = client.post("/api/diagnostics/session/complete", json=base_completion())

    assert response.status_code == 200
    review = stored["snapshot"]["review_snapshot"]
    assert review[0]["user_answer"] == "4"
    assert review[0]["expected_answer"] == "4"
    assert review[0]["guidance_kind"] == "individual"


def test_review_endpoint_requires_owner_and_completion(monkeypatch):
    async def owned_review(_attempt_id, _user_id):
        return {"status": "completed", "pdf_status": "sent", "report_snapshot": {"review_snapshot": [{
            "question_id": "q1", "number": 1, "type": "single", "topic": "Вычисления",
            "title": "Задание 1", "prompt": "Чему равно 2 + 2?", "is_correct": False,
            "user_answer": "3", "expected_answer": "4", "guidance": "Сложите числа.",
            "guidance_kind": "individual", "user_value": "1", "expected_value": "2",
        }]}}

    monkeypatch.setattr(sessions.attempts, "get_review_attempt", owned_review)
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/session/review", json={
        "init_data": signed_init_data(), "attempt_id": "attempt_123", "session_scope": SESSION_SCOPE,
    })

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["pdf_status"] == "sent"
    assert "expected_value" not in response.text


def test_review_endpoint_returns_not_found_for_non_owner(monkeypatch):
    client = make_client(monkeypatch)
    monkeypatch.setattr(sessions.attempts, "get_review_attempt", AsyncMock(return_value=None))

    response = client.post("/api/diagnostics/session/review", json={
        "init_data": signed_init_data(), "attempt_id": "attempt_123", "session_scope": SESSION_SCOPE,
    })

    assert response.status_code == 404


def test_review_endpoint_rejects_in_progress_attempt(monkeypatch):
    client = make_client(monkeypatch)
    monkeypatch.setattr(sessions.attempts, "get_review_attempt", AsyncMock(return_value={
        "status": "in_progress", "pdf_status": None, "report_snapshot": None,
    }))

    response = client.post("/api/diagnostics/session/review", json={
        "init_data": signed_init_data(), "attempt_id": "attempt_123", "session_scope": SESSION_SCOPE,
    })

    assert response.status_code == 409
    assert response.json()["detail"] == "review_not_ready"


def test_review_endpoint_marks_legacy_snapshot_unavailable(monkeypatch):
    client = make_client(monkeypatch)
    monkeypatch.setattr(sessions.attempts, "get_review_attempt", AsyncMock(return_value={
        "status": "completed", "pdf_status": "sent", "report_snapshot": {},
    }))

    response = client.post("/api/diagnostics/session/review", json={
        "init_data": signed_init_data(), "attempt_id": "attempt_123", "session_scope": SESSION_SCOPE,
    })

    assert response.status_code == 200
    assert response.json() == {"ok": True, "available": False, "items": [], "pdf_status": "sent"}
```

Extend the `completion()` helper in `tests/test_attempts_db.py` with a
`report_snapshot: dict[str, object] | None = None` keyword and pass
`report_snapshot=report_snapshot or {}` to `AttemptCompletion`, then add:

```python
@pytest.mark.asyncio
async def test_review_read_is_owner_scoped_and_keeps_first_snapshot():
    attempt_id = f"attempt-{uuid4()}"
    first_snapshot = {"review_snapshot": [{"question_id": "q1", "expected_answer": "4"}]}
    second_snapshot = {"review_snapshot": [{"question_id": "q1", "expected_answer": "5"}]}

    await attempts.complete_attempt(completion(
        attempt_id, answers={"q1": "2"}, user_id=101, report_snapshot=first_snapshot,
    ))
    await attempts.complete_attempt(completion(
        attempt_id, answers={"q1": "3"}, user_id=101, report_snapshot=second_snapshot,
    ))

    owner_row = await attempts.get_review_attempt(attempt_id, 101)
    stranger_row = await attempts.get_review_attempt(attempt_id, 202)

    assert owner_row is not None
    assert owner_row["report_snapshot"] == first_snapshot
    assert stranger_row is None
```

- [ ] **Step 2: Run the endpoint tests and verify the missing repository/route failures**

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q tests/test_api_sessions.py -k "review or freezes_review"
```

Expected: failures mention missing `review_snapshot`, `get_review_attempt`, and `/session/review`.

- [ ] **Step 3: Freeze the resolved review during completion**

```python
# backend/diagnostic/api/sessions.py, build_completion()
selected_questions = (
    diagnostic.questions[: diagnostic.quick_count]
    if body.mode == "quick" else diagnostic.questions
)
review_snapshot = build_review_snapshot(selected_questions, body.answers)
report_snapshot = {
    "diagnostic": {
        "id": diagnostic.id,
        "subject": diagnostic.subject,
        "scoring": diagnostic.scoring.model_dump(mode="json"),
        "questions": [
            question.model_dump(mode="json", exclude={"correct", "explanation"})
            for question in selected_questions
        ],
    },
    "review_snapshot": review_snapshot,
    "mode": body.mode,
    "school": {"brand": school.brand.model_dump(mode="json"), "links": school.links.model_dump(mode="json")},
}
```

Keep `result_snapshot` public and free of review data.

- [ ] **Step 4: Add the private owner-scoped repository query**

```python
# backend/diagnostic/db/attempts.py
async def get_review_attempt(attempt_id: str, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT attempt_id, status, pdf_status, report_snapshot
              FROM diagnostic_attempts
             WHERE attempt_id=$1 AND user_id=$2
            """,
            attempt_id,
            user_id,
        )
```

Do not add `report_snapshot` to `_ATTEMPT_PUBLIC_COLUMNS`.

- [ ] **Step 5: Implement the authenticated review endpoint**

```python
@router.post("/session/review")
async def review(body: SessionRequest, request: Request) -> dict[str, Any]:
    user = telegram_user(request, body.init_data)
    await _require_current_session(request, user["id"], body.session_scope)
    row = await attempts.get_review_attempt(body.attempt_id, user["id"])
    if row is None:
        raise HTTPException(status_code=404, detail="result_not_found")
    if row["status"] != "completed":
        raise HTTPException(status_code=409, detail="review_not_ready")
    items = public_review_items(row["report_snapshot"] or {})
    return {
        "ok": True,
        "available": items is not None,
        "items": items or [],
        "pdf_status": row["pdf_status"],
    }
```

- [ ] **Step 6: Run API and idempotency tests**

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q tests/test_api_sessions.py tests/test_attempts_db.py -k "completion or review or idempotent"
```

Expected: all selected tests pass and repeated completion preserves the first snapshot.

- [ ] **Step 7: Review and commit only Task 2 hunks**

```powershell
rtk git diff -- backend/diagnostic/api/sessions.py backend/diagnostic/db/attempts.py tests/test_api_sessions.py tests/test_attempts_db.py
rtk git add -p -- backend/diagnostic/api/sessions.py backend/diagnostic/db/attempts.py tests/test_api_sessions.py tests/test_attempts_db.py
rtk proxy git -c core.excludesFile=NUL diff --cached --check
rtk git commit -m "Expose completed diagnostic reviews"
```

### Task 3: Add white-label Training Radar color roles and font assets

**Files:**
- Modify: `backend/diagnostic/school.py:266-291`
- Modify: `school/brand.json:5-9`
- Modify: `miniapp/app/types.ts:44-53`
- Modify: `tests/test_school_config.py:126-145,405-435`
- Modify: `tests/test_api_sessions.py:99-109`
- Modify: `THIRD_PARTY_NOTICES.md`
- Create: `backend/diagnostic/assets/fonts/Manrope-Regular.ttf`
- Create: `backend/diagnostic/assets/fonts/Manrope-Bold.ttf`
- Create: `backend/diagnostic/assets/fonts/Forum-Regular.ttf`
- Create: `backend/diagnostic/assets/fonts/OFL-Manrope.txt`
- Create: `backend/diagnostic/assets/fonts/OFL-Forum.txt`

**Interfaces:**
- Consumes: existing `BrandColors` and `public_school_payload()`.
- Produces: always-present `signal`, `ink`, and `paper` fields in public brand colors, with backward-compatible Pydantic defaults.

- [ ] **Step 1: Write failing compatibility and payload tests**

```python
def test_brand_color_roles_have_backwards_compatible_defaults():
    school = load_school(SAMPLE_SCHOOL)
    assert school.brand.colors.signal == "#D8FF42"
    assert school.brand.colors.ink == "#101517"
    assert school.brand.colors.paper == "#F5F5F0"


def test_public_school_payload_includes_resolved_visual_roles():
    payload = public_school_payload(load_school(SAMPLE_SCHOOL))
    assert payload["brand"]["colors"] == {
        "primary": "#5636D3",
        "accent": "#C7F36B",
        "background": "#F7F5EF",
        "signal": "#D8FF42",
        "ink": "#101517",
        "paper": "#F5F5F0",
    }
```

- [ ] **Step 2: Run config/API tests and verify the missing field failures**

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q tests/test_school_config.py tests/test_api_sessions.py -k "color_roles or visual_roles"
```

- [ ] **Step 3: Add optional validated roles and explicit MAXIMUM values**

```python
class BrandColors(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    background: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    signal: str = Field(default="#D8FF42", pattern=r"^#[0-9A-Fa-f]{6}$")
    ink: str = Field(default="#101517", pattern=r"^#[0-9A-Fa-f]{6}$")
    paper: str = Field(default="#F5F5F0", pattern=r"^#[0-9A-Fa-f]{6}$")
```

```json
"colors": {
  "primary": "#FD7E14",
  "accent": "#FF9341",
  "background": "#F5F5F5",
  "signal": "#D8FF42",
  "ink": "#101517",
  "paper": "#F5F5F0"
}
```

Update `Brand.colors` in TypeScript with the same three required response fields.

- [ ] **Step 4: Vendor the already licensed PDF fonts from the reference repository**

Copy these exact source files without text recoding:

```text
C:\Users\sheld\Documents\code\reference_diagnostic\bot\pdf_fonts\Manrope-Regular.ttf
C:\Users\sheld\Documents\code\reference_diagnostic\bot\pdf_fonts\Manrope-Bold.ttf
C:\Users\sheld\Documents\code\reference_diagnostic\bot\pdf_fonts\Forum-Regular.ttf
C:\Users\sheld\Documents\code\reference_diagnostic\bot\pdf_fonts\OFL.txt
C:\Users\sheld\Documents\code\reference_diagnostic\bot\pdf_fonts\FORUM-OFL.txt
```

The destination names are listed in **Files** above. Add Manrope and Forum entries to `THIRD_PARTY_NOTICES.md`; do not remove the existing Liberation notices because legacy and fallback rendering still depend on them.

- [ ] **Step 5: Run config, license, content, and brand checks**

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q tests/test_school_config.py tests/test_api_sessions.py tests/test_repository_hygiene.py
rtk python scripts/validate_school.py
rtk python scripts/check_brand_isolation.py
```

Expected: all tests pass and both scripts print `OK`.

- [ ] **Step 6: Review and commit only Task 3 hunks**

```powershell
rtk git diff -- backend/diagnostic/school.py school/brand.json miniapp/app/types.ts tests/test_school_config.py tests/test_api_sessions.py THIRD_PARTY_NOTICES.md
rtk git add backend/diagnostic/assets/fonts/Manrope-Regular.ttf backend/diagnostic/assets/fonts/Manrope-Bold.ttf backend/diagnostic/assets/fonts/Forum-Regular.ttf backend/diagnostic/assets/fonts/OFL-Manrope.txt backend/diagnostic/assets/fonts/OFL-Forum.txt
rtk git add -p -- backend/diagnostic/school.py school/brand.json miniapp/app/types.ts tests/test_school_config.py tests/test_api_sessions.py THIRD_PARTY_NOTICES.md
rtk proxy git -c core.excludesFile=NUL diff --cached --check
rtk git commit -m "Add diagnostic visual identity tokens"
```

### Task 4: Rebuild the PDF as a Premium Workbook

**Files:**
- Create: `backend/diagnostic/report_layout.py`
- Modify: `backend/diagnostic/report.py:1-339`
- Modify: `tests/test_report.py:1-220`

**Interfaces:**
- Consumes: `report_snapshot.review_snapshot`, `result_snapshot.forecast`, frozen school config, and frozen assets.
- Produces: the same `build_report(attempt, school, catalog=None) -> bytes` interface with new layout and a legacy branch when `review_snapshot` is absent.

- [ ] **Step 1: Write failing PDF content and pagination tests**

```python
from diagnostic.report import build_report
from diagnostic.review import build_review_snapshot


def make_review(*, prompt: str, guidance: str) -> dict[str, object]:
    return {
        "question_id": "q1", "number": 1, "type": "input", "topic": "Алгоритмы",
        "title": "Задание 1", "prompt": prompt, "is_correct": False,
        "user_answer": "12", "expected_answer": "16", "guidance": guidance,
        "guidance_kind": "fallback", "user_value": "12", "expected_value": ["16"],
    }


def make_review_report_snapshot(school, diagnostic, review_snapshot):
    return {
        "diagnostic": {
            "id": diagnostic.id,
            "subject": diagnostic.subject,
            "scoring": diagnostic.scoring.model_dump(mode="json"),
            "questions": [],
        },
        "review_snapshot": review_snapshot,
        "school": {
            "brand": school.brand.model_dump(mode="json"),
            "links": school.links.model_dump(mode="json"),
        },
    }


def test_premium_report_contains_both_answers_guidance_forecast_and_route():
    school = load_school(SAMPLE_SCHOOL)
    catalog = load_catalog(school)
    diagnostic = catalog.get("demo-math")
    review_snapshot = build_review_snapshot(diagnostic.questions, completed_attempt()["answers"])
    attempt = completed_attempt(
        report_snapshot=make_review_report_snapshot(school, diagnostic, review_snapshot),
        result_snapshot={"forecast": {"points": [{"id": "stage", "label": "Первый этап", "value": 100}]}},
    )

    pdf = build_report(attempt, school)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)

    assert "Ваша точка старта" in text
    assert "Ваш ответ" in text
    assert "Правильный ответ" in text
    assert "Как решать" in text
    assert "Первый этап" in text
    assert "Персональный маршрут" in text


def test_long_review_can_split_across_pages_without_blank_page():
    school = load_school(SAMPLE_SCHOOL)
    diagnostic = load_catalog(school).get("demo-math")
    review = make_review(prompt="Длинное условие. " * 160, guidance="Шаг решения. " * 100)
    snapshot = make_review_report_snapshot(school, diagnostic, [review])
    pdf = build_report(completed_attempt(report_snapshot=snapshot), school)
    pages = PdfReader(BytesIO(pdf)).pages
    assert 2 <= len(pages) <= 6
    assert all((page.extract_text() or "").strip() for page in pages)
```

Keep the existing legacy test and assert that a snapshot without `review_snapshot` still renders the shortened question/user-answer report.

- [ ] **Step 2: Run report tests and verify the missing Premium Workbook text failures**

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q tests/test_report.py
```

- [ ] **Step 3: Register Forum and Manrope with Liberation fallback**

```python
_DISPLAY_FONT = "Forum"
_BODY_FONT = "Manrope"
_BODY_BOLD = "Manrope-Bold"

def register_report_fonts() -> None:
    for name, filename in (
        (_DISPLAY_FONT, "Forum-Regular.ttf"),
        (_BODY_FONT, "Manrope-Regular.ttf"),
        (_BODY_BOLD, "Manrope-Bold.ttf"),
    ):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(_FONT_ROOT / filename)))
```

Reuse existing `validate_report_text()` coverage so unsupported glyphs fail during school/content validation instead of PDF delivery.

- [ ] **Step 4: Implement focused layout factories**

`report_layout.py` must define:

```python
@dataclass(frozen=True)
class ReportTheme:
    primary: colors.Color
    signal: colors.Color
    ink: colors.Color
    paper: colors.Color


def make_styles(theme: ReportTheme) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "display": ParagraphStyle(
            "Display", parent=base["Title"], fontName=_DISPLAY_FONT,
            fontSize=30, leading=33, textColor=theme.ink, spaceAfter=14,
        ),
        "heading": ParagraphStyle(
            "Heading", parent=base["Heading2"], fontName=_BODY_BOLD,
            fontSize=15, leading=19, textColor=theme.ink, spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName=_BODY_FONT,
            fontSize=10, leading=15, textColor=theme.ink, spaceAfter=7,
        ),
        "label": ParagraphStyle(
            "Label", parent=base["BodyText"], fontName=_BODY_BOLD,
            fontSize=8, leading=10, textColor=theme.primary, spaceAfter=4,
        ),
        "user_answer": ParagraphStyle(
            "UserAnswer", parent=base["BodyText"], fontName=_BODY_FONT,
            fontSize=9, leading=13, textColor=theme.ink, backColor=theme.paper,
        ),
        "expected_answer": ParagraphStyle(
            "ExpectedAnswer", parent=base["BodyText"], fontName=_BODY_BOLD,
            fontSize=9, leading=13, textColor=theme.ink, backColor=theme.signal,
        ),
    }


def summary_story(
    attempt: Mapping[str, Any],
    school: SchoolConfig,
    styles: Mapping[str, ParagraphStyle],
) -> list[Any]:
    result = attempt.get("result_snapshot") if isinstance(attempt.get("result_snapshot"), Mapping) else {}
    score = int(result.get("score") or 0)
    forecast = result.get("forecast") if isinstance(result.get("forecast"), Mapping) else {}
    points = forecast.get("points") if isinstance(forecast.get("points"), list) else []
    story: list[Any] = [
        Paragraph(escape(school.brand.name), styles["label"]),
        Paragraph("Ваша точка старта", styles["display"]),
        Paragraph(f"Текущий результат: <b>{score}</b>", styles["heading"]),
        Paragraph("Диагностика показывает, что уже получается и где быстрее всего вырастет балл.", styles["body"]),
    ]
    if points:
        rows = [[Paragraph("Прогноз", styles["label"]), Paragraph("Баллы", styles["label"])]]
        rows.extend([
            [Paragraph(escape(str(point.get("label") or "Этап")), styles["body"]),
             Paragraph(str(int(point.get("value") or 0)), styles["heading"])]
            for point in points[:2]
            if isinstance(point, Mapping)
        ])
        table = Table(rows, colWidths=[125 * mm, 35 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#E66A2C")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.extend([Spacer(1, 8 * mm), table])
    return story


def review_story(
    review: Mapping[str, Any],
    styles: Mapping[str, ParagraphStyle],
    images: Sequence[Any],
) -> list[Any]:
    number = int(review.get("number") or 0)
    status = "Верно" if review.get("is_correct") else "Нужно разобрать"
    header = KeepTogether([
        Paragraph(f"Задание {number} · {escape(status)}", styles["label"]),
        Paragraph(escape(str(review.get("title") or f"Задание {number}")), styles["heading"]),
    ])
    answer_table = Table([
        [Paragraph("Ваш ответ", styles["label"]), Paragraph("Правильный ответ", styles["label"])],
        [Paragraph(escape(str(review.get("user_answer") or "Нет ответа")), styles["user_answer"]),
         Paragraph(escape(str(review.get("expected_answer") or "—")), styles["expected_answer"])],
    ], colWidths=[80 * mm, 80 * mm], hAlign="LEFT")
    answer_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 1), (0, 1), styles["user_answer"].backColor),
        ("BACKGROUND", (1, 1), (1, 1), styles["expected_answer"].backColor),
        ("BOX", (0, 1), (-1, 1), 0.5, colors.HexColor("#D7D4CB")),
        ("INNERGRID", (0, 1), (-1, 1), 0.5, colors.HexColor("#D7D4CB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 1), (-1, 1), 8),
        ("LEFTPADDING", (0, 0), (-1, 0), 0),
    ]))
    story: list[Any] = [
        header,
        Paragraph(escape(str(review.get("prompt") or "")), styles["body"]),
        *images,
        Spacer(1, 3 * mm),
        answer_table,
        Spacer(1, 5 * mm),
        Paragraph("Как решать", styles["label"]),
        Paragraph(escape(str(review.get("guidance") or "Сверьте ход решения с правилом по теме задания.")), styles["body"]),
        Spacer(1, 8 * mm),
    ]
    return story


def route_story(
    attempt: Mapping[str, Any],
    school: SchoolConfig,
    styles: Mapping[str, ParagraphStyle],
) -> list[Any]:
    result = attempt.get("result_snapshot") if isinstance(attempt.get("result_snapshot"), Mapping) else {}
    raw_topics = result.get("growth_topics") or result.get("weak_topics") or []
    topics = [
        str(item.get("topic") or "") if isinstance(item, Mapping) else str(item)
        for item in raw_topics[:2]
    ]
    route = [f"Закрыть тему «{topic}»" for topic in topics if topic]
    route.append("Проверить рост на следующей диагностике")
    story: list[Any] = [
        Paragraph("Персональный маршрут", styles["display"]),
        Paragraph("Три ближайших действия", styles["label"]),
    ]
    for index, action in enumerate(route[:3], start=1):
        story.append(Paragraph(f"<b>{index:02d}</b>&nbsp;&nbsp;{escape(str(action))}", styles["heading"]))
    if school.links.offers:
        story.append(Paragraph("Продолжить подготовку можно по ссылке из сообщения бота.", styles["body"]))
    return story


def draw_page(theme: ReportTheme):
    def _draw(canvas: Canvas, document: BaseDocTemplate) -> None:
        canvas.saveState()
        canvas.setStrokeColor(theme.primary)
        canvas.setLineWidth(1)
        canvas.line(18 * mm, 285 * mm, 192 * mm, 285 * mm)
        canvas.setFillColor(theme.ink)
        canvas.setFont(_BODY_FONT, 8)
        canvas.drawString(18 * mm, 10 * mm, "Персональный отчёт")
        canvas.drawRightString(192 * mm, 10 * mm, str(document.page))
        canvas.restoreState()

    return _draw
```

`review_story()` must put user and expected answers in a two-column table when both fit, then append guidance as a separate splittable block. Wrap only the compact question header in `KeepTogether`; allow prompt, images, answer table, and guidance to split naturally.

- [ ] **Step 5: Orchestrate new and legacy snapshots in `build_report()`**

```python
review_snapshot = report_snapshot.get("review_snapshot") if isinstance(report_snapshot, Mapping) else None
if isinstance(review_snapshot, list):
    story.extend(summary_story(attempt, school, styles))
    story.append(PageBreak())
    for review in review_snapshot:
        story.extend(review_story(review, styles, resolved_images(review)))
    story.append(PageBreak())
    story.extend(route_story(attempt, school, styles))
else:
    story.extend(legacy_story(attempt, school, diagnostic, questions, frozen_assets, styles))
```

Use only frozen images when a completion snapshot exists. Keep the existing validation of snapshot school, ZIP bounds, SVG safety, and the final 25 MiB payload check.

- [ ] **Step 6: Run the full PDF, delivery, and worker tests**

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q tests/test_report.py tests/test_delivery.py tests/test_worker.py
```

Expected: all selected tests pass.

- [ ] **Step 7: Rasterize a mixed-format sample and inspect it**

Generate `output/pdf/maximum-premium-workbook.pdf`, rasterize representative summary/review/route pages, and verify:

```text
- no clipped Cyrillic or formulas;
- question status is readable without color;
- long prompts split without blank pages;
- images preserve aspect ratio;
- user and expected answers are visually distinct;
- page number and school identity remain visible.
```

- [ ] **Step 8: Review and commit only Task 4 hunks**

```powershell
rtk git diff -- backend/diagnostic/report.py backend/diagnostic/report_layout.py tests/test_report.py
rtk git add backend/diagnostic/report_layout.py
rtk git add -p -- backend/diagnostic/report.py tests/test_report.py
rtk proxy git -c core.excludesFile=NUL diff --cached --check
rtk git commit -m "Redesign diagnostic PDF workbook"
```

### Task 5: Add the Mini App review/forecast/route data contract

**Files:**
- Create: `miniapp/app/result-flow-model.ts`
- Create: `miniapp/app/result-flow-model.test.ts`
- Modify: `miniapp/app/types.ts:105-193`
- Modify: `miniapp/app/api.ts:1-20,468-531`
- Modify: `miniapp/app/api.test.ts:161-end`
- Modify: `miniapp/app/catalog-security.test.ts:1-end`

**Interfaces:**
- Consumes: Task 2 response and existing `ServerResult`, `ForecastPoint`, `ServerAttempt`.
- Produces: `ReviewItem`, `ReviewResponse`, `loadReview()`, `forecastTrajectory()`, `personalRoute()`, and `pdfStatusCopy()`.

- [ ] **Step 1: Write failing pure model and API tests**

```typescript
import { describe, expect, it } from "vitest";
import { forecastTrajectory, personalRoute, pdfStatusCopy } from "./result-flow-model";

describe("result flow model", () => {
  it("uses current score plus at most two persisted forecast points", () => {
    expect(forecastTrajectory({ score: 40, forecast: { points: [
      { id: "stage", label: "Первый этап", value: 57 },
      { id: "course", label: "Годовой курс", value: 74 },
      { id: "extra", label: "Лишняя точка", value: 88 },
    ] } } as never)).toEqual([
      { id: "current", label: "Сейчас", value: 40 },
      { id: "stage", label: "Первый этап", value: 57 },
      { id: "course", label: "Годовой курс", value: 74 },
    ]);
  });

  it("never invents a forecast point when offers are absent", () => {
    expect(forecastTrajectory({ score: 40 } as never)).toEqual([
      { id: "current", label: "Сейчас", value: 40 },
    ]);
  });

  it("builds a bounded route from growth topics", () => {
    expect(personalRoute(["Алгоритмы", "Информация"]).map((item) => item.title)).toEqual([
      "Закрыть тему «Алгоритмы»",
      "Укрепить тему «Информация»",
      "Проверить рост",
    ]);
  });

  it("distinguishes every PDF delivery state", () => {
    expect(pdfStatusCopy("pending").title).toBe("Готовим PDF для Telegram");
    expect(pdfStatusCopy("sent").title).toBe("PDF отправлен в Telegram");
    expect(pdfStatusCopy("failed").action).toBe("Проверить статус");
    expect(pdfStatusCopy("abandoned").title).toBe("PDF не удалось отправить");
  });
});
```

In `api.test.ts`, assert `loadReview("init", "attempt_123", "scope")` posts only `init_data`, `attempt_id`, and `session_scope` to `/api/diagnostics/session/review`.

- [ ] **Step 2: Run Vitest and verify missing module/type failures**

```powershell
Set-Location miniapp
rtk npm run test:unit -- --run app/result-flow-model.test.ts app/api.test.ts app/catalog-security.test.ts
Set-Location ..
```

- [ ] **Step 3: Add explicit post-completion types without changing `Question`**

```typescript
export type ReviewItem = {
  question_id: string;
  number: number;
  type: QuestionType;
  topic: string;
  title: string;
  prompt: string;
  asset?: string;
  assets?: string[];
  is_correct: boolean;
  user_answer: string;
  expected_answer: string;
  guidance: string;
  guidance_kind: "individual" | "fallback";
};

export type ReviewResponse = {
  ok: true;
  available: boolean;
  items: ReviewItem[];
  pdf_status: "pending" | "sending" | "sent" | "failed" | "abandoned";
};
```

Do not add `correct`, `expected_answer`, or `explanation` to `BaseQuestion` or `PublicDiagnostic`.

- [ ] **Step 4: Implement the client call and pure helpers**

```typescript
export const loadReview = (initData: string, attemptId: string, sessionScope: string) =>
  postDiagnostic<ReviewResponse>("/api/diagnostics/session/review", initData, {
    attempt_id: attemptId,
    session_scope: sessionScope,
  });
```

`forecastTrajectory()` must accept both the current `{points}` shape and legacy records, but return only persisted numeric points. `personalRoute()` must return at most three actions. `pdfStatusCopy()` must never say “sent” for `pending`, `sending`, `failed`, or `abandoned`.

- [ ] **Step 5: Strengthen the public-boundary static test**

```typescript
it("keeps expected answers in the post-completion contract only", async () => {
  const types = await readFile(new URL("./types.ts", import.meta.url), "utf8");
  const publicQuestionBlock = types.slice(types.indexOf("type BaseQuestion"), types.indexOf("export type AnswerValue"));
  expect(publicQuestionBlock).not.toContain("correct");
  expect(publicQuestionBlock).not.toContain("expected_answer");
  expect(types).toContain("export type ReviewItem");
});
```

- [ ] **Step 6: Run the complete Mini App unit suite**

```powershell
Set-Location miniapp
rtk npm run test:unit
Set-Location ..
```

Expected: all Vitest tests pass.

- [ ] **Step 7: Review and commit only Task 5 hunks**

```powershell
rtk git diff -- miniapp/app/result-flow-model.ts miniapp/app/result-flow-model.test.ts miniapp/app/types.ts miniapp/app/api.ts miniapp/app/api.test.ts miniapp/app/catalog-security.test.ts
rtk git add miniapp/app/result-flow-model.ts miniapp/app/result-flow-model.test.ts
rtk git add -p -- miniapp/app/types.ts miniapp/app/api.ts miniapp/app/api.test.ts miniapp/app/catalog-security.test.ts
rtk proxy git -c core.excludesFile=NUL diff --cached --check
rtk git commit -m "Add diagnostic result flow contract"
```

### Task 6: Build the Training Radar Mini App flow

**Files:**
- Create: `miniapp/app/navigation-screens.tsx`
- Create: `miniapp/app/question-screen.tsx`
- Create: `miniapp/app/result-flow.tsx`
- Create: `miniapp/app/result-flow-render.test.tsx`
- Modify: `miniapp/app/page.tsx:1-1090`
- Modify: `miniapp/app/globals.css:1-end`
- Modify: `miniapp/vitest.config.ts:3-7`
- Modify: `miniapp/tests/rendered-html.test.mjs:1-end`

**Interfaces:**
- Consumes: Task 5 `loadReview`, `ReviewResponse`, `forecastTrajectory`, `personalRoute`, and existing question helper modules.
- Produces: presentational navigation/question/result components and `Screen = "loading" | "welcome" | "mode" | "subjects" | "question" | "submitting" | "result" | "review" | "forecast" | "route"`.

- [ ] **Step 1: Write failing render and production-copy tests**

Update Vitest to include `app/**/*.test.tsx` and add:

```tsx
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ForecastScreen, ReviewScreen } from "./result-flow";

describe("result flow screens", () => {
  it("renders the persisted answers and honest fallback label", () => {
    const html = renderToStaticMarkup(<ReviewScreen
      items={[{
        question_id: "q1", number: 1, type: "single", topic: "Алгоритмы",
        title: "Задание 1", prompt: "Условие", is_correct: false,
        user_answer: "12", expected_answer: "16", guidance: "Решайте по шагам.",
        guidance_kind: "fallback",
      }]}
      index={0} onBack={() => undefined} onNext={() => undefined} onForecast={() => undefined}
    />);
    expect(html).toContain("Ваш ответ");
    expect(html).toContain("Правильный ответ");
    expect(html).toContain("Общий алгоритм");
  });

  it("renders only the provided forecast points", () => {
    const html = renderToStaticMarkup(<ForecastScreen
      points={[{ id: "current", label: "Сейчас", value: 40 }]}
      onBack={() => undefined} onRoute={() => undefined}
    />);
    expect(html).toContain("40");
    expect(html).not.toContain("Годовой курс");
  });
});
```

Extend `rendered-html.test.mjs` to require the production output to contain “Сканируем знания”, “Прогноз баллов”, and “Персональный маршрут”.

- [ ] **Step 2: Run focused frontend tests and verify missing component failures**

```powershell
Set-Location miniapp
rtk npm run test:unit -- --run app/result-flow-render.test.tsx
Set-Location ..
```

- [ ] **Step 3: Extract navigation and question presentation without moving state**

`navigation-screens.tsx` exports `WelcomeScreen`, `ModeScreen`, and `SubjectsScreen`. `question-screen.tsx` exports the current `QuestionView` and its answer widgets. Each component receives data and callbacks only; neither imports API functions nor accesses Telegram globals.

```tsx
export type QuestionScreenProps = {
  question: Question;
  index: number;
  total: number;
  answer: AnswerValue | undefined;
  labels: Brand["interface"];
  onAnswer: (value: AnswerValue) => void;
  onBack: () => void;
  onNext: () => void;
};
```

After extraction, `page.tsx` remains responsible for `progressRevision`, local storage, conflict recovery, submission, and screen transitions.

- [ ] **Step 4: Implement the four result-stage components**

`result-flow.tsx` exports:

```tsx
export function ResultScreen(props: {
  result: ServerResult;
  diagnostic: PublicDiagnostic;
  pdfStatus: ReviewResponse["pdf_status"];
  onReview: () => void;
  onForecast: () => void;
}): React.ReactNode;

export function ReviewScreen(props: {
  items: ReviewItem[];
  index: number;
  loading?: boolean;
  error?: string | null;
  legacy?: boolean;
  onRetry?: () => void;
  onBack: () => void;
  onNext: () => void;
  onForecast: () => void;
}): React.ReactNode;

export function ForecastScreen(props: { points: ForecastPoint[]; onBack: () => void; onRoute: () => void }): React.ReactNode;
export function RouteScreen(props: { items: RouteItem[]; pdf: PdfStatusCopy; offers: SchoolLinks["offers"]; onRefreshPdf: () => void; onSubjects: () => void }): React.ReactNode;
```

Review shows only `items.filter(item => !item.is_correct)`. When there are no mistakes, render a success state and the forecast action. When `available` is false, render the legacy explanation and continue to forecast.

- [ ] **Step 5: Wire post-completion state and bounded status refresh in `page.tsx`**

Add state:

```tsx
const [review, setReview] = useState<ReviewResponse | null>(null);
const [reviewIndex, setReviewIndex] = useState(0);
const [reviewError, setReviewError] = useState<string | null>(null);
```

Add a single loader used by review and “Проверить статус”:

```tsx
const refreshReview = useCallback(async () => {
  if (!sessionScope || !initData.current) return null;
  try {
    const response = await loadReview(initData.current, attemptId, sessionScope);
    setReview(response);
    setReviewError(null);
    return response;
  } catch {
    setReviewError("Не удалось загрузить разбор. Повторите запрос.");
    return null;
  }
}, [attemptId, sessionScope]);
```

Do not poll indefinitely. Load once when the user opens review and again only from the explicit status/retry action.

- [ ] **Step 6: Replace the visual system with Training Radar CSS**

Define runtime tokens:

```css
:root {
  --brand-primary: #fd7e14;
  --brand-signal: #d8ff42;
  --brand-ink: #101517;
  --brand-paper: #f5f5f0;
  --brand-background: #f5f5f5;
  --danger: #e95d50;
  --info: #bfe7ff;
}
```

Implement the approved rules:

```text
- dark navigation/result shell;
- one radar motif on welcome and forecast only;
- light question work surface;
- orange actions and lime growth/success signals;
- minimum 44 px targets;
- visible focus ring on every action;
- 320 px single-column support;
- text/icon status in addition to color;
- reduced-motion rule disabling sweep and screen transitions.
```

Map `brand.colors.primary/signal/ink/paper/background` into inline CSS variables in `page.tsx`.

- [ ] **Step 7: Run unit tests, build, and rendered HTML checks**

```powershell
Set-Location miniapp
rtk npm run test:unit
rtk npm run build
rtk npm test
Set-Location ..
```

Expected: all commands exit successfully.

- [ ] **Step 8: Capture and inspect mobile screenshots**

Use the project Playwright workflow to capture at 320×700 and 390×844:

```text
welcome, mode, subjects, single question, matching question,
result, review, forecast, route, loading, network error, legacy review.
```

Reject the visual pass if text clips, a target is smaller than 44 px, focus is invisible, the radar appears on more than welcome/forecast, or the question surface loses contrast.

- [ ] **Step 9: Review and commit only Task 6 hunks**

```powershell
rtk git diff -- miniapp/app/navigation-screens.tsx miniapp/app/question-screen.tsx miniapp/app/result-flow.tsx miniapp/app/result-flow-render.test.tsx miniapp/app/page.tsx miniapp/app/globals.css miniapp/vitest.config.ts miniapp/tests/rendered-html.test.mjs
rtk git add miniapp/app/navigation-screens.tsx miniapp/app/question-screen.tsx miniapp/app/result-flow.tsx miniapp/app/result-flow-render.test.tsx
rtk git add -p -- miniapp/app/page.tsx miniapp/app/globals.css miniapp/vitest.config.ts miniapp/tests/rendered-html.test.mjs
rtk proxy git -c core.excludesFile=NUL diff --cached --check
rtk git commit -m "Build Training Radar diagnostic flow"
```

### Task 7: Document and import optional methodical explanations

**Files:**
- Modify: `docs/CONTENT_FORMAT.md:1-55,184-end`
- Modify: `scripts/import_edcheck_export.py:220-330`
- Modify: `tests/test_import_edcheck_export.py`
- Modify: `tests/test_docs_commands.py`
- Modify: `miniapp/app/catalog-security.test.ts`

**Interfaces:**
- Consumes: Task 1 optional `QuestionBase.explanation`.
- Produces: `_explanation(question: Mapping[str, Any]) -> str | None` in the importer and an explicit documented post-completion exception.

- [ ] **Step 1: Write failing importer tests for supported explanation fields**

```python
from scripts.import_edcheck_export import _convert_question, _explanation


def test_importer_preserves_clean_bounded_explanation():
    converted = _convert_question({
        "question_id": 7,
        "question_index": 1,
        "description_text": "Чему равно 2 + 2?",
        "description_html": "",
        "images": [],
        "audio_file": None,
        "subject": {"code": "math"},
        "blocks": [],
        "type": "short-answer",
        "correct_answers": ["4"],
        "solution": "Сложите два и два: получится четыре.",
    })

    assert converted is not None
    assert converted["explanation"] == "Сложите два и два: получится четыре."


def test_importer_drops_blank_or_oversized_explanation():
    assert _explanation({"solution": "   "}) is None
    assert _explanation({"solution": "x" * 2001}) is None


def test_explanation_uses_supported_alias_priority_and_plain_strings_only():
    assert _explanation({
        "solution": "Первый источник",
        "answer_explanation": "Второй источник",
        "explanation": "Третий источник",
    }) == "Первый источник"
    assert _explanation({
        "solution": {"html": "не строка"},
        "answer_explanation": "Второй источник",
        "explanation": "Третий источник",
    }) == "Второй источник"
```

- [ ] **Step 2: Run importer and docs tests and verify failure**

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q tests/test_import_edcheck_export.py tests/test_docs_commands.py
```

- [ ] **Step 3: Implement strict explanation extraction**

```python
def _explanation(question: Mapping[str, Any]) -> str | None:
    for key in ("solution", "answer_explanation", "explanation"):
        value = question.get(key)
        if not isinstance(value, str):
            continue
        cleaned = _clean_prompt_text(value)
        if cleaned and len(cleaned) <= 2000:
            return cleaned
    return None
```

After `_convert_question()` has produced a supported question, add:

```python
    explanation = _explanation(question)
    if explanation is not None:
        converted["explanation"] = explanation
```

Do not parse HTML, call a network service, or synthesize a subject-specific explanation in the importer.

- [ ] **Step 4: Update the content contract and public-boundary wording**

Document:

```text
- `explanation` is optional, server-owned, UTF-8, and at most 2,000 characters;
- it is excluded from bootstrap and public assets;
- after an authenticated completed attempt, the Mini App may receive display-only
  `expected_answer` and resolved guidance for that attempt;
- missing explanation uses a visibly labeled general algorithm;
- existing attempts without `review_snapshot` remain legacy reports.
```

Remove the obsolete absolute statement that correct answers can never appear in any TypeScript/HTML, and replace it with the exact public/pre-completion boundary above.

- [ ] **Step 5: Run importer, catalog, docs, content, and brand checks**

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q tests/test_import_edcheck_export.py tests/test_catalog.py tests/test_docs_commands.py
rtk python scripts/validate_school.py
rtk python scripts/check_brand_isolation.py
```

Expected: tests pass and both scripts print `OK`.

- [ ] **Step 6: Review and commit only Task 7 hunks**

```powershell
rtk git diff -- docs/CONTENT_FORMAT.md scripts/import_edcheck_export.py tests/test_import_edcheck_export.py tests/test_docs_commands.py miniapp/app/catalog-security.test.ts
rtk git add -p -- docs/CONTENT_FORMAT.md scripts/import_edcheck_export.py tests/test_import_edcheck_export.py tests/test_docs_commands.py miniapp/app/catalog-security.test.ts
rtk proxy git -c core.excludesFile=NUL diff --cached --check
rtk git commit -m "Document diagnostic answer reviews"
```

### Task 8: End-to-end verification and release gate

**Files:**
- Modify only if a verification failure requires a scoped fix: files from Tasks 1-7 and their direct tests.
- Do not modify deployment, retention, delivery state, or unrelated school content to silence a failing gate.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: a verified completion → review → forecast → route → PDF flow and a concise verification record in the final handoff.

- [ ] **Step 1: Run the complete Python test suite**

```powershell
$env:PYTHONPATH='backend'
rtk python -m pytest -q
```

Expected: all non-DB tests pass; DB tests pass when `TEST_DATABASE_URL` is configured and otherwise retain their existing skip behavior.

- [ ] **Step 2: Run content and brand isolation gates**

```powershell
rtk python scripts/validate_school.py
rtk python scripts/check_brand_isolation.py --history
```

Expected: both commands print `OK`.

- [ ] **Step 3: Run the complete Mini App gates**

```powershell
Set-Location miniapp
rtk npm run test:unit
rtk npm run build
rtk npm test
Set-Location ..
```

Expected: unit tests, production build, and rendered HTML tests pass.

- [ ] **Step 4: Validate Compose without changing running services**

```powershell
rtk docker compose config --quiet
```

Expected: exit code 0.

- [ ] **Step 5: Exercise the real API flow with an authenticated test fixture**

Verify this exact sequence:

```text
bootstrap -> progress -> complete -> review -> viewed
```

Assert the bootstrap payload contains neither `correct` nor `explanation`; the review response belongs to the completed attempt and contains `expected_answer`; a second completion/review returns the same frozen content; PDF delivery remains pending/sending/sent according to the existing worker.

- [ ] **Step 6: Compare final screenshots and PDF against approved mockups**

Use the saved visual direction as the acceptance reference:

```text
Mini App: Training Radar, dark navigation, light question surface, orange action,
lime growth signal, radar only on welcome/forecast.

PDF: Premium Workbook, light editorial pages, restrained orange rules,
Forum display, Manrope body, answer comparison and explanation per question.
```

Record any deliberate deviation in the handoff; do not silently substitute the previous visual system.

- [ ] **Step 7: Inspect the final diff for scope and secrets**

```powershell
rtk git status --short
rtk proxy git -c core.excludesFile=NUL diff --check
rtk git diff --stat
rtk git diff -- .env .env.example school backend miniapp docs scripts tests
```

Confirm no secret, `.superpowers/`, screenshot, generated PDF, local domain, or unrelated deployment file is staged.

- [ ] **Step 8: Commit only verification fixes, if any**

If Task 8 exposes a defect, return to the task that owns the failing file, add the missing regression test there, rerun that task's focused gates, and use that task's exact review/staging step. Then rerun all Task 8 gates. If every gate passes without a Task 8 code change, do not create an empty commit.
