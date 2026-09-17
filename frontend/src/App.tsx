import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/layout/AppShell";
import { RequireAnonymous, RequireAuth } from "./components/layout/Guards";
import { EmptyState } from "./components/ui";
import { ApiError } from "./lib/api";
import { AuthProvider, HOME_FOR_ROLE, useAuth } from "./lib/auth";
import { ThemeProvider } from "./lib/theme";
import { AdminSearch } from "./pages/admin/Search";
import { AdminTickets } from "./pages/admin/AdminTickets";
import { AdminUsers } from "./pages/admin/Users";
import { Workload } from "./pages/admin/Workload";
import { GoogleCallback } from "./pages/auth/GoogleCallback";
import { ForgotPassword } from "./pages/auth/ResetPassword";
import { SignIn } from "./pages/auth/SignIn";
import { SignUp } from "./pages/auth/SignUp";
import { ModeratorTickets } from "./pages/moderator/ModeratorTickets";
import { MyTickets } from "./pages/user/MyTickets";
import { NewTicket } from "./pages/user/NewTicket";
import { TicketDetail } from "./pages/user/TicketDetail";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: (count, error) =>
        // Don't retry the user's own mistakes (401/403/404/422).
        !(error instanceof ApiError && error.status < 500) && count < 2,
    },
  },
});

function Home() {
  const { user, loading } = useAuth();
  if (loading) return null;
  return <Navigate to={user ? HOME_FOR_ROLE[user.role] : "/sign-in"} replace />;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/" element={<Home />} />

              <Route
                path="/sign-in"
                element={
                  <RequireAnonymous>
                    <SignIn />
                  </RequireAnonymous>
                }
              />
              <Route
                path="/sign-up"
                element={
                  <RequireAnonymous>
                    <SignUp />
                  </RequireAnonymous>
                }
              />
              <Route
                path="/forgot-password"
                element={
                  <RequireAnonymous>
                    <ForgotPassword />
                  </RequireAnonymous>
                }
              />
              <Route path="/auth/google/callback" element={<GoogleCallback />} />

              <Route
                element={
                  <RequireAuth>
                    <AppShell />
                  </RequireAuth>
                }
              >
                <Route path="/tickets" element={<MyTickets scope="open" />} />
                <Route path="/tickets/history" element={<MyTickets scope="history" />} />
                <Route path="/tickets/new" element={<NewTicket />} />
                <Route path="/tickets/:id" element={<TicketDetail />} />

                <Route
                  path="/moderator/tickets"
                  element={
                    <RequireAuth roles={["moderator", "admin"]}>
                      <ModeratorTickets scope="assigned" />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/moderator/solved"
                  element={
                    <RequireAuth roles={["moderator", "admin"]}>
                      <ModeratorTickets scope="solved" />
                    </RequireAuth>
                  }
                />

                <Route
                  path="/admin/tickets"
                  element={
                    <RequireAuth roles={["admin"]}>
                      <AdminTickets />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/admin/users"
                  element={
                    <RequireAuth roles={["admin"]}>
                      <AdminUsers />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/admin/workload"
                  element={
                    <RequireAuth roles={["admin"]}>
                      <Workload />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/admin/search"
                  element={
                    <RequireAuth roles={["admin"]}>
                      <AdminSearch />
                    </RequireAuth>
                  }
                />

                <Route
                  path="*"
                  element={
                    <EmptyState title="Page not found" description="The link may be out of date." />
                  }
                />
              </Route>
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
