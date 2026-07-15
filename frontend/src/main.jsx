import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import { TeamProvider } from "./context/TeamContext.jsx";
import { ToastProvider } from "./context/ToastContext.jsx";
import "./styles.css";
import { startBackgroundSync } from "./lib/offlineQueue.js";

startBackgroundSync();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <ToastProvider>
          <TeamProvider>
            <Suspense fallback={<div className="page-loading">Loading…</div>}>
              <App />
            </Suspense>
          </TeamProvider>
        </ToastProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>
);
