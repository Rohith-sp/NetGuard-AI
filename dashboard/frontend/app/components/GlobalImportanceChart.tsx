"use client";
import { useEffect, useState } from "react";

interface ImportanceItem { feature: string; importance: number; }

export default function GlobalImportanceChart() {
  const [data, setData] = useState<ImportanceItem[]>([]);
  const [classes, setClasses] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/feature-importance")
      .then(r => r.json())
      .then(d => {
        setData(d.features ?? []);
        setClasses(d.model_classes ?? []);
        setLoaded(true);
      })
      .catch(() => setLoaded(true)); // silently fail if backend offline
  }, []);

  const max = Math.max(...data.map(d => d.importance), 1);

  const featureColors: Record<string, string> = {
    duplicate_ratio:       "var(--amber)",
    seq_increment_mean:    "var(--blue)",
    packet_count:          "var(--green)",
    packet_rate:           "var(--green)",
    mean_inter_arrival_ms: "var(--purple, #a78bfa)",
    min_inter_arrival_ms:  "var(--purple, #a78bfa)",
    max_inter_arrival_ms:  "var(--purple, #a78bfa)",
    std_inter_arrival_ms:  "var(--text-3)",
    seq_increment_std:     "var(--text-3)",
  };

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Global Feature Importance</span>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {classes.map(c => (
            <span key={c} className="card-tag" style={{ fontSize: 10 }}>
              {c.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      </div>

      {!loaded ? (
        <div style={{ color: "var(--text-3)", fontSize: 13, padding: "16px 0" }}>Loading model importances…</div>
      ) : data.length === 0 ? (
        <div style={{ color: "var(--text-3)", fontSize: 13, padding: "16px 0" }}>Backend offline — start the server to load model data.</div>
      ) : (
        <div className="gi-chart">
          <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 12 }}>
            Computed from <strong>200 Random Forest trees</strong> across all {classes.length} classes.
            Shows which features the model relies on globally, averaged across all predictions.
          </div>
          {data.map((item, i) => {
            const pct = (item.importance / max) * 100;
            const color = featureColors[item.feature] ?? "var(--green)";
            return (
              <div key={item.feature} className="gi-row">
                <div className="gi-rank">#{i + 1}</div>
                <div className="gi-name" title={item.feature}>
                  {item.feature.replace(/_/g, " ")}
                </div>
                <div className="gi-bar-track">
                  <div
                    className="gi-bar-fill"
                    style={{ width: `${pct}%`, background: color }}
                  />
                </div>
                <div className="gi-val" style={{ color }}>{item.importance.toFixed(1)}%</div>
              </div>
            );
          })}
          <div className="gi-legend">
            <span style={{ color: "var(--amber)" }}>■</span> Replay/Dup signals &nbsp;
            <span style={{ color: "var(--blue)" }}>■</span> Sequence signals &nbsp;
            <span style={{ color: "var(--green)" }}>■</span> Rate signals &nbsp;
            <span style={{ color: "var(--purple, #a78bfa)" }}>■</span> Timing signals
          </div>
        </div>
      )}
    </div>
  );
}
