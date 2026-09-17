import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { Markdown } from "../../components/Markdown";
import {
  Button,
  Card,
  EmptyState,
  ErrorNote,
  InfoNote,
  PriorityTag,
  Skeleton,
  SkillTags,
  StatusBadge,
  Textarea,
  cx,
  formatDate,
  relativeDate,
} from "../../components/ui";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useAddComment, useChangeStatus, useTicket } from "../../lib/queries";
import type { TicketDetail as Detail, TicketStatus } from "../../lib/types";
import { AssignPanel } from "../admin/AssignPanel";

/** Which status button (if any) this person can press next. */
function nextAction(
  ticket: Detail,
  userId: string,
  role: string,
): { status: TicketStatus; label: string } | null {
  const isAssignee = ticket.assignee?.id === userId;
  const isAdmin = role === "admin";
  const isOwner = ticket.created_by.id === userId;

  if (ticket.status === "assigned" && (isAssignee || isAdmin))
    return { status: "in_progress", label: "Start working on it" };
  if (ticket.status === "in_progress" && (isAssignee || isAdmin))
    return { status: "resolved", label: "Mark as resolved" };
  if (ticket.status === "resolved" && (isOwner || isAdmin))
    return { status: "closed", label: "Close this ticket" };
  return null;
}

function Timeline({ ticket }: { ticket: Detail }) {
  const rows: [string, string | null][] = [
    ["Created", ticket.created_at],
    ["Assigned", ticket.assigned_at],
    ["Resolved", ticket.resolved_at],
    ["Closed", ticket.closed_at],
  ];
  const done = rows.filter(([, value]) => value);

  return (
    <ol className="space-y-3.5">
      {done.map(([label, value], index) => (
        <li key={label} className="relative flex gap-3 pl-0.5">
          {index < done.length - 1 && (
            <span
              aria-hidden
              className="absolute left-0.75 top-3.5 h-[calc(100%+0.4rem)] w-px bg-ink-200"
            />
          )}
          <span
            aria-hidden
            className={cx(
              "mt-1.5 size-1.5 shrink-0 rounded-full",
              index === done.length - 1 ? "bg-accent-500 ring-4 ring-accent-100/70" : "bg-ink-300",
            )}
          />
          <div className="flex min-w-0 flex-1 flex-wrap justify-between gap-x-3 text-[12.5px]">
            <span className="text-ink-600">{label}</span>
            <span className="text-ink-500">{formatDate(value)}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}

function SectionTitle({ children, aside }: { children: string; aside?: string | null }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-400">
        {children}
      </h2>
      {aside && <span className="text-[11.5px] text-ink-400">{aside}</span>}
    </div>
  );
}

export function TicketDetail() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const { data: ticket, isPending, isError, error } = useTicket(id);
  const changeStatus = useChangeStatus(id ?? "");
  const addComment = useAddComment(id ?? "");
  const [comment, setComment] = useState("");
  const [actionError, setActionError] = useState("");

  if (isPending) {
    return (
      <div className="grid gap-5 lg:grid-cols-[1fr_19rem]">
        <div className="space-y-4">
          <Skeleton className="h-7 w-2/3" />
          <Card className="p-6">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="mt-2.5 h-3 w-4/5" />
          </Card>
          <Card className="p-6">
            <Skeleton className="h-3 w-1/3" />
            <Skeleton className="mt-3 h-24 w-full" />
          </Card>
        </div>
        <Card className="h-40 p-6">
          <Skeleton className="h-3 w-1/2" />
        </Card>
      </div>
    );
  }

  if (isError || !ticket) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <EmptyState
        title={notFound ? "Ticket not found" : "We couldn't load this ticket"}
        description={
          notFound
            ? "It may have been removed, or you don't have access to it."
            : "Please try again."
        }
        action={
          <Link to="/tickets" className="text-[13px] font-medium text-accent-600 hover:underline">
            Back to your tickets
          </Link>
        }
      />
    );
  }

  const action = user ? nextAction(ticket, user.id, user.role) : null;
  const isStaff = user?.role === "admin" || ticket.assignee?.id === user?.id;
  const canComment = ticket.status !== "closed" || isStaff;

  async function submitComment(event: FormEvent) {
    event.preventDefault();
    if (!comment.trim()) return;
    setActionError("");
    try {
      await addComment.mutateAsync(comment.trim());
      setComment("");
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Your message wasn't sent.");
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_19rem]">
      <div className="min-w-0 space-y-4">
        <div className="animate-rise">
          <Link
            to="/tickets"
            className="inline-flex items-center gap-1 text-[13px] text-ink-500 transition-colors hover:text-ink-800"
          >
            <span aria-hidden>←</span> Back
          </Link>
          <div className="mt-2.5 flex flex-wrap items-start justify-between gap-3">
            <h1 className="text-[22px] font-semibold leading-tight text-ink-900">{ticket.title}</h1>
            <StatusBadge status={ticket.status} />
          </div>
          <p className="mt-1.5 text-[12.5px] text-ink-500">
            Raised by {ticket.created_by.full_name} · {relativeDate(ticket.created_at)}
          </p>
        </div>

        <Card className="animate-rise p-6">
          <p className="whitespace-pre-wrap text-[14.5px] leading-relaxed text-ink-700">
            {ticket.description}
          </p>
        </Card>

        {ticket.status === "open" && (
          <InfoNote>
            <span className="inline-flex items-center gap-2">
              <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-accent-500" />
              Our AI is reviewing this ticket and finding the best moderator…
            </span>
          </InfoNote>
        )}
        {ticket.status === "pending_review" && (
          <InfoNote>
            This ticket is waiting for an admin to assign it by hand. You'll be emailed when it
            moves.
          </InfoNote>
        )}

        {ticket.ai_notes && (
          <Card className="animate-rise p-6">
            <SectionTitle aside={ticket.ai_model_used}>AI notes for the moderator</SectionTitle>
            <div className="glass-well rounded-xl p-4 text-ink-700">
              <Markdown>{ticket.ai_notes}</Markdown>
            </div>
          </Card>
        )}

        <Card className="animate-rise p-6">
          <SectionTitle>
            {ticket.comments.length > 0 ? `Messages (${ticket.comments.length})` : "Messages"}
          </SectionTitle>

          {ticket.comments.length === 0 ? (
            <p className="text-[13px] text-ink-500">No messages yet.</p>
          ) : (
            <ul className="space-y-2.5">
              {ticket.comments.map((c) => (
                <li key={c.id} className="glass-well rounded-xl p-4">
                  <div className="flex items-center justify-between gap-2 text-[12.5px]">
                    <span className="flex items-center gap-2 font-medium text-ink-800">
                      {c.author?.full_name ?? "Removed user"}
                      {c.author && c.author.role !== "user" && (
                        <span className="rounded-md bg-accent-50 px-1.5 py-0.5 text-[11px] capitalize text-accent-700 ring-1 ring-accent-100">
                          {c.author.role}
                        </span>
                      )}
                    </span>
                    <span className="text-ink-400">{relativeDate(c.created_at)}</span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink-700">
                    {c.body}
                  </p>
                </li>
              ))}
            </ul>
          )}

          {canComment ? (
            <form onSubmit={submitComment} className="mt-4 space-y-2.5">
              <Textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
                maxLength={5000}
                placeholder="Add a message…"
                aria-label="Add a message"
              />
              {actionError && <ErrorNote>{actionError}</ErrorNote>}
              <Button
                type="submit"
                size="sm"
                loading={addComment.isPending}
                disabled={!comment.trim()}
              >
                Send message
              </Button>
            </form>
          ) : (
            <p className="mt-4 text-[13px] text-ink-500">This ticket is closed.</p>
          )}
        </Card>
      </div>

      <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
        {action && (
          <Card className="animate-rise p-4">
            <Button
              className="w-full"
              loading={changeStatus.isPending}
              onClick={async () => {
                setActionError("");
                try {
                  await changeStatus.mutateAsync(action.status);
                } catch (err) {
                  setActionError(
                    err instanceof ApiError ? err.message : "That change didn't go through.",
                  );
                }
              }}
            >
              {action.label}
            </Button>
            {actionError && (
              <div className="mt-2.5">
                <ErrorNote>{actionError}</ErrorNote>
              </div>
            )}
          </Card>
        )}

        <Card className="animate-rise p-5">
          <SectionTitle>Details</SectionTitle>
          <dl className="space-y-2.5 text-[13px]">
            <div className="flex justify-between gap-3">
              <dt className="text-ink-500">Assigned to</dt>
              <dd className="text-right font-medium text-ink-800">
                {ticket.assignee?.full_name ?? (
                  <span className="font-normal text-amber-600 dark:text-amber-300">Nobody yet</span>
                )}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-500">Category</dt>
              <dd className="capitalize text-ink-800">{ticket.category ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-500">Priority</dt>
              <dd className="text-[13px]">
                {ticket.priority ? <PriorityTag priority={ticket.priority} /> : "—"}
              </dd>
            </div>
          </dl>
          {ticket.required_skills.length > 0 && (
            <div className="mt-4 border-t border-line pt-4">
              <p className="mb-2 text-[12.5px] text-ink-500">Skills needed</p>
              <SkillTags skills={ticket.required_skills} />
            </div>
          )}
        </Card>

        <Card className="animate-rise p-5">
          <SectionTitle>Timeline</SectionTitle>
          <Timeline ticket={ticket} />
        </Card>

        {user?.role === "admin" && <AssignPanel ticket={ticket} />}
      </aside>
    </div>
  );
}
