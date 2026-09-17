import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { Button, Card, ErrorNote, Field, Input, PageHeader, Textarea } from "../../components/ui";
import { ApiError } from "../../lib/api";
import { useCreateTicket } from "../../lib/queries";

const STEPS = [
  {
    title: "We read it with AI",
    body: "Your ticket is categorised and given a priority, usually within a minute.",
  },
  {
    title: "It goes to the right person",
    body: "We match what you've described against each moderator's skills and workload.",
  },
  {
    title: "You're kept in the loop",
    body: "You'll get an email when it's assigned, worked on and resolved.",
  },
];

export function NewTicket() {
  const navigate = useNavigate();
  const createTicket = useCreateTicket();
  const [form, setForm] = useState({ title: "", description: "" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setFieldErrors({});
    try {
      const ticket = await createTicket.mutateAsync(form);
      navigate(`/tickets/${ticket.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors);
        if (!Object.keys(err.fieldErrors).length) setError(err.message);
      } else setError("We couldn't create your ticket. Please try again.");
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Create a ticket"
        description="Describe the problem and we'll route it to the right person."
      />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <Card className="animate-rise p-6 sm:p-7">
          <form onSubmit={onSubmit} className="space-y-5">
            {error && <ErrorNote>{error}</ErrorNote>}
            <Field
              label="Title"
              id="title"
              error={fieldErrors.title}
              hint="A short summary, e.g. 'VPN disconnects every few minutes'."
            >
              <Input
                id="title"
                required
                minLength={3}
                maxLength={200}
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </Field>

            <Field
              label="What's happening?"
              id="description"
              error={fieldErrors.description}
              hint="Include when it started, what you've tried, and any error messages."
            >
              <Textarea
                id="description"
                required
                minLength={10}
                maxLength={5000}
                rows={10}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </Field>

            <div className="flex items-center gap-2 pt-1">
              <Button type="submit" loading={createTicket.isPending}>
                Submit ticket
              </Button>
              <Button type="button" variant="secondary" onClick={() => navigate(-1)}>
                Cancel
              </Button>
              <span className="ml-auto text-[12.5px] text-ink-400">
                {form.description.length}/5000
              </span>
            </div>
          </form>
        </Card>

        <Card className="animate-rise p-5">
          <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-400">
            What happens next
          </h2>
          <ol className="space-y-4">
            {STEPS.map((step, index) => (
              <li key={step.title} className="flex gap-3">
                <span
                  aria-hidden
                  className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-accent-50 text-[11px] font-semibold text-accent-700 ring-1 ring-accent-100"
                >
                  {index + 1}
                </span>
                <div>
                  <p className="text-[13px] font-medium text-ink-800">{step.title}</p>
                  <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-500">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}
