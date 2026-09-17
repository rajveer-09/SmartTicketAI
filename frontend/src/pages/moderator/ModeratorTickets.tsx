import { useState } from "react";

import { EMPTY_FILTERS, TicketFilterBar, TicketListView } from "../../components/TicketList";
import type { Filters } from "../../components/TicketList";
import { EmptyState, PageHeader } from "../../components/ui";
import { useModeratorTickets } from "../../lib/queries";
import type { TicketStatus } from "../../lib/types";

const STATUSES: Record<"assigned" | "solved", TicketStatus[]> = {
  assigned: ["assigned", "in_progress"],
  solved: ["resolved", "closed"],
};

export function ModeratorTickets({ scope }: { scope: "assigned" | "solved" }) {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const query = useModeratorTickets(scope, filters);

  return (
    <>
      <PageHeader
        title={scope === "assigned" ? "Assigned to you" : "Solved by you"}
        description={
          scope === "assigned"
            ? "Tickets waiting for you, with AI notes to help you start."
            : "Tickets you've resolved or closed."
        }
      />
      <TicketFilterBar filters={filters} onChange={setFilters} statuses={STATUSES[scope]} />
      <TicketListView
        query={query}
        filters={filters}
        onFilters={setFilters}
        showOwner
        empty={
          <EmptyState
            title={scope === "assigned" ? "Nothing assigned right now" : "Nothing solved yet"}
            description={
              scope === "assigned"
                ? "New tickets that match your skills will land here automatically."
                : "Tickets you resolve will be listed here."
            }
          />
        }
      />
    </>
  );
}
