# Независимый аудит каталога после fix pass

Дата аудита: 1 сентября 2026 года.

Итог: **PASS**.

Проверено 301 из 301 вопросов в 19 диагностиках. Старый отчёт использован только как regression checklist. Каждый вопрос заново проверен по `prompt`, `asset`, `assets`, `options`, `correct`, `selection_limit` и `explanation`. Для 138 enriched draft дополнительно проверены `source`, `source.exam_position` и `max_primary_score`.

## Сводка

| Результат | Число вопросов |
|---|---:|
| PASS | 301 |
| BLOCKER | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 0 |
| Всего | 301 |

Regression checklist из старого отчёта закрыт полностью.

| Проверка исправлений | Число вопросов |
|---|---:|
| Исправлено из старого regression checklist | 35 |
| Исправлено после независимого post-fix аудита | 1 |
| Не исправлено | 0 |
| Новые проблемы | 0 |

Старые 35 вопросов включали 1 BLOCKER, 3 HIGH, 17 MEDIUM и 14 LOW. Групповые пункты M12 и L08 пересчитаны по отдельным ID.

## Дополнительная post-fix проверка

### q9865. Исправлено

Независимый аудит обнаружил, что прежнее поле `asset` указывало на полностью прозрачный PNG размером 1 на 1 пиксель и 120 байт. Вопрос самодостаточен. Все шесть систематических категорий перечислены в `prompt`, ключ `361425` и объяснение верны.

Текущее состояние проверено повторно. Поле `asset` удалено, файл `assets/questions/q9865.png` отсутствует, битой ссылки нет. q9865 имеет итоговый статус PASS.

## Regression checklist

- B01, q1607. Исправлено. `q1607.png` теперь является полной картой 690 на 632 пикселя, 362264 байта. SHA-256 совпадает с проверенной картой `q1605.png`. На карте Евпатория обозначена цифрой 3.
- H01, f26-ege-rus-a04. Исправлено. `correct=[b,c]`, `selection_limit=2`; объяснение согласовано с ключом.
- H02, q1603. Исправлено. Остался единственный допустимый ответ `1423`; объяснение следует порядку столбцов.
- H03, q1537. Исправлено. Ключ равен `o2`; объяснение больше не объявляет государственную собственность обязательным признаком рыночной экономики.
- M01-M11. Исправлено. Уточнены условия и формулировки q9870, q9878, q9858, q9883, q5882, q5891, q1626, q1646, q3392, q1547 и q1551. Ключи и объяснения согласованы с новыми формулировками.
- M12. Исправлено как metadata-контракт. Все шесть f26-oge-rus-a01..a06 имеют заполненные `source`, `exam_position`, `max_primary_score` и статус `draft`. Предварительное сопоставление не выдаётся за approved.
- L01-L12 старого отчёта. Исправлено. Канонизированы q9886, q1610 и q3383. OCR и редакционные дефекты устранены в q9877, q9855, q9896, q9897, q9881, q5887, q1489, q1497, q1505, q1826 и q1528.

## Структурные доказательства

- Диагностик 19. Вопросов 301. Уникальных ID 301.
- Типы вопросов. `input=189`, `multiple=81`, `single=31`.
- Непустые `prompt` и `explanation` есть у 301 из 301.
- Все option ID уникальны в пределах вопроса. Все ключи `single` и `multiple` ссылаются на существующие option ID.
- У всех 81 `multiple` число элементов `correct` совпадает с `selection_limit`.
- Непустые допустимые ответы есть у всех 189 `input`.
- Enriched draft 138. У всех 138 заполнены обязательные поля `source`, включая `exam_position`; у всех есть целый `max_primary_score`. Все 138 имеют `approval_status=draft`. Approved нет.
- Legacy без `source` 163. Это не дефект текущего runtime-каталога, но такие вопросы нельзя считать approved с подтверждённым provenance.

## Ресурсы

- Поле `asset` используется у 36 вопросов и даёт 36 ссылок.
- Поле `assets` используется у 8 вопросов и даёт 21 ссылку.
- Всего 57 ссылок на 57 уникальных файлов. Отсутствующих файлов нет.
- Проверены все фактические 48 raster-файлов и 9 SVG. SVG корректно разбираются как XML, имеют `viewBox` и не содержат внешних ссылок или скриптов.
- Допустимые повторы подтверждены содержанием. q1605/q1607 используют одну карту; q1610/q1611 используют одну пару изображений; q1626/q1628/q1630/q1632 используют одну таблицу; q5889/q5891 используют одну пищевую сеть.
- Прозрачный q9865.png удалён вместе с лишней ссылкой. Проблем ресурсов не осталось.

## Проверки

- `python scripts/validate_school.py` завершился сообщением `OK school=maximum diagnostics=19 questions=301 assets=58`.
- Объединённый запуск regression tests, FIPI partitions, legacy enrichment contract и OGE informatics author draft дал `34 passed`.
- Собственный read-only профиль полей, ключей, лимитов, source metadata и путей не нашёл структурных нарушений.

## Coverage

| Диагностика | Reviewed | PASS | Findings |
|---|---:|---:|---:|
| ege-biology-1207 | 15 | 15 | 0 |
| ege-chemistry-1208 | 15 | 15 | 0 |
| ege-english-language-1204 | 15 | 15 | 0 |
| ege-history-1211 | 15 | 15 | 0 |
| ege-informatics-1205 | 15 | 15 | 0 |
| ege-literature-1209 | 15 | 15 | 0 |
| ege-mathematics-1212 | 15 | 15 | 0 |
| ege-physics-1206 | 15 | 15 | 0 |
| ege-russian-language-1213 | 15 | 15 | 0 |
| ege-social-studies-1210 | 15 | 15 | 0 |
| oge-biology-699 | 20 | 20 | 0 |
| oge-chemistry-192 | 19 | 19 | 0 |
| oge-english-language-202 | 15 | 15 | 0 |
| oge-history-196 | 15 | 15 | 0 |
| oge-informatics-466 | 15 | 15 | 0 |
| oge-mathematics-198 | 19 | 19 | 0 |
| oge-physics-197 | 18 | 18 | 0 |
| oge-russian-language-379 | 15 | 15 | 0 |
| oge-social-studies-195 | 15 | 15 | 0 |
| **Итого** | **301** | **301** | **0** |

## Ledger 301/301

`PASS` означает согласованность условия, вариантов, ключа, лимита выбора и объяснения с учётом всех связанных ресурсов.

### ege-biology-1207

q9861 PASS; q9863 PASS; q9864 PASS; q9865 PASS; q9866 PASS; q9867 PASS; f26-ege-bio-a01 PASS; f26-ege-bio-a02 PASS; f26-ege-bio-a03 PASS; f26-ege-bio-a04 PASS; f26-ege-bio-a05 PASS; f26-ege-bio-a06 PASS; f26-ege-bio-a07 PASS; f26-ege-bio-a08 PASS; f26-ege-bio-a09 PASS.

### ege-chemistry-1208

q9868 PASS; q9869 PASS; q9870 PASS; q9871 PASS; q9872 PASS; q9873 PASS; f26-ege-chem-a01 PASS; f26-ege-chem-a02 PASS; f26-ege-chem-a03 PASS; f26-ege-chem-a04 PASS; f26-ege-chem-a05 PASS; f26-ege-chem-a06 PASS; f26-ege-chem-a07 PASS; f26-ege-chem-a08 PASS; f26-ege-chem-a09 PASS.

### ege-english-language-1204

q9842 PASS; q9843 PASS; q9844 PASS; q9845 PASS; q9846 PASS; q9847 PASS; q9848 PASS; q9849 PASS; f26-ege-eng-a01 PASS; f26-ege-eng-a02 PASS; f26-ege-eng-a03 PASS; f26-ege-eng-a04 PASS; f26-ege-eng-a05 PASS; f26-ege-eng-a06 PASS; f26-ege-eng-a07 PASS.

### ege-history-1211

q9884 PASS; q9885 PASS; q9886 PASS; q9887 PASS; q9888 PASS; f26-ege-hist-a01 PASS; f26-ege-hist-a02 PASS; f26-ege-hist-a03 PASS; f26-ege-hist-a04 PASS; f26-ege-hist-a05 PASS; f26-ege-hist-a06 PASS; f26-ege-hist-a07 PASS; f26-ege-hist-a08 PASS; f26-ege-hist-a09 PASS; f26-ege-hist-a10 PASS.

### ege-informatics-1205

q9851 PASS; q9853 PASS; q9854 PASS; f26-ege-inf-a01 PASS; f26-ege-inf-a02 PASS; f26-ege-inf-a03 PASS; f26-ege-inf-a04 PASS; f26-ege-inf-a05 PASS; f26-ege-inf-a06 PASS; f26-ege-inf-a07 PASS; f26-ege-inf-a08 PASS; f26-ege-inf-a09 PASS; f26-ege-inf-a10 PASS; f26-ege-inf-a11 PASS; f26-ege-inf-a12 PASS.

### ege-literature-1209

q9876 PASS; q9877 PASS; q9878 PASS; f26-ege-lit-a01 PASS; f26-ege-lit-a02 PASS; f26-ege-lit-a03 PASS; f26-ege-lit-a04 PASS; f26-ege-lit-a05 PASS; f26-ege-lit-a06 PASS; f26-ege-lit-a07 PASS; f26-ege-lit-a08 PASS; f26-ege-lit-a09 PASS; f26-ege-lit-a10 PASS; f26-ege-lit-a11 PASS; f26-ege-lit-a12 PASS.

### ege-mathematics-1212

q9891 PASS; q9892 PASS; q9894 PASS; q9895 PASS; f26-ege-math-a01 PASS; f26-ege-math-a02 PASS; f26-ege-math-a03 PASS; f26-ege-math-a04 PASS; f26-ege-math-a05 PASS; f26-ege-math-a06 PASS; f26-ege-math-a07 PASS; f26-ege-math-a08 PASS; f26-ege-math-a09 PASS; f26-ege-math-a10 PASS; f26-ege-math-a11 PASS.

### ege-physics-1206

q9855 PASS; q9856 PASS; q9857 PASS; q9858 PASS; q9859 PASS; q9860 PASS; f26-ege-phys-a01 PASS; f26-ege-phys-a02 PASS; f26-ege-phys-a03 PASS; f26-ege-phys-a04 PASS; f26-ege-phys-a05 PASS; f26-ege-phys-a06 PASS; f26-ege-phys-a07 PASS; f26-ege-phys-a08 PASS; f26-ege-phys-a09 PASS.

### ege-russian-language-1213

q9896 PASS; q9897 PASS; q9898 PASS; q9900 PASS; q9901 PASS; f26-ege-rus-a01 PASS; f26-ege-rus-a02 PASS; f26-ege-rus-a03 PASS; f26-ege-rus-a04 PASS; f26-ege-rus-a05 PASS; f26-ege-rus-a06 PASS; f26-ege-rus-a07 PASS; f26-ege-rus-a08 PASS; f26-ege-rus-a09 PASS; f26-ege-rus-a10 PASS.

### ege-social-studies-1210

q9879 PASS; q9880 PASS; q9881 PASS; q9882 PASS; q9883 PASS; f26-ege-soc-a01 PASS; f26-ege-soc-a02 PASS; f26-ege-soc-a03 PASS; f26-ege-soc-a04 PASS; f26-ege-soc-a05 PASS; f26-ege-soc-a06 PASS; f26-ege-soc-a07 PASS; f26-ege-soc-a08 PASS; f26-ege-soc-a09 PASS; f26-ege-soc-a10 PASS.

### oge-biology-699

q5872 PASS; q5873 PASS; q5874 PASS; q5875 PASS; q5876 PASS; q5877 PASS; q5878 PASS; q5879 PASS; q5880 PASS; q5881 PASS; q5882 PASS; q5883 PASS; q5884 PASS; q5885 PASS; q5886 PASS; q5887 PASS; q5888 PASS; q5889 PASS; q5891 PASS; q5903 PASS.

### oge-chemistry-192

q1484 PASS; q1487 PASS; q1488 PASS; q1489 PASS; q1491 PASS; q1492 PASS; q1495 PASS; q1496 PASS; q1497 PASS; q1498 PASS; q1499 PASS; q1500 PASS; q1501 PASS; q1504 PASS; q1505 PASS; q1506 PASS; q1507 PASS; q1508 PASS; q1509 PASS.

### oge-english-language-202

q1825 PASS; q1826 PASS; f26-oge-eng-a01 PASS; f26-oge-eng-a02 PASS; f26-oge-eng-a03 PASS; f26-oge-eng-a04 PASS; f26-oge-eng-a05 PASS; f26-oge-eng-a06 PASS; f26-oge-eng-a07 PASS; f26-oge-eng-a08 PASS; f26-oge-eng-a09 PASS; f26-oge-eng-a10 PASS; f26-oge-eng-a11 PASS; f26-oge-eng-a12 PASS; f26-oge-eng-a13 PASS.

### oge-history-196

q1588 PASS; q1593 PASS; q1601 PASS; q1602 PASS; q1603 PASS; q1604 PASS; q1605 PASS; q1607 PASS; q1608 PASS; q1610 PASS; q1611 PASS; q1612 PASS; q1613 PASS; q1614 PASS; f26-oge-hist-a01 PASS.

### oge-informatics-466

q3889 PASS; q3888 PASS; q3892 PASS; q3893 PASS; q3896 PASS; q3898 PASS; q3899 PASS; q3901 PASS; q3904 PASS; q3905 PASS; q3909 PASS; f26-oge-inf-a01 PASS; f26-oge-inf-a02 PASS; f26-oge-inf-a03 PASS; f26-oge-inf-a04 PASS.

### oge-mathematics-198

q1626 PASS; q1628 PASS; q1630 PASS; q1632 PASS; q1633 PASS; q1634 PASS; q1636 PASS; q1637 PASS; q1638 PASS; q1640 PASS; q1645 PASS; q1648 PASS; q1653 PASS; q1655 PASS; q1656 PASS; q1658 PASS; q1661 PASS; q1662 PASS; q1663 PASS.

### oge-physics-197

q1620 PASS; q1621 PASS; q1622 PASS; q1623 PASS; q1624 PASS; q1625 PASS; q1627 PASS; q1629 PASS; q1631 PASS; q1635 PASS; q1639 PASS; q1641 PASS; q1642 PASS; q1643 PASS; q1644 PASS; q1646 PASS; q1649 PASS; q1650 PASS.

### oge-russian-language-379

q3377 PASS; q3379 PASS; q3381 PASS; q3383 PASS; q3384 PASS; q3386 PASS; q3389 PASS; q3391 PASS; q3392 PASS; f26-oge-rus-a01 PASS; f26-oge-rus-a02 PASS; f26-oge-rus-a03 PASS; f26-oge-rus-a04 PASS; f26-oge-rus-a05 PASS; f26-oge-rus-a06 PASS.

### oge-social-studies-195

q1528 PASS; q1530 PASS; q1531 PASS; q1535 PASS; q1536 PASS; q1537 PASS; q1538 PASS; q1541 PASS; q1543 PASS; q1544 PASS; q1545 PASS; q1547 PASS; q1548 PASS; q1550 PASS; q1551 PASS.
