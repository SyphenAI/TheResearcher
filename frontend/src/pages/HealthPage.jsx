import React, { useEffect, useState } from "react";
import { api } from "../api/client";

export default function HealthPage() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/health")
      .then(setHealth)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="stack">
      <div>
        <h1>Health / self-check</h1>
        <p className="muted">Startup checks for packages, data directory, and database.</p>
      </div>
      {error && <div className="alert error">{error}</div>}
      {health && (
        <div className="panel stack">
          <div className="row">
            <span className={`badge ${health.status === "ok" ? "good" : "bad"}`}>{health.status}</span>
            <span className="badge">v{health.version}</span>
            <span className="badge">{health.app_env}</span>
          </div>
          <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--mono)", fontSize: "0.85rem" }}>
            {JSON.stringify(health.checks, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
