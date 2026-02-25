import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import Dashboard from "./pages/Dashboard";
import TrendPrediction from "./pages/TrendPrediction";
import HistoricalTrends from "./pages/HistoricalTrends";
import ScenarioStudio from "./pages/ScenarioStudio";


function App() {

  const token = localStorage.getItem("token");

  return (
    <BrowserRouter>
      <Routes>

        {/* Default Route */}
        <Route path="/" element={<Navigate to="/login" />} />

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
          element={token ? <Dashboard /> : <Navigate to="/login" />}
        />

        {/* Protected Trend Prediction */}
        <Route
          path="/trend-prediction"
          element={token ? <TrendPrediction /> : <Navigate to="/login" />}
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
