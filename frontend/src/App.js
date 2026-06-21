import React, { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import HomeScreen from "./screens/HomeScreen";
import CameraScreen from "./screens/CameraScreen";
import ResultsScreen from "./screens/ResultsScreen";
import LoginScreen from "./screens/LoginScreen";
import RegisterScreen from "./screens/RegisterScreen";
import ForgotPasswordScreen from "./screens/ForgotPasswordScreen";
import ResetPasswordScreen from "./screens/ResetPasswordScreen";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import { setupFetchInterceptor } from "./lib/fetchInterceptor";
import "./App.css";

// Attach JWT interceptor once at module load — does nothing if Supabase is unconfigured
setupFetchInterceptor();

function App() {
  return (
    <div className="bg-[#0A0A0A] min-h-screen">
      <BrowserRouter>
        <AuthProvider>
          <div className="max-w-md mx-auto min-h-screen relative overflow-x-hidden">
            <Routes>
              {/* Public auth routes */}
              <Route path="/login" element={<LoginScreen />} />
              <Route path="/register" element={<RegisterScreen />} />
              <Route path="/forgot-password" element={<ForgotPasswordScreen />} />
              <Route path="/reset-password" element={<ResetPasswordScreen />} />

              {/* Protected app routes */}
              <Route path="/" element={<ProtectedRoute><HomeScreen /></ProtectedRoute>} />
              <Route path="/camera" element={<ProtectedRoute><CameraScreen /></ProtectedRoute>} />
              <Route path="/results" element={<ProtectedRoute><ResultsScreen /></ProtectedRoute>} />

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
