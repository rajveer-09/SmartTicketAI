import { useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Skeleton } from "../../components/ui";
import { HOME_FOR_ROLE, useAuth } from "../../lib/auth";

/**
 * Google sends the browser here after the API has set the refresh cookie.
 * We exchange that cookie for a session, so no token ever appears in a URL.
 */
export function GoogleCallback() {
  const { restore } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const error = params.get("error");
    if (error) {
      navigate(`/sign-in?error=${encodeURIComponent(error)}`, { replace: true });
      return;
    }
    restore().then((user) => {
      navigate(user ? HOME_FOR_ROLE[user.role] : "/sign-in?error=google_auth_failed", {
        replace: true,
      });
    });
  }, [navigate, params, restore]);

  return (
    <div className="mx-auto max-w-sm space-y-3 p-10 text-center">
      <p className="text-sm text-ink-600">Finishing sign-in…</p>
      <Skeleton className="h-10 w-full" />
    </div>
  );
}
