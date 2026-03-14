import { lazy, Suspense, type ReactElement } from "react";
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

const Dashboard = lazy(() => import("./pages/Dashboard"));
const TrendPrediction = lazy(() => import("./pages/TrendPrediction"));

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
  return (
    <BrowserRouter>
      <Routes>

        {/* Default Route - Landing Page */}
        <Route path="/" element={<Landing />} />

        {/* Public Pages */}
        <Route path="/about" element={<About />} />
        <Route path="/contact" element={<Contact />} />

        {/* Login Page */}
        <Route path="/login" element={<Login />} />

        {/* Register Page */}
        <Route path="/register" element={<Register />} />

        {/* Forgot Password Page */}
        <Route path="/forgot-password" element={<ForgotPassword />} />

        {/* Reset Password Page */}
        <Route path="/reset-password" element={<ResetPassword />} />

        {/* Protected Dashboard */}
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

        {/* Protected Trend Prediction */}
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

        {/* Protected Historical Trends */}
        <Route
          path="/historical-trends"
          element={<ProtectedRoute><HistoricalTrends /></ProtectedRoute>}
        />

        <Route
          path="/scenario"
          element={<ProtectedRoute><ScenarioStudio /></ProtectedRoute>}
        />

        <Route
          path="/profile"
          element={<ProtectedRoute><Profile /></ProtectedRoute>}
        />

        <Route
          path="/admin"
          element={<AdminRoute><AdminConsole /></AdminRoute>}
        />

        <Route
          path="/admin/system-monitoring"
          element={<AdminRoute><SystemMonitoring /></AdminRoute>}
        />

        <Route
          path="/admin/security-logs"
          element={<AdminRoute><SecurityLogs /></AdminRoute>}
        />

      </Routes>

    </BrowserRouter>
  );
}

export default App;
