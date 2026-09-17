import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { del, get, patch, post, put } from "./api";
import type { AdminUser, Page, Role, Ticket, TicketDetail, TicketStatus, Workload } from "./types";

export interface TicketFilters {
  q?: string;
  status?: TicketStatus[];
  date_from?: string;
  date_to?: string;
  page?: number;
  size?: number;
}

const PAGE_SIZE = 10;

function ticketParams(filters: TicketFilters, extra: Record<string, unknown> = {}) {
  return {
    q: filters.q || undefined,
    status: filters.status?.length ? filters.status : undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    page: filters.page ?? 1,
    size: filters.size ?? PAGE_SIZE,
    ...extra,
  } as Record<string, string | number | boolean | string[] | undefined>;
}

/* --- Tickets (all roles) --- */

export function useMyTickets(scope: "open" | "history" | "all", filters: TicketFilters) {
  return useQuery({
    queryKey: ["tickets", "mine", scope, filters],
    queryFn: () => get<Page<Ticket>>("/tickets/mine", ticketParams(filters, { scope })),
  });
}

export function useTicket(id: string | undefined) {
  return useQuery({
    queryKey: ["ticket", id],
    queryFn: () => get<TicketDetail>(`/tickets/${id}`),
    enabled: Boolean(id),
    // A new ticket is analyzed and assigned in the background; poll until it settles.
    refetchInterval: (query) =>
      query.state.data && query.state.data.status === "open" ? 3000 : false,
  });
}

export function useCreateTicket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { title: string; description: string }) => post<Ticket>("/tickets", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tickets"] }),
  });
}

export function useAddComment(ticketId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => post(`/tickets/${ticketId}/comments`, { body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ticket", ticketId] }),
  });
}

export function useChangeStatus(ticketId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (status: TicketStatus) => patch<Ticket>(`/tickets/${ticketId}/status`, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ticket", ticketId] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
    },
  });
}

/* --- Moderator --- */

export function useModeratorTickets(scope: "assigned" | "solved", filters: TicketFilters) {
  return useQuery({
    queryKey: ["tickets", "moderator", scope, filters],
    queryFn: () => get<Page<Ticket>>("/moderator/tickets", ticketParams(filters, { scope })),
  });
}

/* --- Admin --- */

export interface AdminTicketFilters extends TicketFilters {
  assignee_id?: string;
  unassigned?: boolean;
}

export function useAdminTickets(filters: AdminTicketFilters) {
  return useQuery({
    queryKey: ["tickets", "admin", filters],
    queryFn: () =>
      get<Page<Ticket>>(
        "/admin/tickets",
        ticketParams(filters, {
          assignee_id: filters.assignee_id || undefined,
          unassigned: filters.unassigned || undefined,
        }),
      ),
  });
}

export function useAdminUsers(params: {
  q?: string;
  role?: Role | "";
  is_active?: boolean;
  page?: number;
}) {
  return useQuery({
    queryKey: ["admin", "users", params],
    queryFn: () =>
      get<Page<AdminUser>>("/admin/users", {
        q: params.q || undefined,
        role: params.role || undefined,
        is_active: params.is_active,
        page: params.page ?? 1,
        size: 10,
      }),
  });
}

export function useWorkload() {
  return useQuery({
    queryKey: ["admin", "workload"],
    queryFn: () => get<Workload[]>("/admin/moderators/workload"),
  });
}

export function useGlobalSearch(q: string) {
  return useQuery({
    queryKey: ["admin", "search", q],
    queryFn: () => get<{ tickets: Ticket[]; users: AdminUser[] }>("/admin/search", { q }),
    enabled: q.trim().length > 0,
  });
}

function useAdminMutation<TArgs>(fn: (args: TArgs) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin"] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
      qc.invalidateQueries({ queryKey: ["ticket"] });
    },
  });
}

export const useCreateUser = () =>
  useAdminMutation(
    (body: { full_name: string; email: string; password: string; role: Role; skills: string[] }) =>
      post<AdminUser>("/admin/users", body),
  );

export const useUpdateUser = () =>
  useAdminMutation(
    ({ id, ...body }: { id: string; role?: Role; is_active?: boolean; full_name?: string }) =>
      patch<AdminUser>(`/admin/users/${id}`, body),
  );

export const useRemoveUser = () => useAdminMutation((id: string) => del(`/admin/users/${id}`));

export const useSetSkills = () =>
  useAdminMutation(({ id, skills }: { id: string; skills: string[] }) =>
    put<AdminUser>(`/admin/users/${id}/skills`, { skills }),
  );

export const useAssignTicket = () =>
  useAdminMutation(({ ticketId, moderatorId }: { ticketId: string; moderatorId: string }) =>
    post<Ticket>(`/admin/tickets/${ticketId}/assign`, { moderator_id: moderatorId }),
  );
