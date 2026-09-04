# Импорт диагностик SharePoint

Сгенерировано `python scripts/import_sharepoint_diagnostics.py <docx-dir>` (2026-09-04).

Каталог школы состоит только из этих заданий. Текст задания, вариантов и ключ взяты из редакционно утверждённых документов MAXIMUM без правок. Тема не выводится ни из какого источника: каждому вопросу проставлена тема «Задание N» и первичный балл 1. Раздел «Темы, требующие сопоставления» перечисляет их по предметам, чтобы методист заполнил таблицу «позиция КИМ → тема». Все импортированные вопросы имеют `approval_status = draft` и требуют предметной редактуры.

## Итоги

| Файл | Экзамен | Предмет | Каталог | Заданий | Импортировано | Пропущено |
|---|---|---|---|---:|---:|---:|
| АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | ЕГЭ | Английский язык | ege-english-language-1204.json | 23 | 16 | 7 |
| АЯ_ОГЭ_МРКТ_март_21-22_Заданий 17.docx | ОГЭ | Английский язык | oge-english-language-202.json | 17 | 17 | 0 |
| БИО_ЕГЭ_Диагностика_21-22_Заданий 21.docx | ЕГЭ | Биология | ege-biology-1207.json | 21 | 21 | 0 |
| БИО_ОГЭ_МРКТ_март_21-22_Заданий 24.docx | ОГЭ | Биология | oge-biology-699.json | 23 | 21 | 2 |
| ИНФ_ЕГЭ_Диагностика_21-22_Заданий 18.docx | ЕГЭ | Информатика | ege-informatics-1205.json | 18 | 15 | 3 |
| ИСТ_ЕГЭ_Диагностика_21-22_Заданий 11.docx | ЕГЭ | История | ege-history-1211.json | 11 | 11 | 0 |
| ИСТ_ОГЭ_МРКТ_март_21-22_Заданий 17.docx | ОГЭ | История | oge-history-196.json | 17 | 15 | 2 |
| ЛИТ_ЕГЭ_Диагностика_21-22_Заданий 7.docx | ЕГЭ | Литература | ege-literature-1209.json | 7 | 6 | 1 |
| МА_ЕГЭ_Диагностика_21-22_Заданий 11.docx | ЕГЭ | Математика | ege-mathematics-1212.json | 11 | 11 | 0 |
| МАТ_ОГЭ_Диагностика_21-22_Заданий 19.docx | ОГЭ | Математика | oge-mathematics-198.json | 19 | 19 | 0 |
| ОБЩ_ЕГЭ_Диагностика_21-22_Заданий 16.docx | ЕГЭ | Обществознание | ege-social-studies-1210.json | 16 | 16 | 0 |
| ОБЩ_ОГЭ_МРКТ_март_21-22_Заданий 16.docx | ОГЭ | Обществознание | oge-social-studies-195.json | 16 | 15 | 1 |
| РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx | ЕГЭ | Русский язык | ege-russian-language-1213.json | 26 | 22 | 4 |
| РЯ_ЕГЭ_МП_Пробный ЕГЭ_23-24_КТ_Заданий 26.docx | ЕГЭ | Русский язык | ege-russian-language-1213.json | 26 | 22 | 4 |
| РЯ_ОГЭ_Диагностика_21-22_Заданий 7.docx | ОГЭ | Русский язык | oge-russian-language-379.json | 7 | 7 | 0 |
| РЯ_ОГЭ_МП_Пробный ОГЭ_23-24_КТ_Заданий 11.docx | ОГЭ | Русский язык | oge-russian-language-379.json | 11 | 8 | 3 |
| ФИЗ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | ЕГЭ | Физика | ege-physics-1206.json | 23 | 22 | 1 |
| ФИЗ_ОГЭ_МРКТ_март_21-22_Заданий 18.docx | ОГЭ | Физика | oge-physics-197.json | 18 | 18 | 0 |
| ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | ЕГЭ | Химия | ege-chemistry-1208.json | 28 | 26 | 2 |
| ХИМ_ОГЭ_МРКТ_март_21-22_Заданий 19.docx | ОГЭ | Химия | oge-chemistry-192.json | 19 | 19 | 0 |

## Пропущенные задания

Каждое задание, которое конвертер не перенёс, и причина.

| Файл | Задание | Тип | Причина |
|---|---:|---|---|
| АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 3 | input | prompt_too_long |
| АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 4 | input | prompt_too_long |
| АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 5 | input | prompt_too_long |
| АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 6 | input | prompt_too_long |
| АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 7 | input | prompt_too_long |
| АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 8 | input | prompt_too_long |
| АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 9 | input | prompt_too_long |
| БИО_ОГЭ_МРКТ_март_21-22_Заданий 24.docx | 11 | single | missing_figure |
| БИО_ОГЭ_МРКТ_март_21-22_Заданий 24.docx | 16 | - | irregular_key |
| ИНФ_ЕГЭ_Диагностика_21-22_Заданий 18.docx | 3 | input | external_resource |
| ИНФ_ЕГЭ_Диагностика_21-22_Заданий 18.docx | 9 | input | external_resource |
| ИНФ_ЕГЭ_Диагностика_21-22_Заданий 18.docx | 10 | input | external_resource |
| ИСТ_ОГЭ_МРКТ_март_21-22_Заданий 17.docx | 6 | - | irregular_key |
| ИСТ_ОГЭ_МРКТ_март_21-22_Заданий 17.docx | 13 | - | irregular_key |
| ЛИТ_ЕГЭ_Диагностика_21-22_Заданий 7.docx | 1 | text | prompt_too_long |
| ОБЩ_ОГЭ_МРКТ_март_21-22_Заданий 16.docx | 15 | - | irregular_key |
| РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx | 22 | multiple | prompt_too_long |
| РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx | 23 | multiple | prompt_too_long |
| РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx | 24 | text | prompt_too_long |
| РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx | 25 | input | prompt_too_long |
| РЯ_ЕГЭ_МП_Пробный ЕГЭ_23-24_КТ_Заданий 26.docx | 22 | multiple | prompt_too_long |
| РЯ_ЕГЭ_МП_Пробный ЕГЭ_23-24_КТ_Заданий 26.docx | 23 | multiple | prompt_too_long |
| РЯ_ЕГЭ_МП_Пробный ЕГЭ_23-24_КТ_Заданий 26.docx | 24 | text | prompt_too_long |
| РЯ_ЕГЭ_МП_Пробный ЕГЭ_23-24_КТ_Заданий 26.docx | 25 | input | prompt_too_long |
| РЯ_ОГЭ_МП_Пробный ОГЭ_23-24_КТ_Заданий 11.docx | 9 | multiple | prompt_too_long |
| РЯ_ОГЭ_МП_Пробный ОГЭ_23-24_КТ_Заданий 11.docx | 10 | multiple | prompt_too_long |
| РЯ_ОГЭ_МП_Пробный ОГЭ_23-24_КТ_Заданий 11.docx | 11 | text | prompt_too_long |
| ФИЗ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 22 | - | irregular_key |
| ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | 15 | input | missing_figure |
| ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | 16 | input | missing_figure |

## Темы, требующие сопоставления

У всех импортированных заданий тема равна «Задание N». Заполните позицию КИМ и тему для каждого номера в списке.

| Каталог | Экзамен | Предмет | Документ | Задания |
|---|---|---|---|---|
| ege-biology-1207.json | ЕГЭ | Биология | БИО_ЕГЭ_Диагностика_21-22_Заданий 21.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21 |
| ege-chemistry-1208.json | ЕГЭ | Химия | ХИМ_ЕГЭ_Диагностика_21-22_Заданий 28.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28 |
| ege-english-language-1204.json | ЕГЭ | Английский язык | АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 1, 2, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23 |
| ege-history-1211.json | ЕГЭ | История | ИСТ_ЕГЭ_Диагностика_21-22_Заданий 11.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| ege-informatics-1205.json | ЕГЭ | Информатика | ИНФ_ЕГЭ_Диагностика_21-22_Заданий 18.docx | 1, 2, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18 |
| ege-literature-1209.json | ЕГЭ | Литература | ЛИТ_ЕГЭ_Диагностика_21-22_Заданий 7.docx | 2, 3, 4, 5, 6, 7 |
| ege-mathematics-1212.json | ЕГЭ | Математика | МА_ЕГЭ_Диагностика_21-22_Заданий 11.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |
| ege-physics-1206.json | ЕГЭ | Физика | ФИЗ_ЕГЭ_Диагностика_21-22_Заданий 23.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 23 |
| ege-russian-language-1213.json | ЕГЭ | Русский язык | РЯ_ЕГЭ_Диагностика_21-22_Заданий 26.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 26 |
| ege-russian-language-1213.json | ЕГЭ | Русский язык | РЯ_ЕГЭ_МП_Пробный ЕГЭ_23-24_КТ_Заданий 26.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 26 |
| ege-social-studies-1210.json | ЕГЭ | Обществознание | ОБЩ_ЕГЭ_Диагностика_21-22_Заданий 16.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 |
| oge-biology-699.json | ОГЭ | Биология | БИО_ОГЭ_МРКТ_март_21-22_Заданий 24.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 18, 19, 20, 21, 22, 23, 24 |
| oge-chemistry-192.json | ОГЭ | Химия | ХИМ_ОГЭ_МРКТ_март_21-22_Заданий 19.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19 |
| oge-english-language-202.json | ОГЭ | Английский язык | АЯ_ОГЭ_МРКТ_март_21-22_Заданий 17.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17 |
| oge-history-196.json | ОГЭ | История | ИСТ_ОГЭ_МРКТ_март_21-22_Заданий 17.docx | 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17 |
| oge-mathematics-198.json | ОГЭ | Математика | МАТ_ОГЭ_Диагностика_21-22_Заданий 19.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19 |
| oge-physics-197.json | ОГЭ | Физика | ФИЗ_ОГЭ_МРКТ_март_21-22_Заданий 18.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 |
| oge-russian-language-379.json | ОГЭ | Русский язык | РЯ_ОГЭ_Диагностика_21-22_Заданий 7.docx | 1, 2, 3, 4, 5, 6, 7 |
| oge-russian-language-379.json | ОГЭ | Русский язык | РЯ_ОГЭ_МП_Пробный ОГЭ_23-24_КТ_Заданий 11.docx | 1, 2, 3, 4, 5, 6, 7, 8 |
| oge-social-studies-195.json | ОГЭ | Обществознание | ОБЩ_ОГЭ_МРКТ_март_21-22_Заданий 16.docx | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16 |

## АЯ_ЕГЭ_Диагностика_21-22_Заданий 23.docx

Каталог: `school/diagnostics/ege-english-language-1204.json`. Заявлено заданий в имени файла: 23, найдено блоков: 23.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | input | - | 0 |
| 2 | imported | input | - | 0 |
| 3 | skipped | input | prompt_too_long | 0 |
| 4 | skipped | input | prompt_too_long | 0 |
| 5 | skipped | input | prompt_too_long | 0 |
| 6 | skipped | input | prompt_too_long | 0 |
| 7 | skipped | input | prompt_too_long | 0 |
| 8 | skipped | input | prompt_too_long | 0 |
| 9 | skipped | input | prompt_too_long | 0 |
| 10 | imported | text | - | 0 |
| 11 | imported | text | - | 0 |
| 12 | imported | text | - | 0 |
| 13 | imported | text | - | 0 |
| 14 | imported | text | - | 0 |
| 15 | imported | text | - | 0 |
| 16 | imported | text | - | 0 |
| 17 | imported | text | - | 0 |
| 18 | imported | text | - | 0 |
| 19 | imported | text | - | 0 |
| 20 | imported | text | - | 0 |
| 21 | imported | text | - | 0 |
| 22 | imported | text | - | 0 |
| 23 | imported | input | - | 1 |

## АЯ_ОГЭ_МРКТ_март_21-22_Заданий 17.docx

Каталог: `school/diagnostics/oge-english-language-202.json`. Заявлено заданий в имени файла: 17, найдено блоков: 17.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | input | - | 0 |
| 2 | imported | input | - | 0 |
| 3 | imported | text | - | 0 |
| 4 | imported | text | - | 0 |
| 5 | imported | text | - | 0 |
| 6 | imported | text | - | 0 |
| 7 | imported | text | - | 0 |
| 8 | imported | text | - | 0 |
| 9 | imported | text | - | 0 |
| 10 | imported | text | - | 0 |
| 11 | imported | text | - | 0 |
| 12 | imported | text | - | 0 |
| 13 | imported | text | - | 0 |
| 14 | imported | text | - | 0 |
| 15 | imported | text | - | 0 |
| 16 | imported | text | - | 0 |
| 17 | imported | text | - | 0 |

## БИО_ЕГЭ_Диагностика_21-22_Заданий 21.docx

Каталог: `school/diagnostics/ege-biology-1207.json`. Заявлено заданий в имени файла: 21, найдено блоков: 21.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | text | - | 0 |
| 2 | imported | input | - | 1 |
| 3 | imported | input | - | 0 |
| 4 | imported | input | - | 0 |
| 5 | imported | input | - | 1 |
| 6 | imported | input | - | 1 |
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
| 18 | imported | input | - | 0 |
| 19 | imported | input | - | 0 |
| 20 | imported | input | - | 0 |
| 21 | imported | multiple | - | 0 |

## БИО_ОГЭ_МРКТ_март_21-22_Заданий 24.docx

Каталог: `school/diagnostics/oge-biology-699.json`. Заявлено заданий в имени файла: 24, найдено блоков: 23.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | text | - | 1 |
| 2 | imported | single | - | 0 |
| 3 | imported | single | - | 0 |
| 4 | imported | single | - | 1 |
| 5 | imported | single | - | 0 |
| 6 | imported | single | - | 0 |
| 7 | imported | single | - | 0 |
| 8 | imported | single | - | 0 |
| 9 | imported | single | - | 0 |
| 10 | imported | single | - | 0 |
| 11 | skipped | single | missing_figure | 0 |
| 12 | imported | single | - | 0 |
| 13 | imported | single | - | 0 |
| 14 | imported | single | - | 0 |
| 15 | imported | single | - | 0 |
| 16 | skipped | - | irregular_key | 0 |
| 18 | imported | multiple | - | 1 |
| 19 | imported | multiple | - | 1 |
| 20 | imported | multiple | - | 0 |
| 21 | imported | input | - | 0 |
| 22 | imported | input | - | 0 |
| 23 | imported | input | - | 0 |
| 24 | imported | input | - | 5 |

## ИНФ_ЕГЭ_Диагностика_21-22_Заданий 18.docx

Каталог: `school/diagnostics/ege-informatics-1205.json`. Заявлено заданий в имени файла: 18, найдено блоков: 18.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | input | - | 1 |
| 2 | imported | text | - | 0 |
| 3 | skipped | input | external_resource | 0 |
| 4 | imported | input | - | 0 |
| 5 | imported | input | - | 0 |
| 6 | imported | input | - | 1 |
| 7 | imported | input | - | 0 |
| 8 | imported | text | - | 0 |
| 9 | skipped | input | external_resource | 0 |
| 10 | skipped | input | external_resource | 0 |
| 11 | imported | input | - | 0 |
| 12 | imported | input | - | 2 |
| 13 | imported | input | - | 1 |
| 14 | imported | input | - | 0 |
| 15 | imported | input | - | 0 |
| 16 | imported | input | - | 0 |
| 17 | imported | input | - | 1 |
| 18 | imported | input | - | 0 |

## ИСТ_ЕГЭ_Диагностика_21-22_Заданий 11.docx

Каталог: `school/diagnostics/ege-history-1211.json`. Заявлено заданий в имени файла: 11, найдено блоков: 11.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | input | - | 0 |
| 2 | imported | input | - | 0 |
| 3 | imported | input | - | 0 |
| 4 | imported | input | - | 0 |
| 5 | imported | input | - | 0 |
| 6 | imported | multiple | - | 0 |
| 7 | imported | input | - | 0 |
| 8 | imported | text | - | 1 |
| 9 | imported | text | - | 1 |
| 10 | imported | text | - | 1 |
| 11 | imported | multiple | - | 1 |

## ИСТ_ОГЭ_МРКТ_март_21-22_Заданий 17.docx

Каталог: `school/diagnostics/oge-history-196.json`. Заявлено заданий в имени файла: 17, найдено блоков: 17.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | matching | - | 0 |
| 2 | imported | input | - | 0 |
| 3 | imported | text | - | 0 |
| 4 | imported | multiple | - | 0 |
| 5 | imported | single | - | 0 |
| 6 | skipped | - | irregular_key | 0 |
| 7 | imported | matching | - | 0 |
| 8 | imported | text | - | 1 |
| 9 | imported | text | - | 1 |
| 10 | imported | input | - | 1 |
| 11 | imported | single | - | 1 |
| 12 | imported | text | - | 1 |
| 13 | skipped | - | irregular_key | 0 |
| 14 | imported | single | - | 0 |
| 15 | imported | input | - | 0 |
| 16 | imported | input | - | 0 |
| 17 | imported | input | - | 0 |

## ЛИТ_ЕГЭ_Диагностика_21-22_Заданий 7.docx

Каталог: `school/diagnostics/ege-literature-1209.json`. Заявлено заданий в имени файла: 7, найдено блоков: 7.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | skipped | text | prompt_too_long | 0 |
| 2 | imported | text | - | 0 |
| 3 | imported | input | - | 0 |
| 4 | imported | text | - | 0 |
| 5 | imported | text | - | 0 |
| 6 | imported | text | - | 0 |
| 7 | imported | multiple | - | 0 |

## МА_ЕГЭ_Диагностика_21-22_Заданий 11.docx

Каталог: `school/diagnostics/ege-mathematics-1212.json`. Заявлено заданий в имени файла: 11, найдено блоков: 11.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | input | - | 0 |
| 2 | imported | input | - | 0 |
| 3 | imported | input | - | 0 |
| 4 | imported | input | - | 1 |
| 5 | imported | input | - | 1 |
| 6 | imported | input | - | 0 |
| 7 | imported | input | - | 0 |
| 8 | imported | input | - | 0 |
| 9 | imported | input | - | 0 |
| 10 | imported | input | - | 0 |
| 11 | imported | input | - | 1 |

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

## ОБЩ_ЕГЭ_Диагностика_21-22_Заданий 16.docx

Каталог: `school/diagnostics/ege-social-studies-1210.json`. Заявлено заданий в имени файла: 16, найдено блоков: 16.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | multiple | - | 0 |
| 2 | imported | multiple | - | 0 |
| 3 | imported | matching | - | 0 |
| 4 | imported | multiple | - | 0 |
| 5 | imported | multiple | - | 0 |
| 6 | imported | matching | - | 0 |
| 7 | imported | multiple | - | 0 |
| 8 | imported | multiple | - | 0 |
| 9 | imported | multiple | - | 1 |
| 10 | imported | multiple | - | 0 |
| 11 | imported | multiple | - | 0 |
| 12 | imported | multiple | - | 0 |
| 13 | imported | matching | - | 0 |
| 14 | imported | multiple | - | 0 |
| 15 | imported | matching | - | 0 |
| 16 | imported | multiple | - | 0 |

## ОБЩ_ОГЭ_МРКТ_март_21-22_Заданий 16.docx

Каталог: `school/diagnostics/oge-social-studies-195.json`. Заявлено заданий в имени файла: 16, найдено блоков: 16.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | single | - | 0 |
| 2 | imported | single | - | 0 |
| 3 | imported | single | - | 0 |
| 4 | imported | single | - | 0 |
| 5 | imported | single | - | 0 |
| 6 | imported | single | - | 0 |
| 7 | imported | single | - | 0 |
| 8 | imported | single | - | 0 |
| 9 | imported | single | - | 0 |
| 10 | imported | single | - | 0 |
| 11 | imported | input | - | 0 |
| 12 | imported | single | - | 0 |
| 13 | imported | single | - | 0 |
| 14 | imported | single | - | 0 |
| 15 | skipped | - | irregular_key | 0 |
| 16 | imported | text | - | 0 |

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
| 22 | skipped | multiple | prompt_too_long | 0 |
| 23 | skipped | multiple | prompt_too_long | 0 |
| 24 | skipped | text | prompt_too_long | 0 |
| 25 | skipped | input | prompt_too_long | 0 |
| 26 | imported | input | - | 0 |

## РЯ_ЕГЭ_МП_Пробный ЕГЭ_23-24_КТ_Заданий 26.docx

Каталог: `school/diagnostics/ege-russian-language-1213.json`. Заявлено заданий в имени файла: 26, найдено блоков: 26.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | text | - | 0 |
| 2 | imported | multiple | - | 0 |
| 3 | imported | multiple | - | 0 |
| 4 | imported | multiple | - | 0 |
| 5 | imported | text | - | 0 |
| 6 | imported | text | - | 0 |
| 7 | imported | text | - | 0 |
| 8 | imported | matching | - | 0 |
| 9 | imported | multiple | - | 0 |
| 10 | imported | multiple | - | 0 |
| 11 | imported | multiple | - | 0 |
| 12 | imported | multiple | - | 0 |
| 13 | imported | multiple | - | 0 |
| 14 | imported | multiple | - | 0 |
| 15 | imported | input | - | 0 |
| 16 | imported | multiple | - | 0 |
| 17 | imported | input | - | 0 |
| 18 | imported | input | - | 0 |
| 19 | imported | input | - | 0 |
| 20 | imported | input | - | 0 |
| 21 | imported | input | - | 0 |
| 22 | skipped | multiple | prompt_too_long | 0 |
| 23 | skipped | multiple | prompt_too_long | 0 |
| 24 | skipped | text | prompt_too_long | 0 |
| 25 | skipped | input | prompt_too_long | 0 |
| 26 | imported | input | - | 0 |

## РЯ_ОГЭ_Диагностика_21-22_Заданий 7.docx

Каталог: `school/diagnostics/oge-russian-language-379.json`. Заявлено заданий в имени файла: 7, найдено блоков: 7.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | multiple | - | 0 |
| 2 | imported | input | - | 0 |
| 3 | imported | text | - | 0 |
| 4 | imported | multiple | - | 0 |
| 5 | imported | multiple | - | 0 |
| 6 | imported | multiple | - | 0 |
| 7 | imported | text | - | 0 |

## РЯ_ОГЭ_МП_Пробный ОГЭ_23-24_КТ_Заданий 11.docx

Каталог: `school/diagnostics/oge-russian-language-379.json`. Заявлено заданий в имени файла: 11, найдено блоков: 11.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | multiple | - | 0 |
| 2 | imported | multiple | - | 0 |
| 3 | imported | matching | - | 0 |
| 4 | imported | input | - | 0 |
| 5 | imported | multiple | - | 0 |
| 6 | imported | input | - | 0 |
| 7 | imported | text | - | 0 |
| 8 | imported | text | - | 0 |
| 9 | skipped | multiple | prompt_too_long | 0 |
| 10 | skipped | multiple | prompt_too_long | 0 |
| 11 | skipped | text | prompt_too_long | 0 |

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
| 8 | imported | input | - | 2 |
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
| 19 | imported | input | - | 0 |
| 20 | imported | input | - | 0 |
| 21 | imported | matching | - | 0 |
| 22 | skipped | - | irregular_key | 0 |
| 23 | imported | multiple | - | 0 |

## ФИЗ_ОГЭ_МРКТ_март_21-22_Заданий 18.docx

Каталог: `school/diagnostics/oge-physics-197.json`. Заявлено заданий в имени файла: 18, найдено блоков: 18.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | matching | - | 0 |
| 2 | imported | matching | - | 0 |
| 3 | imported | single | - | 0 |
| 4 | imported | input | - | 1 |
| 5 | imported | input | - | 0 |
| 6 | imported | input | - | 1 |
| 7 | imported | input | - | 2 |
| 8 | imported | input | - | 1 |
| 9 | imported | input | - | 1 |
| 10 | imported | input | - | 1 |
| 11 | imported | input | - | 1 |
| 12 | imported | input | - | 1 |
| 13 | imported | multiple | - | 1 |
| 14 | imported | multiple | - | 1 |
| 15 | imported | single | - | 1 |
| 16 | imported | multiple | - | 1 |
| 17 | imported | input | - | 0 |
| 18 | imported | multiple | - | 0 |

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
| 10 | imported | input | - | 0 |
| 11 | imported | multiple | - | 0 |
| 12 | imported | multiple | - | 0 |
| 13 | imported | multiple | - | 1 |
| 14 | imported | input | - | 0 |
| 15 | skipped | input | missing_figure | 0 |
| 16 | skipped | input | missing_figure | 0 |
| 17 | imported | multiple | - | 0 |
| 18 | imported | multiple | - | 0 |
| 19 | imported | input | - | 0 |
| 20 | imported | matching | - | 0 |
| 21 | imported | input | - | 1 |
| 22 | imported | matching | - | 0 |
| 23 | imported | input | - | 0 |
| 24 | imported | matching | - | 0 |
| 25 | imported | matching | - | 0 |
| 26 | imported | input | - | 0 |
| 27 | imported | input | - | 0 |
| 28 | imported | input | - | 0 |

## ХИМ_ОГЭ_МРКТ_март_21-22_Заданий 19.docx

Каталог: `school/diagnostics/oge-chemistry-192.json`. Заявлено заданий в имени файла: 19, найдено блоков: 19.

| Задание | Итог | Тип | Причина | Рисунков |
|---:|---|---|---|---:|
| 1 | imported | multiple | - | 0 |
| 2 | imported | input | - | 1 |
| 3 | imported | input | - | 0 |
| 4 | imported | matching | - | 0 |
| 5 | imported | multiple | - | 0 |
| 6 | imported | multiple | - | 0 |
| 7 | imported | input | - | 0 |
| 8 | imported | multiple | - | 0 |
| 9 | imported | matching | - | 0 |
| 10 | imported | matching | - | 0 |
| 11 | imported | multiple | - | 0 |
| 12 | imported | matching | - | 0 |
| 13 | imported | multiple | - | 0 |
| 14 | imported | multiple | - | 0 |
| 15 | imported | matching | - | 0 |
| 16 | imported | multiple | - | 0 |
| 17 | imported | matching | - | 0 |
| 18 | imported | input | - | 0 |
| 19 | imported | input | - | 0 |
