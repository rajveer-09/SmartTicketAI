import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Brand } from "../../components/layout/AppShell";
import { ThemeToggle } from "../../components/ThemeToggle";
import { Card } from "../../components/ui";

export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen items-center justify-center px-4 py-12">
      <ThemeToggle className="absolute right-4 top-4 sm:right-6 sm:top-6" />
      <div className="animate-rise w-full max-w-100">
        <Link to="/" className="mb-7 flex justify-center">
          <Brand />
        </Link>

        <Card className="p-7">
          <h1 className="text-[19px] font-semibold text-ink-900">{title}</h1>
          {description && <p className="mt-1.5 text-[13.5px] text-ink-500">{description}</p>}
          <div className="mt-6">{children}</div>
        </Card>

        {footer && <p className="mt-5 text-center text-[13px] text-ink-500">{footer}</p>}
      </div>
    </div>
  );
}

export function GoogleButton({ label = "Continue with Google" }: { label?: string }) {
  return (
    <a
      href="/api/auth/google/login"
      className="flex w-full items-center justify-center gap-2.5 rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-medium text-ink-800 shadow-(--shadow-glass) backdrop-blur-md transition-all duration-200 hover:-translate-y-px hover:bg-surface-hover active:translate-y-0"
    >
      <svg aria-hidden viewBox="0 0 24 24" className="size-4.5">
        <path
          fill="#4285F4"
          d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.4a5.5 5.5 0 0 1-2.4 3.6v3h3.9c2.3-2.1 3.6-5.2 3.6-8.8Z"
        />
        <path
          fill="#34A853"
          d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3a7.2 7.2 0 0 1-10.7-3.8h-4v3.1A12 12 0 0 0 12 24Z"
        />
        <path fill="#FBBC05" d="M5.4 14.3a7.2 7.2 0 0 1 0-4.6v-3.1h-4a12 12 0 0 0 0 10.8l4-3.1Z" />
        <path
          fill="#EA4335"
          d="M12 4.8c1.8 0 3.4.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.4 6.6l4 3.1A7.2 7.2 0 0 1 12 4.8Z"
        />
      </svg>
      {label}
    </a>
  );
}

export function Divider() {
  return (
    <div className="my-5 flex items-center gap-3">
      <span className="h-px flex-1 bg-linear-to-r from-transparent to-ink-200" />
      <span className="text-[12px] text-ink-400">or</span>
      <span className="h-px flex-1 bg-linear-to-l from-transparent to-ink-200" />
    </div>
  );
}

/** The boxed code input used by the sign-up and reset flows. */
export const CODE_INPUT = "text-center text-[22px] font-semibold tracking-[0.5em] text-ink-900";
