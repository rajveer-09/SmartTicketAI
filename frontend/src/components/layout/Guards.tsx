import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { HOME_FOR_ROLE, useAuth } from "../../lib/auth";
import type { Role } from "../../lib/types";
import { Card, Skeleton } from "../ui";

function Loading() {
  return (
    <div className="mx-auto max-w-3xl p-8">
      <Card className="animate-fade p-6">
        <Skeleton className="h-5 w-44" />
        <Skeleton className="mt-4 h-3 w-2/3" />
        <Skeleton className="mt-2.5 h-3 w-1/3" />
      </Card>
    </div>
  );
}

/** Requires a signed-in user, and optionally one of the given roles. */
export function RequireAuth({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading />;
  if (!user) return <Navigate to="/sign-in" state={{ from: location.pathname }} replace />;
  if (roles && !roles.includes(user.role))
    return <Navigate to={HOME_FOR_ROLE[user.role]} replace />;
  return <>{children}</>;
}

/** Sign-in pages: send people who are already signed in to their dashboard. */
export function RequireAnonymous({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (user) return <Navigate to={HOME_FOR_ROLE[user.role]} replace />;
  return <>{children}</>;
}
