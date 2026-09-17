import type { ReactNode } from "react";

import { useTheme } from "../lib/theme";
import type { ThemePreference } from "../lib/theme";
import { cx } from "./ui";

const OPTIONS: { value: ThemePreference; label: string; icon: ReactNode }[] = [
  {
    value: "light",
    label: "Light",
    icon: (
      <>
        <circle cx="8" cy="8" r="3.1" />
        <path d="M8 1.3v1.6M8 13.1v1.6M1.3 8h1.6M13.1 8h1.6M3.3 3.3l1.1 1.1M11.6 11.6l1.1 1.1M12.7 3.3l-1.1 1.1M4.4 11.6l-1.1 1.1" />
      </>
    ),
  },
  {
    value: "system",
    label: "System",
    icon: (
      <>
        <rect x="1.8" y="2.6" width="12.4" height="8.4" rx="1.4" />
        <path d="M5.6 13.4h4.8" />
      </>
    ),
  },
  {
    value: "dark",
    label: "Dark",
    icon: <path d="M13.2 9.6A5.6 5.6 0 0 1 6.4 2.8a5.8 5.8 0 1 0 6.8 6.8Z" />,
  },
];

/** Three-way switch: light, follow the system, or dark. */
export function ThemeToggle({ className }: { className?: string }) {
  const { preference, setPreference } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className={cx(
        "inline-flex items-center gap-0.5 rounded-xl border border-line bg-field p-0.5 backdrop-blur-sm",
        className,
      )}
    >
      {OPTIONS.map((option) => {
        const active = preference === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={option.label}
            title={option.label}
            onClick={() => setPreference(option.value)}
            className={cx(
              "grid size-7 place-items-center rounded-[0.6rem] transition-all duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]",
              active
                ? "bg-surface-hover text-accent-600 shadow-(--shadow-glass)"
                : "text-ink-500 hover:text-ink-800",
            )}
          >
            <svg
              viewBox="0 0 16 16"
              aria-hidden
              className="size-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.3"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {option.icon}
            </svg>
          </button>
        );
      })}
    </div>
  );
}
