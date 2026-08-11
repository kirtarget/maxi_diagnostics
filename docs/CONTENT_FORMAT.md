# School content format

All files are UTF-8 strict JSON: duplicate keys, `NaN`, and `Infinity` are rejected.
Keep IDs stable after launch. Before completion, `correct` and `explanation` are
server-only and excluded from bootstrap, TypeScript, HTML, and public assets.

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
  "scoring": {"max_score": 100, "score_unit": "accuracy_percent"},
  "questions": [
    {
      "id": "q1",
      "type": "input",
      "topic": "Arithmetic",
      "title": "Task 1",
      "prompt": "Enter two plus two.",
      "correct": ["4"]
    }
  ]
}
```

IDs use 1–64 ASCII letters, digits, `_`, or `-`, begin with a letter or digit, and a
diagnostic ID has at least 3 characters. `exam` is at most 32 characters; `subject`,
`mark`, `topic`, and `title` are at most 128; prompts are at most 4,000; option labels
are at most 500. Text cannot be blank. `quick_count` is a strict integer from 1
through the question count. Percentage accuracy is the only score unit, so
`max_score` is exactly `100`.

Every catalog string that can appear in a PDF must have glyphs in both bundled
Liberation Sans regular and bold fonts. The required validator checks this before
deployment. The bundled set covers the shipped Latin and Cyrillic examples; add and
license an appropriate font before authoring content in another script.

There are at most 20 diagnostics and 200 questions across the school; each diagnostic
also has at most 200 questions. A question has at most 50 options/items. Each file is
at most 1 MiB, all diagnostic files together at most 5 MiB, and the complete public
bootstrap payload at most 2 MiB.

## Answer-review boundary

- `explanation` is optional, server-owned, UTF-8, and at most 2,000 characters.
- It is excluded from bootstrap and public assets.
- After an authenticated completed attempt, the Mini App may receive display-only
  `expected_answer` and resolved guidance for that attempt.
- A missing explanation uses a visibly labeled general algorithm.
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
      "forecast_delta": 10
    }
  ]
}
```

Public URLs must be HTTPS, contain no credentials or fragment, be at most 2,048
characters, and have a query of at most 512 characters. Offer IDs are unique lowercase
ASCII IDs up to 32 characters, labels/buttons are at most 128/64, and
`forecast_delta` is a strict integer from 0 to 100. Forecast points are calculated
only on the server and stored with the result.

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

The `input` type is numeric only; arbitrary text answers are not supported. A comma or dot
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

Run `python scripts/validate_school.py` and `python scripts/check_brand_isolation.py`
after every brand, link, content, or asset change. Both commands must print `OK`
before deployment. They use the same runtime validation contract as the API and bot.
