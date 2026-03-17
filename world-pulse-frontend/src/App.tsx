import { lazy, Suspense, type ReactElement, useCallback, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Landing from "./pages/Landing";
import About from "./pages/About";
import Contact from "./pages/Contact";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import HistoricalTrends from "./pages/HistoricalTrends";
import ScenarioStudio from "./pages/ScenarioStudio";
import Profile from "./pages/Profile";
import AdminConsole from "./pages/AdminConsole";
import SystemMonitoring from "./pages/SystemMonitoring";
import SecurityLogs from "./pages/SecurityLogs";
import IntroSplash from "./components/IntroSplash";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const TrendPrediction = lazy(() => import("./pages/TrendPrediction"));

const INTRO_SEEN_KEY = "wp_intro_seen_v3";

type IntroMode = {
  shouldShow: boolean;
  isForced: boolean;
};

function getIntroMode(): IntroMode {
  try {
    const params = new URLSearchParams(window.location.search);
    const intro = (params.get("intro") || "").toLowerCase();
    const forceByQuery = intro === "1" || intro === "true";
    const forceByPath = window.location.pathname.toLowerCase() === "/intro";
    const isForced = forceByQuery || forceByPath;

    if (isForced) {
      return { shouldShow: true, isForced: true };
    }

    const hasSeen = localStorage.getItem(INTRO_SEEN_KEY) === "1";
    return { shouldShow: !hasSeen, isForced: false };
  } catch {
    return { shouldShow: false, isForced: false };
  }
}

function markIntroSeen() {
  try {
    localStorage.setItem(INTRO_SEEN_KEY, "1");
  } catch {
    // Ignore storage errors to avoid blocking app navigation.
  }
}

function cleanupIntroUrlIfNeeded() {
  try {
    const current = new URL(window.location.href);
    const isIntroPath = current.pathname.toLowerCase() === "/intro";

    if (isIntroPath) {
      window.location.replace("/");
      return;
    }

    if (current.searchParams.has("intro")) {
      current.searchParams.delete("intro");
      const nextSearch = current.searchParams.toString();
      const next = `${current.pathname}${nextSearch ? `?${nextSearch}` : ""}${current.hash}`;
      window.history.replaceState({}, "", next);
    }
  } catch {
    // Ignore URL cleanup failures.
  }
}

function isJwtExpired(token: string): boolean {
  try {
    const [, payloadBase64] = token.split(".");
    if (!payloadBase64) return false;

    const normalized = payloadBase64.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(normalized));
    const exp = Number(payload?.exp || 0);
    if (!Number.isFinite(exp) || exp <= 0) return false;

    return Date.now() >= exp * 1000;
  } catch {
    return false;
  }
}

function clearAuthState() {
  localStorage.removeItem("token");
  localStorage.removeItem("role");
  localStorage.removeItem("user_type");
  localStorage.removeItem("name");
  localStorage.removeItem("email");
}

function hasToken(): boolean {
  const token = localStorage.getItem("token");
  if (!token) return false;

  if (isJwtExpired(token)) {
    clearAuthState();
    return false;
  }

  return true;
}

function isAdmin(): boolean {
  return hasToken() && localStorage.getItem("role") === "admin";
}

function ProtectedRoute({ children }: { children: ReactElement }) {
  return hasToken() ? children : <Navigate to="/login" replace />;
}

function AdminRoute({ children }: { children: ReactElement }) {
  if (!hasToken()) return <Navigate to="/login" replace />;
  return isAdmin() ? children : <Navigate to="/dashboard" replace />;
}

function App() {
  const [introMode] = useState<IntroMode>(() => getIntroMode());
  const [showIntro, setShowIntro] = useState(() => introMode.shouldShow);
  const shouldPersistIntroSeen = !introMode.isForced;

  const handleIntroComplete = useCallback(() => {
    if (shouldPersistIntroSeen) {
      markIntroSeen();
    }
    cleanupIntroUrlIfNeeded();
    setShowIntro(false);
  }, [shouldPersistIntroSeen]);

  if (showIntro) {
    return <IntroSplash onComplete={handleIntroComplete} forced={introMode.isForced} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/about" element={<About />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />

        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Suspense fallback={<main className="wp-loading"><section className="wp-loading-card"><div className="wp-loading-spinner" /><p>Loading dashboard...</p></section></main>}>
                <Dashboard />
              </Suspense>
            </ProtectedRoute>
          }
        />

        <Route
          path="/trend-prediction"
          element={
            <ProtectedRoute>
              <Suspense fallback={<main className="wp-loading"><section className="wp-loading-card"><div className="wp-loading-spinner" /><p>Loading trend prediction page...</p></section></main>}>
                <TrendPrediction />
              </Suspense>
            </ProtectedRoute>
          }
        />

        <Route path="/historical-trends" element={<ProtectedRoute><HistoricalTrends /></ProtectedRoute>} />
        <Route path="/scenario" element={<ProtectedRoute><ScenarioStudio /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
        <Route path="/admin" element={<AdminRoute><AdminConsole /></AdminRoute>} />
        <Route path="/admin/system-monitoring" element={<AdminRoute><SystemMonitoring /></AdminRoute>} />
        <Route path="/admin/security-logs" element={<AdminRoute><SecurityLogs /></AdminRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;


