import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { TicketRow } from "../../components/TicketList";
import { Card, EmptyState, Input, ListSkeleton, PageHeader, SkillTags } from "../../components/ui";
import { useGlobalSearch } from "../../lib/queries";

/** Waits for a pause in typing before searching. */
function useDebounced(value: string, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function AdminSearch() {
  const [term, setTerm] = useState("");
  const debounced = useDebounced(term.trim());
  const { data, isFetching } = useGlobalSearch(debounced);

  const nothing =
    debounced && data && data.tickets.length === 0 && data.users.length === 0 && !isFetching;

  return (
    <>
      <PageHeader title="Search" description="Find any ticket, user or moderator." />

      <Input
        type="search"
        autoFocus
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        placeholder="Search tickets by title, people by name or email…"
        aria-label="Search everything"
        className="mb-6"
      />

      {!debounced && <EmptyState title="Start typing" description="Results appear as you type." />}

      {debounced && isFetching && !data && <ListSkeleton rows={3} />}

      {nothing && (
        <EmptyState title={`Nothing matches "${debounced}"`} description="Try another spelling." />
      )}

      {data && (data.tickets.length > 0 || data.users.length > 0) && (
        <div className="space-y-6">
          {data.tickets.length > 0 && (
            <section>
              <h2 className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-400">
                Tickets
              </h2>
              <div className="stagger space-y-3">
                {data.tickets.map((ticket) => (
                  <TicketRow key={ticket.id} ticket={ticket} showOwner />
                ))}
              </div>
            </section>
          )}

          {data.users.length > 0 && (
            <section>
              <h2 className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-400">
                People
              </h2>
              <div className="stagger space-y-3">
                {data.users.map((user) => (
                  <Card key={user.id} hover className="p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-[14px] font-medium text-ink-900">
                          {user.full_name}
                        </p>
                        <p className="truncate text-[13px] text-ink-500">{user.email}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <SkillTags skills={user.skills} />
                        <span className="rounded-full bg-ink-100 px-2 py-0.5 text-[12px] capitalize text-ink-600">
                          {user.role}
                        </span>
                        <Link
                          to="/admin/users"
                          className="text-[13px] font-medium text-accent-600 hover:underline"
                        >
                          Manage
                        </Link>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </>
  );
}
