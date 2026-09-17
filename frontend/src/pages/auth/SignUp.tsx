import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button, ErrorNote, Field, InfoNote, Input } from "../../components/ui";
import { ApiError, post } from "../../lib/api";
import { HOME_FOR_ROLE, useAuth } from "../../lib/auth";
import { AuthLayout, CODE_INPUT, Divider, GoogleButton } from "./AuthLayout";

/** Two steps: details -> emailed code. The account only exists after the code. */
export function SignUp() {
  const { completeSignUp } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState<"details" | "code">("details");
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  function handleError(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      setFieldErrors(err.fieldErrors);
      setError(Object.keys(err.fieldErrors).length ? "" : err.message);
    } else {
      setError(fallback);
    }
  }

  async function requestCode(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setError("");
    setFieldErrors({});
    try {
      await post("/auth/register", form);
      setStep("code");
      setNotice(`We sent a 6-digit code to ${form.email}. It expires in 10 minutes.`);
    } catch (err) {
      handleError(err, "We couldn't start your sign-up. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function verify(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await completeSignUp(form.email, code);
      navigate(HOME_FOR_ROLE[user.role], { replace: true });
    } catch (err) {
      handleError(err, "That code didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (step === "code") {
    return (
      <AuthLayout title="Confirm your email" description="Enter the code we emailed you.">
        <form onSubmit={verify} className="space-y-5">
          {notice && <InfoNote>{notice}</InfoNote>}
          {error && <ErrorNote>{error}</ErrorNote>}
          <Field label="6-digit code" id="code" error={fieldErrors.code}>
            <Input
              id="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              required
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              className={CODE_INPUT}
              placeholder="000000"
            />
          </Field>
          <Button type="submit" loading={busy} className="w-full">
            Create my account
          </Button>
          <div className="flex items-center justify-between text-[13px]">
            <button
              type="button"
              className="text-ink-600 hover:underline"
              onClick={() => setStep("details")}
            >
              Change details
            </button>
            <button
              type="button"
              className="text-accent-600 hover:underline"
              onClick={() => requestCode()}
              disabled={busy}
            >
              Send a new code
            </button>
          </div>
        </form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Create your account"
      description="You'll confirm your email with a short code."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/sign-in" className="font-medium text-accent-600 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={requestCode} className="space-y-5">
        {error && <ErrorNote>{error}</ErrorNote>}
        <Field label="Full name" id="name" error={fieldErrors.full_name}>
          <Input
            id="name"
            required
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          />
        </Field>
        <Field label="Email" id="email" error={fieldErrors.email}>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </Field>
        <Field
          label="Password"
          id="password"
          error={fieldErrors.password}
          hint="At least 8 characters."
        >
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </Field>
        <Button type="submit" loading={busy} className="w-full">
          Send verification code
        </Button>
      </form>
      <Divider />
      <GoogleButton label="Sign up with Google" />
    </AuthLayout>
  );
}
