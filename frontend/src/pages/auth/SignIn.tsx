import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { Button, ErrorNote, Field, Input } from "../../components/ui";
import { ApiError } from "../../lib/api";
import { HOME_FOR_ROLE, useAuth } from "../../lib/auth";
import { AuthLayout, Divider, GoogleButton } from "./AuthLayout";

const GOOGLE_ERRORS: Record<string, string> = {
  google_auth_failed: "Google sign-in didn't complete. Please try again.",
  unauthorized: "Your Google account couldn't be verified.",
  forbidden: "This account has been disabled.",
};

export function SignIn() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [params] = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(GOOGLE_ERRORS[params.get("error") ?? ""] ?? "");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await signIn(email, password);
      navigate(location.state?.from ?? HOME_FOR_ROLE[user.role], { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "We couldn't sign you in. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      description="Access your tickets and updates."
      footer={
        <>
          New here?{" "}
          <Link to="/sign-up" className="font-medium text-accent-600 hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-5">
        {error && <ErrorNote>{error}</ErrorNote>}
        <Field label="Email" id="email">
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
          />
        </Field>
        <Field label="Password" id="password">
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-[13px] text-accent-600 hover:underline">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" loading={busy} className="w-full">
          Sign in
        </Button>
      </form>
      <Divider />
      <GoogleButton />
    </AuthLayout>
  );
}
