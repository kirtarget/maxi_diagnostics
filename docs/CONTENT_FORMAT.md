# School content format

All files are UTF-8 strict JSON: duplicate keys, `NaN`, and `Infinity` are rejected.
Keep IDs stable after launch. Before completion, `correct` and `explanation` are
server-only and excluded from bootstrap, TypeScript, HTML, and public assets.

The shipped catalog is generated from the editor-approved MAXIMUM diagnostics
exported from SharePoint by `scripts/import_sharepoint_diagnostics.py`. Every
question id starts with `sp-`; the catalog has no other source. Runtime JSON with
`approval_status=draft` is only a review draft. It is not an expert-approved
authoring package and must not be presented as approved content. The pre-import
catalog and the retired authoring workflow are kept for reference in
`authoring/archive/2026-09-pre-sharepoint/`.

## Diagnostic file envelope

`school/diagnostics/` contains only regular top-level `.json` files. Filenames use
ASCII letters, digits, `_`, `-`, and `.`, are at most 120 characters, and must not
differ only by case. Each file contains one object with every field below:

```json
{
  "id": "math-grade-9",
  "exam": "exam-2027",
  "subject": "Mathematics",
  "mark": "Grade 9",
  "quick_count": 1,
  "full_count": 1,
  "scoring": {"max_score": 100, "score_unit": "accuracy_percent"},
  "questions": [
    {
      "id": "q1",
      "type": "input",
      "topic": "Arithmetic",
      "title": "Task 1",
      "prompt": "Enter two plus two.",
      "max_primary_score": 1,
      "source": {
        "provider": "maximum",
        "official_year": 2026,
        "approval_status": "approved",
        "source_kind": "original",
        "source_url": "https://maximumtest.ru/",
        "rights_status": "original",
        "verified_at": "2026-09-01"
      },
      "correct": ["4"]
    }
  ]
}
```

IDs use 1–64 ASCII letters, digits, `_`, or `-`, begin with a letter or digit, and a
diagnostic ID has at least 3 characters. `exam` is at most 32 characters; `subject`,
`mark`, `topic`, and `title` are at most 128; prompts are at most 4,000; option labels
are at most 500. Prompts may contain LF line breaks for paragraphs and enumerated
task parts; other control characters remain forbidden. Text cannot be blank.
`quick_count` is a strict integer from 1
through the question count. Percentage accuracy is the only score unit, so
`max_score` is exactly `100`.

`full_count` is optional and defaults to the question count. When present it is a
strict integer from `quick_count` through the question count, and the full mode
asks exactly the first `full_count` questions. Everything the full mode produces
follows that subset: the expected answer set on progress and completion, the
review snapshot, the PDF, and the public `full_count` the Mini App slices by. The
trainer and the daily plan keep drawing from every question in the file, so
questions past `full_count` stay available as practice. Set it when a catalog
gains extra questions that should not lengthen the diagnostic itself.

`max_primary_score` is a strict integer from 1 through 100 and defaults to `1`.
The result keeps `accuracy_percent` as its score unit, but calculates that percentage
from earned primary points divided by available primary points. A correct answer earns
the whole `max_primary_score`; an incorrect or missing answer earns zero. Catalogs in
which every task has the default value therefore keep their existing scores exactly.
The Mini App displays primary-point labels only when `source.approval_status` is
`approved`. The default value remains an internal scoring weight and must not be
presented as a verified FIPI point value without approved attribution.

## Question provenance

`source` is optional and contains traceable, display-safe attribution:

```json
{
  "provider": "fipi",
  "official_year": 2026,
  "approval_status": "approved",
  "source_kind": "open_bank",
  "source_url": "https://ege.fipi.ru/bank/questions.php?proj=...&qid=...",
  "fipi_project_id": "...",
  "fipi_question_id": "...",
  "exam_position": "1",
  "official_criteria_url": "https://doc.fipi.ru/ege/specification.pdf",
  "rights_status": "link_only",
  "verified_at": "2026-09-01"
}
```

`approval_status` is `approved` or `draft`. `source_kind` is `open_bank`,
`open_variant`, `demo`, `specification`, `commission_material`, or `original`.
`rights_status` is `link_only`, `written_permission`, `licensed_copy`, or `original`.
Every source URL must use HTTPS without embedded credentials. For provider `fipi`,
URLs must use `fipi.ru` or one of its subdomains and rights cannot be `original`.
Open-bank content remains link-only until written permission or a license is recorded.
The SharePoint converter never reads the FIPI website. It only preserves source
metadata already present in the supplied editorial documents.

The public catalog may include `max_primary_score` and `source`. It never includes
`correct`, `explanation`, or learning material fields before completion.

Every catalog string that can appear in a PDF must have glyphs in both bundled
Liberation Sans regular and bold fonts. The required validator checks this before
deployment. The bundled set covers the shipped Latin and Cyrillic examples; add and
license an appropriate font before authoring content in another script.

There are at most 20 diagnostics and 200 questions in each diagnostic. A question has
at most 50 options/items. Each file is at most 1 MiB and all diagnostic files together
are at most 5 MiB. Bootstrap contains only diagnostic summaries. An authenticated
diagnostic-detail response is at most 2 MiB.

## Answer-review boundary

- `explanation`, `learning_material_text` and `learning_material_url` are optional,
  server-owned UTF-8 fields. `learning_material_text` is at most 1,200 characters;
  the URL may point only to a canonical article in the MAXIMUM study book.
  - They are excluded from bootstrap and public assets.
- After an authenticated completed attempt, the Mini App may receive display-only
  `expected_answer` and resolved guidance, plus `max_primary_score` and
  `earned_primary_score` for that attempt.
- A submitted trainer answer receives the same maximum and earned primary-point
  values. An unsubmitted trainer question receives only its maximum and attribution.
- A missing verified study-book text is shown as an explicit "разбор пока не
  добавлен" message; the system does not fabricate a general algorithm.
- Existing attempts without `review_snapshot` remain legacy reports.

## Brand and links

`school/brand.json` has this exact schema:

```json
{
  "school_id": "school-slug",
  "name": "School name",
  "short_name": "School",
  "colors": {"primary": "#5636D3", "accent": "#F4B740", "background": "#F7F6FC"},
  "logo": "assets/logo.svg",
  "pdf": {
    "header": "Diagnostic report",
    "score_label": "Score",
    "correct_label": "Correct",
    "strong_topics_label": "Strong topics",
    "growth_topics_label": "Growth topics",
    "forecast_label": "Forecast",
    "answer_label": "Your answer"
  },
  "interface": {
    "command_start": "Open menu",
    "command_diagnostics": "Start diagnostic",
    "command_results": "My results",
    "command_plan": "My plan",
    "start_diagnostic": "Start diagnostic",
    "open_diagnostic": "Open diagnostic",
    "results": "My results",
    "plan": "My plan",
    "home": "Home",
    "take_full_diagnostic": "Take full diagnostic",
    "check_another_subject": "Check another subject",
    "take_another_diagnostic": "Take another diagnostic",
    "quick_result": "Quick result",
    "full_result": "Full result",
    "ready_result": "Result ready",
    "unassessed_full": "the rest of the full diagnostic",
    "results_heading": "Diagnostic results",
    "diagnostic_fallback": "Diagnostic",
    "plan_for": "Your plan for",
    "keep_strong": "Keep strong",
    "focus_next": "Focus next",
    "open_result_hint": "Open the result for the next step.",
    "result_not_found": "Result not found",
    "back": "Back",
    "task_label": "Task",
    "of_label": "of",
    "answer_label": "Your answer",
    "enter_answer": "Enter answer",
    "choose_option": "Choose option",
    "next_question": "Next question",
    "get_result": "Get result",
    "result_in_telegram": "Result in Telegram",
    "privacy_label": "Privacy",
    "support_label": "Support",
    "choose_label": "Choose",
    "close_diagnostic": "Close diagnostic",
    "illustration_alt": "Question illustration",
    "result_score": "Score",
    "result_correct": "Correct answers",
    "delivery_note": "The detailed report will appear in Telegram."
  },
  "messages": {
    "welcome": "Welcome to {school_name}.",
    "results_empty": "No completed diagnostics yet.",
    "plan_empty": "Your plan will appear here.",
    "data_erased": "Your data was erased. Try again in 15 minutes.",
    "quick_complete": "Your quick {subject} result is ready.",
    "full_complete": "Your full {subject} result is ready.",
    "not_started": "Start a diagnostic when you are ready.",
    "incomplete": "Continue your {subject} diagnostic.",
    "result_unviewed": "Your {subject} result is waiting.",
    "day_followup": "Review your {subject} result.",
    "quick_to_full": "Try the full diagnostic: {primary_offer_url}",
    "month_retest": "Retake your {subject} diagnostic in a month.",
    "generic": "{school_name}: open the diagnostic menu."
  }
}
```

`school_id` is a 2–63 character lowercase slug. Names are at most 128/64 characters,
PDF labels at most 128, interface labels at most 64, and message templates at most
2,048 characters. Labels and messages cannot contain control characters or line
breaks. Message placeholders are limited to the names shown in the sample plus
`school_short_name`, offer/website/support/privacy values, and `mode`; format specs,
conversions, malformed Telegram HTML, nested links, and non-HTTPS links are rejected.
Completion captions must render within 1,024 characters and other messages within
4,096. Colors are six-digit hex values.

`school/links.json` contains `website`, `support`, `privacy`, and up to 10 offers:

```json
{
  "website": "https://school.example/",
  "support": "https://school.example/support",
  "privacy": "https://school.example/privacy",
  "offers": [
    {
      "id": "course",
      "label": "Preparation course",
      "button": "Learn more",
      "url": "https://school.example/course",
      "recovery_share": 10
    }
  ]
}
```

Public URLs must be HTTPS, contain no credentials or fragment, be at most 2,048
characters, and have a query of at most 512 characters. Offer IDs are unique lowercase
ASCII IDs up to 32 characters, labels/buttons are at most 128/64, and
`recovery_share` is a strict integer from 0 to 100. It is the share of the primary
points missed in the growth topics that the forecast assumes the student recovers.
Forecast points are calculated only on the server and stored with the result.

## Score scales

`school/score_scales.json` is optional. It maps a diagnostic's primary score onto the
official 2026 exam scale so the result can show an estimated test score or grade next
to the accuracy percent.

```json
{
  "scales": [
    {
      "id": "ege-physics",
      "exam": "ЕГЭ",
      "subject": "Физика",
      "kind": "test_score",
      "max_primary": 45,
      "min_pass": 36,
      "table": [0, 5, 9],
      "interpolated_primary": [17],
      "notes": "",
      "source": {
        "title": "...",
        "url": "https://example.org/scale.pdf",
        "date": "2026-05-07",
        "confidence": "secondary"
      }
    }
  ]
}
```

`exam` and `subject` must match a diagnostic exactly; a scale that matches no
diagnostic fails validation, and each pair may appear at most once. `kind` is
`test_score` (EGE) or `grade` (OGE). A `test_score` scale carries `table` with
`max_primary + 1` non-decreasing values from 0 to 100, indexed by primary score. A
`grade` scale carries `grades` with ascending `"3"`, `"4"` and `"5"` primary
thresholds, none above `max_primary`. `min_pass` is the passing value in the same unit
as the estimate, or `null`. `interpolated_primary` lists primary scores whose table
value was reconstructed rather than published. `notes` is free text for conditions the
runtime does not model, such as the OGE geometry minimum; nothing reads it as logic.

Rebuild the file from the research data with
`python scripts/build_score_scales.py`.

## Public assets

Everything under `school/assets/` is public. Only referenced `.svg`, `.png`, `.jpg`,
and `.jpeg` files are allowed. Unreferenced files, symlinks, private files, and
case-mismatched paths fail validation. Paths start with `assets/`, use portable ASCII
segments, do not use Windows reserved device names (`CON`, `NUL`, `COM1`, and similar),
match on-disk case exactly, and contain no consecutive dots. Each file is
at most 5 MiB, unique assets together at most 20 MiB, and at most 201 assets may be
referenced. Reference-weighted input is also capped at 20 MiB and 50,000,000 raster
pixels, so repeatedly using one large file is not a bypass. Raster images are
limited to 4,096 pixels per side and 4,000,000 pixels total.

SVG must be bounded valid XML without DTD/entities, scripts, `foreignObject`, event
handlers, processing instructions, external/data/file references, CSS imports, or
external `url(...)`. Internal `#fragment` references are allowed. Raster files must
fully decode. SVGs have at most 10,000 XML/CSS nodes or tokens, 65,536 characters
per attribute/text node, and 262,144 characters of aggregate markup complexity.
Never put correct answers, credentials, exports, or learner data in an asset.

A question may reference one illustration with `"asset": "assets/questions/task.png"`
or an ordered set of one to five illustrations with
`"assets": ["assets/questions/task-1.png", "assets/questions/task-2.png"]`.
Do not set both fields on the same question. Every referenced image is included in the
completion snapshot and the frozen PDF asset bundle.

## Single choice

```json
{
  "id": "q-single",
  "type": "single",
  "topic": "Arithmetic",
  "title": "Task 1",
  "prompt": "Choose one answer.",
  "asset": "assets/questions/single.svg",
  "options": [
    {"id": "a", "label": "First"},
    {"id": "b", "label": "Second"}
  ],
  "correct": "b"
}
```

## Multiple choice

`selection_limit` is the exact number of choices required and must equal the number
of unique IDs in `correct`.

```json
{
  "id": "q-multiple",
  "type": "multiple",
  "topic": "Fractions",
  "title": "Task 2",
  "prompt": "Choose two answers.",
  "options": [
    {"id": "a", "label": "1/2"},
    {"id": "b", "label": "2/4"},
    {"id": "c", "label": "3/4"}
  ],
  "selection_limit": 2,
  "correct": ["a", "b"]
}
```

## Numeric input

The `input` type is numeric only; free-text answers use the `text` type below. A comma or dot
decimal separator is accepted: `3.5` and `3,5` compare equally, as do `42`,
`42.0`, and `42,0`. Values are 1–64 characters and use an optional sign, digits,
comma/dot, and optional scientific exponent with 1–3 digits (for example `1e999`).
Whitespace and non-finite values are rejected. Up to 20 equivalent variants are
allowed.

```json
{
  "id": "q-number",
  "type": "input",
  "topic": "Equations",
  "title": "Task 3",
  "prompt": "Enter 7 divided by 2.",
  "correct": ["3.5"]
}
```

## Short free text

The `text` type accepts a short written answer such as a conjunction or a single
term. `correct` holds 1–20 accepted variants and `max_length` (a strict integer from
1 through 200, default `80`) is the only public field of the type: it tells the Mini
App how long the answer field may be. Every variant is 1–`max_length` characters,
must not be blank or control-bearing, and must render with the bundled PDF fonts.
Two variants that normalize to the same string are a duplicate and rejected.

Both sides of the comparison pass through the same normalization before they are
compared:

1. Unicode NFC.
2. Leading and trailing whitespace removed.
3. Lowercased.
4. `ё` folded to `е`.
5. Runs of internal whitespace collapsed to a single space.
6. Trailing `.`, `,`, `;`, `!`, and `?` dropped.
7. `–` and `—` unified to `-`.

So `"  ОДНАКО.  "`, `"Однако"`, and `"однако"` all match a stored `"однако"`, and
`"всё-таки"`, `"ВСЁ–ТАКИ!"`, and `"все—таки"` all match one another. Word order and
internal spelling are not normalized: `"но однако"` does not match `"однако"`.

```json
{
  "id": "q-text",
  "type": "text",
  "topic": "Союзы",
  "title": "Task 5",
  "prompt": "Выпишите подчинительный союз из предложения.",
  "max_length": 40,
  "correct": ["но", "однако"]
}
```

## Matching

Every item ID maps to one valid option ID in `correct`.

```json
{
  "id": "q-matching",
  "type": "matching",
  "topic": "Matching",
  "title": "Task 4",
  "prompt": "Match each item.",
  "items": [
    {"id": "left-a", "label": "A"},
    {"id": "left-b", "label": "B"}
  ],
  "options": [
    {"id": "right-1", "label": "One"},
    {"id": "right-2", "label": "Two"}
  ],
  "correct": {"left-a": "right-2", "left-b": "right-1"}
}
```

## Free short text (in progress)

`scripts/import_sharepoint_diagnostics.py` appends editor-approved MAXIMUM
diagnostics to the existing catalogs. Tasks whose key is a word or a `#`-joined
list of accepted wordings are emitted as `text`:

```json
{
  "id": "sp-chemistry-oge-2022-q6",
  "type": "text",
  "topic": "Задание 6",
  "title": "Задание 6",
  "prompt": "Впишите название процесса.",
  "correct": ["возгонка", "сублимация"],
  "max_length": 80
}
```

Run `python scripts/validate_school.py` and `python scripts/check_brand_isolation.py`
after every brand, link, content, or asset change. Both commands must print `OK`
before deployment. They use the same runtime validation contract as the API and bot.
