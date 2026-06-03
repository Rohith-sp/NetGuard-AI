"use client";
import { IncidentState } from "../hooks/useLiveData";

interface Props { incident: IncidentState; }

export default function IncidentReport({ incident }: Props) {
  if (!incident.text) return null;

  const colorMap: Record<string, string> = {
    DOS_FLOOD:        "var(--red)",
    REPLAY_ATTACK:    "var(--amber)",
    SLOW_RATE_ATTACK: "var(--blue)",
  };
  const color = colorMap[incident.label] ?? "var(--red)";

  return (
    <div className="card incident-card" style={{ borderLeft: `3px solid ${color}` }}>
      <div className="card-header">
        <span className="card-title">
          <span style={{ color, marginRight: 8 }}>⚡</span>
          AI Incident Report
        </span>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className="card-tag" style={{ background: `${color}22`, color, borderColor: `${color}55` }}>
            {incident.label.replace(/_/g, " ")}
          </span>
          <span style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--mono)" }}>
            {incident.ts}
          </span>
        </div>
      </div>

      <div className="incident-body">
        {/* RAG badge */}
        <div className="incident-rag-badge">
          <span className="rag-dot" />
          AUTO-GENERATED · SHAP-GROUNDED · RAG ANALYST
        </div>
        <p className="incident-text">{incident.text}</p>
      </div>
    </div>
  );
}
