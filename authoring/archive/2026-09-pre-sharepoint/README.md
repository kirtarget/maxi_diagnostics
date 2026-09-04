# Архив: каталог и авторская обвязка до перехода на SharePoint

Дата: 04.09.2026. Решение владельца продукта: каталог школы содержит только
задания из редакционно утверждённой выгрузки MAXIMUM (SharePoint). Всё, что было
написано нами самими, и всё, что пришло из старой выгрузки Edcheck, из рабочего
дерева убрано и лежит здесь.

## Почему

До этой даты `school/diagnostics/*.json` смешивали три источника: 178 вопросов из
выгрузки Edcheck, 123 вопроса нашей кампании `fipi-2026-min15` и задания,
дописанные импортом SharePoint. Смешанный каталог нельзя показать методисту как
редакционно утверждённый: часть вопросов никто из предметников не подтверждал.
Каталог сведён к одному источнику, а самописный и legacy-контент сохранён здесь
как справочный материал.

## Что внутри

- `diagnostics/` — 19 файлов `school/diagnostics/*.json` ровно в том виде, в
  котором они были на `main` (коммит `d907984`), до импорта SharePoint. Это
  единственная копия старых 301 вопроса вне истории git.
- `campaigns/fipi-2026-min15/` — манифест нашей авторской кампании (123 вопроса).
- `legacy-enrichment/` — манифест и стилевые правила обогащения вопросов Edcheck.
- `reviews/` — редакционные ревью полного каталога от 01.09.2026.
- `scripts/validate_original_campaign.py` — валидатор кампании.
- `scripts/build_legacy_enrichment_registry.py` — сборка реестра обогащения.
- `scripts/import_edcheck_export.py` и `tests/test_import_edcheck_export.py` —
  конвертер выгрузки Edcheck и его тест.
- `docs/ORIGINAL_CONTENT_AUTHORING.md`, `docs/CURRENT_CATALOG_GAP_ANALYSIS.md`,
  `docs/FIPI_2026_CONTENT_MATRIX.md`, `docs/FIPI_CONTENT_SOURCES_2026.md`,
  `docs/FIPI_OGE_INFORMATICS_2026_SCORING.md` — методология авторской кампании и
  карта позиций ФИПИ. Шкалы перевода баллов (`docs/SCORE_SCALES_2026.md`,
  `scripts/build_score_scales.py`) остались на своих местах: они описывают экзамен,
  а не наш контент.

Здесь нет кода, который исполняется в проде. Ничего в `authoring/archive/` не
читают ни runtime, ни CI: `pytest` собирает только `tests/`, `ruff` проверяет
только `backend scripts tests`.

## Что удалено вместе с контентом

- Тесты, существовавшие только ради этого контента: `test_fipi_2026_partition_*`,
  `test_validate_original_campaign`, `test_legacy_enrichment_*`,
  `test_full_catalog_review_fixes`, `test_oge_informatics_author_draft`,
  `test_original_content`, вспомогательный модуль `tests/campaign_catalog.py`.
- `school/diagnostics/oge-informatics-466.json` — у этой диагностики нет исходного
  документа SharePoint, поэтому после чистки в ней не осталось бы ни одного
  вопроса. Её шкала убрана из `school/score_scales.json`.
- Картинки заданий `school/assets/questions/*.png`, на которые больше никто не
  ссылается. Файлы не скопированы сюда намеренно: они целиком лежат в истории git
  и восстанавливаются командами ниже.

## Как восстановить

Любой файл — из истории git:

```text
git show d907984:school/diagnostics/oge-informatics-466.json > school/diagnostics/oge-informatics-466.json
git show d907984:school/assets/questions/<имя>.png > school/assets/questions/<имя>.png
```

Каталог целиком в состоянии до импорта:

```text
git checkout d907984 -- school/diagnostics school/assets/questions school/score_scales.json
```

Скрипты и документы можно вернуть простым перемещением из этого каталога обратно.
Восстановленный контент снова смешивает источники, поэтому возвращать его в
`school/` стоит только с явным решением владельца продукта.
