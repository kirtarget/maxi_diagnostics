import io
import json
from pathlib import Path

import pytest
from docx import Document
from docx.shared import Inches
from PIL import Image

from scripts import import_sharepoint_diagnostics as importer


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "ХИМ_ОГЭ_Диагностика_21-22_Заданий 8.docx"


def _png(width: int = 40, height: int = 30) -> io.BytesIO:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _task(document, number: int) -> None:
    document.add_paragraph(f"Задание {number}")


def _answer(document, solution: str | None, key: str) -> None:
    if solution is not None:
        document.add_paragraph("Решение:")
        document.add_paragraph(solution)
    document.add_paragraph("Ответ:")
    document.add_paragraph(key)


def test_import_preserves_grouped_superscripts_and_subscripts(tmp_path):
    document = Document()
    _task(document, 1)
    prompt = document.add_paragraph("Решите уравнение: 4")
    prompt.add_run("x").font.superscript = True
    prompt.add_run(" – 3").font.superscript = True
    prompt.add_run(" = 1/8")
    document.add_paragraph("Решение:")
    solution = document.add_paragraph("2")
    solution.add_run("2(x – 3)").font.superscript = True
    solution.add_run(" = 2")
    solution.add_run("–3").font.superscript = True
    document.add_paragraph("Ответ:")
    document.add_paragraph("1,5")
    _task(document, 2)
    table = document.add_table(rows=1, cols=1)
    formula = table.cell(0, 0).paragraphs[0]
    formula.add_run("H")
    formula.add_run("2").font.subscript = True
    formula.add_run("O")
    _answer(document, None, "1")
    source = tmp_path / "formula.docx"
    document.save(source)

    tasks = importer.parse_document(source)
    assert tasks[0].prompt_blocks == ["Решите уравнение: 4^(x – 3) = 1/8"]
    assert tasks[0].solution == ["2^(2(x – 3)) = 2^(–3)"]
    assert tasks[0].answer == ["1,5"]
    assert tasks[1].prompt_tables[0].rows == ((("H_(2)O",),),)


def build_source_document(path: Path) -> None:
    """One task per supported mapping, plus an irregular key and a figure."""
    document = Document()

    _task(document, 1)
    document.add_paragraph("Выберите одно вещество.")
    document.add_paragraph("Варианты:")
    for label in ("Кислород", "Азот", "Хлор"):
        document.add_paragraph(label)
    _answer(document, "Хлор стоит третьим в списке.", "3")

    _task(document, 2)
    document.add_paragraph("Выберите два вещества.")
    document.add_paragraph("Варианты:")
    for label in ("Медь", "Сера", "Железо", "Неон"):
        document.add_paragraph(label)
    _answer(document, None, "1#3")

    _task(document, 3)
    document.add_paragraph("Установите соответствие между формулой и классом.")
    table = document.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "ФОРМУЛА"
    table.cell(0, 1).text = "КЛАСС"
    table.cell(1, 0).text = "А) HCl"
    table.cell(1, 1).text = "1) Кислота"
    table.cell(2, 0).text = "Б) NaOH"
    table.cell(2, 1).text = "2) Основание"
    _answer(document, "Соляная кислота и щёлочь.", "12")

    _task(document, 4)
    document.add_paragraph("Вычислите массовую долю в процентах.")
    _answer(document, "Считаем по формуле.", "0,25")

    _task(document, 5)
    document.add_paragraph("Расположите вещества в порядке возрастания массы.")
    _answer(document, None, "312")

    _task(document, 6)
    document.add_paragraph("Впишите название процесса.")
    _answer(document, "Переход из твёрдого состояния в газообразное.", "возгонка#сублимация")

    _task(document, 7)
    document.add_paragraph("Измерьте значение и запишите его с погрешностью.")
    _answer(document, None, "0,100,01")

    _task(document, 8)
    document.add_paragraph("Определите вещество по прибору.")
    document.add_picture(_png(), width=Inches(1))
    _answer(document, None, "42")

    document.save(str(path))


def build_repository(root: Path) -> Path:
    (root / "school" / "diagnostics").mkdir(parents=True)
    (root / "school" / "assets" / "questions").mkdir(parents=True)
    (root / "docs").mkdir()
    diagnostic = {
        "id": "oge-chemistry-1",
        "exam": "ОГЭ",
        "subject": "Химия",
        "mark": "9 класс",
        "quick_count": 1,
        "scoring": {"max_score": 100, "score_unit": "accuracy_percent"},
        "questions": [
            {
                "id": "seed1",
                "type": "input",
                "topic": "Периодический закон",
                "title": "Задание 4",
                "prompt": "Сколько протонов у углерода?",
                "max_primary_score": 1,
                "source": {
                    "provider": "maximum",
                    "official_year": 2026,
                    "approval_status": "draft",
                    "source_kind": "original",
                    "source_url": "https://maximumtest.ru/",
                    "exam_position": "4",
                    "rights_status": "original",
                    "verified_at": "2026-09-01",
                },
                "correct": ["6"],
            }
        ],
    }
    path = root / "school" / "diagnostics" / "oge-chemistry-1.json"
    path.write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


@pytest.fixture()
def imported(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    catalog_path = build_repository(tmp_path)
    importer.main([str(source_directory), "--root", str(tmp_path)])
    return tmp_path, catalog_path, source_directory


def _questions(catalog_path: Path) -> dict[str, dict]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {question["id"]: question for question in payload["questions"]}


def test_every_mapping_is_emitted_in_the_catalog_format(imported):
    _, catalog_path, _ = imported
    questions = _questions(catalog_path)

    single = questions["sp-chemistry-oge-2022-q1"]
    assert single["type"] == "single"
    assert [option["id"] for option in single["options"]] == ["a", "b", "c"]
    assert single["correct"] == "c"
    assert single["explanation"] == "Хлор стоит третьим в списке."

    multiple = questions["sp-chemistry-oge-2022-q2"]
    assert multiple["type"] == "multiple"
    assert multiple["selection_limit"] == 2
    assert multiple["correct"] == ["a", "c"]
    assert "explanation" not in multiple

    matching = questions["sp-chemistry-oge-2022-q3"]
    assert matching["type"] == "matching"
    assert [item["label"] for item in matching["items"]] == ["А) HCl", "Б) NaOH"]
    assert [option["id"] for option in matching["options"]] == ["o1", "o2"]
    assert matching["correct"] == {"i1": "o1", "i2": "o2"}
    assert "ФОРМУЛА" not in matching["prompt"]

    numeric = questions["sp-chemistry-oge-2022-q4"]
    assert numeric["type"] == "input"
    assert numeric["correct"] == ["0,25", "0.25"]

    sequence = questions["sp-chemistry-oge-2022-q5"]
    assert sequence["type"] == "input"
    assert sequence["correct"] == ["312"]
    assert sequence["prompt"].endswith(importer.SEQUENCE_HINT)

    text = questions["sp-chemistry-oge-2022-q6"]
    assert text["type"] == "text"
    assert text["correct"] == ["возгонка", "сублимация"]
    assert text["max_length"] == 80


def test_source_metadata_marks_editorial_drafts(imported):
    _, catalog_path, _ = imported
    source = _questions(catalog_path)["sp-chemistry-oge-2022-q1"]["source"]
    assert source == {
        "provider": "maximum_editorial",
        "official_year": 2022,
        "approval_status": "draft",
        "source_kind": "original",
        "source_url": "https://maximumtest.ru/",
        "rights_status": "original",
        "verified_at": source["verified_at"],
    }


def test_every_topic_is_a_placeholder_a_methodologist_still_has_to_map(imported):
    _, catalog_path, _ = imported

    for question in _questions(catalog_path).values():
        if not question["id"].startswith(importer.ID_PREFIX):
            continue
        expected = f"Задание {question['id'].rsplit('-q', 1)[1]}"
        assert question["topic"] == expected
        assert question["title"] == expected
        assert question["max_primary_score"] == 1
        assert "exam_position" not in question["source"]


def test_irregular_key_is_skipped_and_explained_in_the_report(imported):
    root, catalog_path, _ = imported
    assert "sp-chemistry-oge-2022-q7" not in _questions(catalog_path)
    report = (root / "authoring" / "sharepoint-import" / "report.md").read_text(
        encoding="utf-8"
    )
    assert SOURCE_NAME in report
    assert "| 7 | skipped | - | irregular_key | 0 |" in report
    assert "| 1 | imported | single | - | 0 |" in report
    assert f"| {SOURCE_NAME} | 7 | - | irregular_key |" in report
    assert "## Темы, требующие сопоставления" in report


def test_inline_figure_becomes_a_deduplicated_question_asset(imported):
    root, catalog_path, _ = imported
    question = _questions(catalog_path)["sp-chemistry-oge-2022-q8"]
    assert question["asset"] == "assets/questions/sp-chemistry-oge-2022-q8-1.png"
    assert "assets" not in question
    asset = root / "school" / question["asset"]
    with Image.open(asset) as image:
        assert image.size == (40, 30)


def test_existing_questions_keep_their_exact_bytes(imported):
    _, catalog_path, _ = imported
    text = catalog_path.read_text(encoding="utf-8")
    assert '"id": "seed1"' in text
    assert '"correct": [\n        "6"\n      ]' in text
    assert json.loads(text)["questions"][0]["id"] == "seed1"
    assert json.loads(text)["quick_count"] == 1


def test_rerunning_the_import_replaces_only_the_prefixed_questions(imported):
    root, catalog_path, source_directory = imported
    before = catalog_path.read_bytes()
    assets_before = {
        path.name: path.read_bytes()
        for path in (root / "school" / "assets" / "questions").iterdir()
    }

    importer.main([str(source_directory), "--root", str(root)])

    assert catalog_path.read_bytes() == before
    assert {
        path.name: path.read_bytes()
        for path in (root / "school" / "assets" / "questions").iterdir()
    } == assets_before


def test_stale_prefixed_assets_are_removed_on_reimport(imported):
    root, _, source_directory = imported
    stale = root / "school" / "assets" / "questions" / "sp-old-question-1.png"
    stale.write_bytes(_png(8, 8).getvalue())
    kept = root / "school" / "assets" / "questions" / "legacy.png"
    kept.write_bytes(_png(8, 8).getvalue())

    importer.main([str(source_directory), "--root", str(root)])

    assert not stale.exists()
    assert kept.exists()


def test_dry_run_leaves_the_repository_untouched(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    catalog_path = build_repository(tmp_path)
    before = catalog_path.read_bytes()

    importer.main([str(source_directory), "--root", str(tmp_path), "--dry-run"])

    assert catalog_path.read_bytes() == before
    assert not (tmp_path / "authoring").exists()


def test_repository_catalogs_round_trip_without_reformatting():
    for path in sorted((ROOT / "school" / "diagnostics").glob("*.json")):
        target = importer.read_target(path)
        rendered = importer.render_target(target, target.chunks)
        assert rendered == path.read_text(encoding="utf-8")


def test_the_import_never_shortens_the_full_diagnostic(imported):
    _, catalog_path, _ = imported
    document = json.loads(catalog_path.read_text(encoding="utf-8"))

    assert "full_count" not in document
    assert document["questions"][0]["id"] == "seed1"
    assert len(document["questions"]) > 1


def test_the_repository_catalog_holds_only_sharepoint_questions():
    paths = sorted((ROOT / "school" / "diagnostics").glob("*.json"))
    assert paths

    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        # Every catalog pins `full_count`, so a later bank import cannot lengthen
        # the diagnostic. The leading questions stay the diagnostic; whatever a
        # topical package appends after them feeds the trainer and the daily plan.
        assert document["quick_count"] <= document["full_count"], path.name
        assert document["full_count"] <= len(document["questions"]), path.name
        assert all(
            question["id"].startswith(importer.ID_PREFIX)
            for question in document["questions"]
        ), path.name
        assert 1 <= document["quick_count"] <= 5, path.name
        assert document["quick_count"] <= len(document["questions"]), path.name


def test_reordered_numeric_keys_become_accepted_input_variants():
    task = importer.SourceTask(number=1, answer=["1234#2134#1243#2143"])
    task.prompt_blocks.append("Заполните таблицу.")

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert payload["correct"] == ["1234", "2134", "1243", "2143"]
    assert payload["sequence"] is True


def test_packed_multi_digit_keys_are_still_skipped():
    task = importer.SourceTask(number=1, answer=["12#345"])
    task.prompt_blocks.append("Ответьте на два вопроса.")

    assert importer.classify(task) == ("skip", "irregular_key")


def test_unsupported_pdf_glyphs_are_normalized_instead_of_dropping_the_task():
    assert importer.clean_line("сто́л") == "стол"
    assert importer.clean_line("𝑚 · 𝑔") == "m · g"
    assert importer.clean_line("∠ABC") == "угол ABC"
    assert importer.renders(importer.clean_line("∠ABC = 30°"))


PLAN_SOURCE_NAME = "ХИМ_Кислоты_Заданий 8.docx"


def write_plan(path: Path, entries: list[dict]) -> Path:
    path.write_text(
        json.dumps({"sources": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return path


def plan_entry(source: Path, **overrides) -> dict:
    entry = {
        "path": f"/sites/x/{source.name}",
        "file_name": source.name,
        "content_hash": importer.file_digest(source),
        "subject": "chemistry",
        "exam": "oge",
        "season": "21-22",
        "topic": "Кислоты и основания",
        "topic_slug": "kisloty",
        "declared_question_count": 8,
    }
    entry.update(overrides)
    return entry


@pytest.fixture()
def planned(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    source = source_directory / PLAN_SOURCE_NAME
    build_source_document(source)
    catalog_path = build_repository(tmp_path)
    plan = write_plan(tmp_path / "plan.json", [plan_entry(source)])
    return tmp_path, catalog_path, source_directory, plan


def test_plan_supplies_subject_exam_year_and_topic(planned):
    root, catalog_path, source_directory, plan = planned

    importer.main([str(source_directory), "--plan", str(plan), "--root", str(root)])

    questions = _questions(catalog_path)
    single = questions["sp-chemistry-oge-2022-kisloty-q1"]
    assert single["type"] == "single"
    assert single["topic"] == "Кислоты и основания"
    assert single["title"] == "Задание 1"
    assert single["source"]["official_year"] == 2022


def test_plan_hash_mismatch_stops_the_import(planned):
    root, _, source_directory, _ = planned
    source = source_directory / PLAN_SOURCE_NAME
    plan = write_plan(
        root / "bad-plan.json", [plan_entry(source, content_hash="0" * 64)]
    )

    with pytest.raises(importer.ImportError, match="does not match the plan"):
        importer.main([str(source_directory), "--plan", str(plan), "--root", str(root)])


def test_a_file_outside_the_plan_keeps_its_filename_derived_id(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    catalog_path = build_repository(tmp_path)
    plan = write_plan(
        tmp_path / "plan.json",
        [plan_entry(source_directory / SOURCE_NAME, file_name="другой.docx")],
    )

    importer.main([str(source_directory), "--plan", str(plan), "--root", str(tmp_path)])
    with_plan = catalog_path.read_bytes()
    importer.main([str(source_directory), "--root", str(tmp_path)])

    assert catalog_path.read_bytes() == with_plan
    assert "sp-chemistry-oge-2022-q1" in _questions(catalog_path)


def test_colliding_ids_stop_the_import(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    build_source_document(source_directory / "ХИМ_ОГЭ_МРКТ_21-22_Заданий 8.docx")
    build_repository(tmp_path)

    with pytest.raises(importer.ImportError, match="Duplicate question ids"):
        importer.main([str(source_directory), "--root", str(tmp_path), "--dry-run"])


def test_a_numeric_key_may_end_with_a_full_stop():
    task = importer.SourceTask(number=1, answer=["1,84."])
    task.prompt_blocks.append("Вычислите плотность.")

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert payload["correct"] == ["1,84", "1.84"]


def test_an_explanation_paragraph_after_the_key_moves_to_the_solution(tmp_path):
    document = Document()
    _task(document, 1)
    document.add_paragraph("Вычислите массовую долю.")
    document.add_paragraph("Ответ:")
    document.add_paragraph("0,25")
    document.add_paragraph("Пояснение: делим массу вещества на массу раствора.")
    source = tmp_path / "explanation.docx"
    document.save(str(source))

    task = importer.parse_document(source)[0]

    assert task.answer == ["0,25"]
    assert task.solution == ["Пояснение: делим массу вещества на массу раствора."]


def test_open_answer_tasks_are_skipped_with_their_own_reason():
    task = importer.SourceTask(
        number=1,
        answer=["Развёрнутый ответ"],
        solution=["Критерии оценивания. Максимальный балл — 3."],
    )
    task.prompt_blocks.append("Обоснуйте ответ.")

    assert importer.classify(task) == ("skip", "open_answer")


def test_pdf_unsafe_degree_and_figure_dash_are_replaced():
    assert importer.clean_line("t = 30ᵒC") == "t = 30°C"
    assert importer.clean_line("5 ‒ 3") == "5 - 3"
    assert importer.renders(importer.clean_line("t = 30ᵒC"))


def test_base_diagnostic_questions_stay_ahead_of_bank_packages(tmp_path):
    """The leading questions are the diagnostic, so `full_count` keeps covering them."""
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    topical = source_directory / PLAN_SOURCE_NAME
    build_source_document(topical)
    catalog_path = build_repository(tmp_path)
    plan = write_plan(
        tmp_path / "plan.json", [plan_entry(topical, season="20-21")]
    )

    importer.main([str(source_directory), "--plan", str(plan), "--root", str(tmp_path)])

    identifiers = [
        question["id"]
        for question in json.loads(catalog_path.read_text(encoding="utf-8"))["questions"]
        if question["id"].startswith(importer.ID_PREFIX)
    ]
    topical_start = min(
        index for index, identifier in enumerate(identifiers) if "kisloty" in identifier
    )
    assert all("kisloty" not in identifier for identifier in identifiers[:topical_start])
    assert identifiers[0] == "sp-chemistry-oge-2022-q1"


def _numbered_source(document, number: int, lines: list[str], *, leading: bool) -> None:
    """A task whose option list is typed as plain `N)` prompt lines."""
    _task(document, number)
    stem = "Укажите порядковый номер верного утверждения."
    blocks = lines + [stem] if leading else [stem] + lines
    for block in blocks:
        document.add_paragraph(block)


OPTION_LINES = ["1) Первое;", "2) Второе;", "3) Третье;", "4) Четвёртое."]


def test_a_trailing_numbered_block_becomes_the_option_list(tmp_path):
    document = Document()
    _numbered_source(document, 1, OPTION_LINES, leading=False)
    _answer(document, None, "3")
    source = tmp_path / "inline-options.docx"
    document.save(str(source))

    task = importer.parse_document(source)[0]

    assert task.options == ["Первое;", "Второе;", "Третье;", "Четвёртое."]
    assert task.prompt_blocks == ["Укажите порядковый номер верного утверждения."]
    assert importer.classify(task) == ("single", {"indices": [3]})


def test_a_leading_numbered_block_becomes_the_option_list(tmp_path):
    """One editor typed the shared option list above the question stem."""
    document = Document()
    _numbered_source(document, 1, OPTION_LINES, leading=True)
    _answer(document, None, "2")
    source = tmp_path / "leading-options.docx"
    document.save(str(source))

    task = importer.parse_document(source)[0]

    assert task.options == ["Первое;", "Второе;", "Третье;", "Четвёртое."]
    assert task.prompt_blocks == ["Укажите порядковый номер верного утверждения."]
    assert importer.classify(task) == ("single", {"indices": [2]})


def test_a_numbered_block_stays_in_the_prompt_when_the_key_orders_it(tmp_path):
    """`2314` reorders the four lines; they are not four answers to pick from."""
    document = Document()
    _numbered_source(document, 1, OPTION_LINES, leading=False)
    _answer(document, None, "2314")
    source = tmp_path / "ordering.docx"
    document.save(str(source))

    task = importer.parse_document(source)[0]

    assert task.options == []
    assert task.prompt_blocks[-1] == "4) Четвёртое."
    assert importer.classify(task)[0] == "input"


def test_a_numbered_block_stays_in_the_prompt_when_it_is_part_of_the_question(tmp_path):
    """A numbered list the prompt wraps on both sides is condition text."""
    document = Document()
    _task(document, 1)
    for block in ("Дан список величин.", *OPTION_LINES, "Сколько из них положительны?"):
        document.add_paragraph(block)
    _answer(document, None, "2")
    source = tmp_path / "mid-prompt.docx"
    document.save(str(source))

    task = importer.parse_document(source)[0]

    assert task.options == []
    assert len(task.prompt_blocks) == 6


def test_a_numbered_block_with_a_gap_is_not_an_option_list(tmp_path):
    document = Document()
    _numbered_source(document, 1, ["1) Первое;", "2) Второе;", "4) Четвёртое."], leading=False)
    _answer(document, None, "2")
    source = tmp_path / "gap.docx"
    document.save(str(source))

    assert importer.parse_document(source)[0].options == []


def test_two_numbered_lines_are_too_few_to_be_an_option_list(tmp_path):
    document = Document()
    _numbered_source(document, 1, ["1) Первое;", "2) Второе."], leading=False)
    _answer(document, None, "2")
    source = tmp_path / "pair.docx"
    document.save(str(source))

    assert importer.parse_document(source)[0].options == []


def test_a_single_digit_key_carries_no_sequence_hint():
    task = importer.SourceTask(number=1, answer=["3"])
    task.prompt_blocks.append("Сколько молекул участвует в реакции?")

    kind, payload = importer.classify(task)

    assert kind == "input"
    assert payload["sequence"] is False


def test_a_multi_digit_key_still_carries_the_sequence_hint():
    task = importer.SourceTask(number=1, answer=["134"])
    task.prompt_blocks.append("Выпишите номера верных утверждений.")

    assert importer.classify(task)[1]["sequence"] is True


def _english_source() -> importer.SourceFile:
    return importer.SourceFile(
        path=Path("АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx"),
        exam="ЕГЭ",
        subject_code="english-language",
        year=2022,
        declared_tasks=23,
        tasks=(),
    )


def _word_formation(key: str, hint: str) -> importer.SourceTask:
    task = importer.SourceTask(number=12, answer=[key])
    task.prompt_blocks.append("Преобразуйте слово так, чтобы оно подошло по смыслу.")
    task.prompt_blocks.append(f"12 | Apollo ________ by her grace. | {hint}")
    return task


def test_a_glued_multi_word_key_is_skipped_instead_of_shipping_unanswerable(tmp_path):
    for key, hint in (("wasimpressed", "IMPRESS"), ("didnotbelieve", "NOT BELIEVE")):
        task = _word_formation(key, hint)
        kind, payload = importer.classify(task)
        assert kind == "text"
        assert importer.build_question(
            _english_source(), task, kind, payload, verified_at="2026-09-04"
        ) == "glued_answer"


def test_a_regular_word_formation_key_still_ships(tmp_path):
    for key, hint in (("greatest", "GREAT"), ("unbelievable", "BELIEVE"), ("women", "WOMAN")):
        task = _word_formation(key, hint)
        kind, payload = importer.classify(task)
        question = importer.build_question(
            _english_source(), task, kind, payload, verified_at="2026-09-04"
        )
        assert question["correct"] == [key]


def test_verified_at_can_be_pinned_to_a_given_day(tmp_path):
    source_directory = tmp_path / "docx"
    source_directory.mkdir()
    build_source_document(source_directory / SOURCE_NAME)
    catalog_path = build_repository(tmp_path)

    importer.main(
        [str(source_directory), "--root", str(tmp_path), "--verified-at", "2026-09-04"]
    )

    questions = _questions(catalog_path)
    imported_questions = [
        question
        for identifier, question in questions.items()
        if identifier.startswith(importer.ID_PREFIX)
    ]
    assert imported_questions
    assert all(
        question["source"]["verified_at"] == "2026-09-04"
        for question in imported_questions
    )


def test_a_matching_table_labelled_with_dots_becomes_a_matching_question():
    """Editors label the two columns with a dot as often as with a bracket."""
    table = importer.SourceTable(rows=(
        (("События",), ("Годы",)),
        (("А. Первое событие",), ("1. 1185 г.",)),
        (("Б. Второе событие",), ("2. 1825 г.",)),
        (("B. Третье событие",), ("3. 1613 г.",)),
        ((), ("4. 1762 г.",)),
    ))
    task = importer.SourceTask(
        number=1,
        prompt_blocks=["Установите соответствие."],
        prompt_tables=[table],
        answer=["213"],
    )

    kind, payload = importer.classify(task)

    assert kind == "matching"
    # The third row is labelled with a Latin B that looks like the Cyrillic one.
    assert len(payload["items"]) == 3
    assert [digit for digit, _ in payload["options"]] == ["1", "2", "3", "4"]


def test_an_unreadable_matching_table_is_skipped_instead_of_flattened():
    """A table the converter cannot read renders as `left | right` noise."""
    table = importer.SourceTable(rows=(
        (("Величины",), ("Значения",)),
        (("Первый пункт без буквы",), ("1) Первое",)),
        (("Б) Второй пункт",), ("2) Второе",)),
        ((), ("3) Третье",)),
    ))
    task = importer.SourceTask(
        number=1,
        prompt_blocks=["Установите соответствие."],
        prompt_tables=[table],
        answer=["12"],
    )
    kind, payload = importer.classify(task)
    assert kind == "input"

    question = importer.build_question(
        importer.SourceFile(Path("f.docx"), "ЕГЭ", "physics", 2022, 1, ()),
        task, kind, payload, verified_at="2026-09-04",
    )

    assert importer._rejection(question, []) == "unreadable_matching"


def test_answer_sheet_instructions_leave_the_prompt_the_app_collects():
    """The Mini App collects the answer, so telling the student where to write it lies."""
    stripped = importer.strip_answer_sheet_instructions(
        "Установите соответствие между событиями и годами.\n"
        "В ответ запишите последовательность цифр, соответствующую буквам АБВ."
    )
    assert stripped == "Установите соответствие между событиями и годами."

    # The sentence survives without its full stop in some documents.
    assert importer.strip_answer_sheet_instructions(
        "Подберите позицию второго столбца.\nВ ответ запишите последовательность цифр"
    ) == "Подберите позицию второго столбца."

    # A task that is genuinely about writing a measurement keeps its wording.
    kept = "Запишите результат измерения напряжения с учётом погрешности."
    assert importer.strip_answer_sheet_instructions(kept) == kept


def test_option_labels_drop_the_list_punctuation_of_their_source():
    assert importer._option_label("Реформация в Германии;") == "Реформация в Германии"
    assert importer._option_label("вторая позиция,") == "вторая позиция"
    assert importer._option_label("обычный вариант") == "обычный вариант"


def test_a_matching_task_keeps_the_data_table_it_reasons_about():
    """Only the table that became the pairs is dropped from the prompt."""
    data = importer.SourceTable(rows=(
        (("Статья",), ("Доля",)),
        (("На армию",), ("40 %",)),
        (("На флот",), ("10 %",)),
    ))
    pairs = importer.SourceTable(rows=(
        (("Начала",), ("Завершения",)),
        (("А) Расходы на армию",), ("1) Составляли более половины.",)),
        (("Б) Расходы на флот",), ("2) Были меньше десятой части.",)),
    ))
    task = importer.SourceTask(
        number=7,
        prompt_blocks=["Используя данные таблицы, завершите суждения."],
        prompt_tables=[data, pairs],
        answer=["12"],
    )

    kind, payload = importer.classify(task)
    assert kind == "matching"

    question = importer.build_question(
        importer.SourceFile(Path("f.docx"), "ОГЭ", "history", 2022, 1, ()),
        task, kind, payload, verified_at="2026-09-04",
    )

    assert "На армию | 40 %" in question["prompt"]
    assert "Составляли более половины" not in question["prompt"]
