import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import LoadingSpinner from "./components/LoadingSpinner.jsx";
import {
  GuestRoute,
  JudgeOrAdminRoute,
  JudgeProtectedRoute,
  ProtectedRoute,
  RootRedirect,
} from "./components/ProtectedRoute.jsx";

const Login = lazy(() => import("./pages/Login.jsx"));
const Submit = lazy(() => import("./pages/Submit.jsx"));
const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
const Leaderboard = lazy(() => import("./pages/Leaderboard.jsx"));
const Admin = lazy(() => import("./pages/Admin.jsx"));
const JudgeQueue = lazy(() => import("./pages/JudgeQueue.jsx"));

function PageFallback() {
  return (
    <div className="route-loading">
      <LoadingSpinner label="Loading page…" />
    </div>
  );
}

export default function App() {
  return (
    <div className="app">
      <main className="main">
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<RootRedirect />} />
            <Route
              path="/login"
              element={
                <GuestRoute>
                  <Login />
                </GuestRoute>
              }
            />
            <Route
              path="/submit"
              element={
                <ProtectedRoute>
                  <Submit />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/leaderboard"
              element={
                <JudgeOrAdminRoute>
                  <Leaderboard />
                </JudgeOrAdminRoute>
              }
            />
            <Route path="/admin" element={<Admin />} />
            <Route path="/judge/login" element={<Navigate to="/login" replace />} />
            <Route
              path="/judge"
              element={
                <JudgeProtectedRoute>
                  <JudgeQueue />
                </JudgeProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
