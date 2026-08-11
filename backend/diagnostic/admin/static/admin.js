"use strict";

const apiRoot = "/api/admin/diagnostics";

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function replaceChildren(target, children) {
  target.replaceChildren(...children);
}

function displayDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "-" : parsed.toLocaleString("ru-RU");
}

async function request(path, options = {}) {
  const response = await fetch(apiRoot + path, {
    credentials: "same-origin",
    ...options,
  });
  if (!response.ok) throw new Error("request_failed");
  return response.json();
}

function setStatus(id, text, failed = false) {
  const target = document.getElementById(id);
  target.textContent = text;
  target.style.color = failed ? "#a12638" : "";
}

function tableRow(values) {
  const row = node("tr");
  values.forEach((value) => row.append(node("td", "", value)));
  return row;
}

async function loadSummary() {
  const data = await request("/summary");
  const labels = [
    ["Попытки", data.attempts],
    ["Завершены", data.completed],
    ["PDF в работе", data.pending_pdfs],
    ["Уведомления к отправке", data.due_notifications],
  ];
  replaceChildren(document.getElementById("summary"), labels.map(([label, value]) => {
    const card = node("article", "card");
    card.append(node("div", "metric", value), node("div", "muted", label));
    return card;
  }));
}

async function loadAttempts() {
  const data = await request("/attempts?limit=50&offset=0");
  const rows = data.items.map((item) => tableRow([
    item.attempt_id,
    item.user_id,
    `${item.subject || "-"} (${item.diagnostic_id || "-"})`,
    item.mode,
    item.score === null ? "-" : `${item.score} / ${item.max_score}`,
    `${item.pdf_status} (${item.pdf_attempts})`,
    displayDate(item.updated_at),
  ]));
  replaceChildren(document.getElementById("attempts-body"), rows);
  setStatus("attempts-status", rows.length ? `Показано ${rows.length} из ${data.total}` : "Попыток пока нет");
}

async function loadIssues() {
  const [delivery, notifications] = await Promise.all([
    request("/delivery-issues?limit=50&offset=0"),
    request("/notification-issues?limit=50&offset=0"),
  ]);
  const rows = delivery.items.map((item) => tableRow([
    "PDF", item.attempt_id, item.user_id, item.pdf_status, item.pdf_attempts, displayDate(item.updated_at),
  ]));
  notifications.items.forEach((item) => rows.push(tableRow([
    item.kind, item.id, item.user_id, item.status, item.attempts, displayDate(item.updated_at),
  ])));
  replaceChildren(document.getElementById("issues-body"), rows);
  setStatus("issues-status", rows.length ? `Найдено проблем: ${rows.length}` : "Проблем доставки нет");
}

function messageCard(message) {
  const card = node("article", "message-card");
  const title = node("h3", "", message.key);
  const description = node("p", "muted", message.description);
  const editor = node("textarea");
  editor.value = message.text;
  editor.setAttribute("aria-label", `Текст ${message.key}`);
  const actions = node("div", "message-actions");
  const save = node("button", "secondary", "Сохранить");
  const status = node("span", "status", "");
  save.addEventListener("click", async () => {
    save.disabled = true;
    status.textContent = "Сохранение...";
    try {
      await request(`/messages/${encodeURIComponent(message.key)}`, {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: editor.value}),
      });
      status.textContent = "Сохранено";
    } catch (_) {
      status.textContent = "Не удалось сохранить";
    } finally {
      save.disabled = false;
    }
  });
  actions.append(status, save);
  card.append(title, description, editor, actions);
  return card;
}

async function loadMessages() {
  const data = await request("/messages");
  const cards = data.items.map(messageCard);
  replaceChildren(document.getElementById("messages-list"), cards);
  setStatus("messages-status", cards.length ? `Сообщений: ${cards.length}` : "Сообщений нет");
}

function configureDelete() {
  const input = document.getElementById("delete-user-id");
  const button = document.getElementById("delete-user");
  let armedId = null;
  input.addEventListener("input", () => {
    armedId = null;
    button.textContent = "Подготовить удаление";
    setStatus("delete-status", "");
  });
  button.addEventListener("click", async () => {
    const userId = Number(input.value);
    if (!Number.isInteger(userId) || userId < 1) {
      setStatus("delete-status", "Введите положительный ID пользователя", true);
      return;
    }
    if (armedId !== userId) {
      armedId = userId;
      button.textContent = "Подтвердить удаление";
      setStatus("delete-status", `Повторно нажмите для удаления данных пользователя ${userId}`);
      return;
    }
    button.disabled = true;
    setStatus("delete-status", "Удаление...");
    try {
      const data = await request("/users", {
        method: "DELETE",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({user_id: userId, confirm: true}),
      });
      input.value = "";
      armedId = null;
      button.textContent = "Подготовить удаление";
      setStatus("delete-status", `Удалено строк: ${data.deleted.notifications + data.deleted.attempts + data.deleted.engagements}`);
      await Promise.all([loadSummary(), loadAttempts(), loadIssues()]);
    } catch (_) {
      setStatus("delete-status", "Не удалось удалить данные", true);
    } finally {
      button.disabled = false;
    }
  });
}

async function start() {
  configureDelete();
  try {
    await Promise.all([loadSummary(), loadAttempts(), loadIssues(), loadMessages()]);
    setStatus("page-status", "Данные обновлены");
  } catch (_) {
    setStatus("page-status", "Не удалось загрузить данные", true);
  }
}

document.addEventListener("DOMContentLoaded", start);
