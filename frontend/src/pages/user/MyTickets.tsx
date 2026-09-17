import { useState } from "react";
import { Link } from "react-router-dom";

import { EMPTY_FILTERS, TicketFilterBar, TicketListView } from "../../components/TicketList";
import type { Filters } from "../../components/TicketList";
import { EmptyState, LINK_BUTTON, PageHeader } from "../../components/ui";
import { useMyTickets } from "../../lib/queries";
import type { TicketStatus } from "../../lib/types";

const OPEN_STATUSES: TicketStatus[] = [
  "open",
  "pending_review",
  "assigned",
  "in_progress",
  "resolved",
];

export function MyTickets({ scope }: { scope: "open" | "history" }) {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const query = useMyTickets(scope, filters);

  return (
    <>
      <PageHeader
        title={scope === "open" ? "Your tickets" : "History"}
        description={
          scope === "open"
            ? "Tickets you've raised that are still being handled."
            : "Tickets you've closed."
        }
        actions={
          scope === "open" ? (
            <Link to="/tickets/new" className={LINK_BUTTON}>
              New ticket
            </Link>
          ) : undefined
        }
      />
      <TicketFilterBar
        filters={filters}
        onChange={setFilters}
        statuses={scope === "open" ? OPEN_STATUSES : ["closed"]}
      />
      <TicketListView
        query={query}
        filters={filters}
        onFilters={setFilters}
        empty={
          scope === "open" ? (
            <EmptyState
              title="No open tickets"
              description="When you raise a ticket, it appears here while our team works on it."
              action={
                <Link to="/tickets/new" className={LINK_BUTTON}>
                  Create a ticket
                </Link>
              }
            />
          ) : (
            <EmptyState
              title="Nothing here yet"
              description="Closed tickets are kept here for your records."
            />
          )
        }
      />
    </>
  );
}
