"""The authoring document format shared by the converter and the checker.

An authoring document (``docs/AUTHORING_TEMPLATE.md``) is a ``.docx`` whose
body is a header of ``Поле: значение`` paragraphs followed by ``Задание N``
blocks. Inside a block every field opens with its own heading paragraph
(``Тип:``, ``Условие:``, ``Пункты:``, ``Варианты:``, ``Ответ:``, ``Решение:``,
``Тема:``) or carries its value on the same line (``Тип: один ответ``).

This module owns the vocabulary and the reader. It does not guess: a document
either parses into `Document` or the reader reports which task and field is
malformed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata

from docx import Document as load_docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run


NEEDS_REVIEW = "ТРЕБУЕТ ПРОВЕРКИ"

SUBJECTS = (
    "Английский язык", "Биология", "Информатика", "История", "Литература",
    "Математика", "Обществознание", "Русский язык", "Физика", "Химия",
)
EXAMS = ("ЕГЭ", "ОГЭ")
HEADER_FIELDS = ("Предмет", "Экзамен", "Класс", "Сезон", "Тема")
TASK_FIELDS = ("Тип", "Тема", "Условие", "Пункты", "Варианты", "Ответ", "Решение")

TYPE_SINGLE = "один ответ"
TYPE_MULTIPLE = "несколько ответов"
TYPE_MATCHING = "соответствие"
TYPE_NUMBER = "число"
TYPE_SHORT = "короткий ответ"
TYPES = (TYPE_SINGLE, TYPE_MULTIPLE, TYPE_MATCHING, TYPE_NUMBER, TYPE_SHORT)

TASK_HEADING = re.compile(r"^Задание\s+(\d+)$")
FIELD_LINE = re.compile(r"^(Тип|Тема|Условие|Пункты|Варианты|Ответ|Решение):\s*(.*)$", re.DOTALL)
HEADER_LINE = re.compile(r"^(Предмет|Экзамен|Класс|Сезон|Тема):\s*(.*)$", re.DOTALL)
ITEM_LINE = re.compile(r"^([А-ЯЁ])\)\s*(.+)$", re.DOTALL)
OPTION_LINE = re.compile(r"^(\d+)\)\s*(.+)$", re.DOTALL)
SEASON = re.compile(r"^\d{2}-\d{2}$")
FIGURE_WORDS = re.compile(
    r"рисун|схем[аеуы]|график|чертёж|чертеж|изображени|фотограф|на рисунке|диаграмм",
    re.IGNORECASE,
)
ANSWER_FORM_HINT = re.compile(
    r"^\(?в ответе? запишите (последовательность|только число|цифры|выбранные цифры)",
    re.IGNORECASE,
)


@dataclass
class Block:
    """One body element of a field: a paragraph, a table, or a figure paragraph."""

    kind: str  # "text" | "table" | "image"
    text: str = ""
    element: object = None


@dataclass
class Task:
    number: int
    fields: dict[str, list[Block]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)

    def text(self, name: str) -> str:
        return "\n".join(
            block.text for block in self.fields.get(name, ()) if block.kind == "text" and block.text
        )

    def lines(self, name: str) -> list[str]:
        return [
            block.text for block in self.fields.get(name, ()) if block.kind == "text" and block.text
        ]

    def has_image(self, name: str) -> bool:
        return any(block.kind == "image" for block in self.fields.get(name, ()))


@dataclass
class AuthoringDocument:
    header: dict[str, str]
    tasks: list[Task]
    problems: list[str]


@dataclass(frozen=True)
class Problem:
    task: int | None
    field: str | None
    message: str

    def __str__(self) -> str:
        where = "Шапка" if self.task is None else f"Задание {self.task}"
        if self.field:
            where += f", поле «{self.field}»"
        return f"{where}: {self.message}."


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFC", value).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", value).strip()


def paragraph_text(paragraph: Paragraph) -> str:
    """Plain text with superscripts as ^(…) and subscripts as _(…), like the importer."""
    parts: list[str] = []
    segment = ""
    alignment = None
    for element in paragraph._p.iter(qn("w:r")):
        run = Run(element, paragraph)
        if not run.text:
            continue
        current = "super" if run.font.superscript else "sub" if run.font.subscript else None
        if current != alignment:
            parts.append(_wrap(segment, alignment))
            segment = ""
            alignment = current
        segment += run.text
    parts.append(_wrap(segment, alignment))
    return normalize("".join(parts))


def _wrap(segment: str, alignment: str | None) -> str:
    if not segment:
        return ""
    if alignment == "super":
        return f"^({segment})"
    if alignment == "sub":
        return f"_({segment})"
    return segment


def has_drawing(element) -> bool:
    return any(True for _ in element.iter(qn("w:drawing"))) or any(
        True for _ in element.iter(qn("w:pict"))
    )


def iter_body(document):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def read_document(path) -> AuthoringDocument:
    """Parse an authoring document. Structural faults go to `problems`, never raise."""
    document = load_docx(str(path))
    header: dict[str, str] = {}
    tasks: list[Task] = []
    problems: list[str] = []
    current: Task | None = None
    field_name: str | None = None

    for block in iter_body(document):
        if isinstance(block, Table):
            if current is None:
                problems.append(str(Problem(None, None, "таблица до первого задания")))
            elif field_name is None:
                problems.append(str(Problem(current.number, None, "таблица вне поля")))
            else:
                current.fields[field_name].append(Block("table", element=block._tbl))
            continue

        text = paragraph_text(block)
        image = has_drawing(block._p)
        heading = TASK_HEADING.match(text)
        if heading:
            current = Task(number=int(heading.group(1)))
            tasks.append(current)
            field_name = None
            continue

        if current is None:
            if not text:
                continue
            found = HEADER_LINE.match(text)
            if found is None:
                problems.append(str(Problem(None, None, f"неожиданный абзац «{text[:60]}»")))
                continue
            name, value = found.group(1), normalize(found.group(2))
            if name in header:
                problems.append(str(Problem(None, name, "поле повторяется")))
            header[name] = value
            continue

        found = FIELD_LINE.match(text)
        if found:
            name, inline = found.group(1), normalize(found.group(2))
            if name in current.fields:
                problems.append(str(Problem(current.number, name, "поле повторяется")))
            current.fields[name] = []
            current.order.append(name)
            field_name = name
            if inline:
                current.fields[name].append(Block("text", inline))
            continue

        if field_name is None:
            if text or image:
                problems.append(
                    str(Problem(current.number, None, f"абзац вне поля: «{text[:60]}»"))
                )
            continue
        if image:
            current.fields[field_name].append(Block("image", text, block._p))
        elif text:
            current.fields[field_name].append(Block("text", text, block._p))

    return AuthoringDocument(header, tasks, problems)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def check_document(document: AuthoringDocument) -> list[Problem]:
    problems = [Problem(None, None, message) for message in document.problems]
    problems.extend(_check_header(document.header))
    if not document.tasks:
        problems.append(Problem(None, None, "в документе нет ни одного задания"))
    seen: set[int] = set()
    for index, task in enumerate(document.tasks, start=1):
        if task.number != index:
            problems.append(Problem(task.number, None, f"ожидался номер {index}"))
        if task.number in seen:
            problems.append(Problem(task.number, None, "номер повторяется"))
        seen.add(task.number)
        problems.extend(_check_task(task))
    return problems


def _check_header(header: dict[str, str]) -> list[Problem]:
    problems = []
    for name in HEADER_FIELDS:
        value = header.get(name, "")
        if not value:
            problems.append(Problem(None, name, "поле не заполнено"))
        elif value == NEEDS_REVIEW:
            problems.append(Problem(None, name, f"помечено «{NEEDS_REVIEW}»"))
    subject = header.get("Предмет", "")
    if subject and subject != NEEDS_REVIEW and subject not in SUBJECTS:
        problems.append(Problem(None, "Предмет", f"неизвестный предмет «{subject}»"))
    exam = header.get("Экзамен", "")
    if exam and exam != NEEDS_REVIEW and exam not in EXAMS:
        problems.append(Problem(None, "Экзамен", "ожидается ЕГЭ или ОГЭ"))
    grade = header.get("Класс", "")
    if grade and grade != NEEDS_REVIEW and not grade.isdigit():
        problems.append(Problem(None, "Класс", "ожидается число"))
    season = header.get("Сезон", "")
    if season and season != NEEDS_REVIEW and not SEASON.match(season):
        problems.append(Problem(None, "Сезон", "ожидается учебный год вида 21-22"))
    return problems


def _check_task(task: Task) -> list[Problem]:
    number = task.number
    problems: list[Problem] = []
    for name in task.fields:
        if name not in TASK_FIELDS:
            problems.append(Problem(number, name, "неизвестное поле"))

    for name, blocks in task.fields.items():
        for block in blocks:
            if block.kind == "text" and NEEDS_REVIEW in block.text:
                problems.append(Problem(number, name, f"помечено «{NEEDS_REVIEW}»"))
                break

    kind = task.text("Тип")
    if "Тип" not in task.fields:
        problems.append(Problem(number, "Тип", "поле отсутствует"))
        return problems
    if kind == NEEDS_REVIEW:
        return problems
    if kind not in TYPES:
        problems.append(Problem(number, "Тип", f"ожидается одно из: {', '.join(TYPES)}"))
        return problems

    prompt = task.text("Условие")
    if "Условие" not in task.fields:
        problems.append(Problem(number, "Условие", "поле отсутствует"))
    elif not prompt and not task.has_image("Условие") and not any(
        block.kind == "table" for block in task.fields["Условие"]
    ):
        problems.append(Problem(number, "Условие", "поле пустое"))
    if prompt and FIGURE_WORDS.search(prompt) and not task.has_image("Условие"):
        problems.append(Problem(number, "Условие", "условие ссылается на рисунок, а рисунка нет"))
    for line in task.lines("Условие"):
        if ANSWER_FORM_HINT.match(line):
            problems.append(
                Problem(number, "Условие", f"описание бланка ответа: «{line[:60]}»")
            )
            break

    if "Ответ" not in task.fields:
        problems.append(Problem(number, "Ответ", "поле отсутствует"))
        return problems
    answer_lines = task.lines("Ответ")
    answer = " ".join(answer_lines)
    if not answer:
        problems.append(Problem(number, "Ответ", "поле пустое"))
        return problems

    options = task.lines("Варианты")
    items = task.lines("Пункты")
    needs_options = kind in {TYPE_SINGLE, TYPE_MULTIPLE, TYPE_MATCHING}
    if needs_options:
        if not options:
            problems.append(Problem(number, "Варианты", "поле отсутствует или пустое"))
        else:
            problems.extend(_check_numbered(number, "Варианты", options, OPTION_LINE))
    elif options:
        problems.append(Problem(number, "Варианты", f"у типа «{kind}» вариантов нет"))
    if kind == TYPE_MATCHING:
        if not items:
            problems.append(Problem(number, "Пункты", "поле отсутствует или пустое"))
        else:
            problems.extend(_check_numbered(number, "Пункты", items, ITEM_LINE))
    elif items:
        problems.append(Problem(number, "Пункты", f"у типа «{kind}» пунктов нет"))

    if kind == TYPE_SINGLE:
        if not (answer.isdigit() and options and 1 <= int(answer) <= len(options)):
            problems.append(
                Problem(number, "Ответ", f"ожидается номер одного варианта от 1 до {len(options)}")
            )
    elif kind == TYPE_MULTIPLE:
        parts = [part.strip() for part in answer.split(",")]
        valid = all(part.isdigit() and 1 <= int(part) <= len(options) for part in parts)
        if not valid or len(set(parts)) != len(parts):
            problems.append(
                Problem(number, "Ответ", "ожидаются номера вариантов через запятую, без повторов")
            )
    elif kind == TYPE_MATCHING:
        digits = {found.group(1) for found in map(OPTION_LINE.match, options) if found}
        if not answer.isdigit() or len(answer) != len(items):
            problems.append(
                Problem(
                    number, "Ответ",
                    f"у задания типа «{TYPE_MATCHING}» ответ должен состоять из {len(items)} "
                    f"цифр по числу пунктов, получено {len(answer)}",
                )
            )
        elif not set(answer) <= digits:
            problems.append(Problem(number, "Ответ", "цифра ответа не соответствует ни одному варианту"))
    elif kind == TYPE_NUMBER:
        if len(answer_lines) != 1 or not re.fullmatch(r"-?\d+([.,]\d+)?", answer):
            problems.append(Problem(number, "Ответ", "ожидается одно число"))
    elif kind == TYPE_SHORT:
        if any(len(line) > 80 for line in answer_lines):
            problems.append(Problem(number, "Ответ", "формулировка длиннее 80 символов"))
    return problems


def _check_numbered(number: int, name: str, lines: list[str], pattern: re.Pattern) -> list[Problem]:
    problems = []
    labels = []
    for line in lines:
        found = pattern.match(line)
        if found is None:
            problems.append(Problem(number, name, f"строка без номера: «{line[:60]}»"))
            continue
        labels.append(found.group(1))
    if len(set(labels)) != len(labels):
        problems.append(Problem(number, name, "номера повторяются"))
    return problems
