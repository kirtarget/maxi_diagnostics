import type { CheckpointNode as CheckpointNodeData, TopicPathNode, TopicPathResponse } from "./types";
import { topicMasteryPercent } from "./today-path-model";
import { checkpointNodeCaption, checkpointNodeMarker } from "./checkpoint-path-model";
import { plural } from "./text-utils";

export type TopicPathScreenProps = {
  path: TopicPathResponse;
  /** Launch the weekly checkpoint for a unit. Only called for an `available` node. */
  onStartCheckpoint?: (unitIndex: number) => void;
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

/** The weekly checkpoint node, rendered from real unit state. Clickable only when available. */
function CheckpointNode({ node, onStart }: { node: CheckpointNodeData; onStart?: (unitIndex: number) => void }) {
  const caption = checkpointNodeCaption(node);
  const marker = checkpointNodeMarker(node.status);
  const body = (
    <>
      <span className="path-node-rail" aria-hidden="true">
        <span className="path-node-badge">{marker}</span>
      </span>
      <div className="path-node-body">
        <strong className="path-node-topic">Чекпоинт недели</strong>
        <small className="path-node-caption">{caption}</small>
        <span className="path-checkpoint-tag">Раз в неделю</span>
      </div>
    </>
  );
  if (node.status === "available" && onStart) {
    return (
      <li className="path-node path-checkpoint is-available">
        <button type="button" className="path-checkpoint-button" onClick={() => onStart(node.unit_index)}>
          {body}
          <span className="path-checkpoint-go" aria-hidden="true">▶</span>
        </button>
      </li>
    );
  }
  return <li className={`path-node path-checkpoint is-${node.status}`}>{body}</li>;
}

export function TopicPathScreen({ path, onStartCheckpoint }: TopicPathScreenProps) {
  // Checkpoints sit after the last topic of their unit, keyed by that path index.
  const checkpointByTopicIndex = new Map<number, CheckpointNodeData>();
  for (const checkpoint of path.checkpoints) {
    checkpointByTopicIndex.set(checkpoint.topic_to, checkpoint);
  }
  return (
    <section className="screen path-screen" aria-labelledby="path-title">
      <span className="today-eyebrow">{path.subject} · {path.exam}</span>
      <h1 id="path-title">Твой путь</h1>
      <p className="path-lead">Темы кодификатора ФИПИ. Каждая открывается, когда закрыта предыдущая. Пройдено {path.done_count} из {path.total_count} {plural(path.total_count, ["темы", "тем", "тем"])}.</p>
      <ol className="path-list">
        {path.topics.flatMap((node) => {
          const checkpoint = checkpointByTopicIndex.get(node.index);
          const topicNode = <PathNode key={node.topic} node={node} />;
          return checkpoint
            ? [topicNode, <CheckpointNode key={`checkpoint-${checkpoint.unit_index}`} node={checkpoint} onStart={onStartCheckpoint} />]
            : [topicNode];
        })}
      </ol>
    </section>
  );
}
