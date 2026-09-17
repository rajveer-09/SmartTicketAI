export type Role = "user" | "moderator" | "admin";

export type TicketStatus =
  "open" | "pending_review" | "assigned" | "in_progress" | "resolved" | "closed";

export type Priority = "low" | "medium" | "high" | "urgent";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  auth_provider: "email" | "google";
  has_password: boolean;
  created_at: string;
}

export interface AdminUser extends Omit<User, "has_password"> {
  is_active: boolean;
  skills: string[];
}

export interface UserBrief {
  id: string;
  full_name: string;
  email: string;
  role: Role;
}

export interface Ticket {
  id: string;
  title: string;
  description: string;
  status: TicketStatus;
  category: string | null;
  priority: Priority | null;
  required_skills: string[];
  ai_notes: string | null;
  ai_model_used: string | null;
  created_by: UserBrief;
  assignee: UserBrief | null;
  created_at: string;
  updated_at: string;
  assigned_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
}

export interface Comment {
  id: string;
  body: string;
  author: UserBrief | null;
  created_at: string;
}

export interface TicketDetail extends Ticket {
  comments: Comment[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface Workload {
  id: string;
  full_name: string;
  email: string;
  role: Role;
  is_active: boolean;
  skills: string[];
  active: number;
  resolved: number;
  closed: number;
  total: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export const STATUS_LABELS: Record<TicketStatus, string> = {
  open: "Open",
  pending_review: "Pending review",
  assigned: "Assigned",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
};
