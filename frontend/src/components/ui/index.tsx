import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

import type { Priority, TicketStatus } from "../../lib/types";
import { STATUS_LABELS } from "../../lib/types";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/* --- Button ---------------------------------------------------------------
   Primary carries the one gradient in the system; the rest are glass or quiet. */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
};

const BUTTON_VARIANTS = {
  primary:
    "bg-linear-to-b from-accent-500 to-accent-600 text-white shadow-(--shadow-accent) hover:from-accent-400 hover:to-accent-500 active:from-accent-600 active:to-accent-700 disabled:from-accent-400/50 disabled:to-accent-500/50 disabled:shadow-none",
  secondary:
    "bg-surface text-ink-800 ring-1 ring-line shadow-(--shadow-glass) backdrop-blur-md hover:bg-surface-hover hover:text-ink-900 disabled:text-ink-400",
  ghost: "text-ink-600 hover:bg-surface hover:text-ink-900 disabled:text-ink-400",
  danger:
    "bg-surface text-rose-600 ring-1 ring-rose-200/80 backdrop-blur-md hover:bg-rose-50/90 hover:text-rose-700 dark:text-rose-400 dark:ring-rose-400/30 dark:hover:bg-rose-500/15 dark:hover:text-rose-300",
};

export function Button({
  variant = "primary",
  size = "md",
  loading,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]",
        "active:translate-y-px disabled:cursor-not-allowed disabled:active:translate-y-0",
        size === "sm" ? "px-3 py-1.5 text-[13px]" : "px-4 py-2.5 text-sm",
        BUTTON_VARIANTS[variant],
        className,
      )}
    >
      {loading && (
        <span
          aria-hidden
          className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}

/** A link that reads as the primary button. */
export const LINK_BUTTON =
  "inline-flex items-center justify-center gap-2 rounded-xl bg-linear-to-b from-accent-500 to-accent-600 px-4 py-2.5 text-sm font-medium text-white shadow-(--shadow-accent) transition-all duration-200 hover:from-accent-400 hover:to-accent-500 active:translate-y-px";

/* --- Form fields --- */

export function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[13px] font-medium text-ink-700">
      {children}
    </label>
  );
}

const FIELD = cx(
  "w-full rounded-xl border border-line bg-field px-3.5 py-2.5 text-sm text-ink-900 shadow-[inset_0_1px_2px_rgb(23_29_43_/_0.04)] backdrop-blur-sm",
  "placeholder:text-ink-400 transition-all duration-200",
  "hover:bg-field-hover focus:border-accent-400 focus:bg-surface-hover focus:shadow-[0_0_0_4px_rgb(79_111_229_/_0.12)] focus:outline-none",
  "disabled:bg-ink-100/60 disabled:text-ink-400",
);

export function Field({
  label,
  error,
  hint,
  children,
  id,
}: {
  label?: string;
  error?: string;
  hint?: string;
  children: ReactNode;
  id?: string;
}) {
  return (
    <div>
      {label && <Label htmlFor={id}>{label}</Label>}
      {children}
      {error ? (
        <p className="mt-1.5 text-[12.5px] text-rose-600">{error}</p>
      ) : hint ? (
        <p className="mt-1.5 text-[12.5px] text-ink-500">{hint}</p>
      ) : null}
    </div>
  );
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={cx(FIELD, className)} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={cx(FIELD, "min-h-28 resize-y", className)} />;
}

export function Select({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...rest} className={cx(FIELD, "cursor-pointer pr-9", className)} />;
}

/* --- Surfaces --- */

export function Card({
  className,
  children,
  hover,
}: {
  className?: string;
  children: ReactNode;
  hover?: boolean;
}) {
  return (
    <div
      className={cx(
        "glass glass-edge rounded-2xl",
        hover &&
          "transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-0.5 hover:bg-surface-hover hover:shadow-(--shadow-raised)",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="animate-rise mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[22px] font-semibold text-ink-900">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-[13.5px] text-ink-500">{description}</p>}
      </div>
      {actions}
    </header>
  );
}

/* --- Status and priority --- */

const STATUS_STYLES: Record<TicketStatus, string> = {
  open: "bg-ink-100/80 text-ink-600 ring-ink-200/70",
  pending_review:
    "bg-amber-50/90 text-amber-700 ring-amber-200/70 dark:bg-amber-400/12 dark:text-amber-300 dark:ring-amber-300/25",
  assigned: "bg-accent-50 text-accent-700 ring-accent-200",
  in_progress:
    "bg-violet-50/90 text-violet-700 ring-violet-200/70 dark:bg-violet-400/14 dark:text-violet-300 dark:ring-violet-300/25",
  resolved:
    "bg-emerald-50/90 text-emerald-700 ring-emerald-200/70 dark:bg-emerald-400/14 dark:text-emerald-300 dark:ring-emerald-300/25",
  closed: "bg-ink-100/70 text-ink-500 ring-ink-200/60",
};

const STATUS_DOTS: Record<TicketStatus, string> = {
  open: "bg-ink-400",
  pending_review: "bg-amber-500",
  assigned: "bg-accent-500",
  in_progress: "bg-violet-500",
  resolved: "bg-emerald-500",
  closed: "bg-ink-400",
};

export function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium ring-1 ring-inset backdrop-blur-sm",
        STATUS_STYLES[status],
      )}
    >
      <span className={cx("size-1.5 rounded-full", STATUS_DOTS[status])} aria-hidden />
      {STATUS_LABELS[status]}
    </span>
  );
}

const PRIORITY_STYLES: Record<Priority, string> = {
  low: "text-ink-500",
  medium: "text-ink-600",
  high: "text-orange-600 dark:text-orange-300",
  urgent: "text-rose-600 dark:text-rose-300",
};

export function PriorityTag({ priority }: { priority: Priority | null }) {
  if (!priority) return null;
  return (
    <span className={cx("font-medium capitalize", PRIORITY_STYLES[priority])}>
      {priority} priority
    </span>
  );
}

export function SkillTags({ skills }: { skills: string[] }) {
  if (!skills.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {skills.map((skill) => (
        <span
          key={skill}
          className="rounded-lg border border-line bg-field px-2 py-0.5 text-[12px] text-ink-600 backdrop-blur-sm"
        >
          {skill}
        </span>
      ))}
    </div>
  );
}

/* --- States --- */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("shimmer rounded-lg bg-ink-200/70", className)} />;
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Card key={i} className="p-5">
          <div className="flex items-center justify-between gap-4">
            <Skeleton className="h-4 w-2/5" />
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
          <Skeleton className="mt-3.5 h-3 w-3/5" />
          <Skeleton className="mt-2.5 h-3 w-1/4" />
        </Card>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <Card className="animate-rise px-6 py-14 text-center">
      <div
        aria-hidden
        className="mx-auto mb-4 grid size-11 place-items-center rounded-2xl bg-accent-50 ring-1 ring-line"
      >
        <span className="size-2.5 rounded-full bg-accent-400/70" />
      </div>
      <p className="text-[15px] font-medium text-ink-900">{title}</p>
      {description && (
        <p className="mx-auto mt-1.5 max-w-sm text-[13.5px] text-ink-500">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </Card>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <div
      role="alert"
      className="animate-fade rounded-xl border border-rose-200/70 bg-rose-50/80 px-3.5 py-2.5 text-[13px] text-rose-700 backdrop-blur-sm dark:border-rose-400/25 dark:bg-rose-500/12 dark:text-rose-200"
    >
      {children}
    </div>
  );
}

export function InfoNote({ children }: { children: ReactNode }) {
  return (
    <div className="animate-fade rounded-xl border border-accent-200 bg-accent-50 px-3.5 py-2.5 text-[13px] text-accent-700 backdrop-blur-sm">
      {children}
    </div>
  );
}

/* --- Pagination --- */

export function Pagination({
  page,
  pages,
  total,
  onChange,
  noun = "ticket",
}: {
  page: number;
  pages: number;
  total: number;
  onChange: (page: number) => void;
  noun?: string;
}) {
  if (total === 0) return null;
  return (
    <div className="mt-4 flex items-center justify-between gap-3">
      <p className="text-[12.5px] text-ink-500">
        Page {page} of {Math.max(pages, 1)} · {total} {total === 1 ? noun : `${noun}s`}
      </p>
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="secondary"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          Previous
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}

/* --- Dates --- */

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function relativeDate(value: string): string {
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(value);
}
