import { Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { useTheme } from "@/hooks/useTheme";
import DefaultLayout from "@/layouts/DefaultLayout";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import GroupsPage from "@/pages/GroupsPage";
import GroupDetailPage from "@/pages/GroupDetailPage";
import BlacklistPage from "@/pages/BlacklistPage";
import WhitelistPage from "@/pages/WhitelistPage";
import PointsPage from "@/pages/PointsPage";
import UserStatusPage from "@/pages/UserStatusPage";
import BotInfoPage from "@/pages/BotInfoPage";
import PluginsPage from "@/pages/PluginsPage";
import QQGroupsPage from "@/pages/QQGroupsPage";
import GroupFeaturesPage from "@/pages/GroupFeaturesPage";
import MessageLogsPage from "@/pages/MessageLogsPage";
import { useAuthStore } from "@/store/authStore";

function AuthChecker({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  const { isDark } = useTheme();
  return (
    <>
      {/* NapCat 同款 Toast: 20px 圆角纯色 */}
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 3000,
          style: {
            borderRadius: "20px",
            background: isDark ? "#333" : "#fff",
            color: isDark ? "#fff" : "#333",
            maxWidth: "400px",
            wordBreak: "break-word",
          },
        }}
      />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <AuthChecker>
              <DefaultLayout />
            </AuthChecker>
          }
        >
          <Route path="/permissions" element={<DashboardPage />} />
          <Route path="/permissions/groups" element={<GroupsPage />} />
          <Route path="/permissions/groups/:id" element={<GroupDetailPage />} />
          <Route path="/permissions/blacklist" element={<BlacklistPage />} />
          <Route path="/permissions/whitelist" element={<WhitelistPage />} />
          <Route path="/permissions/points" element={<PointsPage />} />
          <Route path="/permissions/user-status" element={<UserStatusPage />} />
          <Route path="/info" element={<BotInfoPage />} />
          <Route path="/plugins" element={<PluginsPage />} />
          <Route path="/groups/list" element={<QQGroupsPage />} />
          <Route path="/groups/features" element={<GroupFeaturesPage />} />
          <Route path="/logs" element={<MessageLogsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/permissions" replace />} />
      </Routes>
    </>
  );
}
