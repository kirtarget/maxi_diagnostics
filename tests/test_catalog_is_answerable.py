"""Every defect a student met on screen, turned into a guard.

These read the shipped catalog, not a fixture. A converter change that brings one
of them back fails here instead of in front of a student.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
CATALOGS = sorted((ROOT / "school" / "diagnostics").glob("*.json"))

FLATTENED_MATCHING = re.compile(
    r"^\s*(?:[А-ЯЁA-Z][.)]|_{3,})\s.*\|\s*\d[.)]\s", re.MULTILINE
)
ANSWER_SHEET = re.compile(
    r"запиш\w+\s+в\s+таблиц|в\s+ответе?\s+запиш|запиш\w+\s+цифры,\s+под\s+которыми",
    re.IGNORECASE,
)
INLINE_OPTION = re.compile(r"^\s*(\d)[.)]\s+\S", re.MULTILINE)
SEQUENCE_HINT = "Введите последовательность цифр без пробелов."
UI_COLLECTS_THE_ANSWER = {"single", "multiple", "matching"}
WORD_FORMATION_HINT = re.compile(r"\|\s*([A-Z][A-Z' -]*)\s*$", re.MULTILINE)


def questions():
    for path in CATALOGS:
        document = json.loads(path.read_text(encoding="utf-8"))
        for question in document["questions"]:
            yield path.name, document, question


@pytest.fixture(scope="module")
def catalog():
    assert CATALOGS, "the shipped catalog is missing"
    return list(questions())


def test_no_matching_table_is_left_as_text(catalog):
    """A table of pairs the converter could not read stays in the prompt as noise.

    The app draws a plain table, so `cell | cell` lines are fine on their own. A
    lettered column beside a numbered one is a matching task, and those pairs
    belong in controls the student can use.
    """
    offenders = [
        (name, question["id"])
        for name, _, question in catalog
        if len(FLATTENED_MATCHING.findall(question["prompt"])) >= 2
    ]
    assert offenders == []


def test_no_task_tells_the_student_to_write_on_a_form(catalog):
    """The printed exam says where to write the answer. The app collects it."""
    offenders = [
        (name, question["id"])
        for name, _, question in catalog
        if question["type"] in UI_COLLECTS_THE_ANSWER
        and ANSWER_SHEET.search(question["prompt"])
    ]
    assert offenders == []


def test_no_one_digit_answer_asks_for_a_sequence(catalog):
    offenders = [
        (name, question["id"])
        for name, _, question in catalog
        if question["type"] == "input"
        and SEQUENCE_HINT in question["prompt"]
        and all(
            isinstance(value, str) and value.isdigit() and len(value) == 1
            for value in question["correct"]
        )
    ]
    assert offenders == []


def test_no_choice_is_served_as_a_typed_digit(catalog):
    """Options printed in the prompt with a text box under them are a guess."""
    offenders = []
    for name, _, question in catalog:
        if question["type"] != "input":
            continue
        markers = INLINE_OPTION.findall(question["prompt"])
        answers = question["correct"]
        if len(set(markers)) < 3 or not answers:
            continue
        if all(
            isinstance(value, str) and value.isdigit() and len(value) == 1 and value in markers
            for value in answers
        ):
            offenders.append((name, question["id"]))
    assert offenders == []


def test_no_word_formation_key_lost_the_space_between_its_words(catalog):
    """`| NOT BELIEVE` with `didnotbelieve` as the only key cannot be answered."""
    offenders = []
    for name, _, question in catalog:
        if question["type"] != "text":
            continue
        hint = WORD_FORMATION_HINT.search(question["prompt"])
        if hint is None or len(hint.group(1).split()) < 2:
            continue
        if all(" " not in value for value in question["correct"]):
            offenders.append((name, question["id"], question["correct"]))
    assert offenders == []


def test_no_option_label_keeps_the_punctuation_of_its_source_list(catalog):
    offenders = [
        (name, question["id"], option["label"])
        for name, _, question in catalog
        for option in question.get("options", []) + question.get("items", [])
        if option["label"].rstrip().endswith((";", ","))
    ]
    assert offenders == []


def test_every_prompt_and_label_carries_text(catalog):
    for name, _, question in catalog:
        assert question["prompt"].strip(), (name, question["id"])
        for option in question.get("options", []) + question.get("items", []):
            assert option["label"].strip(), (name, question["id"])


def test_the_quick_diagnostic_asks_eight_questions_or_the_whole_file(catalog):
    seen = {}
    for name, document, _ in catalog:
        seen[name] = document
    for name, document in seen.items():
        total = len(document["questions"])
        assert document["quick_count"] == min(8, total), name
        assert document["quick_count"] <= document["full_count"] <= total, name
