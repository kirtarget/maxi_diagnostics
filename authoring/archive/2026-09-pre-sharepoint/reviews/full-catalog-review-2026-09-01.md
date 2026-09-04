# Полный независимый аудит каталога заданий

Дата аудита: 1 сентября 2026 года.

Итог: **ISSUES**.

Просмотрено 301 из 301 заданий в 19 диагностиках. Correction pass выполнен по каждому пункту ledger после объединения полей `asset` и `assets`.

## Исправление предыдущего отчёта

Предыдущая версия ошибочно проверяла только `assets` и объявила отсутствующими ресурсы из `asset`. Ошибка Boundary Discipline исправлена.

- Ссылок через `asset`: 37.
- Ссылок через `assets`: 21.
- Всего ссылок на ресурсы: 58.
- Отсутствующих путей: 0.
- Просмотрены все фактические PNG, JPG и SVG.
- Повторно проверены B01-B30 предыдущей версии.
- Ложных BLOCKER удалено: 29.
- Реальный BLOCKER остался один. `q1607.png` содержит только крошечную букву «A», а не карту с нумерацией.

## Сводка

| Severity | Число заданий |
|---|---:|
| BLOCKER | 1 |
| HIGH | 3 |
| MEDIUM | 17 |
| LOW | 14 |
| PASS | 266 |
| Всего | 301 |

Три изменения `correct` предлагаются как доказанные. Для 163 legacy-заданий отсутствие `source` не учитывалось как дефект. Их нельзя переводить в официальный approved без provenance.

## Coverage

| Диагностика | Expected | Reviewed | PASS | Findings |
|---|---:|---:|---:|---:|
| ege-biology-1207 | 15 | 15 | 15 | 0 |
| ege-chemistry-1208 | 15 | 15 | 14 | 1 |
| ege-english-language-1204 | 15 | 15 | 15 | 0 |
| ege-history-1211 | 15 | 15 | 14 | 1 |
| ege-informatics-1205 | 15 | 15 | 15 | 0 |
| ege-literature-1209 | 15 | 15 | 13 | 2 |
| ege-mathematics-1212 | 15 | 15 | 15 | 0 |
| ege-physics-1206 | 15 | 15 | 13 | 2 |
| ege-russian-language-1213 | 15 | 15 | 12 | 3 |
| ege-social-studies-1210 | 15 | 15 | 13 | 2 |
| oge-biology-699 | 20 | 20 | 17 | 3 |
| oge-chemistry-192 | 19 | 19 | 16 | 3 |
| oge-english-language-202 | 15 | 15 | 14 | 1 |
| oge-history-196 | 15 | 15 | 12 | 3 |
| oge-informatics-466 | 15 | 15 | 15 | 0 |
| oge-mathematics-198 | 19 | 19 | 18 | 1 |
| oge-physics-197 | 18 | 18 | 17 | 1 |
| oge-russian-language-379 | 15 | 15 | 7 | 8 |
| oge-social-studies-195 | 15 | 15 | 11 | 4 |
| **Итого** | **301** | **301** | **266** | **35** |

## BLOCKER

### B01. oge-history-196 / q1607, история

Отрывок позволяет установить название «Евпатория», но вопрос просит цифру на схеме. Ресурс `assets/questions/q1607.png` существует, однако содержит только крошечную букву «A», а не карту с цифрами. Номер 3 нельзя вывести из текста. На карте `q1605.png` Евпатория действительно отмечена цифрой 3, но q1607 ссылается на другой файл.

Исправление: привязать полноценную карту к q1607 и затем подтвердить `correct=3`. Меняется `asset`; остальные поля не меняются.

## HIGH

### H01. ege-russian-language-1213 / f26-ege-rus-a04

`correct=[a,b,c]` неверно включает вариант a. В «Уставшие после похода мы сразу уснули» оборот перед личным местоимением требует одной запятой после «похода». Варианты b и c требуют по две запятые.

Исправление: `correct=[b,c]`, `selection_limit=2`. Обновить объяснение. Меняются `correct`, `selection_limit`, `explanation`; `prompt`, `options`, `score` не меняются.

### H02. oge-history-196 / q1603

Система принимает `2314`, хотя таблица требует порядок «тезис 1, факт 1, тезис 2, факт 2». Столыпин 1 подтверждается фактом 4, Витте 2 фактом 3. Единственная запись равна `1423`.

Исправление: оставить `correct="1423"` и обновить объяснение.

### H03. oge-social-studies-195 / q1537

Ключ `o3` считает верным обязательное «минимальное наличие» государственной собственности в рыночной экономике. Рыночный механизм совместим со смешанной экономикой и значительным государственным сектором. Верно только Б.

Исправление: `correct="o2"`, обновить объяснение.

## MEDIUM

### M01. ege-chemistry-1208 / q9870

Ионное уравнение доступно в `asset=q9870.png`, поэтому задание решаемо и ключ `o3,o5` верен. Текст вокруг изображения оборван после двоеточия. Связать его с ресурсом фразой «уравнением на рисунке».

### M02. ege-literature-1209 / q9878

Отнесение «Есть в осени первоначальной…» именно к философской лирике спорно. Его часто рассматривают как пейзажную лирику с философским мотивом. Уточнить критерий либо заменить вариант. Нужен литературовед.

### M03. ege-physics-1206 / q9858

Вариант 4 говорит о максимальной энергии, а объяснение доказывает рост текущей энергии при Q=const и C↓. Максимально допустимая энергия требует сведений о пробое. Заменить формулировку на «энергия электрического поля конденсатора».

### M04. ege-social-studies-1210 / q9883

Положительное торговое сальдо названо универсальным показателем эффективности. Превышение экспорта над импортом само по себе эффективность не доказывает. Заменить на точный факт либо пересмотреть ключ с обществоведом.

### M05. oge-biology-699 / q5882

Суждение о верхнем и нижнем корковых слоях обобщено на все лишайники. У накипных лишайников нижний слой может отсутствовать. Уточнить тип слоевища либо признать верным только Б. Нужен биолог.

### M06. oge-biology-699 / q5891

Пищевая сеть доступна в `asset=q5891.png`. Объяснение считает лягушек неизменными только из-за отсутствия прямой связи с ястребом, но схема допускает косвенный трофический эффект через сову. Условие не говорит, учитывать ли только прямые связи. Уточнить модель рассуждения или перепроверить ключ с биологом.

### M07. oge-mathematics-198 / q1626

Оба ресурса существуют, соответствие `132` верно. Однако мощность насосов 120–205 кВт при цене около 15 тысяч рублей похожа на OCR-ошибку единицы. Сверить кВт и Вт. Ключ не меняется.

### M08. oge-physics-197 / q1646

Фраза «крайней частью ножниц» допускает разные толкования и противоречит обычному выигрышу в силе ближе к шарниру. Точно назвать положение точки резания или привести измерение.

### M09. oge-russian-language-379 / q3392

«Дрожащими пальчиками» в варианте 4 можно трактовать как художественно окрашенное определение, но ключ включает только 1 и 3. Выделить проверяемое слово или заменить вариант. Нужен филолог.

### M10. oge-social-studies-195 / q1547

Право собственности противопоставлено праву на труд, хотя оба входят в социально-экономический блок. Уточнить вопрос либо заменить вариант 2.

### M11. oge-social-studies-195 / q1551

«Священная книга» сформулирована как универсальный признак религиозных норм, хотя не каждая традиция основана на единой книге. Нужна менее абсолютная формулировка.

### M12. oge-russian-language-379 / f26-oge-rus-a01, a02, a03, a04, a05, a06

Заполнены позиции 2, 3, 4, 5, 6 и 8 и балл 1, но локальная матрица помечает соответствие нумерации 2026 как «не установлено». Все источники остаются `draft`. Нужна документированная предметная пересверка. Содержательные ключи по текущим текстам верны.

## LOW

### L01. ege-history-1211 / q9886

Принимаются все шесть перестановок 1, 2, 3. Оставить канонический порядок либо явно разрешить любой.

### L02. ege-literature-1209 / q9877

Исправить OCR-разрывы «данно м стихотворени и».

### L03. ege-physics-1206 / q9855

Исправить «внутренней энергия тела» на «внутренней энергии газа».

### L04. ege-russian-language-1213 / q9896

Исправить OCR-повреждения, включая «серебря(З)ое».

### L05. ege-russian-language-1213 / q9897

Исправить «НЕМАЛЕНЬКЙ» на «НЕМАЛЕНЬКИЙ».

### L06. ege-social-studies-1210 / q9881

Исправить согласование на «производитель пищевых продуктов, специализирующийся».

### L07. oge-biology-699 / q5887

Исправить OCR-разрыв «мышц ы».

### L08. oge-chemistry-192 / q1489, q1497, q1505

Нормализовать букву В, пробелы внутри формул и опечатку «последовательнсть».

### L09. oge-english-language-202 / q1826

Исправить `only watches` на `only watched`, `Australi a` на `Australia`.

### L10. oge-history-196 / q1610

Принимаются `25` и `52`. Оставить каноническую запись или явно разрешить любой порядок.

### L11. oge-russian-language-379 / q3383

Принимаются `34` и `43`. Оставить каноническую запись или явно разрешить любой порядок.

### L12. oge-social-studies-195 / q1528

Исправить на «пользование обществом природными ресурсами».

## Предлагаемые изменения correct

| Диагностика / ID | Before | After | Связанные поля |
|---|---|---|---|
| ege-russian-language-1213 / f26-ege-rus-a04 | `[a,b,c]` | `[b,c]` | `selection_limit: 3 -> 2`, explanation |
| oge-history-196 / q1603 | `[1423,2314]` | `1423` | explanation |
| oge-social-studies-195 / q1537 | `o3` | `o2` | explanation |

Предложенных смен `correct`: **3**.

## Source и score

`source` есть у 138 вопросов. Все имеют статус `draft`; approved равен нулю. Там, где локальная матрица допускает сопоставление, `max_primary_score` совпадает с ней. Доказанного неверного первичного балла не найдено. ОГЭ по русскому языку требует ручной пересверки. ЕГЭ по математике требует явного уровня `profile`.

## Автоматические проверки

- `validate_school.py`: `OK school=maximum diagnostics=19 questions=301 assets=59`.
- Ссылки: `asset=37`, `assets=21`, missing paths `0`.
- 19 JSON-файлов, 301 уникальный ID.
- У всех текущих `multiple` число ключей совпадает с текущим `selection_limit`. Для H01 оба поля нужно изменить синхронно.
- Editorial audit: 301 incomplete, approved 0. Это ожидаемо для draft и legacy без provenance.

## Appendix. Coverage ledger

`PASS` означает, что после просмотра `prompt`, `asset`, `assets`, вариантов, ключа и объяснения независимое решение совпало с `correct`.

### ege-biology-1207

q9861 PASS; q9863 PASS; q9864 PASS; q9865 PASS; q9866 PASS; q9867 PASS; f26-ege-bio-a01 PASS; f26-ege-bio-a02 PASS; f26-ege-bio-a03 PASS; f26-ege-bio-a04 PASS; f26-ege-bio-a05 PASS; f26-ege-bio-a06 PASS; f26-ege-bio-a07 PASS; f26-ege-bio-a08 PASS; f26-ege-bio-a09 PASS.

### ege-chemistry-1208

q9868 PASS; q9869 PASS; q9870 M01; q9871 PASS; q9872 PASS; q9873 PASS; f26-ege-chem-a01 PASS; f26-ege-chem-a02 PASS; f26-ege-chem-a03 PASS; f26-ege-chem-a04 PASS; f26-ege-chem-a05 PASS; f26-ege-chem-a06 PASS; f26-ege-chem-a07 PASS; f26-ege-chem-a08 PASS; f26-ege-chem-a09 PASS.

### ege-english-language-1204

q9842 PASS; q9843 PASS; q9844 PASS; q9845 PASS; q9846 PASS; q9847 PASS; q9848 PASS; q9849 PASS; f26-ege-eng-a01 PASS; f26-ege-eng-a02 PASS; f26-ege-eng-a03 PASS; f26-ege-eng-a04 PASS; f26-ege-eng-a05 PASS; f26-ege-eng-a06 PASS; f26-ege-eng-a07 PASS.

### ege-history-1211

q9884 PASS; q9885 PASS; q9886 L01; q9887 PASS; q9888 PASS; f26-ege-hist-a01 PASS; f26-ege-hist-a02 PASS; f26-ege-hist-a03 PASS; f26-ege-hist-a04 PASS; f26-ege-hist-a05 PASS; f26-ege-hist-a06 PASS; f26-ege-hist-a07 PASS; f26-ege-hist-a08 PASS; f26-ege-hist-a09 PASS; f26-ege-hist-a10 PASS.

### ege-informatics-1205

q9851 PASS; q9853 PASS; q9854 PASS; f26-ege-inf-a01 PASS; f26-ege-inf-a02 PASS; f26-ege-inf-a03 PASS; f26-ege-inf-a04 PASS; f26-ege-inf-a05 PASS; f26-ege-inf-a06 PASS; f26-ege-inf-a07 PASS; f26-ege-inf-a08 PASS; f26-ege-inf-a09 PASS; f26-ege-inf-a10 PASS; f26-ege-inf-a11 PASS; f26-ege-inf-a12 PASS.

### ege-literature-1209

q9876 PASS; q9877 L02; q9878 M02; f26-ege-lit-a01 PASS; f26-ege-lit-a02 PASS; f26-ege-lit-a03 PASS; f26-ege-lit-a04 PASS; f26-ege-lit-a05 PASS; f26-ege-lit-a06 PASS; f26-ege-lit-a07 PASS; f26-ege-lit-a08 PASS; f26-ege-lit-a09 PASS; f26-ege-lit-a10 PASS; f26-ege-lit-a11 PASS; f26-ege-lit-a12 PASS.

### ege-mathematics-1212

q9891 PASS; q9892 PASS; q9894 PASS; q9895 PASS; f26-ege-math-a01 PASS; f26-ege-math-a02 PASS; f26-ege-math-a03 PASS; f26-ege-math-a04 PASS; f26-ege-math-a05 PASS; f26-ege-math-a06 PASS; f26-ege-math-a07 PASS; f26-ege-math-a08 PASS; f26-ege-math-a09 PASS; f26-ege-math-a10 PASS; f26-ege-math-a11 PASS.

### ege-physics-1206

q9855 L03; q9856 PASS; q9857 PASS; q9858 M03; q9859 PASS; q9860 PASS; f26-ege-phys-a01 PASS; f26-ege-phys-a02 PASS; f26-ege-phys-a03 PASS; f26-ege-phys-a04 PASS; f26-ege-phys-a05 PASS; f26-ege-phys-a06 PASS; f26-ege-phys-a07 PASS; f26-ege-phys-a08 PASS; f26-ege-phys-a09 PASS.

### ege-russian-language-1213

q9896 L04; q9897 L05; q9898 PASS; q9900 PASS; q9901 PASS; f26-ege-rus-a01 PASS; f26-ege-rus-a02 PASS; f26-ege-rus-a03 PASS; f26-ege-rus-a04 H01; f26-ege-rus-a05 PASS; f26-ege-rus-a06 PASS; f26-ege-rus-a07 PASS; f26-ege-rus-a08 PASS; f26-ege-rus-a09 PASS; f26-ege-rus-a10 PASS.

### ege-social-studies-1210

q9879 PASS; q9880 PASS; q9881 L06; q9882 PASS; q9883 M04; f26-ege-soc-a01 PASS; f26-ege-soc-a02 PASS; f26-ege-soc-a03 PASS; f26-ege-soc-a04 PASS; f26-ege-soc-a05 PASS; f26-ege-soc-a06 PASS; f26-ege-soc-a07 PASS; f26-ege-soc-a08 PASS; f26-ege-soc-a09 PASS; f26-ege-soc-a10 PASS.

### oge-biology-699

q5872 PASS; q5873 PASS; q5874 PASS; q5875 PASS; q5876 PASS; q5877 PASS; q5878 PASS; q5879 PASS; q5880 PASS; q5881 PASS; q5882 M05; q5883 PASS; q5884 PASS; q5885 PASS; q5886 PASS; q5887 L07; q5888 PASS; q5889 PASS; q5891 M06; q5903 PASS.

### oge-chemistry-192

q1484 PASS; q1487 PASS; q1488 PASS; q1489 L08; q1491 PASS; q1492 PASS; q1495 PASS; q1496 PASS; q1497 L08; q1498 PASS; q1499 PASS; q1500 PASS; q1501 PASS; q1504 PASS; q1505 L08; q1506 PASS; q1507 PASS; q1508 PASS; q1509 PASS.

### oge-english-language-202

q1825 PASS; q1826 L09; f26-oge-eng-a01 PASS; f26-oge-eng-a02 PASS; f26-oge-eng-a03 PASS; f26-oge-eng-a04 PASS; f26-oge-eng-a05 PASS; f26-oge-eng-a06 PASS; f26-oge-eng-a07 PASS; f26-oge-eng-a08 PASS; f26-oge-eng-a09 PASS; f26-oge-eng-a10 PASS; f26-oge-eng-a11 PASS; f26-oge-eng-a12 PASS; f26-oge-eng-a13 PASS.

### oge-history-196

q1588 PASS; q1593 PASS; q1601 PASS; q1602 PASS; q1603 H02; q1604 PASS; q1605 PASS; q1607 B01; q1608 PASS; q1610 L10; q1611 PASS; q1612 PASS; q1613 PASS; q1614 PASS; f26-oge-hist-a01 PASS.

### oge-informatics-466

q3889 PASS; q3888 PASS; q3892 PASS; q3893 PASS; q3896 PASS; q3898 PASS; q3899 PASS; q3901 PASS; q3904 PASS; q3905 PASS; q3909 PASS; f26-oge-inf-a01 PASS; f26-oge-inf-a02 PASS; f26-oge-inf-a03 PASS; f26-oge-inf-a04 PASS.

### oge-mathematics-198

q1626 M07; q1628 PASS; q1630 PASS; q1632 PASS; q1633 PASS; q1634 PASS; q1636 PASS; q1637 PASS; q1638 PASS; q1640 PASS; q1645 PASS; q1648 PASS; q1653 PASS; q1655 PASS; q1656 PASS; q1658 PASS; q1661 PASS; q1662 PASS; q1663 PASS.

### oge-physics-197

q1620 PASS; q1621 PASS; q1622 PASS; q1623 PASS; q1624 PASS; q1625 PASS; q1627 PASS; q1629 PASS; q1631 PASS; q1635 PASS; q1639 PASS; q1641 PASS; q1642 PASS; q1643 PASS; q1644 PASS; q1646 M08; q1649 PASS; q1650 PASS.

### oge-russian-language-379

q3377 PASS; q3379 PASS; q3381 PASS; q3383 L11; q3384 PASS; q3386 PASS; q3389 PASS; q3391 PASS; q3392 M09; f26-oge-rus-a01 M12; f26-oge-rus-a02 M12; f26-oge-rus-a03 M12; f26-oge-rus-a04 M12; f26-oge-rus-a05 M12; f26-oge-rus-a06 M12.

### oge-social-studies-195

q1528 L12; q1530 PASS; q1531 PASS; q1535 PASS; q1536 PASS; q1537 H03; q1538 PASS; q1541 PASS; q1543 PASS; q1544 PASS; q1545 PASS; q1547 M10; q1548 PASS; q1550 PASS; q1551 M11.
