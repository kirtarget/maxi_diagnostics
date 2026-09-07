# Импорт диагностик SharePoint

Сгенерировано `python scripts/import_sharepoint_diagnostics.py <docx-dir>` (2026-09-04).

Это отчёт частичного импорта. Он покрывает только выбранные исходники. Остальные задания и ресурсы каталога сохранены. Текст задания, варианты и ключ взяты из редакционно утверждённых документов MAXIMUM. Импортёр применяет только узкие нормализации и исправления, разрешённые для источника с совпавшим SHA-256: канонизацию Unicode и пробелов, исправление известных OCR-похожих символов и пунктуации, а также проверенное удаление дублирующего маркера. Тема берётся из плана источников, а без плана каждому вопросу проставлена тема «Задание N». Первичный балл берётся из закреплённой score policy только для проверенных позиций, остальные остаются со статусом draft. Раздел «Темы, требующие сопоставления» перечисляет их по предметам, чтобы методист заполнил таблицу «позиция КИМ → тема». Только позиции из score policy получают `approval_status = approved`; остальные требуют предметной редактуры.

## Итоги

| Файл | Экзамен | Предмет | Каталог | Заданий | Импортировано | Пропущено |
|---|---|---|---|---:|---:|---:|
| БИО_ЕГЭ_Диагностика_21-22_Заданий 21.docx | ЕГЭ | Биология | ege-biology-1207.json | 21 | 21 | 0 |
| МАТ_ОГЭ_Диагностика_21-22_Заданий 19.docx | ОГЭ | Математика | oge-mathematics-198.json | 19 | 19 | 0 |
| РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx | ЕГЭ | Русский язык | ege-russian-language-1213.json | 26 | 26 | 0 |
| ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | ЕГЭ | Химия | ege-chemistry-1208.json | 28 | 25 | 3 |

## Пропущенные задания

Каждое задание, которое конвертер не перенёс, и причина.

| Файл | Задание | Тип | Причина |
|---|---:|---|---|
| ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | 14 | - | unsupported_table_cell_figure |
| ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | 15 | - | unsupported_table_cell_figure |
| ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | 16 | input | missing_figure |

## Темы, требующие сопоставления

У импортированных заданий без записи в плане тема равна «Задание N». Заполните позицию КИМ и тему для каждого номера в списке.

| Каталог | Экзамен | Предмет | Документ | Задания |
|---|---|---|---|---|
| ege-biology-1207.json | ЕГЭ | Биология | БИО_ЕГЭ_Диагностика_21-22_Заданий 21.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21 |
| ege-chemistry-1208.json | ЕГЭ | Химия | ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28 |
| ege-russian-language-1213.json | ЕГЭ | Русский язык | РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26 |
| oge-mathematics-198.json | ОГЭ | Математика | МАТ_ОГЭ_Диагностика_21-22_Заданий 19.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19 |

## БИО_ЕГЭ_Диагностика_21-22_Заданий 21.docx

Каталог: `school/diagnostics/ege-biology-1207.json`. Заявлено заданий в имени файла: 21, найдено блоков: 21.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | text | - | 0 |
| 2 | imported | input | - | 1 |
| 3 | imported | input | - | 0 |
| 4 | imported | input | - | 0 |
| 5 | imported | input | - | 1 |
| 6 | imported | matching | - | 1 |
| 7 | imported | multiple | - | 1 |
| 8 | imported | input | - | 0 |
| 9 | imported | multiple | - | 1 |
| 10 | imported | matching | - | 0 |
| 11 | imported | input | - | 0 |
| 12 | imported | multiple | - | 1 |
| 13 | imported | matching | - | 0 |
| 14 | imported | input | - | 0 |
| 15 | imported | multiple | - | 0 |
| 16 | imported | matching | - | 0 |
| 17 | imported | multiple | - | 0 |
| 18 | imported | matching | - | 0 |
| 19 | imported | input | - | 0 |
| 20 | imported | input | - | 0 |
| 21 | imported | multiple | - | 0 |

## МАТ_ОГЭ_Диагностика_21-22_Заданий 19.docx

Каталог: `school/diagnostics/oge-mathematics-198.json`. Заявлено заданий в имени файла: 19, найдено блоков: 19.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | input | - | 1 |
| 2 | imported | input | - | 1 |
| 3 | imported | input | - | 1 |
| 4 | imported | input | - | 1 |
| 5 | imported | input | - | 1 |
| 6 | imported | input | - | 1 |
| 7 | imported | single | - | 1 |
| 8 | imported | input | - | 1 |
| 9 | imported | input | - | 1 |
| 10 | imported | input | - | 0 |
| 11 | imported | input | - | 1 |
| 12 | imported | input | - | 0 |
| 13 | imported | input | - | 2 |
| 14 | imported | input | - | 0 |
| 15 | imported | input | - | 0 |
| 16 | imported | input | - | 1 |
| 17 | imported | input | - | 0 |
| 18 | imported | input | - | 1 |
| 19 | imported | multiple | - | 0 |

## РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx

Каталог: `school/diagnostics/ege-russian-language-1213.json`. Заявлено заданий в имени файла: 26, найдено блоков: 26.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | multiple | - | 0 |
| 2 | imported | text | - | 0 |
| 3 | imported | single | - | 0 |
| 4 | imported | single | - | 0 |
| 5 | imported | text | - | 0 |
| 6 | imported | text | - | 0 |
| 7 | imported | text | - | 0 |
| 8 | imported | matching | - | 0 |
| 9 | imported | multiple | - | 0 |
| 10 | imported | multiple | - | 0 |
| 11 | imported | multiple | - | 0 |
| 12 | imported | multiple | - | 0 |
| 13 | imported | text | - | 0 |
| 14 | imported | text | - | 0 |
| 15 | imported | input | - | 0 |
| 16 | imported | multiple | - | 0 |
| 17 | imported | input | - | 0 |
| 18 | imported | input | - | 0 |
| 19 | imported | input | - | 0 |
| 20 | imported | input | - | 0 |
| 21 | imported | input | - | 0 |
| 22 | imported | multiple | - | 0 |
| 23 | imported | multiple | - | 0 |
| 24 | imported | text | - | 0 |
| 25 | imported | input | - | 0 |
| 26 | imported | input | - | 0 |

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
| 14 | skipped | - | unsupported_table_cell_figure | 0 |
| 15 | skipped | - | unsupported_table_cell_figure | 0 |
| 16 | skipped | input | missing_figure | 0 |
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
