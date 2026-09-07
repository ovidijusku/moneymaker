import type { StreamEvent } from "../api";

const KIND_LABELS: Record<StreamEvent["kind"], string> = {
  news: "News",
  social: "Social",
  advice: "Signal",
};

function relative(timestamp: string): string {
  const minutes = Math.round((Date.now() - Date.parse(timestamp)) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

interface Props {
  events: StreamEvent[];
  selectedId: string | null;
  onSelect: (event: StreamEvent) => void;
}

export function EventStream({ events, selectedId, onSelect }: Props) {
  if (events.length === 0) {
    return <p className="empty">Nothing yet. The worker fills this in as feeds arrive.</p>;
  }

  return (
    <ul className="stream">
      {events.map((event) => (
        <li key={event.id}>
          <button
            type="button"
            className={`stream-item ${event.id === selectedId ? "selected" : ""}`}
            onClick={() => onSelect(event)}
            // Untagged market-wide items have no asset to size, so they are not clickable.
            disabled={event.symbols.length === 0}
          >
            <div className="stream-meta">
              <span className={`kind kind-${event.kind}`}>{KIND_LABELS[event.kind]}</span>
              {event.direction && (
                <span className={`direction ${event.direction}`}>
                  {event.direction.toUpperCase()}
                  {event.conviction !== null && ` ${Math.round(event.conviction * 100)}%`}
                </span>
              )}
              <span className="time">{relative(event.timestamp)}</span>
            </div>
            <div className="stream-title">{event.title}</div>
            {event.summary && event.summary !== event.title && (
              <p className="stream-summary">{event.summary}</p>
            )}
            <div className="stream-tags">
              {event.names.map((name) => (
                <span key={name} className="tag">
                  {name}
                </span>
              ))}
              {event.source && <span className="source">{event.source}</span>}
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}
