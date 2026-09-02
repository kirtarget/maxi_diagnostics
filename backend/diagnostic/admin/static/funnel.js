"use strict";

const apiRoot = "/api/admin/diagnostics";
const STEPS = [
  ["opened", "Открыли"],
  ["started", "Начали"],
  ["completed", "Завершили"],
  ["result_viewed", "Открыли результат"],
];

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function share(part, whole) {
  if (!whole) return "-";
  return `${Math.round((part / whole) * 1000) / 10}%`;
}

function setStatus(id, text, failed = false) {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = text;
  element.style.color = failed ? "#a12638" : "";
}

async function request(path) {
  const response = await fetch(apiRoot + path, {
    credentials: "same-origin",
    headers: {"Content-Type": "application/json"},
  });
  if (!response.ok) throw new Error("request_failed");
  return response.json();
}

function metricCard(label, value, hint) {
  const card = node("div", "card");
  card.append(node("div", "metric", value), node("div", "muted", label));
  if (hint) card.append(node("div", "muted", hint));
  return card;
}

function renderSummary(containerId, bodyId, report) {
  const summary = report.summary;
  const cards = [
    metricCard("Учеников в окне", summary.subjects),
    metricCard("Завершили диагностику", summary.completed, share(summary.completed, summary.opened)),
    metricCard("Вернулись на следующий день", summary.returned_d1, share(summary.returned_d1, summary.subjects)),
    metricCard("Вернулись за 7 дней", summary.returned_d7, share(summary.returned_d7, summary.subjects)),
    metricCard("Ответили в тренажёре", summary.trainer_answered, share(summary.trainer_answered, summary.subjects)),
    metricCard("Нажали на предложение", summary.offer_clicked, share(summary.offer_clicked, summary.subjects)),
  ];
  document.getElementById(containerId).replaceChildren(...cards);

  let previous = null;
  const rows = STEPS.map(([key, label]) => {
    const value = summary[key];
    const row = node("tr");
    row.append(
      node("td", null, label),
      node("td", null, value),
      node("td", null, share(value, summary.opened)),
      node("td", null, previous === null ? "-" : share(value, previous)),
    );
    previous = value;
    return row;
  });
  document.getElementById(bodyId).replaceChildren(...rows);
}

function renderBreakdown(report) {
  const rows = report.breakdown.map((item) => {
    const row = node("tr");
    row.append(
      node("td", null, item.exam),
      node("td", null, item.subject),
      node("td", null, item.started),
      node("td", null, item.completed),
      node("td", null, item.result_viewed),
      node("td", null, item.trainer_answered),
      node("td", null, share(item.completed, item.started)),
    );
    return row;
  });
  document.getElementById("breakdown-body").replaceChildren(...rows);
}

function filterQuery(days) {
  const parameters = new URLSearchParams({days: String(days)});
  const exam = document.getElementById("filter-exam").value.trim();
  const subject = document.getElementById("filter-subject").value.trim();
  if (exam) parameters.set("exam", exam);
  if (subject) parameters.set("subject", subject);
  return `/funnel?${parameters.toString()}`;
}

async function load() {
  setStatus("funnel-status", "Загрузка данных...");
  try {
    const [week, month] = await Promise.all([
      request(filterQuery(7)),
      request(filterQuery(30)),
    ]);
    renderSummary("week-summary", "week-body", week);
    renderSummary("month-summary", "month-body", month);
    renderBreakdown(month);
    setStatus("funnel-status", "Данные обновлены");
  } catch (_) {
    setStatus("funnel-status", "Не удалось загрузить воронку", true);
  }
}

function start() {
  document.getElementById("apply-filter").addEventListener("click", load);
  load();
}

document.addEventListener("DOMContentLoaded", start);
