import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../../lib/auth";
import { ThemeToggle } from "../ThemeToggle";
import type { Role } from "../../lib/types";
import { Button, cx } from "../ui";

interface NavItem {
  to: string;
  label: string;
  roles: Role[];
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: "/tickets", label: "Your tickets", roles: ["user", "moderator", "admin"], end: true },
  { to: "/tickets/history", label: "History", roles: ["user", "moderator", "admin"] },
  { to: "/tickets/new", label: "Create ticket", roles: ["user", "moderator", "admin"] },
  { to: "/moderator/tickets", label: "Assigned to you", roles: ["moderator", "admin"], end: true },
  { to: "/moderator/solved", label: "Solved", roles: ["moderator", "admin"] },
  { to: "/admin/tickets", label: "All tickets", roles: ["admin"], end: true },
  { to: "/admin/users", label: "Users & moderators", roles: ["admin"] },
  { to: "/admin/workload", label: "Workload", roles: ["admin"] },
  { to: "/admin/search", label: "Search", roles: ["admin"] },
];

const SECTIONS: { title: string; roles: Role[]; prefix: string }[] = [
  { title: "Your account", roles: ["user", "moderator", "admin"], prefix: "/tickets" },
  { title: "Moderation", roles: ["moderator", "admin"], prefix: "/moderator" },
  { title: "Administration", roles: ["admin"], prefix: "/admin" },
];

function initials(name: string) {
  return name
    .split(/\s+/)
    .map((part) => part.replace(/[^\p{L}]/gu, ""))
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

export function Brand({ className }: { className?: string }) {
  return (
    <span className={cx("flex items-center gap-2.5", className)}>
      <span
        aria-hidden
        className="grid size-8 place-items-center rounded-xl bg-linear-to-br from-accent-400 to-accent-600 shadow-(--shadow-accent)"
      >
        <span className="size-2.5 rounded-[4px] bg-white/90" />
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-ink-900">
        SmartTicket<span className="text-accent-600">AI</span>
      </span>
    </span>
  );
}

export function AppShell() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => setMenuOpen(false), [location.pathname]);

  if (!user) return null;
  const role = user.role;

  const nav = (
    <nav className="space-y-7">
      {SECTIONS.filter((s) => s.roles.includes(role)).map((section) => (
        <div key={section.title}>
          <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-400">
            {section.title}
          </p>
          <ul className="space-y-1">
            {NAV.filter((i) => i.to.startsWith(section.prefix) && i.roles.includes(role)).map(
              (item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      cx(
                        "group relative flex items-center rounded-xl px-3 py-2 text-[13.5px] transition-all duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]",
                        isActive
                          ? "bg-surface font-medium text-accent-700 shadow-(--shadow-glass) ring-1 ring-line"
                          : "text-ink-600 hover:bg-field hover:text-ink-900",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <span
                          aria-hidden
                          className={cx(
                            "absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full bg-linear-to-b from-accent-400 to-accent-600 transition-all duration-200",
                            isActive ? "opacity-100" : "opacity-0",
                          )}
                        />
                        {item.label}
                      </>
                    )}
                  </NavLink>
                </li>
              ),
            )}
          </ul>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen">
      <header className="glass-bar sticky top-0 z-30">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
          <button
            className="-ml-1 grid size-9 place-content-center gap-[5px] rounded-xl text-ink-600 transition-colors hover:bg-surface lg:hidden"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label="Toggle navigation"
            aria-expanded={menuOpen}
          >
            <span className="block h-0.5 w-5 rounded-full bg-current" />
            <span className="block h-0.5 w-5 rounded-full bg-current" />
            <span className="block h-0.5 w-3.5 rounded-full bg-current" />
          </button>

          <Brand />

          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle className="hidden sm:inline-flex" />
            <div className="hidden text-right sm:block">
              <p className="text-[13px] font-medium leading-tight text-ink-800">{user.full_name}</p>
              <p className="text-[12px] capitalize leading-tight text-ink-500">{user.role}</p>
            </div>
            <span className="grid size-9 place-items-center rounded-full bg-accent-50 text-[12.5px] font-semibold text-accent-700 ring-1 ring-line">
              {initials(user.full_name)}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                await signOut();
                navigate("/sign-in");
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl gap-7 px-4 py-7 sm:px-6">
        <aside className="hidden w-56 shrink-0 lg:block">
          <div className="sticky top-24">{nav}</div>
        </aside>

        {menuOpen && (
          <div
            className="animate-fade fixed inset-0 z-40 bg-ink-900/25 backdrop-blur-[2px] lg:hidden"
            onClick={() => setMenuOpen(false)}
          >
            <div
              className="glass animate-rise h-full w-72 rounded-r-2xl p-5"
              onClick={(event) => event.stopPropagation()}
            >
              <Brand className="mb-7" />
              {nav}
              <ThemeToggle className="mt-7" />
            </div>
          </div>
        )}

        <main key={location.pathname} className="animate-fade min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
