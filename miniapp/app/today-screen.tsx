import type { TodaySession, TopicPathNode } from "./types";
import { estimatedMinutesLabel, pathPreview, todayCtaSummary, topicNodeCaption } from "./today-path-model";
import { plural } from "./text-utils";

export type TodayScreenProps = {
  today: TodaySession;
  onStartSession: () => void;
  onOpenPath: () => void;
  onStartOnboarding: () => void;
  /** Launch the weekly checkpoint blocking today's path. Called with `checkpoint_unit_index`. */
  onStartCheckpoint: (unitIndex: number) => void;
};

function TodayHeroStat({ value, label }: { value: string; label: string }) {
  return (
    <div className="today-stat">
      <strong>{value}</strong>
      <small>{label}</small>
    </div>
  );
}

function PathPreviewNode({ node }: { node: TopicPathNode }) {
  const marker = node.status === "done" ? "✓" : node.status === "current" ? String(node.index + 1) : "🔒";
  return (
    <div className={`today-path-node is-${node.status}`}>
      <span className="today-path-badge" aria-hidden="true">{marker}</span>
      <span className="today-path-copy">
        <strong>{node.topic}</strong>
        <small>{topicNodeCaption(node)}</small>
      </span>
    </div>
  );
}

export function TodayScreen({ today, onStartSession, onOpenPath, onStartOnboarding, onStartCheckpoint }: TodayScreenProps) {
  if (today.status === "no_diagnostic") {
    return (
      <section className="screen today-screen" aria-labelledby="today-title">
        <div className="today-hero today-hero-empty">
          <span className="today-eyebrow">Тренажёр</span>
          <h1 id="today-title">Соберём твой путь</h1>
          <p>Пройди короткую диагностику — по ней тренажёр составит ежедневные сессии по твоим темам.</p>
          <button className="primary-button today-cta" onClick={onStartOnboarding} type="button">
            Пройти диагностику <span aria-hidden="true">→</span>
          </button>
        </div>
      </section>
    );
  }

  if (today.status === "path_complete") {
    return (
      <section className="screen today-screen" aria-labelledby="today-title">
        <div className="today-hero today-hero-complete">
          <span className="today-eyebrow">{today.subject} · {today.exam}</span>
          <h1 id="today-title">Путь пройден 🎉</h1>
          <p>Все темы кодификатора закрыты. Загляни в путь, чтобы повторить слабые места, или дождись нового чекпоинта.</p>
          <button className="primary-button today-cta" onClick={onOpenPath} type="button">
            Смотреть путь <span aria-hidden="true">→</span>
          </button>
        </div>
        <TodayStats today={today} />
      </section>
    );
  }

  if (today.status === "checkpoint") {
    const preview = pathPreview(today.path);
    const unitIndex = today.checkpoint_unit_index;
    return (
      <section className="screen today-screen" aria-labelledby="today-title">
        <div className="today-hero today-hero-checkpoint">
          <div className="today-hero-top">
            <span className="today-eyebrow">{today.subject} · {today.exam}</span>
            <span className="today-streak-pill" aria-label={`Серия ${today.streak_days} ${plural(today.streak_days, ["день", "дня", "дней"])}`}>
              <span aria-hidden="true">🔥</span> {today.streak_days} {plural(today.streak_days, ["день", "дня", "дней"])}
            </span>
          </div>
          <h1 id="today-title">Чекпоинт недели 🎯</h1>
          <p className="today-lead">Ты закрыл блок тем. Пройди короткий срез — он закрепит блок и откроет следующие темы пути.</p>
          <button
            className="primary-button today-cta"
            onClick={() => { if (unitIndex !== null) onStartCheckpoint(unitIndex); }}
            type="button"
            disabled={unitIndex === null}
          >
            <span className="today-cta-main">Пройти чекпоинт недели</span>
            <span className="today-cta-play" aria-hidden="true">▶</span>
          </button>
          <TodayStats today={today} />
        </div>

        <div className="today-path-preview">
          <div className="today-section-head">
            <h2>Твой путь</h2>
            <button className="today-path-link" onClick={onOpenPath} type="button">Весь путь <span aria-hidden="true">→</span></button>
          </div>
          <div className="today-path-list">
            {preview.map((node) => <PathPreviewNode key={node.topic} node={node} />)}
          </div>
        </div>
      </section>
    );
  }

  const cta = todayCtaSummary(today);
  const preview = pathPreview(today.path);
  return (
    <section className="screen today-screen" aria-labelledby="today-title">
      <div className="today-hero">
        <div className="today-hero-top">
          <span className="today-eyebrow">{today.subject} · {today.exam}</span>
          <span className="today-streak-pill" aria-label={`Серия ${today.streak_days} ${plural(today.streak_days, ["день", "дня", "дней"])}`}>
            <span aria-hidden="true">🔥</span> {today.streak_days} {plural(today.streak_days, ["день", "дня", "дней"])}
          </span>
        </div>
        <h1 id="today-title">Привет 👋</h1>
        <p className="today-lead">Сегодняшняя порция — {cta.size} по темам, где ты растёшь. Разберём каждое сразу.</p>
        <button className="primary-button today-cta" onClick={onStartSession} type="button">
          <span className="today-cta-main">Заниматься</span>
          <span className="today-cta-meta">{cta.size}{cta.topic ? ` · ${cta.topic}` : ""} · {estimatedMinutesLabel(today.estimated_minutes)}</span>
          <span className="today-cta-play" aria-hidden="true">▶</span>
        </button>
        <TodayStats today={today} />
      </div>

      <div className="today-path-preview">
        <div className="today-section-head">
          <h2>Твой путь</h2>
          <button className="today-path-link" onClick={onOpenPath} type="button">Весь путь <span aria-hidden="true">→</span></button>
        </div>
        <div className="today-path-list">
          {preview.map((node) => <PathPreviewNode key={node.topic} node={node} />)}
        </div>
      </div>
    </section>
  );
}

function TodayStats({ today }: { today: TodaySession }) {
  return (
    <div className="today-stats" aria-label="Прогресс за сегодня">
      <TodayHeroStat value={String(today.streak_days)} label={`${plural(today.streak_days, ["день", "дня", "дней"])} подряд`} />
      <TodayHeroStat value={`${today.daily_goal.progress}/${today.daily_goal.target}`} label="цель дня" />
      <TodayHeroStat value={String(today.xp_total)} label="XP" />
    </div>
  );
}
