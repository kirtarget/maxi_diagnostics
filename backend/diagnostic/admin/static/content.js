"use strict";

const contentRoot = "/api/admin/diagnostics/content";
let contentState = {index: null, draft: null, diagnosticId: null, questionId: null};

function contentNode(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

async function contentRequest(path, options = {}) {
  const response = await fetch(contentRoot + path, {
    credentials: "same-origin",
    ...options,
  });
  if (!response.ok) {
    const error = new Error("content_request_failed");
    error.status = response.status;
    throw error;
  }
  return response;
}

function setContentStatus(id, text, failed = false) {
  const target = document.getElementById(id);
  target.textContent = text;
  target.style.color = failed ? "#a12638" : "";
}

function fillSelect(id, values) {
  const select = document.getElementById(id);
  const current = select.value;
  const options = [contentNode("option", "", "Все")];
  options[0].value = "";
  [...new Set(values)].sort((a, b) => a.localeCompare(b, "ru")).forEach((value) => {
    const option = contentNode("option", "", value);
    option.value = value;
    options.push(option);
  });
  select.replaceChildren(...options);
  select.value = current;
}

function findQuestion(diagnosticId, questionId) {
  const diagnostic = contentState.index.items.find((item) => item.diagnostic_id === diagnosticId);
  return diagnostic && diagnostic.questions.find((item) => item.id === questionId);
}

async function ensureDraft(diagnosticId) {
  if (contentState.draft && contentState.diagnosticId === diagnosticId) return;
  let response = await contentRequest(`/${encodeURIComponent(diagnosticId)}/draft`).catch((error) => {
    if (error.status === 404) return null;
    throw error;
  });
  if (!response) {
    response = await contentRequest(`/${encodeURIComponent(diagnosticId)}/draft`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: "{}",
    });
  }
  contentState.draft = await response.json();
  contentState.diagnosticId = diagnosticId;
}

function answerText(question) {
  if (typeof question.correct === "string") return question.correct;
  if (Array.isArray(question.correct)) return question.correct.join("\n");
  return Object.entries(question.correct || {}).map(([left, right]) => `${left} = ${right}`).join("\n");
}

function optionText(values) {
  return (values || []).map((item) => `${item.id} | ${item.label}`).join("\n");
}

function fillSource(source) {
  const value = source || {};
  document.getElementById("source-provider").value = value.provider || "";
  document.getElementById("source-year").value = value.official_year || "";
  document.getElementById("source-approval").value = value.approval_status || "approved";
  document.getElementById("source-kind").value = value.source_kind || "open_bank";
  document.getElementById("source-url").value = value.source_url || "";
  document.getElementById("source-project-id").value = value.fipi_project_id || "";
  document.getElementById("source-question-id").value = value.fipi_question_id || "";
  document.getElementById("source-position").value = value.exam_position || "";
  document.getElementById("source-verified-at").value = value.verified_at || "";
  document.getElementById("source-criteria-url").value = value.official_criteria_url || "";
  document.getElementById("source-rights").value = value.rights_status || "link_only";
}

async function openQuestion(diagnosticId, questionId) {
  setContentStatus("editor-status", "Загрузка черновика...");
  try {
    await ensureDraft(diagnosticId);
    const question = contentState.draft.payload.questions.find((item) => item.id === questionId);
    if (!question) throw new Error("question_not_found");
    contentState.questionId = questionId;
    document.getElementById("question-id").value = question.id;
    document.getElementById("question-id").disabled = true;
    document.getElementById("question-type").value = question.type;
    document.getElementById("question-type").disabled = true;
    document.getElementById("question-title").value = question.title;
    document.getElementById("question-topic").value = question.topic;
    document.getElementById("question-max-score").value = question.max_primary_score || 1;
    document.getElementById("question-selection-limit").value = question.selection_limit || "";
    document.getElementById("question-prompt").value = question.prompt;
    document.getElementById("question-options").value = optionText(question.options);
    document.getElementById("question-items").value = optionText(question.items);
    document.getElementById("question-correct").value = answerText(question);
    document.getElementById("question-explanation").value = question.explanation || "";
    document.getElementById("question-learning-text").value = question.learning_material_text || "";
    document.getElementById("question-learning-url").value = question.learning_material_url || "";
    fillSource(question.source);
    document.getElementById("editor-section").hidden = false;
    setContentStatus("editor-status", `Черновик, версия ${contentState.draft.edit_revision}`);
    document.getElementById("editor-section").scrollIntoView({behavior: "smooth", block: "start"});
  } catch (_) {
    setContentStatus("editor-status", "Не удалось открыть задание", true);
  }
}

async function newInputQuestion(diagnosticId) {
  setContentStatus("editor-status", "Подготовка нового задания...");
  try {
    await ensureDraft(diagnosticId);
    contentState.questionId = null;
    document.getElementById("question-id").value = "";
    document.getElementById("question-id").disabled = false;
    document.getElementById("question-type").value = "input";
    document.getElementById("question-type").disabled = true;
    ["question-title", "question-topic", "question-prompt", "question-correct", "question-explanation", "question-learning-text", "question-learning-url", "question-options", "question-items", "question-selection-limit"].forEach((id) => {
      document.getElementById(id).value = "";
    });
    document.getElementById("question-max-score").value = "1";
    fillSource(null);
    document.getElementById("editor-section").hidden = false;
    setContentStatus("editor-status", `Новое числовое задание. Черновик, версия ${contentState.draft.edit_revision}`);
    document.getElementById("editor-section").scrollIntoView({behavior: "smooth", block: "start"});
  } catch (_) {
    setContentStatus("editor-status", "Не удалось создать черновик", true);
  }
}

function renderContent() {
  const query = document.getElementById("content-query").value.trim().toLocaleLowerCase("ru");
  const exam = document.getElementById("content-exam").value;
  const subject = document.getElementById("content-subject").value;
  const type = document.getElementById("content-type").value;
  const cards = [];
  let visible = 0;
  contentState.index.items.forEach((diagnostic) => {
    if (exam && diagnostic.exam !== exam) return;
    if (subject && diagnostic.subject !== subject) return;
    const questions = diagnostic.questions.filter((question) => {
      if (type && question.type !== type) return false;
      return !query || `${question.id} ${question.title} ${question.topic}`.toLocaleLowerCase("ru").includes(query);
    });
    if (!questions.length) return;
    const card = contentNode("article", "message-card");
    card.append(contentNode("h3", "", `${diagnostic.exam} · ${diagnostic.subject}${diagnostic.is_draft ? " · черновик" : ""}`));
    questions.forEach((question) => {
      visible += 1;
      const button = contentNode("button", "question-button", `${question.title} · ${question.topic}${question.has_explanation ? "" : " · нет разбора"}`);
      button.type = "button";
      button.addEventListener("click", () => openQuestion(diagnostic.diagnostic_id, question.id));
      card.append(button);
    });
    const create = contentNode("button", "secondary", "Добавить числовое задание");
    create.type = "button";
    create.addEventListener("click", () => newInputQuestion(diagnostic.diagnostic_id));
    card.append(create);
    cards.push(card);
  });
  document.getElementById("content-list").replaceChildren(...cards);
  document.getElementById("content-count").textContent = `Показано ${visible}. Всего ${contentState.index.catalog_question_count}. Лимит ${contentState.index.diagnostic_question_limit} на диагностику.`;
}

function parsedCorrect(question) {
  const lines = document.getElementById("question-correct").value.split("\n").map((value) => value.trim()).filter(Boolean);
  if (question.type === "single") return lines[0] || "";
  if (question.type === "matching") {
    return Object.fromEntries(lines.map((line) => line.split("=").map((value) => value.trim())).filter((parts) => parts.length === 2));
  }
  return lines;
}

function parsedOptions(id) {
  return document.getElementById(id).value.split("\n").map((line) => {
    const separator = line.indexOf("|");
    if (separator < 1) return null;
    return {id: line.slice(0, separator).trim(), label: line.slice(separator + 1).trim()};
  }).filter((item) => item && item.id && item.label);
}

function parsedSource() {
  const provider = document.getElementById("source-provider").value.trim();
  if (!provider) return null;
  const source = {
    provider,
    official_year: Number(document.getElementById("source-year").value),
    approval_status: document.getElementById("source-approval").value,
    source_kind: document.getElementById("source-kind").value,
    source_url: document.getElementById("source-url").value.trim(),
    rights_status: document.getElementById("source-rights").value,
    verified_at: document.getElementById("source-verified-at").value,
  };
  const optional = {
    fipi_project_id: "source-project-id",
    fipi_question_id: "source-question-id",
    exam_position: "source-position",
    official_criteria_url: "source-criteria-url",
  };
  Object.entries(optional).forEach(([key, id]) => {
    const value = document.getElementById(id).value.trim();
    if (value) source[key] = value;
  });
  return source;
}

async function saveQuestion() {
  const existing = contentState.draft.payload.questions.find((item) => item.id === contentState.questionId);
  const question = existing || {type: "input", correct: []};
  const updated = {
    ...question,
    id: document.getElementById("question-id").value.trim(),
    title: document.getElementById("question-title").value,
    topic: document.getElementById("question-topic").value,
    prompt: document.getElementById("question-prompt").value,
    max_primary_score: Number(document.getElementById("question-max-score").value),
    correct: parsedCorrect(question),
  };
  if ("options" in question) updated.options = parsedOptions("question-options");
  if ("items" in question) updated.items = parsedOptions("question-items");
  if ("selection_limit" in question) updated.selection_limit = Number(document.getElementById("question-selection-limit").value);
  const source = parsedSource();
  if (source) updated.source = source; else delete updated.source;
  const explanation = document.getElementById("question-explanation").value.trim();
  const learningText = document.getElementById("question-learning-text").value.trim();
  const learningUrl = document.getElementById("question-learning-url").value.trim();
  if (explanation) updated.explanation = explanation; else delete updated.explanation;
  if (learningText) updated.learning_material_text = learningText; else delete updated.learning_material_text;
  if (learningUrl) updated.learning_material_url = learningUrl; else delete updated.learning_material_url;
  setContentStatus("editor-status", "Сохранение...");
  try {
    const suffix = existing ? `/questions/${encodeURIComponent(question.id)}` : "/questions";
    const response = await contentRequest(`/${encodeURIComponent(contentState.diagnosticId)}/draft${suffix}`, {
      method: existing ? "PUT" : "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({expected_revision: contentState.draft.edit_revision, question: updated}),
    });
    contentState.draft = await response.json();
    contentState.questionId = updated.id;
    setContentStatus("editor-status", `Сохранено. Версия ${contentState.draft.edit_revision}`);
    await loadContent();
  } catch (error) {
    setContentStatus("editor-status", error.status === 409 ? "Черновик уже изменён. Обновите страницу." : "Не удалось сохранить. Проверьте поля.", true);
  }
}

async function draftAction(action) {
  setContentStatus("editor-status", action === "validate" ? "Проверка..." : "Подготовка файла...");
  try {
    const response = await contentRequest(`/${encodeURIComponent(contentState.diagnosticId)}/draft/${action}`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({expected_revision: contentState.draft.edit_revision}),
    });
    if (action === "validate") {
      const result = await response.json();
      setContentStatus("editor-status", `Проверка пройдена. Вопросов в каталоге: ${result.question_count}.`);
      return;
    }
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${contentState.diagnosticId}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    setContentStatus("editor-status", "JSON скачан. Перед deployment добавьте его в Git и запустите проверки контента.");
  } catch (error) {
    setContentStatus("editor-status", error.status === 409 ? "Черновик уже изменён. Обновите страницу." : "Проверка не пройдена.", true);
  }
}

async function loadContent() {
  const response = await contentRequest("");
  contentState.index = await response.json();
  fillSelect("content-exam", contentState.index.items.map((item) => item.exam));
  fillSelect("content-subject", contentState.index.items.map((item) => item.subject));
  renderContent();
  setContentStatus("content-status", "База вопросов загружена");
}

document.addEventListener("DOMContentLoaded", () => {
  ["content-query", "content-exam", "content-subject", "content-type"].forEach((id) => {
    document.getElementById(id).addEventListener(id === "content-query" ? "input" : "change", renderContent);
  });
  document.getElementById("save-question").addEventListener("click", saveQuestion);
  document.getElementById("validate-draft").addEventListener("click", () => draftAction("validate"));
  document.getElementById("export-draft").addEventListener("click", () => draftAction("export"));
  loadContent().catch(() => setContentStatus("content-status", "Не удалось загрузить базу вопросов", true));
});
