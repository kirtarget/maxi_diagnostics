# Импорт диагностик SharePoint

Сгенерировано `python scripts/import_sharepoint_diagnostics.py <docx-dir>` (2026-09-04).

Это отчёт частичного импорта. Он покрывает только выбранные исходники. Остальные задания и ресурсы каталога сохранены. Текст задания, варианты и ключ взяты из редакционно утверждённых документов MAXIMUM. Импортёр применяет только узкие нормализации и исправления, разрешённые для источника с совпавшим SHA-256: канонизацию Unicode и пробелов, исправление известных OCR-похожих символов и пунктуации, а также проверенное удаление дублирующего маркера. Тема берётся из плана источников, а без плана каждому вопросу проставлена тема «Задание N». Первичный балл берётся из закреплённой score policy только для проверенных позиций, остальные остаются со статусом draft. Раздел «Темы, требующие сопоставления» перечисляет их по предметам, чтобы методист заполнил таблицу «позиция КИМ → тема». Только позиции из score policy получают `approval_status = approved`; остальные требуют предметной редактуры.

## Итоги

| Файл | Экзамен | Предмет | Каталог | Заданий | Импортировано | Пропущено |
|---|---|---|---|---:|---:|---:|
| ФИЗ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | ЕГЭ | Физика | ege-physics-1206.json | 23 | 21 | 2 |
| ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | ЕГЭ | Химия | ege-chemistry-1208.json | 28 | 28 | 0 |

## Пропущенные задания

Каждое задание, которое конвертер не перенёс, и причина.

| Файл | Задание | Тип | Причина |
|---|---:|---|---|
| ФИЗ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 8 | - | unsupported_table_cell_figure |
| ФИЗ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 22 | - | irregular_key |

## Темы, требующие сопоставления

У импортированных заданий без записи в плане тема равна «Задание N». Заполните позицию КИМ и тему для каждого номера в списке.

| Каталог | Экзамен | Предмет | Документ | Задания |
|---|---|---|---|---|
| ege-chemistry-1208.json | ЕГЭ | Химия | ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28 |
| ege-physics-1206.json | ЕГЭ | Физика | ФИЗ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 23 |

## ФИЗ_ЕГЭ_Диагностика_21-22_Заданий 23.docx

Каталог: `school/diagnostics/ege-physics-1206.json`. Заявлено заданий в имени файла: 23, найдено блоков: 23.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | multiple | - | 0 |
| 2 | imported | input | - | 1 |
| 3 | imported | input | - | 1 |
| 4 | imported | input | - | 1 |
| 5 | imported | input | - | 0 |
| 6 | imported | multiple | - | 1 |
| 7 | imported | matching | - | 1 |
| 8 | skipped | - | unsupported_table_cell_figure | 0 |
| 9 | imported | input | - | 0 |
| 10 | imported | input | - | 0 |
| 11 | imported | input | - | 0 |
| 12 | imported | multiple | - | 1 |
| 13 | imported | input | - | 0 |
| 14 | imported | input | - | 0 |
| 15 | imported | input | - | 1 |
| 16 | imported | input | - | 0 |
| 17 | imported | multiple | - | 1 |
| 18 | imported | matching | - | 0 |
| 19 | imported | matching | - | 2 |
| 20 | imported | input | - | 0 |
| 21 | imported | matching | - | 0 |
| 22 | skipped | - | irregular_key | 0 |
| 23 | imported | multiple | - | 0 |

## ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx

Каталог: `school/diagnostics/ege-chemistry-1208.json`. Заявлено заданий в имени файла: 28, найдено блоков: 28.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | multiple | - | 0 |
| 2 | imported | input | - | 0 |
| 3 | imported | multiple | - | 0 |
| 4 | imported | multiple | - | 0 |
| 5 | imported | input | - | 0 |
| 6 | imported | input | - | 0 |
| 7 | imported | matching | - | 0 |
| 8 | imported | input | - | 0 |
| 9 | imported | input | - | 1 |
| 10 | imported | matching | - | 0 |
| 11 | imported | multiple | - | 0 |
| 12 | imported | multiple | - | 0 |
| 13 | imported | multiple | - | 1 |
| 14 | imported | matching | - | 2 |
| 15 | imported | matching | - | 1 |
| 16 | imported | input | - | 0 |
| 17 | imported | multiple | - | 0 |
| 18 | imported | multiple | - | 0 |
| 19 | imported | matching | - | 0 |
| 20 | imported | matching | - | 0 |
| 21 | imported | input | - | 1 |
| 22 | imported | matching | - | 0 |
| 23 | imported | input | - | 0 |
| 24 | imported | matching | - | 0 |
| 25 | imported | matching | - | 0 |
| 26 | imported | input | - | 0 |
| 27 | imported | input | - | 0 |
| 28 | imported | input | - | 0 |
