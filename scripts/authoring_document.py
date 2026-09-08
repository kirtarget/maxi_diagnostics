"""Read a document written in the authoring format.

`docs/AUTHORING_TEMPLATE.md` is the contract, and this module is its only reader.
Nothing here guesses. The task type is a word, the items and the options live
under their own headings, the key stands in its own field. A document is either
understood whole, or the reader names the task and the field the editor has to
fix.

The editorial converter next door has to guess, which is why it exists as a
separate module: it maps free-form MAXIMUM documents onto the catalog and drops
what it cannot read. This reader refuses instead of dropping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import sys

from docx import Document
from docx.table import Table

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
for entry in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from diagnostic.numeric import is_valid_numeric_answer  # noqa: E402
from scripts.import_sharepoint_diagnostics import (  # noqa: E402
    AUTHORING_HEADER_FIELDS,
    EXAM_CODES,
    MAX_TEXT_ANSWER_CHARS,
    SEASON,
    SUBJECT_NAMES,
    SourceTable,
    _iter_blocks,
    _paragraph_images,
    _paragraph_text,
    _read_table,
    clean_line,
)


SINGLE = "один ответ"
MULTIPLE = "несколько ответов"
MATCHING = "соответствие"
SEQUENCE = "последовательность"
NUMBER = "число"
SHORT = "короткий ответ"
KINDS = (SINGLE, MULTIPLE, MATCHING, SEQUENCE, NUMBER, SHORT)

# The converter names these too, so that it can refuse a document written in
# this format. One list, read from there.
HEADER_FIELDS = AUTHORING_HEADER_FIELDS
TASK_FIELDS = ("Тип", "Тема", "Условие", "Пункты", "Варианты", "Ответ", "Решение")
SINGLE_LINE_FIELDS = frozenset({"Тип", "Тема"})

HEADER_LINE = re.compile(rf"^({'|'.join(HEADER_FIELDS)}):(?:\s+(.*))?$")
FIELD_HEADING = re.compile(rf"^({'|'.join(TASK_FIELDS)}):(?:\s+(.*))?$")
TASK_HEADING = re.compile(r"^Задание\s+(\d+)$")
ITEM_LABEL = re.compile(r"^([А-ЯЁ])[.)]\s+(.+)$")
OPTION_LABEL = re.compile(r"^(\d+)[.)]\s+(.+)$")
GRADE = re.compile(r"^\d{1,2}$")

# Which fields each type needs, and which it must not carry. A pick-one task
# with a `Пункты` block means the editor picked the wrong type, not that the
# block should be ignored.
OPTION_KINDS = frozenset({SINGLE, MULTIPLE, MATCHING, SEQUENCE})
ITEM_KINDS = frozenset({MATCHING})
# A sequence may name the cells it fills, and then the answer has to be as long.
OPTIONAL_ITEM_KINDS = frozenset({SEQUENCE})


class AuthoringError(Exception):
    """One thing the editor has to fix, named by task and field."""

    def __init__(self, message: str, *, task: int | None = None, field: str = "") -> None:
        self.message = message
        self.task = task
        self.field = field
        super().__init__(self._render())

    def _render(self) -> str:
        where = "Шапка" if self.task is None else f"Задание {self.task}"
        return f"{where}, поле «{self.field}»: {self.message}" if self.field else f"{where}: {self.message}"


@dataclass(frozen=True)
class AuthoringTask:
    number: int
    kind: str
    prompt_blocks: tuple[str, ...]
    prompt_tables: tuple[SourceTable, ...]
    items: tuple[str, ...]
    options: tuple[str, ...]
    answers: tuple[str, ...]
    explanation: tuple[str, ...]
    topic: str
    images: tuple[bytes, ...]


@dataclass(frozen=True)
class AuthoringDocument:
    subject: str
    exam: str
    grade: int
    season: str
    topic: str
    tasks: tuple[AuthoringTask, ...]


@dataclass
class _RawTask:
    number: int
    fields: dict[str, list[str]] = field(default_factory=dict)
    tables: list[SourceTable] = field(default_factory=list)
    images: list[bytes] = field(default_factory=list)
    errors: list[AuthoringError] = field(default_factory=list)


def read_authoring_document(path: Path) -> AuthoringDocument:
    """Parse the document, or raise the first thing that needs fixing."""
    document, errors = _parse(path)
    if errors:
        raise errors[0]
    assert document is not None
    return document


def check_authoring_document(path: Path) -> list[AuthoringError]:
    """Every problem the document has, in document order. Empty means it reads."""
    return _parse(path)[1]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _parse(path: Path) -> tuple[AuthoringDocument | None, list[AuthoringError]]:
    try:
        header_lines, raw_tasks = _read_blocks(path)
        header = _read_header(header_lines)
    except AuthoringError as error:
        return None, [error]

    errors: list[AuthoringError] = []
    for expected, raw in enumerate(raw_tasks, start=1):
        if raw.number != expected:
            errors.append(
                AuthoringError(
                    f"задания нумеруются по порядку, ожидалось «Задание {expected}»",
                    task=raw.number,
                )
            )
    if not raw_tasks:
        errors.append(AuthoringError("в документе нет ни одного задания"))
    if errors:
        return None, errors

    tasks: list[AuthoringTask] = []
    for raw in raw_tasks:
        task, task_errors = _build_task(raw, header["Тема"])
        errors.extend(task_errors)
        if task is not None:
            tasks.append(task)
    if errors:
        return None, errors
    return (
        AuthoringDocument(
            subject=header["Предмет"],
            exam=header["Экзамен"],
            grade=int(header["Класс"]),
            season=header["Сезон"],
            topic=header["Тема"],
            tasks=tuple(tasks),
        ),
        [],
    )


def _read_blocks(path: Path) -> tuple[list[str], list[_RawTask]]:
    document = Document(str(path))
    relationships = document.part.rels
    header_lines: list[str] = []
    tasks: list[_RawTask] = []
    current: _RawTask | None = None
    current_field: str | None = None

    for block in _iter_blocks(document):
        if isinstance(block, Table):
            if current is None or current_field != "Условие":
                raise AuthoringError(
                    "таблица стоит вне поля «Условие»",
                    task=current.number if current else None,
                    field=current_field or "",
                )
            current.tables.append(_read_table(block))
            continue

        text = clean_line(_paragraph_text(block))
        heading = TASK_HEADING.match(text)
        if heading is not None:
            current = _RawTask(number=int(heading.group(1)))
            tasks.append(current)
            current_field = None
            continue

        if current is None:
            if text:
                header_lines.append(text)
            continue

        field_heading = FIELD_HEADING.match(text)
        if field_heading is not None:
            current_field = field_heading.group(1)
            if current_field in current.fields:
                current.errors.append(
                    AuthoringError(
                        "поле встречается второй раз",
                        task=current.number,
                        field=current_field,
                    )
                )
            values = current.fields.setdefault(current_field, [])
            inline = (field_heading.group(2) or "").strip()
            if inline:
                values.append(inline)
            continue

        if current_field is None:
            if not text:
                continue
            raise AuthoringError(
                f"строка «{text}» стоит вне поля, у неё нет заголовка",
                task=current.number,
            )
        if current_field == "Условие":
            current.images.extend(_paragraph_images(block, relationships))
        if text:
            current.fields[current_field].append(text)

    return header_lines, tasks


def _read_header(lines: list[str]) -> dict[str, str]:
    header: dict[str, str] = {}
    for line in lines:
        match = HEADER_LINE.match(line)
        if match is None:
            raise AuthoringError(f"строка «{line}» не является полем шапки")
        name = match.group(1)
        if name in header:
            raise AuthoringError("поле встречается второй раз", field=name)
        value = (match.group(2) or "").strip()
        if not value:
            raise AuthoringError("значение не заполнено", field=name)
        header[name] = value
    for name in HEADER_FIELDS:
        if name not in header:
            raise AuthoringError("поле отсутствует", field=name)

    if header["Предмет"] not in set(SUBJECT_NAMES.values()):
        raise AuthoringError(
            f"неизвестный предмет «{header['Предмет']}»", field="Предмет"
        )
    if header["Экзамен"] not in EXAM_CODES:
        raise AuthoringError(
            "экзамен должен быть ЕГЭ или ОГЭ", field="Экзамен"
        )
    if not GRADE.match(header["Класс"]) or not 1 <= int(header["Класс"]) <= 11:
        raise AuthoringError("класс должен быть числом от 1 до 11", field="Класс")
    if SEASON.match(header["Сезон"]) is None:
        raise AuthoringError(
            "сезон записывается двумя парами цифр, например 21-22", field="Сезон"
        )
    return header


# --------------------------------------------------------------------------
# Task validation
# --------------------------------------------------------------------------


def _build_task(
    raw: _RawTask, document_topic: str
) -> tuple[AuthoringTask | None, list[AuthoringError]]:
    errors = list(raw.errors)

    def fail(message: str, field_name: str) -> None:
        errors.append(AuthoringError(message, task=raw.number, field=field_name))

    for name in SINGLE_LINE_FIELDS:
        if len(raw.fields.get(name, [])) > 1:
            fail("значение занимает одну строку", name)

    kind = _single_value(raw, "Тип")
    if kind is None:
        fail("поле отсутствует", "Тип")
    elif kind not in KINDS:
        fail(
            f"тип «{kind}» неизвестен, допустимы: {', '.join(KINDS)}",
            "Тип",
        )
        kind = None

    prompt_blocks = tuple(raw.fields.get("Условие", ()))
    if "Условие" not in raw.fields:
        fail("поле отсутствует", "Условие")
    elif not prompt_blocks and not raw.tables:
        fail("условие пустое", "Условие")

    items = _labelled(raw, "Пункты", ITEM_LABEL, fail)
    options = _labelled(raw, "Варианты", OPTION_LABEL, fail)

    if kind is not None:
        _check_presence(raw, kind, fail)
        answers = tuple(raw.fields.get("Ответ", ()))
        if "Ответ" not in raw.fields:
            fail("поле отсутствует", "Ответ")
        elif not answers:
            fail("ответ не заполнен", "Ответ")
        else:
            _check_answer(kind, answers, items, options, fail)
    else:
        answers = tuple(raw.fields.get("Ответ", ()))

    if errors or kind is None:
        return None, errors
    return (
        AuthoringTask(
            number=raw.number,
            kind=kind,
            prompt_blocks=prompt_blocks,
            prompt_tables=tuple(raw.tables),
            items=items,
            options=options,
            answers=answers,
            explanation=tuple(raw.fields.get("Решение", ())),
            topic=_single_value(raw, "Тема") or document_topic,
            images=tuple(raw.images),
        ),
        [],
    )


def _single_value(raw: _RawTask, name: str) -> str | None:
    values = raw.fields.get(name)
    return values[0] if values else None


def _labelled(raw: _RawTask, name: str, label: re.Pattern[str], fail) -> tuple[str, ...]:
    """Strip the `А)` or `1.` label off every line, and check the numbering."""
    lines = raw.fields.get(name)
    if not lines:
        return ()
    labels: list[str] = []
    texts: list[str] = []
    for line in lines:
        match = label.match(line)
        if match is None:
            expected = "буквы" if name == "Пункты" else "цифры"
            fail(f"строка «{line}» не начинается с {expected} и метки", name)
            continue
        labels.append(match.group(1))
        texts.append(match.group(2).strip())
    if len(set(labels)) != len(labels):
        fail("метки повторяются", name)
    if name == "Варианты" and labels != [str(index) for index in range(1, len(labels) + 1)]:
        fail("варианты нумеруются подряд начиная с 1", name)
    return tuple(texts)


def _check_presence(raw: _RawTask, kind: str, fail) -> None:
    for name, needed_by in (("Варианты", OPTION_KINDS), ("Пункты", ITEM_KINDS)):
        present = name in raw.fields
        if kind in needed_by and not present:
            fail(f"поле обязательно для типа «{kind}»", name)
        elif kind not in needed_by and present and kind not in OPTIONAL_ITEM_KINDS:
            fail(f"поле недопустимо для типа «{kind}»", name)


def _check_answer(
    kind: str,
    answers: tuple[str, ...],
    items: tuple[str, ...],
    options: tuple[str, ...],
    fail,
) -> None:
    if kind != SHORT and len(answers) > 1:
        fail(f"у задания типа «{kind}» ответ занимает одну строку", "Ответ")
        return
    key = answers[0]

    if kind == SINGLE:
        if not key.isdigit() or not 1 <= int(key) <= len(options):
            fail(
                f"ответ должен быть номером одного из {len(options)} вариантов, "
                f"получено «{key}»",
                "Ответ",
            )
    elif kind == MULTIPLE:
        parts = [part.strip() for part in key.split(",")]
        if len(parts) < 2:
            fail("нужно не меньше двух номеров через запятую", "Ответ")
        elif any(not part.isdigit() or not 1 <= int(part) <= len(options) for part in parts):
            fail(
                f"каждый номер должен быть номером одного из {len(options)} вариантов, "
                f"получено «{key}»",
                "Ответ",
            )
        elif len(set(parts)) != len(parts):
            fail("номера вариантов повторяются", "Ответ")
    elif kind == MATCHING:
        if len(key) != len(items):
            fail(
                f"у задания типа «{MATCHING}» ответ должен состоять из {len(items)} "
                f"цифр по числу пунктов, получено {len(key)}.",
                "Ответ",
            )
        elif any(not digit.isdigit() or not 1 <= int(digit) <= len(options) for digit in key):
            fail(
                f"каждая цифра ответа должна быть номером одного из {len(options)} "
                f"вариантов, получено «{key}»",
                "Ответ",
            )
    elif kind == SEQUENCE:
        if len(key) < 2 or not key.isdigit():
            fail(f"ответ должен быть двумя или более цифрами, получено «{key}»", "Ответ")
        elif any(not 1 <= int(digit) <= len(options) for digit in key):
            fail(
                f"каждая цифра ответа должна быть номером одного из {len(options)} "
                f"вариантов, получено «{key}»",
                "Ответ",
            )
        elif items and len(key) != len(items):
            fail(
                f"пунктов {len(items)}, значит и цифр в ответе должно быть {len(items)}, "
                f"получено {len(key)}",
                "Ответ",
            )
    elif kind == NUMBER:
        if not is_valid_numeric_answer(key):
            fail(f"«{key}» не является числом", "Ответ")
    elif kind == SHORT:
        for wording in answers:
            if len(wording) > MAX_TEXT_ANSWER_CHARS:
                fail(
                    f"формулировка длиннее {MAX_TEXT_ANSWER_CHARS} знаков: «{wording}»",
                    "Ответ",
                )
