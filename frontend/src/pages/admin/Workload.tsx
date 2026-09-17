import { Link } from "react-router-dom";

import {
  Card,
  EmptyState,
  LINK_BUTTON,
  ListSkeleton,
  PageHeader,
  SkillTags,
  cx,
} from "../../components/ui";
import { useWorkload } from "../../lib/queries";

export function Workload() {
  const { data, isPending, isError } = useWorkload();

  if (isPending) return <ListSkeleton rows={3} />;
  if (isError) return <EmptyState title="We couldn't load the workload" />;

  const busiest = Math.max(1, ...data!.map((m) => m.active));

  return (
    <>
      <PageHeader
        title="Workload"
        description="Tickets per moderator. New tickets go to the best skill match, then the least busy person."
      />

      {data!.length === 0 ? (
        <EmptyState
          title="No moderators yet"
          description="Add moderators and give them skills so tickets can be assigned automatically."
          action={
            <Link to="/admin/users" className={LINK_BUTTON}>
              Add a moderator
            </Link>
          }
        />
      ) : (
        <div className="stagger space-y-3">
          {data!.map((m) => (
            <Card key={m.id} hover className={cx("p-5", !m.is_active && "opacity-70")}>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-medium text-ink-900">
                    {m.full_name}
                    {!m.is_active && (
                      <span className="ml-2 rounded-full bg-ink-100 px-2 py-0.5 text-[12px] text-ink-500">
                        Disabled
                      </span>
                    )}
                  </p>
                  <p className="truncate text-[13px] text-ink-500">{m.email}</p>
                  <div className="mt-2">
                    {m.skills.length ? (
                      <SkillTags skills={m.skills} />
                    ) : (
                      <Link
                        to="/admin/users"
                        className="text-[12.5px] text-amber-700 hover:underline dark:text-amber-300"
                      >
                        No skills set — tickets can't match them
                      </Link>
                    )}
                  </div>
                </div>

                <dl className="flex gap-2">
                  {[
                    ["Active", m.active],
                    ["Resolved", m.resolved],
                    ["Closed", m.closed],
                    ["Total", m.total],
                  ].map(([label, value]) => (
                    <div
                      key={label as string}
                      className="glass-well min-w-16 rounded-xl px-3 py-2 text-center"
                    >
                      <dd className="text-[17px] font-semibold text-ink-900">{value}</dd>
                      <dt className="text-[11.5px] text-ink-500">{label}</dt>
                    </div>
                  ))}
                </dl>
              </div>

              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-ink-200/60">
                <div
                  className="h-full rounded-full bg-linear-to-r from-accent-400 to-accent-600 transition-[width] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
                  style={{ width: `${Math.max((m.active / busiest) * 100, 2)}%` }}
                />
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
