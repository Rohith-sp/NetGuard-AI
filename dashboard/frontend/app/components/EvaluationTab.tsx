"use client";
import React, { useMemo, useState, useRef, useEffect } from "react";
import type { EvaluationState, SimTopology, SimNodeStates } from "../hooks/useLiveData";
import Network50Tab from "./Network50Tab";
import { RefreshIcon, MicroscopeIcon, SearchIcon, BookIcon } from "./Icons";

interface EvaluationTabProps {
  evaluation: EvaluationState;
  resetEvaluation: () => Promise<void>;
  wsReady: boolean;
  showSimulated?: boolean;
  toggleSimulated?: (show: boolean) => Promise<void>;
  simTopology?: SimTopology | null;
  simNodeStates?: SimNodeStates;
  simAttack?: (mode: string, targetNode?: number) => Promise<void>;
  simRelease?: () => Promise<void>;
}

export default function EvaluationTab({ evaluation, resetEvaluation, wsReady, showSimulated, toggleSimulated, simTopology, simNodeStates, simAttack, simRelease }: EvaluationTabProps) {
  const { hybrid_cm, baseline_cm, hybrid_metrics, baseline_metrics, drift_score, drift_history, total_samples, classes } = evaluation;
  const [hoveredCell, setHoveredCell] = useState<{ model: "hybrid" | "baseline"; actual: string; pred: string; count: number } | null>(null);
  const driftSvgRef = useRef<SVGSVGElement>(null);

  // SVG Gauge calculations
  const radius = 40;
  const circumference = 2 * Math.PI * radius; // ~251.3
  const arcLength = circumference * 0.75; // ~188.5 (270 degrees arc)
  const maxDrift = 5.0;
  const currentDrift = Math.min(drift_score, maxDrift);
  const strokeDashoffset = arcLength - (currentDrift / maxDrift) * arcLength;

  // Gauge color classification
  const driftColor = drift_score < 1.5 ? "var(--green)" : drift_score < 3.0 ? "var(--amber)" : "var(--red)";
  const driftLabel = drift_score < 1.5 ? "Nominal" : drift_score < 3.0 ? "Warning" : "Critical Drift";
  const driftClass = drift_score < 1.5 ? "normal" : drift_score < 3.0 ? "warning" : "critical";

  // Drift History SVG Path Generation
  useEffect(() => {
    if (!driftSvgRef.current || drift_history.length < 2) return;
    const W = 500, H = 100, PAD = 20;
    const scores = drift_history.map(d => d.score);
    const maxVal = Math.max(...scores, 3.5); // Ensure threshold 3.0 is visible

    const pts = scores.map((val, idx) => {
      const x = PAD + (idx / (scores.length - 1)) * (W - PAD * 2);
      const y = (H - 10) - (val / maxVal) * (H - PAD * 2);
      return [x, y] as [number, number];
    });

    const linePath = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
    const areaPath = linePath + ` L${pts[pts.length - 1][0]},${H} L${pts[0][0]},${H} Z`;

    const lineEl = driftSvgRef.current.querySelector("#drift-line") as SVGPathElement | null;
    const areaEl = driftSvgRef.current.querySelector("#drift-area") as SVGPathElement | null;
    const color = drift_score < 1.5 ? "#059669" : drift_score < 3.0 ? "#d97706" : "#dc2626";
    const grad = drift_score < 1.5 ? "url(#drift-grad-green)" : drift_score < 3.0 ? "url(#drift-grad-amber)" : "url(#drift-grad-red)";

    if (lineEl) {
      lineEl.setAttribute("d", linePath);
      lineEl.setAttribute("stroke", color);
    }
    if (areaEl) {
      areaEl.setAttribute("d", areaPath);
      areaEl.setAttribute("fill", grad);
    }
  }, [drift_history, drift_score]);

  // Helper to color confusion matrix cells based on correct diagonal vs errors
  const getCellColor = (actualIdx: number, predIdx: number, count: number, maxCount: number) => {
    if (count === 0) return "rgba(0, 0, 0, 0.02)";
    const ratio = maxCount > 0 ? Math.min(count / maxCount, 1.0) : 0;
    
    if (actualIdx === predIdx) {
      // Diagonal (TP) - Green shading
      return `rgba(5, 150, 105, ${0.15 + ratio * 0.75})`;
    } else {
      // Off-diagonal (FP/FN) - Red shading
      return `rgba(220, 38, 38, ${0.15 + ratio * 0.75})`;
    }
  };

  // Helper to color text in confusion matrix cell
  const getCellTextColor = (actualIdx: number, predIdx: number, count: number) => {
    if (count === 0) return "var(--text-3)";
    if (actualIdx === predIdx) {
      return count > (total_samples * 0.05) ? "#ffffff" : "var(--green)";
    } else {
      return "var(--red)";
    }
  };

  // Find maximum count in confusion matrix to normalize cell backgrounds
  const maxHybridCount = useMemo(() => {
    let m = 0;
    hybrid_cm.forEach(row => row.forEach(val => { if (val > m) m = val; }));
    return m;
  }, [hybrid_cm]);

  const maxBaselineCount = useMemo(() => {
    let m = 0;
    baseline_cm.forEach(row => row.forEach(val => { if (val > m) m = val; }));
    return m;
  }, [baseline_cm]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, marginBottom: 20 }}>
      {/* Tab Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h3 style={{ fontSize: 16, fontWeight: 600, color: "var(--text)" }}>Automated Benchmarking & Evaluation</h3>
          <p style={{ fontSize: 12, color: "var(--text-3)" }}>
            Ablation studies comparing the Two-Stage Hybrid Pipeline against a baseline ML Model.
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span style={{ fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-3)" }}>
            Samples Evaluated: <strong>{total_samples}</strong>
          </span>
          <button className="btn btn-secondary" style={{ padding: "6px 12px", display: "inline-flex", alignItems: "center", gap: 6 }} onClick={resetEvaluation}>
            <RefreshIcon width={12} height={12} /> Reset Metrics
          </button>
        </div>
      </div>

      {/* Simulator Toggle */}
      {toggleSimulated && (
        <div className="card" style={{ padding: "12px 18px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", display: "inline-flex", alignItems: "center", gap: 6 }}>
              <MicroscopeIcon width={14} height={14} color="var(--text)" /> 50-Node Simulated Benchmark
            </span>
            <span style={{ fontSize: 11, color: "var(--text-3)" }}>
              Toggle to view large-scale network simulation with attack benchmarking
            </span>
          </div>
          <label style={{ position: "relative", display: "inline-block", width: 44, height: 24, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={showSimulated ?? false}
              onChange={(e) => toggleSimulated(e.target.checked)}
              style={{ opacity: 0, width: 0, height: 0, position: "absolute" }}
            />
            <span style={{
              position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
              borderRadius: 12,
              background: showSimulated ? "var(--green)" : "var(--surface2)",
              border: `1px solid ${showSimulated ? "var(--green)" : "var(--border)"}`,
              transition: "all 0.3s",
            }}>
              <span style={{
                position: "absolute", left: showSimulated ? 22 : 2, top: 2,
                width: 18, height: 18, borderRadius: "50%",
                background: "#fff",
                transition: "left 0.3s",
                boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
              }} />
            </span>
          </label>
        </div>
      )}

      {/* Embedded 50-Node Network when toggled on */}
      {showSimulated && simAttack && simRelease && (
        <Network50Tab
          topology={simTopology ?? null}
          nodeStates={simNodeStates ?? {}}
          simAttack={simAttack}
          simRelease={simRelease}
        />
      )}

      {/* Row 1: Metrics Scorecards */}
      <div className="eval-grid">
        {/* Two-Stage Hybrid Pipeline Scorecard */}
        <div className="card" style={{ borderLeft: "4px solid var(--green)" }}>
          <div className="card-header">
            <span className="card-title">Two-Stage Hybrid Pipeline (Proposed)</span>
            <span className="card-tag green">HYBRID</span>
          </div>
          <div className="card-body">
            <div className="metrics-comparison">
              <div className="metric-box">
                <div className="metric-header">Accuracy</div>
                <div className="metric-value-row">
                  <span className="metric-val">{hybrid_metrics.accuracy}%</span>
                  {total_samples > 0 && (
                    <span className={`metric-delta ${hybrid_metrics.accuracy >= baseline_metrics.accuracy ? "positive" : "negative"}`}>
                      {hybrid_metrics.accuracy >= baseline_metrics.accuracy ? "▲" : "▼"}{" "}
                      {Math.abs(hybrid_metrics.accuracy - baseline_metrics.accuracy).toFixed(1)}%
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 10, color: "var(--text-3)" }}>Overall correct predictions</div>
              </div>
              
              <div className="metric-box">
                <div className="metric-header">Macro-F1 Score</div>
                <div className="metric-value-row">
                  <span className="metric-val">{hybrid_metrics.f1}%</span>
                  {total_samples > 0 && (
                    <span className={`metric-delta ${hybrid_metrics.f1 >= baseline_metrics.f1 ? "positive" : "negative"}`}>
                      {hybrid_metrics.f1 >= baseline_metrics.f1 ? "▲" : "▼"}{" "}
                      {Math.abs(hybrid_metrics.f1 - baseline_metrics.f1).toFixed(1)}%
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 10, color: "var(--text-3)" }}>Balance of Precision & Recall</div>
              </div>

              <div className="metric-box">
                <div className="metric-header">Macro-Precision</div>
                <div className="metric-value-row">
                  <span className="metric-val">{hybrid_metrics.precision}%</span>
                  {total_samples > 0 && (
                    <span className={`metric-delta ${hybrid_metrics.precision >= baseline_metrics.precision ? "positive" : "negative"}`}>
                      {hybrid_metrics.precision >= baseline_metrics.precision ? "▲" : "▼"}{" "}
                      {Math.abs(hybrid_metrics.precision - baseline_metrics.precision).toFixed(1)}%
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 10, color: "var(--text-3)" }}>Ratio of correct alert triggers</div>
              </div>

              <div className="metric-box">
                <div className="metric-header">Macro-Recall</div>
                <div className="metric-value-row">
                  <span className="metric-val">{hybrid_metrics.recall}%</span>
                  {total_samples > 0 && (
                    <span className={`metric-delta ${hybrid_metrics.recall >= baseline_metrics.recall ? "positive" : "negative"}`}>
                      {hybrid_metrics.recall >= baseline_metrics.recall ? "▲" : "▼"}{" "}
                      {Math.abs(hybrid_metrics.recall - baseline_metrics.recall).toFixed(1)}%
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 10, color: "var(--text-3)" }}>Fraction of attacks captured</div>
              </div>
            </div>
          </div>
        </div>

        {/* Baseline ML Model Scorecard */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Baseline Ensemble ML Model</span>
            <span className="card-tag blue">BASELINE</span>
          </div>
          <div className="card-body">
            <div className="metrics-comparison">
              <div className="metric-box">
                <div className="metric-header">Accuracy</div>
                <div className="metric-value-row">
                  <span className="metric-val">{baseline_metrics.accuracy}%</span>
                </div>
                <div style={{ fontSize: 10, color: "var(--text-3)" }}>Standard ensemble predictions</div>
              </div>

              <div className="metric-box">
                <div className="metric-header">Macro-F1 Score</div>
                <div className="metric-value-row">
                  <span className="metric-val">{baseline_metrics.f1}%</span>
                </div>
                <div style={{ fontSize: 10, color: "var(--text-3)" }}>Standard F1 benchmark</div>
              </div>

              <div className="metric-box">
                <div className="metric-header">Macro-Precision</div>
                <div className="metric-value-row">
                  <span className="metric-val">{baseline_metrics.precision}%</span>
                </div>
                <div style={{ fontSize: 10, color: "var(--text-3)" }}>False positive benchmark</div>
              </div>

              <div className="metric-box">
                <div className="metric-header">Macro-Recall</div>
                <div className="metric-value-row">
                  <span className="metric-val">{baseline_metrics.recall}%</span>
                </div>
                <div style={{ fontSize: 10, color: "var(--text-3)" }}>Vulnerable to low-frequency attacks</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Confusion Matrices */}
      <div className="eval-grid">
        {/* Hybrid CM */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Two-Stage Hybrid Confusion Matrix</span>
            <span className="card-tag green">7 x 7</span>
          </div>
          <div className="card-body">
            <div className="matrix-container">
              <div className="matrix-grid-wrap">
                {/* Header corner */}
                <div className="matrix-label-y" style={{ fontSize: 8, color: "var(--text-3)" }}>ACTUAL \ PRED</div>
                {classes.map(c => (
                  <div key={`hx-${c}`} className="matrix-label-x" title={c}>{c.replace(/_ATTACK/g, "").replace(/_FLOOD/g, "")}</div>
                ))}

                {classes.map((actual, aIdx) => (
                  <React.Fragment key={`hr-${actual}`}>
                    <div className="matrix-label-y">{actual.replace(/_ATTACK/g, "").replace(/_FLOOD/g, "")}</div>
                    {classes.map((pred, pIdx) => {
                      const val = hybrid_cm[aIdx]?.[pIdx] ?? 0;
                      return (
                        <div
                          key={`hc-${actual}-${pred}`}
                          className="matrix-cell"
                          style={{
                            backgroundColor: getCellColor(aIdx, pIdx, val, maxHybridCount),
                            color: getCellTextColor(aIdx, pIdx, val)
                          }}
                          onMouseEnter={() => setHoveredCell({ model: "hybrid", actual, pred, count: val })}
                          onMouseLeave={() => setHoveredCell(null)}
                        >
                          {val > 0 ? val : "—"}
                        </div>
                      );
                    })}
                  </React.Fragment>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Baseline CM */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Baseline ML Confusion Matrix</span>
            <span className="card-tag blue">7 x 7</span>
          </div>
          <div className="card-body">
            <div className="matrix-container">
              <div className="matrix-grid-wrap">
                {/* Header corner */}
                <div className="matrix-label-y" style={{ fontSize: 8, color: "var(--text-3)" }}>ACTUAL \ PRED</div>
                {classes.map(c => (
                  <div key={`bx-${c}`} className="matrix-label-x" title={c}>{c.replace(/_ATTACK/g, "").replace(/_FLOOD/g, "")}</div>
                ))}

                {classes.map((actual, aIdx) => (
                  <React.Fragment key={`br-${actual}`}>
                    <div className="matrix-label-y">{actual.replace(/_ATTACK/g, "").replace(/_FLOOD/g, "")}</div>
                    {classes.map((pred, pIdx) => {
                      const val = baseline_cm[aIdx]?.[pIdx] ?? 0;
                      return (
                        <div
                          key={`bc-${actual}-${pred}`}
                          className="matrix-cell"
                          style={{
                            backgroundColor: getCellColor(aIdx, pIdx, val, maxBaselineCount),
                            color: getCellTextColor(aIdx, pIdx, val)
                          }}
                          onMouseEnter={() => setHoveredCell({ model: "baseline", actual, pred, count: val })}
                          onMouseLeave={() => setHoveredCell(null)}
                        >
                          {val > 0 ? val : "—"}
                        </div>
                      );
                    })}
                  </React.Fragment>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Hover Info Banner */}
      <div style={{ height: 32, display: "flex", alignItems: "center", justifyContent: "center" }}>
        {hoveredCell ? (
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "4px 14px", fontSize: 11.5, fontFamily: "var(--mono)", color: "var(--text-2)", display: "inline-flex", alignItems: "center", gap: 6 }}>
            <SearchIcon width={12} height={12} color="var(--text-2)" /> <strong>{hoveredCell.model.toUpperCase()} MODEL:</strong> Actual: <strong>{hoveredCell.actual}</strong> &nbsp;·&nbsp; Predicted: <strong>{hoveredCell.pred}</strong> &nbsp;·&nbsp; Count: <strong style={{ color: hoveredCell.actual === hoveredCell.pred ? "var(--green)" : "var(--red)" }}>{hoveredCell.count} samples</strong>
          </div>
        ) : (
          <div style={{ fontSize: 11, color: "var(--text-3)" }}>Hover over matrix cells to view mapping breakdowns.</div>
        )}
      </div>

      {/* Row 3: Concept Drift Analysis */}
      <div className="eval-grid">
        {/* Drift Gauge */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Concept Drift Monitor</span>
            <span className="card-tag blue">LIVE GA UGE</span>
          </div>
          <div className="card-body">
            <div className="drift-gauge-container">
              <svg width="150" height="110" viewBox="0 0 100 80">
                <defs>
                  <linearGradient id="gauge-grad" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="var(--green)" />
                    <stop offset="60%" stopColor="var(--amber)" />
                    <stop offset="100%" stopColor="var(--red)" />
                  </linearGradient>
                </defs>
                {/* Background arc */}
                <path
                  d="M20,70 A35,35 0 0,1 80,70"
                  fill="none"
                  stroke="var(--border)"
                  strokeWidth="8"
                  strokeLinecap="round"
                />
                {/* Foreground colored arc */}
                <path
                  d="M20,70 A35,35 0 0,1 80,70"
                  fill="none"
                  stroke="url(#gauge-grad)"
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray="164.9"
                  strokeDashoffset={strokeDashoffset * (164.9 / 188.5)} /* Scale to fits 35r arc length */
                  style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1)" }}
                />
                {/* Dial needle pointing to val */}
                {(() => {
                  const angle = 210 - (currentDrift / maxDrift) * 240; // Map [0, 5] to [210deg, -30deg]
                  const rad = (angle * Math.PI) / 180;
                  const x = 50 + 28 * Math.cos(rad);
                  const y = 70 - 28 * Math.sin(rad);
                  return (
                    <line
                      x1="50"
                      y1="70"
                      x2={x.toFixed(2)}
                      y2={y.toFixed(2)}
                      stroke="var(--text)"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                    />
                  );
                })()}
                {/* Center peg */}
                <circle cx="50" cy="70" r="4" fill="var(--text)" />
              </svg>
              <div className="drift-gauge-value" style={{ color: driftColor }}>
                {drift_score.toFixed(2)}
              </div>
              <div className="drift-gauge-label">Baseline Feature Deviation (Z-score)</div>
              <div className={`drift-status-pill ${driftClass}`}>{driftLabel.toUpperCase()}</div>
            </div>
          </div>
        </div>

        {/* Drift History */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Concept Drift History Trend</span>
            <span className="card-tag blue">TIME-SERIES</span>
          </div>
          <div className="card-body">
            <div style={{ position: "relative", height: "120px", width: "100%" }}>
              <svg ref={driftSvgRef} id="drift-svg" width="100%" height="100%" viewBox="0 0 500 100" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="drift-grad-green" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#059669" stopOpacity="0.18" />
                    <stop offset="100%" stopColor="#059669" stopOpacity="0" />
                  </linearGradient>
                  <linearGradient id="drift-grad-amber" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#d97706" stopOpacity="0.18" />
                    <stop offset="100%" stopColor="#d97706" stopOpacity="0" />
                  </linearGradient>
                  <linearGradient id="drift-grad-red" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#dc2626" stopOpacity="0.18" />
                    <stop offset="100%" stopColor="#dc2626" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {/* Normal drift bounds indicators */}
                <line x1="0" y1="70" x2="500" y2="70" stroke="var(--border)" strokeWidth="0.8" strokeDasharray="3,3" />
                <text x="5" y="66" fontFamily="var(--mono)" fontSize="7" fill="var(--text-3)">Warning (1.5)</text>
                <line x1="0" y1="40" x2="500" y2="40" stroke="var(--red-mid)" strokeWidth="0.8" strokeDasharray="3,3" />
                <text x="5" y="36" fontFamily="var(--mono)" fontSize="7" fill="var(--red)">Critical (3.0)</text>
                
                {/* Chart elements filled dynamically */}
                <path id="drift-area" d="" />
                <path id="drift-line" d="" fill="none" strokeWidth="1.5" />
              </svg>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 10, color: "var(--text-3)", fontFamily: "var(--mono)" }}>
              <span>{drift_history.length > 0 ? drift_history[0].time : "—"}</span>
              <span>Live Drift Tracking</span>
              <span>{drift_history.length > 0 ? drift_history[drift_history.length - 1].time : "—"}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Conference Paper Rationale note */}
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "14px 18px", fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.6, display: "flex", gap: 10, alignItems: "flex-start" }}>
        <BookIcon width={18} height={18} color="var(--text-3)" style={{ marginTop: 2, flexShrink: 0 }} />
        <div>
          <strong>Academic Ablation & Drift Rationale:</strong> Traditional IoT classifiers struggle when network payloads or rate frequencies shift. NetGuard's <strong>Two-Stage Architecture</strong> handles drift (poisoning / rate timing) using Stage 1 statistical logic, resulting in higher overall classification accuracy and zero-shot robustness even when baseline features drift significantly.
        </div>
      </div>
    </div>
  );
}
