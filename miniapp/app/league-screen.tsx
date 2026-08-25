"use client";

import type { LeagueResponse, LeagueRow, LeagueScreenState } from "./league-model";

function rowLabel(row: LeagueRow): string {
  return row.display_label;
}

function LeagueRowView({ row }: { row: LeagueRow }) {
  return (
    <li className={`league-row${row.is_me ? " league-row-me" : ""}`}>
      <span className="league-rank" aria-label={`Место ${row.rank}`}>{row.rank}</span>
      <span className="league-avatar" aria-hidden="true">{rowLabel(row).slice(0, 1).toUpperCase() || "?"}</span>
      <span className="league-label">{rowLabel(row)}{row.is_me ? " · ты" : ""}</span>
      <span className="league-xp">{row.xp_week} XP</span>
    </li>
  );
}

function LeagueReady({ data }: { data: LeagueResponse }) {
  if (data.status === "forming") {
    return (
      <section className="league-screen" aria-labelledby="league-title">
        <header className="league-header">
          <span className="league-trophy" aria-hidden="true">🏆</span>
          <div>
            <p className="eyebrow">Лига недели</p>
            <h1 id="league-title">Лига формируется</h1>
          </div>
        </header>
        <p className="league-empty">Сделай первую тренировку на этой неделе, чтобы попасть в рейтинг.</p>
        <p className="league-dates">{data.week_start} · {data.week_end}</p>
      </section>
    );
  }

  return (
    <section className="league-screen" aria-labelledby="league-title">
      <header className="league-header">
        <span className="league-trophy" aria-hidden="true">🏆</span>
        <div>
          <p className="eyebrow">Лига недели</p>
          <h1 id="league-title">Твой рейтинг</h1>
        </div>
      </header>
      <p className="league-dates">{data.week_start} · {data.week_end}</p>
      {data.rows.length > 0 ? (
        <ol className="league-list">
          {data.rows.map((row, index) => <LeagueRowView key={`${row.rank}-${index}`} row={row} />)}
        </ol>
      ) : (
        <p className="league-empty">Пока никто не набрал XP. Твоя первая тренировка откроет рейтинг.</p>
      )}
      {data.me && !data.rows.some((row) => row.is_me) && (
        <div className="league-me-summary" aria-label="Твоя позиция">
          <span>Твоя позиция</span>
          <strong>{data.me.rank === null ? "—" : `Место ${data.me.rank}`}</strong>
          <b>{data.me.xp_week} XP</b>
        </div>
      )}
    </section>
  );
}

export function LeagueScreen({ state, onRetry, onHome }: { state: LeagueScreenState; onRetry?: () => void; onHome?: () => void }) {
  if (state.kind === "loading") {
    return <section className="league-screen league-state" aria-busy="true"><p>Загружаем рейтинг…</p></section>;
  }
  if (state.kind === "error") {
    return <section className="league-screen league-state" role="alert"><p>{state.message}</p>{onRetry && <button className="primary-button" onClick={onRetry} type="button">Повторить</button>}{onHome && <button className="text-back" onClick={onHome} type="button">На главную</button>}</section>;
  }
  return <>{onHome && <button className="text-back league-back" onClick={onHome} type="button">На главную</button>}<LeagueReady data={state.data} /></>;
}
