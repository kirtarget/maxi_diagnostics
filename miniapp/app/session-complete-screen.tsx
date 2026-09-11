import type { CSSProperties } from "react";
import type { SessionCompleteView } from "./session-complete-model";
import { plural } from "./text-utils";

export type SessionCompleteScreenProps = {
  view: SessionCompleteView;
  onHome: () => void;
  onReview?: () => void;
};

export function SessionCompleteScreen({ view, onHome, onReview }: SessionCompleteScreenProps) {
  return (
    <section className="screen session-complete" aria-labelledby="session-complete-title">
      <span className="session-complete-eyebrow" aria-hidden="true">✦ Сессия закончена ✦</span>
      <h1 id="session-complete-title">Отличная работа!</h1>
      <p className="session-complete-sub">
        {view.topic ? `${view.topic} · ` : ""}{view.solved} из {view.size} {plural(view.size, ["задание", "задания", "заданий"])}
      </p>

      <div className="session-streak" role="group" aria-label="Серия">
        <span className="session-streak-flame" aria-hidden="true">🔥</span>
        <strong className="session-streak-count">{view.streakDays} {plural(view.streakDays, ["день", "дня", "дней"])} подряд</strong>
        <small>{view.streakGrew ? "серия продолжается" : "продолжай серию"}</small>
        {view.streakGrew && <span className="session-streak-delta">+1 день</span>}
      </div>

      <div className="session-tiles" aria-label="Итоги сессии">
        <div className="session-tile">
          <strong>+{view.xpEarned}</strong>
          <small>XP за сессию</small>
        </div>
        <div className="session-tile">
          <strong>{view.solved}/{view.size}</strong>
          <small>верно</small>
        </div>
        {view.masteryPercent !== null && (
          <div className="session-tile">
            <strong>{view.masteryPercent}%</strong>
            <small>тема пройдена</small>
          </div>
        )}
      </div>

      <div className="session-changes">
        <h2>Что изменилось</h2>
        {view.topic && (view.masteryDelta !== null || view.masteryPercent !== null) && (
          <div className="session-change is-up">
            <span className="session-change-icon" aria-hidden="true">↑</span>
            <span className="session-change-copy">
              <strong>{view.topic}</strong>
              <small>
                {view.masteryBefore !== null && view.masteryPercent !== null
                  ? `было ${view.masteryBefore}% → стало ${view.masteryPercent}%`
                  : `тема пройдена на ${view.masteryPercent}%`}
              </small>
              {view.masteryPercent !== null && (
                <span
                  className="session-mastery"
                  aria-hidden="true"
                  style={{ "--from": `${view.masteryBefore ?? 0}%`, "--to": `${view.masteryPercent}%` } as CSSProperties}
                >
                  <span className="session-mastery-fill" />
                </span>
              )}
            </span>
            {view.masteryDelta !== null && view.masteryDelta > 0 && <span className="session-change-delta">+{view.masteryDelta}%</span>}
          </div>
        )}
        {view.toRepeat > 0 && (
          <div className="session-change is-repeat">
            <span className="session-change-icon" aria-hidden="true">!</span>
            <span className="session-change-copy">
              <strong>Над чем ещё поработать</strong>
              <small>{view.toRepeat} {plural(view.toRepeat, ["задание", "задания", "заданий"])} вернём завтра</small>
            </span>
            <span className="session-change-tag">повтор</span>
          </div>
        )}
      </div>

      {view.nextSize !== null && (
        <div className="session-tomorrow">
          <span className="session-tomorrow-icon" aria-hidden="true">→</span>
          <span className="session-tomorrow-copy">
            <strong>Завтра: {view.nextSize} {plural(view.nextSize, ["задание", "задания", "заданий"])}{view.nextTopic ? ` по теме «${view.nextTopic}»` : ""}</strong>
            {view.toRepeat > 0 && <small>плюс разбор вчерашних ошибок</small>}
          </span>
        </div>
      )}

      <button className="primary-button session-complete-home" onClick={onHome} type="button">На главную</button>
      {onReview && (
        <button className="secondary-button session-complete-review" onClick={onReview} type="button">Разбор этой сессии</button>
      )}
    </section>
  );
}
