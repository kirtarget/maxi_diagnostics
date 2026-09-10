import type { TopicPathNode, TopicPathResponse } from "./types";
import { topicMasteryPercent } from "./today-path-model";

export type TopicPathScreenProps = {
  path: TopicPathResponse;
};

function PathNode({ node }: { node: TopicPathNode }) {
  const marker = node.status === "done" ? "✓" : node.status === "current" ? "▶" : "🔒";
  const caption = node.status === "done"
    ? `Пройдено · ${node.mastered}/${node.total}`
    : node.status === "current"
      ? `Сейчас здесь · ${node.mastered}/${node.total}`
      : node.index === 0 ? "Дальше по пути" : "Откроется после предыдущей темы";
  return (
    <li className={`path-node is-${node.status}`}>
      <span className="path-node-rail" aria-hidden="true">
        <span className="path-node-badge">{marker}</span>
      </span>
      <div className="path-node-body">
        <strong className="path-node-topic">{node.topic}</strong>
        <small className="path-node-caption">{caption}</small>
        {node.status === "current" && node.total > 0 && (
          <span className="path-node-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={topicMasteryPercent(node.mastered, node.total)}>
            <span style={{ width: `${topicMasteryPercent(node.mastered, node.total)}%` }} />
          </span>
        )}
      </div>
    </li>
  );
}

/** Visual-only weekly checkpoint marker. The checkpoint mechanic ships in a later package. */
function CheckpointNode() {
  return (
    <li className="path-node path-checkpoint">
      <span className="path-node-rail" aria-hidden="true">
        <span className="path-node-badge">◆</span>
      </span>
      <div className="path-node-body">
        <strong className="path-node-topic">Чекпоинт недели</strong>
        <small className="path-node-caption">Короткая диагностика закрывает блок</small>
        <span className="path-checkpoint-tag">Раз в неделю</span>
      </div>
    </li>
  );
}

export function TopicPathScreen({ path }: TopicPathScreenProps) {
  const currentIndex = path.topics.findIndex((node) => node.status === "current");
  const checkpointAfter = currentIndex >= 0
    ? currentIndex
    : path.topics.reduce((last, node, index) => (node.status === "done" ? index : last), -1);
  return (
    <section className="screen path-screen" aria-labelledby="path-title">
      <span className="today-eyebrow">{path.subject} · {path.exam}</span>
      <h1 id="path-title">Твой путь</h1>
      <p className="path-lead">Темы кодификатора ФИПИ. Каждая открывается, когда закрыта предыдущая. Пройдено {path.done_count} из {path.total_count}.</p>
      <ol className="path-list">
        {path.topics.map((node, index) => (
          <PathNode key={node.topic} node={node} />
        )).flatMap((element, index) => index === checkpointAfter ? [element, <CheckpointNode key="checkpoint" />] : [element])}
      </ol>
    </section>
  );
}
