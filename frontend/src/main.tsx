import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./monacoSetup";
import "highlight.js/styles/github-dark.css";
import "./index.css";
import { useProject } from "./stores/project";
import { useSession } from "./stores/session";
import { useAgents } from "./stores/agents";
import { useRun } from "./stores/run";
import { useBuild } from "./stores/build";

// Dev-only testing hook: exposes the stores so end-to-end checks can drive
// state without depending on Monaco's internal editing events.
if (import.meta.env.DEV) {
  (window as unknown as { __wb: unknown }).__wb = {
    useProject,
    useSession,
    useAgents,
    useRun,
    useBuild,
  };
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
