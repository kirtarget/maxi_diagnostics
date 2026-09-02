# Авторский конвейер заданий MAXIMUM

## Назначение

Этот документ задаёт воспроизводимый формат авторских пакетов для оригинальных
заданий MAXIMUM, составленных по утверждённой матрице ФИПИ. Он является контрактом
для будущих `validate_original_content.py` и `import_original_content.py`.

Конвейер не копирует открытый банк ФИПИ. Условие, правильный ответ и объяснение
создаёт MAXIMUM. ФИПИ используется как нормативный источник структуры экзамена,
позиции задания, проверяемого элемента и максимального первичного балла. Основания
этого решения и официальные ссылки собраны в
[`FIPI_CONTENT_SOURCES_2026.md`](FIPI_CONTENT_SOURCES_2026.md).

Автоматическая проверка доказывает корректность формы данных и поведение runtime.
Она не доказывает предметную истинность ответа, качество объяснения, соответствие
позиции КИМ или оригинальность формулировки. Эти четыре решения принимает человек.

## Границы первой версии

- Один пакет относится ровно к одной существующей диагностике.
- Пакет заменяет существующие вопросы или добавляет новые вопросы в конец.
- Пакет не меняет `exam`, `subject`, `mark`, `quick_count` или `scoring` диагностики.
- Замена сохраняет индекс вопроса. Добавление не меняет состав quick-режима.
- Пакет не публикуется напрямую в БД или работающий сервис.
- Импортёр формирует один staged JSON-файл. После этого обязательны Git review,
  `validate_school.py`, `check_brand_isolation.py`, тесты и обычный deployment.
- Загрузка новых изображений через `/admin/content` не поддерживается. Пакет может
  ссылаться только на уже проверенный asset либо поставлять MAXIMUM-owned asset по
  правилам этого документа.
- На 1 сентября 2026 года рабочая нормативная версия равна 2026. Проекты 2027 года
  нельзя использовать в пакете со статусом `approved`.

## Исходное место в каталоге

До кампании `fipi-2026-min15` в `school/diagnostics/` находились 19 диагностик и
178 вопросов. Таблица ниже фиксирует этот baseline. После внедрения компактного
bootstrap и ленивой загрузки одной диагностики глобальная связь с лимитом 200
удалена. Сохраняются пределы 20 диагностик, 200 вопросов в одной диагностике,
1 MiB на файл, 5 MiB на каталог и 2 MiB на один authenticated detail response.
Материализованный каталог содержит 301 вопрос.

| Diagnostic ID | Экзамен | Предмет | Вопросов | Quick | Типы |
|---|---|---|---:|---:|---|
| `ege-biology-1207` | ЕГЭ | Биология | 6 | 3 | input 5, multiple 1 |
| `ege-chemistry-1208` | ЕГЭ | Химия | 6 | 3 | input 3, multiple 3 |
| `ege-english-language-1204` | ЕГЭ | Английский язык | 8 | 3 | input 1, single 7 |
| `ege-history-1211` | ЕГЭ | История | 5 | 3 | input 5 |
| `ege-informatics-1205` | ЕГЭ | Информатика | 3 | 3 | input 3 |
| `ege-literature-1209` | ЕГЭ | Литература | 3 | 3 | input 1, multiple 2 |
| `ege-mathematics-1212` | ЕГЭ | Математика | 4 | 3 | input 4 |
| `ege-physics-1206` | ЕГЭ | Физика | 6 | 3 | input 4, multiple 2 |
| `ege-russian-language-1213` | ЕГЭ | Русский язык | 5 | 3 | multiple 5 |
| `ege-social-studies-1210` | ЕГЭ | Обществознание | 5 | 3 | input 1, multiple 4 |
| `oge-biology-699` | ОГЭ | Биология | 20 | 3 | input 8, multiple 7, single 5 |
| `oge-chemistry-192` | ОГЭ | Химия | 19 | 3 | input 11, multiple 8 |
| `oge-english-language-202` | ОГЭ | Английский язык | 2 | 2 | input 2 |
| `oge-history-196` | ОГЭ | История | 14 | 3 | input 11, multiple 1, single 2 |
| `oge-informatics-466` | ОГЭ | Информатика | 11 | 3 | input 11 |
| `oge-mathematics-198` | ОГЭ | Математика | 19 | 3 | input 16, multiple 1, single 2 |
| `oge-physics-197` | ОГЭ | Физика | 18 | 3 | input 12, multiple 4, single 2 |
| `oge-russian-language-379` | ОГЭ | Русский язык | 9 | 3 | input 4, multiple 5 |
| `oge-social-studies-195` | ОГЭ | Обществознание | 15 | 3 | input 2, single 13 |

Runtime поддерживает `single`, `multiple`, `matching` и числовой `input`. В текущих
19 файлах нет `matching`, но авторский формат его поддерживает.

## Структура пакета

Пакет является каталогом с такой формой:

```text
authoring/original/<package_id>/
  package.json
  assets/
    <sha256>.<ext>
```

`package.json` хранится как строгий UTF-8 JSON без BOM. Дубли ключей, `NaN`,
`Infinity`, управляющие символы кроме разрешённых LF и неизвестные поля запрещены.
Имена package directory и `package_id` совпадают.

### Полная data shape

```json
{
  "schema_version": 1,
  "package_id": "original-ege-math-2026-batch-01",
  "target": {
    "diagnostic_id": "ege-mathematics-1212",
    "expected_catalog_sha256": "64 lowercase hex characters"
  },
  "matrix": {
    "exam": "ЕГЭ",
    "subject": "Математика",
    "official_year": 2026,
    "official_status": "approved",
    "documents": [
      {
        "id": "spec-2026",
        "kind": "specification",
        "url": "https://doc.fipi.ru/ege/demoversii-specifikacii-kodifikatory/2026/ma_11_2026.zip",
        "sha256": "64 lowercase hex characters",
        "retrieved_at": "2026-09-01"
      }
    ],
    "positions": [
      {
        "id": "position-06",
        "exam_position": "6",
        "topic_codes": ["code-from-approved-codifier"],
        "max_primary_score": 1,
        "task_model": "Краткое описание модели задания",
        "task_locator": {
          "document_id": "spec-2026",
          "locator": "Таблица 3, строка 6"
        },
        "score_locator": {
          "document_id": "spec-2026",
          "locator": "Таблица 4, строка 6"
        }
      }
    ]
  },
  "assets": [],
  "items": [
    {
      "operation": "replace",
      "expected_existing_question_sha256": "64 lowercase hex characters",
      "question": {
        "id": "q9891",
        "type": "input",
        "topic": "Показательные уравнения",
        "title": "Задание 6",
        "prompt": "Оригинальное условие MAXIMUM.",
        "max_primary_score": 1,
        "source": {
          "provider": "maximum",
          "official_year": 2026,
          "approval_status": "approved",
          "source_kind": "original",
          "source_url": "https://maximumtest.ru/",
          "fipi_project_id": null,
          "fipi_question_id": null,
          "exam_position": "6",
          "official_criteria_url": "https://doc.fipi.ru/ege/demoversii-specifikacii-kodifikatory/2026/ma_11_2026.zip",
          "rights_status": "original",
          "verified_at": "2026-09-01"
        },
        "explanation": "Самостоятельный разбор MAXIMUM с обоснованием ответа.",
        "learning_material_text": "Краткая подсказка по теме.",
        "learning_material_url": "https://maximumtest.ru/uchebnik/matematika",
        "correct": ["2"]
      },
      "matrix_position_id": "position-06",
      "evidence": {
        "originality": {
          "declaration_version": 1,
          "author_id": "editor-017",
          "declared_at": "2026-09-01T10:00:00Z"
        },
        "answer": {
          "method": "independent_solution",
          "canonical_answer": ["2"],
          "reference": null,
          "derivation_summary": "Краткая внутренняя запись способа проверки ответа."
        },
        "score": {
          "max_primary_score": 1,
          "matrix_position_id": "position-06"
        },
        "answer_checks": [
          {"submitted": "2", "expected_is_correct": true},
          {"submitted": "3", "expected_is_correct": false}
        ]
      },
      "workflow": {
        "status": "approved",
        "authored_by": "editor-017",
        "authored_at": "2026-09-01T10:00:00Z",
        "subject_review": {
          "reviewer_id": "expert-math-04",
          "reviewed_at": "2026-09-01T12:00:00Z",
          "review_subject_sha256": "64 lowercase hex characters",
          "answer_correct": true,
          "explanation_correct": true,
          "score_correct": true,
          "matrix_match": true,
          "originality_reviewed": true
        },
        "approval": {
          "approver_id": "expert-math-04",
          "approved_at": "2026-09-01T12:15:00Z",
          "review_subject_sha256": "64 lowercase hex characters"
        }
      },
      "question_sha256": "64 lowercase hex characters",
      "review_subject_sha256": "64 lowercase hex characters"
    }
  ]
}
```

Значение `null` разрешено только там, где это явно показано. Импортёр удаляет
необязательные поля со значением `null` перед передачей данных в runtime Pydantic
model. Пустая строка не заменяет `null`.

## Ограничения полей пакета

### Envelope

- `schema_version` равен целому числу `1`.
- `package_id` соответствует `^[a-z0-9][a-z0-9-]{2,63}$`.
- `target.diagnostic_id` обязан существовать в текущем каталоге.
- `target.expected_catalog_sha256` равен SHA-256 сырых байтов текущего JSON-файла.
- `matrix.exam` и `matrix.subject` точно совпадают с целевой диагностикой.
- `matrix.official_year` находится в диапазоне 2000..2100.
- `matrix.official_status` равен `approved` или `draft`.
- `documents`, `positions` и `items` не пусты.
- `items` отсортированы строго по `question.id` в ASCII-порядке.

### Официальные документы

- `documents[].id` уникален в пакете и соответствует runtime ID pattern.
- `kind` равен `specification`, `codifier`, `demo`, `open_variant`,
  `commission_material` или `open_bank`.
- `url` использует HTTPS и host `fipi.ru` либо его поддомен.
- `sha256` является зафиксированным human-supplied hash байтов документа в дату
  `retrieved_at`. Первая версия offline validator проверяет формат и внутренние
  ссылки, но не подтверждает этот hash без отдельного доверенного evidence cache.
- PDF и страницы ФИПИ не включаются в пакет. Хранятся URL, hash и locator.
- Для `approved` пакета каждый используемый документ относится к утверждённому
  комплекту того же `official_year`.
- Документ проекта 2027 года имеет `matrix.official_status=draft`. Такой пакет не
  может перейти в `workflow.status=approved`.

### Матрица позиций

- `positions[].id` уникален в пакете.
- `exam_position` является непустой строкой. Строка сохраняет обозначения вроде
  `24`, `24.1` или `устная-3` без числового предположения.
- `topic_codes` содержит уникальные непустые строки из утверждённого кодификатора.
- `max_primary_score` является строгим целым числом 1..100.
- Оба locator ссылаются на существующий `document_id`.
- `locator` является проверяемым адресом внутри документа. Примеры включают номер
  таблицы, строку, страницу и пункт. Текст вроде `где-то в спецификации` запрещён.

### Runtime question

`question` должен пройти актуальную `Diagnostic` model без преобразований смысла.
Импортёр не исправляет ID, текст, ответ, балл или источник.

Общие поля:

- `id` соответствует runtime pattern и уникален в целевой диагностике после импорта.
- `topic`, `title`, `prompt` и `explanation` не пусты.
- `explanation` обязательна для `reviewed` и `approved`.
- `max_primary_score` точно равен баллу выбранной matrix position.
- `source.provider` равен `maximum` для оригинального задания.
- `source.source_kind` и `source.rights_status` равны `original`.
- `source.source_url` равен утверждённому публичному publisher URL MAXIMUM.
- `source.official_year` равен `matrix.official_year`.
- `source.exam_position` равен позиции из matrix.
- `source.official_criteria_url` совпадает с URL документа, указанного в
  `score_locator`.
- `source.verified_at` равен календарной дате предметной проверки.
- `source.approval_status` равен `approved` только у импортируемого approved item.
- `fipi_project_id` и `fipi_question_id` обычно отсутствуют у полностью
  оригинального задания. Они допустимы только как link-only provenance. Их наличие
  не разрешает копировать формулировку банка.

Типовые поля:

- `single` содержит уникальные `options[].id` и один `correct`, который существует
  в options.
- `multiple` содержит уникальные options. `correct` содержит уникальные ID,
  существует в options и имеет длину `selection_limit`.
- `matching` содержит уникальные `items` и options. Ключи `correct` точно равны ID
  items. Значения существуют в options.
- `input` содержит 1..20 строковых числовых вариантов. Каждый вариант соответствует
  runtime numeric grammar. Варианты, равные после `Decimal(value.replace(",", "."))`,
  считаются дублями и запрещены.

### Operation

Для `replace`:

- `question.id` уже существует.
- `expected_existing_question_sha256` обязателен и совпадает с canonical hash
  существующего private question.
- Вопрос заменяется на прежнем индексе.

Для `add`:

- `question.id` отсутствует в диагностике и во всех других approved packages.
- `expected_existing_question_sha256` отсутствует.
- Вопрос добавляется в конец после всех замен.
- Все additions применяются в порядке `question.id`.

Любое другое значение operation запрещено. Импортёр не удаляет и не переставляет
вопросы.

### Assets

Запись asset имеет точную форму:

```json
{
  "path": "assets/questions/q-new.png",
  "file": "assets/<sha256>.png",
  "sha256": "64 lowercase hex characters",
  "media_type": "image/png",
  "rights_status": "original",
  "created_by": "designer-08"
}
```

- `path` проходит существующий asset path validator.
- `file` находится внутри package directory и не является symlink.
- Hash файла совпадает с `sha256`.
- Допустимы только форматы, уже разрешённые каталогом.
- `rights_status` равен `original`. В первой версии лицензированные чужие assets не
  принимаются.
- Один target path соответствует одному hash во всём наборе пакетов.
- Импортёр не перезаписывает существующий target path с другим hash.
- После materialization применяются существующие лимиты количества, размера,
  пикселей и общего asset inventory.

## Hash и канонизация

Все hash в пакете используют SHA-256 и lowercase hexadecimal output.

Canonical JSON строится так:

1. Строки нормализуются Unicode NFC.
2. CRLF и CR заменяются на LF.
3. Пробелы в начале и конце строки не удаляются автоматически. Runtime validator
   должен отклонить недопустимые значения.
4. Ключи объектов сортируются по Unicode code point.
5. Порядок массивов сохраняется, кроме явно перечисленных set-like полей.
6. JSON кодируется как UTF-8 с `ensure_ascii=false`, separators `,` и `:` и без BOM.

Set-like поля перед hash сортируются:

- `matrix.positions[].topic_codes` по ASCII.
- `multiple.correct` по option ID.
- `documents` по `id`.
- `positions` по `id`.
- `assets` по `path`.
- `items` по `question.id`.

Остальные массивы сохраняют порядок. В частности, порядок questions, options,
matching items и input correct variants является авторским.

`question_sha256` считается от canonical `question`.

`review_subject_sha256` считается от canonical объекта:

```json
{
  "operation": "replace",
  "expected_existing_question_sha256": "...",
  "question": {},
  "matrix_position": {},
  "evidence": {},
  "referenced_assets": []
}
```

В hash не входят `workflow`, `question_sha256` и сам `review_subject_sha256`.
Предметный reviewer и approver подписывают один и тот же hash. Изменение question,
evidence, matrix position или asset автоматически возвращает item в `draft`.

## Editorial state machine

`workflow.status` описывает редакционный статус MAXIMUM. Он не совпадает с
`question.source.approval_status`, который попадает в runtime source metadata.

```text
draft -> reviewed -> approved
  ^          |           |
  |----------|-----------|
       любое изменение review subject
```

### draft

- Разрешены неполные evidence и отсутствующая review.
- `authored_by` и `authored_at` обязательны.
- Автоматический validator может сообщать ошибки и предупреждения.
- Импортёр никогда не импортирует draft item.

### reviewed

- Question, evidence, matrix link, hashes и answer checks проходят machine validation.
- `subject_review` заполнен.
- Reviewer является предметным экспертом и отличается от `authored_by`.
- Все пять флагов review равны `true`.
- `subject_review.review_subject_sha256` совпадает с вычисленным hash.
- `approval` отсутствует.
- Импортёр никогда не импортирует reviewed item.

### approved

- Выполнены все требования reviewed.
- `approval` заполнен.
- Approver отличается от `authored_by`. Approver может совпадать с subject reviewer.
- `approval.review_subject_sha256` совпадает с текущим hash.
- `matrix.official_status` равен `approved`.
- `question.source.approval_status` равен `approved`.
- Только approved item допускается к импорту.

Статус не повышается автоматически. CLI может только отказать в переходе или
импорте. Решение reviewer или approver нельзя подменить результатом теста, LLM,
ответом open-bank oracle или совпадением hash.

## Проверка правильного ответа

Проверка состоит из двух независимых слоёв.

Machine layer:

1. Question проходит discriminated Pydantic model.
2. `evidence.answer.canonical_answer` точно совпадает с canonical `question.correct`.
3. Каждый `answer_checks[]` прогоняется через production `is_answer_correct`.
4. Результат точно равен `expected_is_correct`.
5. Есть минимум один positive и один negative check.
6. Для input есть positive check для каждого уникального Decimal-класса accepted
   variants.

Human layer:

- Эксперт независимо решает оригинальное задание.
- Эксперт сверяет применимость официального ключа или критерия, если reference есть.
- Эксперт подтверждает `answer_correct=true` для текущего hash.

Machine layer доказывает, что runtime правильно распознаёт записанный ответ. Human
layer подтверждает, что записанный ответ истинен.

## Проверка объяснения

Для reviewed и approved item `explanation` обязательна. Она является собственным
текстом MAXIMUM и не называется объяснением ФИПИ.

Validator проверяет длину, UTF-8, допустимые символы, отсутствие HTML и прохождение
PDF font validation. Эксперт вручную подтверждает:

- объяснение приводит к `correct`;
- ключевой переход обоснован;
- нет скрытого предположения, которого нет в условии;
- единицы, знаки, даты, термины и округление корректны;
- объяснение соответствует уровню экзамена и выбранной position;
- текст не повторяет условие вместо разбора.

Эти проверки фиксируются единым флагом `explanation_correct`. Автоматический анализ
стиля не имеет права выставлять этот флаг.

## Проверка первичного балла

`question.max_primary_score`, `evidence.score.max_primary_score` и
`matrix.positions[].max_primary_score` должны быть равны.

Баллу требуется `score_locator` в утверждённой спецификации того же года. Эксперт
подтверждает, что оригинальная задача действительно соответствует выбранной модели
и сохраняет объём проверяемого действия. Нельзя назначать балл только по похожему
названию темы или соседнему номеру задания.

Общая шкала экзамена и рекомендации по переводу баллов не заменяют score locator
конкретной позиции.

## Проверка источника и прав

Для оригинального задания MAXIMUM runtime source фиксируется так:

- `provider=maximum`;
- `source_kind=original`;
- `rights_status=original`;
- `source_url` указывает на утверждённый publisher URL MAXIMUM;
- `official_criteria_url` указывает на документ ФИПИ, который задаёт матрицу и балл.

Официальные `proj` и `qid` можно хранить как link-only provenance. Они не являются
лицензией на перенос формулировки, изображения, аудио или объяснения.

`evidence.originality` является заявлением автора, а не автоматическим доказательством.
Reviewer вручную сравнивает формулировку с использованными официальными примерами и
подтверждает `originality_reviewed=true`. Exact hash search по внутренним каталогам
обнаруживает только дословные внутренние дубли и не заменяет эту проверку.

## Уникальность

Validator строит глобальный индекс текущего каталога и всех переданных пакетов.
Он отклоняет:

- повтор `package_id`;
- повтор document ID, position ID или question ID в области, где ID должен быть
  уникален;
- add с существующим question ID;
- replace с отсутствующим question ID;
- два operation для одного target question ID;
- повтор `question_sha256` среди разных question ID;
- повтор `(fipi_project_id, fipi_question_id)` среди approved items, если оба поля
  заданы;
- два разных asset hash для одного target path;
- дубликаты option IDs, matching item IDs и normalized input answers.

Совпадение exam position не является дублем. Для одной позиции допустимы несколько
разных оригинальных заданий.

Similarity search может выдавать reviewer warning, но не является детерминированным
блокирующим правилом.

## Алгоритм validator

Будущий validator выполняет этапы в этом порядке и не изменяет вход:

1. Проверяет layout, отсутствие symlink, UTF-8 без BOM, strict JSON и размер файлов.
2. Проверяет envelope и package schema с `extra=forbid`.
3. Сверяет directory name, `package_id`, target diagnostic, exam и subject.
4. Сверяет `expected_catalog_sha256` с сырыми байтами target JSON.
5. Проверяет official document metadata, формат hashes, year и matrix locators.
   Соответствие document hash реальным официальным bytes остаётся ручным гейтом,
   пока не введён отдельный доверенный evidence cache.
6. Проверяет каждый runtime question через production model.
7. Проверяет operation и expected existing question hash.
8. Проверяет evidence, answer checks и три равных значения primary score.
9. Пересчитывает question и review subject hashes.
10. Проверяет workflow state и human attestations для текущего hash.
11. Строит глобальные uniqueness indexes.
12. Материализует изменения только в памяти.
13. Строит полный `DiagnosticCatalog` и проверяет все текущие лимиты.
14. Проверяет asset inventory через существующие validators.
15. Печатает отсортированные stable error codes без private correct values.

Error code имеет форму `original_content.<scope>.<reason>`. Сортировка выполняется по
`package_id`, `question.id`, code. Текст ошибки не включает prompt, correct,
explanation, source document bytes или полный payload.

Минимальные blocking codes:

```text
original_content.package.invalid_utf8
original_content.package.schema_invalid
original_content.target.catalog_changed
original_content.matrix.unapproved_year
original_content.matrix.locator_missing
original_content.question.runtime_invalid
original_content.question.duplicate_id
original_content.question.duplicate_content
original_content.question.answer_check_failed
original_content.question.explanation_missing
original_content.question.score_mismatch
original_content.question.source_invalid
original_content.question.hash_mismatch
original_content.workflow.human_review_missing
original_content.workflow.hash_not_approved
original_content.asset.invalid
original_content.catalog.limit_exceeded
```

## Алгоритм importer

Importer принимает только пакет, для которого validator вернул zero blocking errors.
Он выполняет чистое детерминированное преобразование:

1. Загружает текущий target diagnostic и повторно проверяет catalog hash.
2. Применяет replacements по существующим индексам.
3. Добавляет additions в ASCII-порядке question ID.
4. Удаляет authoring-only поля. В output остаются только runtime question objects.
5. Копирует новые assets по content hash без перезаписи другого содержимого.
6. Сериализует diagnostic как UTF-8 без BOM, `ensure_ascii=false`, indent 2 и LF.
7. Пишет staged output, а не `school/diagnostics/`.
8. Повторно загружает staged файл через production catalog loader.
9. Печатает output path, old SHA-256, new SHA-256, replace count и add count.

Рекомендуемый CLI contract:

```text
python scripts/validate_original_content.py authoring/original/<package_id>
python scripts/import_original_content.py authoring/original/<package_id> --output-dir build/original-content
```

Одинаковые входные bytes, каталог и версия importer должны производить одинаковые
output bytes. Network access во время validation и import запрещён. Официальные URL
и document hashes собираются до запуска конвейера.

## Связь с `/admin/content`

Админка и authoring package используют один runtime question shape, но решают разные
задачи.

- `/admin/content` удобен для просмотра, ручной правки, production validation и
  UTF-8 export одного diagnostic draft.
- Authoring package хранит matrix evidence, workflow status, human attestations и
  reproducibility hashes.
- Экспорт админки не является approved authoring package.
- Approved package не публикуется через live DB edit.
- Для preview importer может сформировать staged diagnostic JSON. Редактор может
  вручную перенести вопрос в admin draft, но source of truth остаётся approved package
  и reviewed Git change.

## Read-only аудит текущего каталога

`audit_editorial_readiness.py` показывает машинно обнаружимые gaps в уже
материализованных 19 каталогах:

```text
python scripts/audit_editorial_readiness.py
python scripts/audit_editorial_readiness.py --diagnostic ege-mathematics-1212
python scripts/audit_editorial_readiness.py --require-complete
```

Без `--require-complete` корректно прочитанный каталог даёт exit code 0 даже при
gaps. С флагом любой gap даёт exit code 1. Ошибка каталога, UTF-8 или неизвестный
diagnostic ID даёт exit code 2.

Аудитор выставляет `draft`, когда есть machine gaps, и `reviewed`, когда обязательные
runtime metadata заполнены. Он всегда выводит `approved=0` и отдельный список
`manual_gates`. Это намеренно. Runtime JSON не хранит human attestations из
authoring package, поэтому аудитор не имеет права подтверждать editorial approval.

## Definition of done для одного задания

Задание готово к импорту только когда одновременно истинны все условия:

- status равен `approved`;
- target catalog и expected question hashes актуальны;
- условие и объяснение являются оригинальными материалами MAXIMUM;
- runtime model принимает question;
- production checker проходит все positive и negative answer checks;
- предметный эксперт подтвердил ответ и объяснение;
- max primary score связан locator с утверждённой спецификацией;
- position и topic codes подтверждены matrix;
- source и rights metadata заполнены;
- reviewer и approver подписали текущий review subject hash;
- assets принадлежат MAXIMUM и проходят inventory validation;
- staged каталог не превышает 20 диагностик и 200 вопросов в каждой диагностике,
  1 MiB на файл и 5 MiB суммарно; authenticated detail payload не превышает 2 MiB;
- `validate_school.py`, `check_brand_isolation.py` и затронутые тесты проходят.

## Кампания минимум по 15 заданий

План расширения находится в
`authoring/campaigns/fipi-2026-min15/manifest.json`. Он фиксирует baseline из 19
диагностик и 178 вопросов, 123 add-only слота и итоговый объём 301 вопрос. Четыре
диагностики уже содержат больше 15 вопросов, поэтому итоговый объём превышает 285.

Manifest не содержит условий, ответов или объяснений. Материализованные материалы
имеют статус `draft`, источник и права `original`, не используют assets и не меняют
`quick_count`. Из кампании исключены позиции, которые требуют развёрнутого ответа
или не сопоставлены с моделью 2026 года.

Перед началом и после каждого раздела авторских работ выполняется read-only проверка:

```text
python scripts/validate_original_campaign.py
```

Проверка принимает два состояния. До материализации она сверяет SHA-256 и количество
вопросов каждого исходного файла. После материализации она проверяет точный порядок
123 добавленных ID, draft-метаданные, отсутствие assets, разрешённые сочетания
позиции, типа и балла, а также независимое владение файлами в трёх разделах по 41
слоту. Произвольное частичное состояние отклоняется.

Human approval остаётся обязательным даже при полном прохождении всех автоматических
проверок.
