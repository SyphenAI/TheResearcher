import React, { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./api/auth";
import LoginPage from "./pages/LoginPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import HomeDashboardPage from "./pages/HomeDashboardPage";
import ResearchWorkspacePage from "./pages/ResearchWorkspacePage";
import SecurityPage from "./pages/SecurityPage";
import AiCheckerPage from "./pages/AiCheckerPage";
import UsersPage from "./pages/UsersPage";
import HealthPage from "./pages/HealthPage";
import SettingsPage from "./pages/SettingsPage";
import SearchPage from "./pages/SearchPage";

function Shell({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [route, setRoute] = useState(location.pathname);

  useEffect(() => {
    setRoute(location.pathname);
  }, [location.pathname]);

  function go(path) {
    setRoute(path);
    navigate(path);
  }

  const dashActive = route === "/app" || route.startsWith("/app/research");
  const role = user?.role || "researcher";

  // Role-aware defaults: reviewers land heavier on quality tools in nav order.
  const nav = [];
  if (role === "reviewer") {
    nav.push(
      { path: "/app", label: "Dashboard", active: dashActive },
      { path: "/search", label: "Search", active: route.startsWith("/search") },
      { path: "/ai-check", label: "AI Checker", active: route.startsWith("/ai-check") },
      { path: "/settings", label: "Settings", active: route.startsWith("/settings") },
      { path: "/health", label: "Health", active: route.startsWith("/health") }
    );
  } else {
    nav.push(
      { path: "/app", label: "Dashboard", active: dashActive },
      { path: "/search", label: "Search", active: route.startsWith("/search") },
      { path: "/ai-check", label: "AI Checker", active: route.startsWith("/ai-check") },
      { path: "/security", label: "Security", active: route.startsWith("/security") },
      { path: "/settings", label: "Settings", active: route.startsWith("/settings") }
    );
    if (role === "admin") {
      nav.push({ path: "/users", label: "Users", active: route.startsWith("/users") });
    }
    nav.push({ path: "/health", label: "Health", active: route.startsWith("/health") });
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand" style={{ cursor: "pointer" }} onClick={() => go("/app")}>
          <div className="brand-mark" />
          <div>
            TheResearcher
            <div className="muted" style={{ fontSize: "0.78rem", fontWeight: 400 }}>
              SecOps research desk
            </div>
          </div>
        </div>
        <nav className="nav">
          {nav.map((item) => (
            <button key={item.path} className={item.active ? "active" : ""} onClick={() => go(item.path)}>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="row">
          <span className="badge">
            {user?.username} · {user?.role}
          </span>
          <button
            className="btn ghost"
            onClick={() => {
              logout();
              navigate("/login");
            }}
          >
            Log out
          </button>
        </div>
      </header>
      <main className="main">{children}</main>
    </div>
  );
}

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="main">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  return <Shell>{children}</Shell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/change-password" element={<ChangePasswordPage />} />
      <Route path="/app" element={<PrivateRoute><HomeDashboardPage /></PrivateRoute>} />
      <Route path="/app/research/:projectId" element={<PrivateRoute><ResearchWorkspacePage /></PrivateRoute>} />
      <Route path="/search" element={<PrivateRoute><SearchPage /></PrivateRoute>} />
      <Route path="/security" element={<PrivateRoute><SecurityPage /></PrivateRoute>} />
      <Route path="/settings" element={<PrivateRoute><SettingsPage /></PrivateRoute>} />
      <Route path="/ai-check" element={<PrivateRoute><AiCheckerPage /></PrivateRoute>} />
      <Route path="/users" element={<PrivateRoute><UsersPage /></PrivateRoute>} />
      <Route path="/health" element={<PrivateRoute><HealthPage /></PrivateRoute>} />
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}
