import { useState } from "react";

import { EMPTY_FILTERS, TicketFilterBar, TicketListView } from "../../components/TicketList";
import type { Filters } from "../../components/TicketList";
import { Button, EmptyState, PageHeader } from "../../components/ui";
import { useAdminTickets } from "../../lib/queries";
import type { TicketStatus } from "../../lib/types";

const ALL_STATUSES: TicketStatus[] = [
  "open",
  "pending_review",
  "assigned",
  "in_progress",
  "resolved",
  "closed",
];

export function AdminTickets() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [unassigned, setUnassigned] = useState(false);
  const query = useAdminTickets({ ...filters, unassigned: unassigned || undefined });

  const pendingOnly = filters.status.length === 1 && filters.status[0] === "pending_review";

  return (
    <>
      <PageHeader
        title="All tickets"
        description="Every ticket in the system, with search and filters."
        actions={
          <Button
            variant={pendingOnly ? "primary" : "secondary"}
            size="sm"
            onClick={() =>
              setFilters({ ...filters, status: pendingOnly ? [] : ["pending_review"], page: 1 })
            }
          >
            {pendingOnly ? "Showing pending review" : "Pending review queue"}
          </Button>
        }
      />
      <TicketFilterBar filters={filters} onChange={setFilters} statuses={ALL_STATUSES}>
        <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-line bg-field px-3 py-2.5 text-[13px] text-ink-600 backdrop-blur-sm transition-colors hover:bg-surface">
          <input
            type="checkbox"
            checked={unassigned}
            onChange={(e) => {
              setUnassigned(e.target.checked);
              setFilters({ ...filters, page: 1 });
            }}
            className="size-3.5 accent-accent-600"
          />
          Unassigned only
        </label>
      </TicketFilterBar>
      <TicketListView
        query={query}
        filters={filters}
        onFilters={setFilters}
        showOwner
        empty={
          <EmptyState
            title="No tickets match"
            description="Try clearing the filters or searching for something else."
          />
        }
      />
    </>
  );
}
