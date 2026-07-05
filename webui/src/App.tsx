import { Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import DefaultLayout from "@/layouts/DefaultLayout";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import GroupsPage from "@/pages/GroupsPage";
import GroupDetailPage from "@/pages/GroupDetailPage";
import BlacklistPage from "@/pages/BlacklistPage";
import WhitelistPage from "@/pages/WhitelistPage";
import PointsPage from "@/pages/PointsPage";
import UserStatusPage from "@/pages/UserStatusPage";
import { useAuthStore } from "@/store/authStore";

function AuthChecker({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <>
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 3000,
          style: {
            background: "hsl(var(--heroui-content1) / 0.8)",
            color: "hsl(var(--heroui-foreground))",
            border: "1px solid hsl(var(--heroui-divider) / 0.4)",
            borderRadius: "16px",
            fontSize: "14px",
            fontWeight: 500,
            padding: "12px 16px",
            backdropFilter: "blur(16px) saturate(180%)",
            WebkitBackdropFilter: "blur(16px) saturate(180%)",
            boxShadow: "0 8px 32px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06)",
          },
          success: {
            iconTheme: {
              primary: "hsl(var(--heroui-success))",
              secondary: "white",
            },
          },
          error: {
            iconTheme: {
              primary: "hsl(var(--heroui-danger))",
              secondary: "white",
            },
          },
        }}
      />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/permissions"
          element={
            <AuthChecker>
              <DefaultLayout />
            </AuthChecker>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="groups" element={<GroupsPage />} />
          <Route path="groups/:id" element={<GroupDetailPage />} />
          <Route path="blacklist" element={<BlacklistPage />} />
          <Route path="whitelist" element={<WhitelistPage />} />
          <Route path="points" element={<PointsPage />} />
          <Route path="user-status" element={<UserStatusPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/permissions" replace />} />
      </Routes>
    </>
  );
}
