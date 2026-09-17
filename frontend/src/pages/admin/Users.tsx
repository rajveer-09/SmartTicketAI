import { useState } from "react";
import type { FormEvent } from "react";

import {
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  ListSkeleton,
  PageHeader,
  Pagination,
  Select,
  SkillTags,
  cx,
} from "../../components/ui";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import {
  useAdminUsers,
  useCreateUser,
  useRemoveUser,
  useSetSkills,
  useUpdateUser,
} from "../../lib/queries";
import type { AdminUser, Role } from "../../lib/types";

const ROLES: Role[] = ["user", "moderator", "admin"];

/** `capitalize` doesn't reach the closed <select>, so label the options directly. */
const ROLE_LABELS: Record<Role, string> = {
  user: "User",
  moderator: "Moderator",
  admin: "Admin",
};

function SkillsEditor({ user }: { user: AdminUser }) {
  const setSkills = useSetSkills();
  const [value, setValue] = useState(user.skills.join(", "));
  const [error, setError] = useState("");
  const dirty = value !== user.skills.join(", ");

  if (user.role === "user") {
    return <p className="text-[12.5px] text-ink-400">Skills apply to moderators and admins.</p>;
  }

  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={async (event: FormEvent) => {
        event.preventDefault();
        setError("");
        try {
          await setSkills.mutateAsync({
            id: user.id,
            skills: value
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
          });
        } catch (err) {
          setError(err instanceof ApiError ? err.message : "Skills weren't saved.");
        }
      }}
    >
      <div className="min-w-56 flex-1">
        <Field label="Skills (comma separated)" id={`skills-${user.id}`}>
          <Input
            id={`skills-${user.id}`}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="vpn, networking, billing"
          />
        </Field>
      </div>
      <Button
        type="submit"
        size="sm"
        variant="secondary"
        disabled={!dirty}
        loading={setSkills.isPending}
      >
        Save skills
      </Button>
      {error && <ErrorNote>{error}</ErrorNote>}
    </form>
  );
}

function UserCard({ user }: { user: AdminUser }) {
  const { user: me } = useAuth();
  const updateUser = useUpdateUser();
  const removeUser = useRemoveUser();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const isSelf = me?.id === user.id;
  // A role change is staged until it's saved, so a stray click can't demote someone.
  const [role, setRole] = useState<Role>(user.role);
  const roleChanged = role !== user.role;

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
    } catch (err) {
      setRole(user.role);
      setError(err instanceof ApiError ? err.message : "That change didn't go through.");
    }
  }

  return (
    <Card hover className={cx("p-5", !user.is_active && "opacity-70")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[14px] font-medium text-ink-900">
            {user.full_name}
            {isSelf && <span className="ml-2 text-[12px] text-ink-400">you</span>}
          </p>
          <p className="truncate text-[13px] text-ink-500">{user.email}</p>
          {user.skills.length > 0 && (
            <div className="mt-2">
              <SkillTags skills={user.skills} />
            </div>
          )}
        </div>
        <div className="flex w-full items-center gap-2 sm:w-auto">
          {!user.is_active && (
            <span className="rounded-full bg-ink-100 px-2 py-0.5 text-[12px] text-ink-500">
              Disabled
            </span>
          )}
          <div className="w-36 shrink-0">
            <Select
              aria-label={`Role for ${user.full_name}`}
              value={role}
              disabled={isSelf || updateUser.isPending}
              onChange={(e) => setRole(e.target.value as Role)}
            >
              {ROLES.map((option) => (
                <option key={option} value={option}>
                  {ROLE_LABELS[option]}
                </option>
              ))}
            </Select>
          </div>
          {roleChanged ? (
            <>
              <Button
                size="sm"
                loading={updateUser.isPending}
                onClick={() => run(() => updateUser.mutateAsync({ id: user.id, role }))}
              >
                Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setRole(user.role)}>
                Cancel
              </Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setOpen((o) => !o)}>
              {open ? "Close" : "Manage"}
            </Button>
          )}
        </div>
      </div>

      {open && (
        <div className="mt-4 space-y-3 border-t border-line pt-4">
          <SkillsEditor user={user} />
          <div className="flex flex-wrap items-center gap-2">
            {user.is_active ? (
              <Button
                size="sm"
                variant="danger"
                disabled={isSelf}
                loading={removeUser.isPending}
                onClick={() => run(() => removeUser.mutateAsync(user.id))}
              >
                Remove access
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                loading={updateUser.isPending}
                onClick={() => run(() => updateUser.mutateAsync({ id: user.id, is_active: true }))}
              >
                Restore access
              </Button>
            )}
            <p className="text-[12.5px] text-ink-500">
              Removing access keeps their tickets and sends any open work back to Pending review.
            </p>
          </div>
          {error && <ErrorNote>{error}</ErrorNote>}
        </div>
      )}
    </Card>
  );
}

function NewUserForm({ onDone }: { onDone: () => void }) {
  const createUser = useCreateUser();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    role: "moderator" as Role,
    skills: "",
  });
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  return (
    <Card className="animate-rise mb-5 p-6">
      <h2 className="mb-3 text-[14px] font-semibold text-ink-900">Add someone</h2>
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={async (event: FormEvent) => {
          event.preventDefault();
          setError("");
          setFieldErrors({});
          try {
            await createUser.mutateAsync({
              ...form,
              skills: form.skills
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            });
            onDone();
          } catch (err) {
            if (err instanceof ApiError) {
              setFieldErrors(err.fieldErrors);
              if (!Object.keys(err.fieldErrors).length) setError(err.message);
            } else setError("We couldn't add this person.");
          }
        }}
      >
        <Field label="Full name" id="new-name" error={fieldErrors.full_name}>
          <Input
            id="new-name"
            required
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          />
        </Field>
        <Field label="Email" id="new-email" error={fieldErrors.email}>
          <Input
            id="new-email"
            type="email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </Field>
        <Field
          label="Temporary password"
          id="new-password"
          error={fieldErrors.password}
          hint="At least 8 characters. They can reset it later."
        >
          <Input
            id="new-password"
            required
            minLength={8}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </Field>
        <Field label="Role" id="new-role">
          <Select
            id="new-role"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {ROLE_LABELS[role]}
              </option>
            ))}
          </Select>
        </Field>
        {form.role !== "user" && (
          <div className="sm:col-span-2">
            <Field
              label="Skills (comma separated)"
              id="new-skills"
              hint="Used to match tickets automatically."
            >
              <Input
                id="new-skills"
                value={form.skills}
                onChange={(e) => setForm({ ...form, skills: e.target.value })}
                placeholder="vpn, networking"
              />
            </Field>
          </div>
        )}
        {error && (
          <div className="sm:col-span-2">
            <ErrorNote>{error}</ErrorNote>
          </div>
        )}
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" loading={createUser.isPending}>
            Add person
          </Button>
          <Button type="button" variant="secondary" onClick={onDone}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

export function AdminUsers() {
  const [q, setQ] = useState("");
  const [role, setRole] = useState<Role | "">("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const query = useAdminUsers({ q, role, page });

  return (
    <>
      <PageHeader
        title="Users & moderators"
        description="Add people, change roles, and set the skills used for AI matching."
        actions={!adding && <Button onClick={() => setAdding(true)}>Add someone</Button>}
      />

      {adding && <NewUserForm onDone={() => setAdding(false)} />}

      <Card className="animate-rise mb-5 flex flex-wrap gap-2.5 p-3">
        <div className="min-w-48 flex-1">
          <Input
            type="search"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="Search by name or email…"
            aria-label="Search people"
          />
        </div>
        <div className="w-40">
          <Select
            aria-label="Filter by role"
            value={role}
            onChange={(e) => {
              setRole(e.target.value as Role | "");
              setPage(1);
            }}
          >
            <option value="">Any role</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      {query.isPending ? (
        <ListSkeleton />
      ) : query.data && query.data.total > 0 ? (
        <>
          <div className="stagger space-y-3">
            {query.data.items.map((user) => (
              <UserCard key={user.id} user={user} />
            ))}
          </div>
          <Pagination
            page={query.data.page}
            pages={query.data.pages}
            total={query.data.total}
            onChange={setPage}
            noun="person"
          />
        </>
      ) : (
        <EmptyState
          title="Nobody matches that search"
          description="Try a different name or email."
        />
      )}
    </>
  );
}
