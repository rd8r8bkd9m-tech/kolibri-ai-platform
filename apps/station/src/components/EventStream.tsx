import type { EventRow } from "../api/types";

export function EventStream({ events }: { events: EventRow[] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>time</th>
          <th>subject</th>
          <th>type</th>
        </tr>
      </thead>
      <tbody>
        {events.map((event) => (
          <tr key={event.id}>
            <td>{event.created_at}</td>
            <td>{event.subject}</td>
            <td>{event.event_type}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
