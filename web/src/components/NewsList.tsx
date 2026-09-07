import type { NewsEvent } from "../api";

export function NewsList({ events }: { events: NewsEvent[] }) {
  if (events.length === 0) {
    return <p className="empty">No tagged headlines in this window.</p>;
  }
  return (
    <ul className="news">
      {events.map((event) => (
        <li key={event.id}>
          <a href={event.url} target="_blank" rel="noreferrer noopener">
            {event.title}
          </a>
          <span className="news__meta">
            {event.feed} &middot; {new Date(event.published_at).toLocaleString()}
          </span>
        </li>
      ))}
    </ul>
  );
}
