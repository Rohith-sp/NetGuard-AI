"use client";
import type { NodeData, PacketEntry, AlertEntry, MLState } from "../hooks/useLiveData";

const ATTACKS = ["DOS_FLOOD", "REPLAY_ATTACK", "SLOW_RATE_ATTACK", "DATA_POISON", "TOPIC_BOMB", "EVASION_ATTACK"];

function sevClass(s: string) {
  return s === "CRITICAL" ? "sev-critical" : s === "HIGH" ? "sev-high" : s === "MEDIUM" ? "sev-medium" : "sev-low";
}
function labelClass(l: string) {
  return l === "LEGITIMATE" ? "legit" : l === "DOS_FLOOD" ? "dos" : l === "REPLAY_ATTACK" ? "replay" : l === "SLOW_RATE_ATTACK" ? "slow" : l === "DATA_POISON" ? "poison" : l === "TOPIC_BOMB" ? "bomb" : l === "EVASION_ATTACK" ? "evasion" : "normal";
}
// Translate raw mode to a neutral public-facing label
function publicLabel(l: string, device: string): string {
  if (device === "netguard/attacker") {
    if (l === "DOS_FLOOD")         return "HIGH-FREQ";
    if (l === "REPLAY_ATTACK")     return "REPEAT-TX";
    if (l === "SLOW_RATE_ATTACK")  return "LOW-FREQ";
    if (l === "DATA_POISON")       return "SPOOFING";
    if (l === "TOPIC_BOMB")        return "OVERLOAD";
    if (l === "EVASION_ATTACK")    return "EVASION";
    if (l === "NORMAL")            return "LEGITIMATE";
  }
  return l;
}
// Translate device topic to public device name
function publicDevice(d: string): string {
  if (d === "netguard/attacker") return "netguard/device3";
  return d;
}

// ── KPI Row ───────────────────────────────────────────────────────────────────
export function KpiRow({ totalPkts, alertCount, anomaly, nodesOnline }: { totalPkts: number; alertCount: number; anomaly: number; nodesOnline: number }) {
  return (
    <div className="kpi-row">
      <div className="kpi-card">
        <div className="kpi-header"><span className="kpi-label">Total Packets</span><div className="kpi-icon" style={{ background: "#ecfdf5" }}>📦</div></div>
        <div className="kpi-value green">{totalPkts.toLocaleString()}</div>
        <div className="kpi-meta">packets captured this session</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-header"><span className="kpi-label">Alerts Fired</span><div className="kpi-icon" style={{ background: "#fef2f2" }}>🔴</div></div>
        <div className="kpi-value red">{alertCount}</div>
        <div className="kpi-meta">intrusion events detected</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-header"><span className="kpi-label">Anomaly Score</span><div className="kpi-icon" style={{ background: "#fffbeb" }}>📊</div></div>
        <div className="kpi-value amber">{anomaly.toFixed(0)}%</div>
        <div className="kpi-meta">{anomaly > 50 ? "⚠ above threat threshold" : "within normal baseline"}</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-header"><span className="kpi-label">Nodes Online</span><div className="kpi-icon" style={{ background: "#eff6ff" }}>🟢</div></div>
        <div className="kpi-value">{nodesOnline}/3</div>
        <div className="kpi-meta">ESP32 devices connected</div>
      </div>
    </div>
  );
}

// ── Node Cards ─────────────────────────────────────────────────────────────────
export function NodeRow({ n1, n2, n3, ml }: { n1: NodeData; n2: NodeData; n3: NodeData; ml: MLState }) {
  const isAttack = ATTACKS.includes(ml.label);
  return (
    <div className="node-row">
      {/* DHT Node */}
      <div className="node-card">
        <div className="node-header">
          <div><div className="node-id">ESP32_1 · DHT22</div><div className="node-ip">netguard/device1</div></div>
          <div className="node-status">
            <div className={`status-dot ${n1.online ? "green" : "offline"}`} />
            <span style={{ color: n1.online ? "var(--green)" : "var(--text-3)", fontWeight: 500, fontSize: 12 }}>{n1.online ? "Normal" : "Offline"}</span>
          </div>
        </div>
        <div className="node-body">
          <div className="node-stat-row"><span className="node-stat-label">Temperature</span><span className="node-stat-value">{n1.temp != null ? `${n1.temp.toFixed(1)} °C` : "—"}</span></div>
          <div className="node-stat-row"><span className="node-stat-label">Humidity</span><span className="node-stat-value">{n1.humidity != null ? `${n1.humidity.toFixed(1)}%` : "—"}</span></div>
          <div className="node-stat-row"><span className="node-stat-label">Packet rate</span><span className="node-stat-value">{n1.pktRate} pkt/s</span></div>
          <div className="trust-bar-wrap">
            <span className="trust-bar-label">Trust</span>
            <div className="trust-bar-track"><div className="trust-bar-fill" style={{ width: `${n1.trust}%`, background: "var(--green)" }} /></div>
            <span className="trust-bar-val">{n1.trust}%</span>
          </div>
        </div>
      </div>

      {/* LDR Node */}
      <div className="node-card">
        <div className="node-header">
          <div><div className="node-id">ESP32_2 · LDR</div><div className="node-ip">netguard/device2</div></div>
          <div className="node-status">
            <div className={`status-dot ${n2.online ? "green" : "offline"}`} />
            <span style={{ color: n2.online ? "var(--green)" : "var(--text-3)", fontWeight: 500, fontSize: 12 }}>{n2.online ? "Normal" : "Offline"}</span>
          </div>
        </div>
        <div className="node-body">
          <div className="node-stat-row"><span className="node-stat-label">Light level</span><span className="node-stat-value">{n2.light != null ? `${n2.light} LUX` : "—"}</span></div>
          <div className="node-stat-row"><span className="node-stat-label">Cycle phase</span><span className="node-stat-value">{(n2.light ?? 0) > 500 ? "Daytime ☀" : "Nighttime 🌙"}</span></div>
          <div className="node-stat-row"><span className="node-stat-label">Packet rate</span><span className="node-stat-value">{n2.pktRate} pkt/s</span></div>
          <div className="trust-bar-wrap">
            <span className="trust-bar-label">Trust</span>
            <div className="trust-bar-track"><div className="trust-bar-fill" style={{ width: `${n2.trust}%`, background: "var(--green)" }} /></div>
            <span className="trust-bar-val">{n2.trust}%</span>
          </div>
        </div>
      </div>

      {/* MQ135 Gas Sensor (Attacker Node) */}
      <div className="node-card">
        <div className="node-header">
          <div><div className="node-id">ESP32_3 · MQ135 Gas</div><div className="node-ip">netguard/device3</div></div>
          <div className="node-status">
            <div className={`status-dot ${n3.online ? "green" : "offline"}`} />
            <span style={{ color: n3.online ? "var(--green)" : "var(--text-3)", fontWeight: 500, fontSize: 12 }}>
              {n3.online ? "Active" : "Offline"}
            </span>
          </div>
        </div>
        <div className="node-body">
          <div className="node-stat-row"><span className="node-stat-label">Gas Level (PPM)</span><span className="node-stat-value">{n3.gas_ppm != null ? `${n3.gas_ppm} PPM` : "—"}</span></div>
          <div className="node-stat-row" style={{ marginTop: -4 }}><span className="node-stat-label" style={{ fontSize: 10, color: "var(--text-3)" }}>AI Analysis</span><span className="node-stat-value" style={{ fontSize: 10, color: "var(--amber)", fontWeight: 600, textAlign: "right", maxWidth: "65%", lineHeight: 1.2 }}>{n3.gas_explanation ?? "Waiting for Groq..."}</span></div>
          <div className="node-stat-row"><span className="node-stat-label">Packet rate</span><span className="node-stat-value">{n3.pktRate} pkt/s</span></div>
          <div className="trust-bar-wrap">
            <span className="trust-bar-label">Trust</span>
            <div className="trust-bar-track"><div className="trust-bar-fill" style={{ width: `${n3.trust}%`, background: n3.trust < 40 ? "var(--red)" : n3.trust < 70 ? "var(--amber)" : "var(--green)" }} /></div>
            <span className="trust-bar-val">{n3.trust}%</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Network Analyzer (ML + SHAP Force Plot) ───────────────────────────────────
export function MLPanel({ ml }: { ml: MLState }) {
  const top5   = (ml.shap ?? []).slice(0, 5);
  const maxAbs = top5.length ? Math.max(...top5.map(s => Math.abs(s.value)), 0.001) : 1;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Network Analyzer</span>
        <span className={`card-tag ${ml.isAttack ? "red" : "green"}`}>
          {ml.label === "AWAITING" ? "AWAITING" : ml.isAttack ? "THREAT" : "NORMAL"}
        </span>
      </div>
      <div className="card-body">
        {/* Classification result */}
        <div className={`ml-class-display ${ml.isAttack ? "threat" : ""}`}>
          <div>
            <div className="ml-class-name">{ml.label}</div>
            <div className="ml-conf-pct">{ml.confidence}% confidence</div>
            <div className="ml-conf-bar-wrap" style={{ width: 140, marginTop: 6 }}>
              <div className="ml-conf-bar" style={{ width: `${ml.confidence}%`, background: ml.isAttack ? "var(--red)" : "var(--green)" }} />
            </div>
          </div>
        </div>

        {/* SHAP Force Plot */}
        {top5.length > 0 ? (
          <div className="shap-section">
            <div className="shap-title">Feature Importance (SHAP)</div>
            {top5.map((s, i) => {
              const pct = Math.abs(s.value) / maxAbs * 100;
              const pos = s.value > 0;
              return (
                <div key={i} className="shap-row">
                  <div className="shap-feat-name" title={s.feature}>{s.feature.replace(/_/g, " ")}</div>
                  <div className="shap-bar-track">
                    <div className={`shap-bar-fill ${pos ? "shap-pos" : "shap-neg"}`} style={{ width: `${pct}%` }} />
                  </div>
                  <div className="shap-raw">{s.raw}</div>
                  <div className={`shap-val ${pos ? "shap-val-pos" : "shap-val-neg"}`}>
                    {pos ? "+" : ""}{s.value.toFixed(3)}
                  </div>
                </div>
              );
            })}
            <div className="shap-legend">
              <span className="shap-leg-dot shap-pos-dot" /> Toward attack &nbsp;&nbsp;
              <span className="shap-leg-dot shap-neg-dot" /> Toward normal
            </div>
          </div>
        ) : (
          <div className="ml-features">
            <div className="ml-feat"><div className="ml-feat-name">pkt_rate</div><div className={`ml-feat-value ${ml.pktRate > 10 ? "anomalous" : ""}`}>{ml.pktRate.toFixed(1)}</div></div>
            <div className="ml-feat"><div className="ml-feat-name">iat_mean (ms)</div><div className={`ml-feat-value ${ml.iatMean > 0 && ml.iatMean < 500 ? "anomalous" : ""}`}>{ml.iatMean}</div></div>
            <div className="ml-feat"><div className="ml-feat-name">dup_ratio</div><div className={`ml-feat-value ${ml.dupRatio > 0.5 ? "anomalous" : ""}`}>{ml.dupRatio.toFixed(2)}</div></div>
            <div className="ml-feat"><div className="ml-feat-name">seq_gap</div><div className={`ml-feat-value ${ml.seqGap === 0 ? "anomalous" : ""}`}>{ml.seqGap}</div></div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Device Heatmap ────────────────────────────────────────────────────────────
export function HeatmapPanel({ n1, n2, n3, ml }: { n1: NodeData; n2: NodeData; n3: NodeData; ml: MLState }) {
  const cells = [
    { id: "ESP32_1", icon: "🌡", label: "DHT22 Sensor", online: n1.online, trust: n1.trust,
      metric: `${n1.temp?.toFixed(1) ?? "—"}°C`, sub: `Humidity ${n1.humidity?.toFixed(0) ?? "—"}%`,
      threat: n1.trust < 40, warn: n1.trust < 70 },
    { id: "ESP32_2", icon: "💡", label: "LDR Sensor", online: n2.online, trust: n2.trust,
      metric: `${n2.light ?? "—"} LUX`, sub: (n2.light ?? 0) > 500 ? "Daytime ☀" : "Nighttime 🌙",
      threat: n2.trust < 40, warn: n2.trust < 70 },
    { id: "ESP32_3", icon: "💨", label: "MQ135 Gas", online: n3.online, trust: n3.trust,
      metric: `${n3.gas_ppm ?? "—"} PPM`, sub: ml.isAttack ? ml.label.replace(/_/g, " ") : "Monitoring",
      threat: ml.isAttack || n3.trust < 40, warn: n3.trust < 70 },
  ];
  const atRisk = cells.filter(c => c.threat).length;

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Device Threat Heatmap</span>
        <span className={`card-tag ${atRisk > 0 ? "red" : "green"}`}>
          {atRisk > 0 ? `${atRisk} node${atRisk > 1 ? "s" : ""} at risk` : "All clear"}
        </span>
      </div>
      <div className="heatmap-grid">
        {cells.map(c => (
          <div key={c.id} className={`heatmap-cell ${!c.online ? "heatmap-offline" : c.threat ? "heatmap-threat" : c.warn ? "heatmap-warn" : "heatmap-ok"}`}>
            <div className="heatmap-icon">{c.icon}</div>
            <div className="heatmap-id">{c.id}</div>
            <div className="heatmap-label">{c.label}</div>
            <div className="heatmap-metric">{c.online ? c.metric : "Offline"}</div>
            <div className="heatmap-sub">{c.online ? c.sub : "—"}</div>
            <div className="heatmap-trust-bar">
              <div className="heatmap-trust-fill" style={{ width: `${c.trust}%`, background: c.threat ? "var(--red)" : c.warn ? "var(--amber)" : "var(--green)" }} />
            </div>
            <div className="heatmap-trust-pct">{c.trust}%</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Alert Log ─────────────────────────────────────────────────────────────────
export function AlertLog({ alerts }: { alerts: AlertEntry[] }) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Alert Log</span>
        {alerts.length > 0 && <span className="card-tag red">{alerts.length} active</span>}
      </div>
      <div className="alert-list">
        {alerts.length === 0
          ? <div style={{ padding: "24px 16px", textAlign: "center", color: "var(--text-3)", fontSize: 13 }}>No alerts — network is clean ✓</div>
          : alerts.map(a => (
            <div key={a.id} className="alert-item">
              <span className={`alert-sev ${sevClass(a.severity)}`}>{a.severity}</span>
              <div><div className="alert-title">{a.title}</div><div className="alert-meta">{a.time} · {a.meta}</div></div>
            </div>
          ))}
      </div>
    </div>
  );
}

// ── Packet Feed ────────────────────────────────────────────────────────────────
export function PacketFeed({ packets, totalPkts }: { packets: PacketEntry[]; totalPkts: number }) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Live Packet Feed</span>
        <span style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--mono)" }}>{totalPkts} packets</span>
      </div>
      <div className="feed-header"><span>Time</span><span>Label</span><span>Device</span><span style={{ textAlign: "right" }}>IAT (ms)</span></div>
      <div className="feed-list">
        {packets.length === 0
          ? <div style={{ padding: 24, textAlign: "center", color: "var(--text-3)", fontSize: 13 }}>Waiting for packets…</div>
          : packets.map(p => (
            <div key={p.id} className={`feed-entry ${p.label !== "LEGITIMATE" && p.label !== "NORMAL" ? "attack" : ""}`}>
              <span className="feed-time">{p.time}</span>
              <span className={`feed-label ${labelClass(p.label)}`}>{publicLabel(p.label, p.device)}</span>
              <span className="feed-device">{publicDevice(p.device)}</span>
              <span className="feed-iat">{p.iat > 0 ? p.iat.toLocaleString() : "—"}</span>
            </div>
          ))}
      </div>
    </div>
  );
}
