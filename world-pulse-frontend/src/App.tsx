import { lazy, Suspense } from "react";
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

const Dashboard = lazy(() => import("./pages/Dashboard"));
const TrendPrediction = lazy(() => import("./pages/TrendPrediction"));


function App() {

  const token = localStorage.getItem("token");

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
            token ? (
              <Suspense fallback={<main className="wp-loading"><section className="wp-loading-card"><div className="wp-loading-spinner" /><p>Loading dashboard...</p></section></main>}>
                <Dashboard />
              </Suspense>
            ) : <Navigate to="/login" />
          }
        />

        {/* Protected Trend Prediction */}
        <Route
          path="/trend-prediction"
          element={
            token ? (
              <Suspense fallback={<main className="wp-loading"><section className="wp-loading-card"><div className="wp-loading-spinner" /><p>Loading trend prediction page...</p></section></main>}>
                <TrendPrediction />
              </Suspense>
            ) : <Navigate to="/login" />
          }
        />

        {/* Protected Historical Trends */}
        <Route
          path="/historical-trends"
          element={token ? <HistoricalTrends /> : <Navigate to="/login" />}
        />

        <Route
          path="/scenario"
          element={token ? <ScenarioStudio /> : <Navigate to="/login" />}
        />


      </Routes>

    </BrowserRouter>
  );
}

export default App;
