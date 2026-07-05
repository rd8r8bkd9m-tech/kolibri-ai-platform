import { EventStream } from "../components/EventStream";
import type { EventRow } from "../api/types";

const EMPTY: EventRow[] = [];

export function EventsPage() {
  return (
    <section>
      <h2>Events</h2>
      <EventStream events={EMPTY} />
    </section>
  );
}
