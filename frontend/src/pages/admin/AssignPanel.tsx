import { useState } from "react";

import { Button, Card, ErrorNote, Select } from "../../components/ui";
import { ApiError } from "../../lib/api";
import { useAssignTicket, useWorkload } from "../../lib/queries";
import type { Ticket } from "../../lib/types";

/** Admin-only: assign or reassign, with each moderator's current load shown. */
export function AssignPanel({ ticket }: { ticket: Ticket }) {
  const { data: moderators, isPending } = useWorkload();
  const assign = useAssignTicket();
  const [choice, setChoice] = useState("");
  const [error, setError] = useState("");

  const closed = ticket.status === "resolved" || ticket.status === "closed";

  return (
    <Card className="p-5">
      <h2 className="mb-1 text-[13px] font-semibold text-ink-900">
        {ticket.assignee ? "Reassign" : "Assign"} this ticket
      </h2>
      <p className="mb-3 text-[12.5px] text-ink-500">
        {closed
          ? "A resolved or closed ticket can't be reassigned."
          : "Matching skills are handled automatically; use this to override."}
      </p>

      <div className="space-y-2">
        <Select
          value={choice}
          disabled={closed || isPending}
          onChange={(e) => setChoice(e.target.value)}
          aria-label="Choose a moderator"
        >
          <option value="">Choose a moderator…</option>
          {moderators
            ?.filter((m) => m.is_active)
            .map((m) => (
              <option key={m.id} value={m.id}>
                {m.full_name} — {m.active} active
                {m.skills.length ? ` · ${m.skills.slice(0, 3).join(", ")}` : ""}
              </option>
            ))}
        </Select>
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button
          size="sm"
          className="w-full"
          disabled={!choice || closed}
          loading={assign.isPending}
          onClick={async () => {
            setError("");
            try {
              await assign.mutateAsync({ ticketId: ticket.id, moderatorId: choice });
              setChoice("");
            } catch (err) {
              setError(err instanceof ApiError ? err.message : "That assignment didn't work.");
            }
          }}
        >
          {ticket.assignee ? "Reassign" : "Assign"}
        </Button>
      </div>
    </Card>
  );
}
