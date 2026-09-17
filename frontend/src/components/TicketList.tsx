import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { Page, Ticket, TicketStatus } from "../lib/types";
import { STATUS_LABELS } from "../lib/types";
import {
  Button,
  Card,
  EmptyState,
  Input,
  ListSkeleton,
  Pagination,
  PriorityTag,
  Select,
  StatusBadge,
  relativeDate,
} from "./ui";

export interface Filters {
  q: string;
  status: TicketStatus[];
  date_from: string;
  date_to: string;
  page: number;
}

export const EMPTY_FILTERS: Filters = {
  q: "",
  status: [],
  date_from: "",
  date_to: "",
  page: 1,
};

export function TicketFilterBar({
  filters,
  onChange,
  statuses,
  children,
}: {
  filters: Filters;
  onChange: (next: Filters) => void;
  statuses: TicketStatus[];
  children?: ReactNode;
}) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch, page: 1 });
  const active = Boolean(
    filters.q || filters.status.length || filters.date_from || filters.date_to,
  );

  return (
    <Card className="animate-rise mb-5 p-3">
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="min-w-52 flex-1">
          <Input
            type="search"
            value={filters.q}
            onChange={(e) => set({ q: e.target.value })}
            placeholder="Search by title…"
            aria-label="Search tickets by title"
          />
        </div>
        <div className="w-40">
          <Select
            aria-label="Filter by status"
            value={filters.status[0] ?? ""}
            onChange={(e) =>
              set({
                status: e.target.value ? [e.target.value as TicketStatus] : [],
              })
            }
          >
            <option value="">Any status</option>
            {statuses.map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status]}
              </option>
            ))}
          </Select>
        </div>
        <DateField
          label="From"
          value={filters.date_from}
          onChange={(value) => set({ date_from: value })}
        />
        <DateField
          label="To"
          value={filters.date_to}
          onChange={(value) => set({ date_to: value })}
        />
        {children}
        {active && (
          <Button variant="ghost" size="sm" onClick={() => onChange(EMPTY_FILTERS)}>
            Clear
          </Button>
        )}
      </div>
    </Card>
  );
}

/** A date input with its "From" / "To" label inline, so it's obvious which is which. */
function DateField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const id = `date-${label.toLowerCase()}`;
  return (
    <div className="flex items-center gap-2 rounded-xl border border-line bg-field pl-3 backdrop-blur-sm">
      <label htmlFor={id} className="text-[12.5px] font-medium text-ink-500">
        {label}
      </label>
      <input
        id={id}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-33 rounded-xl border-0 bg-transparent py-2.5 pr-3 text-sm text-ink-900 focus:outline-none"
      />
    </div>
  );
}

export function TicketRow({ ticket, showOwner }: { ticket: Ticket; showOwner?: boolean }) {
  return (
    <Card hover>
      <Link to={`/tickets/${ticket.id}`} className="block p-5">
        <div className="flex items-start justify-between gap-4">
          <p className="truncate text-[15px] font-medium text-ink-900">{ticket.title}</p>
          <StatusBadge status={ticket.status} />
        </div>
        <p className="mt-1.5 line-clamp-1 text-[13px] text-ink-500">{ticket.description}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12.5px] text-ink-500">
          <span>{relativeDate(ticket.created_at)}</span>
          {ticket.category && (
            <>
              <Dot />
              <span className="capitalize">{ticket.category}</span>
            </>
          )}
          {ticket.priority && (
            <>
              <Dot />
              <PriorityTag priority={ticket.priority} />
            </>
          )}
          {showOwner && (
            <>
              <Dot />
              <span>from {ticket.created_by.full_name}</span>
            </>
          )}
          <Dot />
          {ticket.assignee ? (
            <span>assigned to {ticket.assignee.full_name}</span>
          ) : (
            <span className="text-amber-600 dark:text-amber-300">unassigned</span>
          )}
        </div>
      </Link>
    </Card>
  );
}

function Dot() {
  return <span aria-hidden className="size-0.5 rounded-full bg-ink-300" />;
}

export function TicketListView({
  query,
  filters,
  onFilters,
  empty,
  showOwner,
}: {
  query: { data?: Page<Ticket>; isPending: boolean; isError: boolean };
  filters: Filters;
  onFilters: (next: Filters) => void;
  empty: ReactNode;
  showOwner?: boolean;
}) {
  if (query.isPending) return <ListSkeleton />;
  if (query.isError)
    return <EmptyState title="We couldn't load these tickets" description="Please try again." />;

  const page = query.data!;
  if (page.total === 0) return <>{empty}</>;

  return (
    <>
      <div className="stagger space-y-3">
        {page.items.map((ticket) => (
          <TicketRow key={ticket.id} ticket={ticket} showOwner={showOwner} />
        ))}
      </div>
      <Pagination
        page={page.page}
        pages={page.pages}
        total={page.total}
        onChange={(next) => onFilters({ ...filters, page: next })}
      />
    </>
  );
}
