import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button, ErrorNote, Field, InfoNote, Input } from "../../components/ui";
import { ApiError, post } from "../../lib/api";
import { AuthLayout, CODE_INPUT } from "./AuthLayout";

/** Request a code, then set a new password with it. */
export function ForgotPassword() {
  const navigate = useNavigate();
  const [step, setStep] = useState<"request" | "reset">("request");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  function handleError(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      setFieldErrors(err.fieldErrors);
      setError(Object.keys(err.fieldErrors).length ? "" : err.message);
    } else setError(fallback);
  }

  async function requestCode(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setError("");
    try {
      await post("/auth/forgot-password", { email });
      setStep("reset");
    } catch (err) {
      handleError(err, "We couldn't send a reset code. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function reset(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setFieldErrors({});
    try {
      await post("/auth/reset-password", { email, code, new_password: password });
      navigate("/sign-in?reset=1", { replace: true });
    } catch (err) {
      handleError(err, "We couldn't reset your password. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title={step === "request" ? "Reset your password" : "Choose a new password"}
      description={
        step === "request"
          ? "We'll email you a code if an account exists."
          : "Enter the code we emailed you and a new password."
      }
      footer={
        <Link to="/sign-in" className="font-medium text-accent-600 hover:underline">
          Back to sign in
        </Link>
      }
    >
      {step === "request" ? (
        <form onSubmit={requestCode} className="space-y-5">
          {error && <ErrorNote>{error}</ErrorNote>}
          <Field label="Email" id="email">
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Button type="submit" loading={busy} className="w-full">
            Send reset code
          </Button>
        </form>
      ) : (
        <form onSubmit={reset} className="space-y-5">
          <InfoNote>If an account exists for {email}, the code is on its way.</InfoNote>
          {error && <ErrorNote>{error}</ErrorNote>}
          <Field label="6-digit code" id="code" error={fieldErrors.code}>
            <Input
              id="code"
              inputMode="numeric"
              maxLength={6}
              required
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              className={CODE_INPUT}
              placeholder="000000"
            />
          </Field>
          <Field
            label="New password"
            id="password"
            error={fieldErrors.new_password}
            hint="At least 8 characters."
          >
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Button type="submit" loading={busy} className="w-full">
            Set new password
          </Button>
          <button
            type="button"
            className="w-full text-[13px] text-accent-600 hover:underline"
            onClick={() => requestCode()}
            disabled={busy}
          >
            Send a new code
          </button>
        </form>
      )}
    </AuthLayout>
  );
}
