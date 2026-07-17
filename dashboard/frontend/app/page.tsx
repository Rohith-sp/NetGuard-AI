"use client";
import { useState, useEffect } from "react";
import { useLiveData } from "./hooks/useLiveData";
import { AnomalyGraph, PktRateGraph } from "./components/Graphs";
import { KpiRow, NodeRow, MLPanel, AlertLog, PacketFeed, HeatmapPanel } from "./components/Panels";
import TopologyTab, { type SimKey } from "./components/TopologyTab";
import AnalyticsTab from "./components/AnalyticsTab";
import IncidentReport from "./components/IncidentReport";
import GlobalImportanceChart from "./components/GlobalImportanceChart";

function renderMarkdown(text: string) {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`([^`]+)`/g, "<code class='mono-code'>$1</code>");
  html = html.replace(/^###\s+([^\n]+)/gm, "<h4 class='chat-h4'>$1</h4>");
  html = html.replace(/^\*\s+([^\n]+)/gm, "<li class='chat-li'>$1</li>");
  html = html.replace(/\n/g, "<br />");
  return { __html: html };
}

export default function Page() {
  const { nodes, packets, alerts, temporal, sensorTemporal, ml, incident, totalPkts, wsReady, triggerAttack, simulate } = useLiveData();
  const [tab, setTab] = useState<"overview" | "analytics" | "topology" | "chat" | "working">("analytics");
  const simKey = (nodes.esp32_3?.mode as SimKey) || "NORMAL";
  const [clock, setClock]         = useState("—");
  const [chatMsgs, setChatMsgs]   = useState([{ from: "AI", text: "NetGuard AI online. Ask me about the current network state." }]);
  const [chatInput, setChatInput] = useState("");

  useEffect(() => {
    const t = setInterval(() => setClock(new Date().toLocaleTimeString("en-GB")), 1000);
    return () => clearInterval(t);
  }, []);

  const latestAnomaly  = temporal.at(-1)?.anomaly ?? 0;
  const anomalyTagCls  = latestAnomaly > 70 ? "red" : latestAnomaly > 30 ? "amber" : "green";
  const anomalyLabel   = latestAnomaly > 70 ? "CRITICAL" : latestAnomaly > 30 ? "SUSPICIOUS" : "NORMAL";
  const nodesOnline    = Object.values(nodes).filter(n => n.online).length;

  async function sendChat(overrideText?: string) {
    const q = (typeof overrideText === "string" ? overrideText : chatInput).trim();
    if (!q) return;
    setChatMsgs(m => [...m, { from: "You", text: q }, { from: "AI", text: "Thinking..." }]);
    setChatInput("");

    try {
      const apiKey = process.env.NEXT_PUBLIC_NETGUARD_API_KEY || "";
      const res = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
        body: JSON.stringify({ question: q }),
      });
      const data = await res.json();
      setChatMsgs(m => {
        const next = [...m];
        if (next.length > 0 && next[next.length - 1].text === "Thinking...") {
          next[next.length - 1] = { from: "AI", text: data.reply || "No response received." };
        } else {
          next.push({ from: "AI", text: data.reply || "No response received." });
        }
        return next;
      });
    } catch (err) {
      console.error("[Chat] Error:", err);
      setChatMsgs(m => {
        const next = [...m];
        if (next.length > 0 && next[next.length - 1].text === "Thinking...") {
          next[next.length - 1] = { from: "AI", text: "⚠️ Failed to connect to NetGuard AI Analyst backend." };
        } else {
          next.push({ from: "AI", text: "⚠️ Failed to connect to NetGuard AI Analyst backend." });
        }
        return next;
      });
    }
  }



  return (
    <>
      {/* HEADER */}
      <header className="header">
        <div className="header-logo">
          <div className="logo-mark">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ width: 16, height: 16 }}>
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <div>
            <div className="logo-text">NetGuard AI</div>
            <div className="logo-sub">Security Operations Center</div>
          </div>
        </div>
        <nav className="header-nav">
          <span className={`nav-item ${tab === "analytics" ? "active" : ""}`} onClick={() => setTab("analytics")}>Live Analytics</span>
          <span className={`nav-item ${tab === "overview"  ? "active" : ""}`} onClick={() => setTab("overview")}>Overview</span>
          <span className={`nav-item ${tab === "topology"  ? "active" : ""}`} onClick={() => setTab("topology")}>Topology</span>
          <span className={`nav-item ${tab === "working"   ? "active" : ""}`} onClick={() => setTab("working")}>Working</span>
          <span className={`nav-item ${tab === "chat"      ? "active" : ""}`} onClick={() => setTab("chat")}>AI Analyst</span>
        </nav>
        <div className="header-right">
          {alerts.length > 0 && <div className="alert-pill">⚠ {alerts.length} alerts</div>}
          <div className="live-pill"><div className="live-dot" />{wsReady ? "Live" : "Connecting…"}</div>
          <div className="clock">{clock}</div>
        </div>
      </header>

      <main className="main">
        <div className="page-title-row">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
            <div>
              <div className="page-title">{tab === "analytics" ? "Live Sensor Analytics" : tab === "overview" ? "Network Overview" : tab === "topology" ? "Network Topology" : tab === "working" ? "System Architecture" : "AI Security Analyst"}</div>
              <div className="page-subtitle">{tab === "analytics" ? "Real-time temperature, humidity & light readings from your IoT nodes" : tab === "working" ? "End-to-end hybrid pipeline — how NetGuard AI detects intrusions" : "Active Fleet · 3 Edge Nodes Monitored"}</div>
            </div>
            {simKey !== "NORMAL" && (
              <span className="demo-active-pill" style={{ background: "var(--red-bg)", color: "var(--red)", borderColor: "var(--red)", fontSize: "11px", padding: "4px 10px" }}>
                ⚠ {simKey.replace(/_/g, " ")} ACTIVE
              </span>
            )}
          </div>
        </div>

        {/* ── OVERVIEW ──────────────────────────────────────────────────── */}
        {tab === "overview" && (
          <>
            <KpiRow totalPkts={totalPkts} alertCount={alerts.length} anomaly={latestAnomaly} nodesOnline={nodesOnline} />

            <div className="section-divider">Device Status</div>
            <NodeRow n1={nodes.esp32_1} n2={nodes.esp32_2} n3={nodes.esp32_3} ml={ml} />

            <div className="grid-main">
              <div className="grid-left">
                {/* Anomaly Graph */}
                <div className="card">
                  <div className="card-header">
                    <span className="card-title">Temporal Anomaly Score</span>
                    <span className={`card-tag ${anomalyTagCls}`}>{anomalyLabel}</span>
                  </div>
                  <div className="card-body" style={{ paddingTop: 10, paddingBottom: 10 }}>
                    <AnomalyGraph data={temporal} />
                  </div>
                </div>

                {/* Packet Rate */}
                <div className="card">
                  <div className="card-header">
                    <span className="card-title">Packet Rate — All Nodes</span>
                    <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--text-3)", fontFamily: "var(--mono)" }}>
                      <span style={{ color: "var(--green)" }}>— ESP32_1</span>
                      <span style={{ color: "#2563eb" }}>— ESP32_2</span>
                      <span style={{ color: "var(--red)" }}>— ESP32_3</span>
                    </div>
                  </div>
                  <div className="card-body" style={{ paddingTop: 10, paddingBottom: 10 }}>
                    <PktRateGraph data={temporal} />
                  </div>
                </div>

                <PacketFeed packets={packets} totalPkts={totalPkts} />
              </div>

              <div className="grid-right">
                <MLPanel ml={ml} />
                {incident.text && <IncidentReport incident={incident} />}
                <GlobalImportanceChart />
                <HeatmapPanel n1={nodes.esp32_1} n2={nodes.esp32_2} n3={nodes.esp32_3} ml={ml} />
                <AlertLog alerts={alerts} />
              </div>
            </div>
          </>
        )}

        {/* ── ANALYTICS TAB ─────────────────────────────────────────────── */}
        {tab === "analytics" && (
          <AnalyticsTab data={sensorTemporal} n1={nodes.esp32_1} n2={nodes.esp32_2} n3={nodes.esp32_3} />
        )}

        {/* ── TOPOLOGY TAB ──────────────────────────────────────────────── */}
        {tab === "topology" && (
          <div className="card" style={{ padding: 24 }}>
            <TopologyTab
              n1={nodes.esp32_1} n2={nodes.esp32_2} n3={nodes.esp32_3}
              ml={ml} wsReady={wsReady}
              simulate={simulate}
              triggerAttack={triggerAttack}
              simKey={simKey}
            />
          </div>
        )}
        {/* ── WORKING TAB ───────────────────────────────────────────────── */}
        {tab === "working" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20, marginBottom: 20 }}>

            {/* Pipeline Overview */}
            <div className="card">
              <div className="card-header">
                <span className="card-title">Two-Stage Hybrid Detection Pipeline</span>
                <span className="card-tag blue">ARCHITECTURE</span>
              </div>
              <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <p style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.7, margin: 0 }}>
                  NetGuard AI uses a <strong>Two-Stage Hybrid Pipeline</strong> to overcome the limitations of purely flow-based ML. Every 5 seconds, incoming MQTT traffic is passed through both stages in order.
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                  {[
                    { stage: "Stage 1", name: "Statistical Profiler", color: "var(--amber)", desc: "Unsupervised EMA Z-Score anomaly detection on payload values. Catches Data Poisoning & Slow Rate attacks that fool flow-based ML.", tags: ["Z-Score > 3.0", "EMA Baseline", "IAT Tracking"] },
                    { stage: "Stage 2", name: "Random Forest ML", color: "var(--blue)", desc: "7-class Random Forest classifier trained on 9 flow features extracted from a sliding 10-second packet window. Catches DoS, Replay, Evasion & Topic Bomb.", tags: ["9 Features", "SHAP Values", "7 Classes"] },
                  ].map(s => (
                    <div key={s.stage} style={{ background: "var(--surface2)", border: `1px solid color-mix(in srgb, ${s.color} 30%, var(--border))`, borderRadius: "var(--radius)", padding: "16px 18px" }}>
                      <div style={{ fontSize: 10, fontWeight: 600, color: s.color, textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 4 }}>{s.stage}</div>
                      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", marginBottom: 8 }}>{s.name}</div>
                      <div style={{ fontSize: 12, color: "var(--text-2)", lineHeight: 1.6, marginBottom: 12 }}>{s.desc}</div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {s.tags.map(t => <span key={t} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 20, background: `color-mix(in srgb, ${s.color} 10%, var(--surface))`, color: s.color, border: `1px solid color-mix(in srgb, ${s.color} 25%, transparent)` }}>{t}</span>)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Attack Detection Matrix */}
            <div className="card">
              <div className="card-header">
                <span className="card-title">Attack Detection Strategy Matrix</span>
                <span className="card-tag green">7 ATTACK CLASSES</span>
              </div>
              <div className="card-body">
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                        {["Attack Class", "Detection Stage", "Key Indicator", "ML Limitation", "Solution"].map(h => (
                          <th key={h} style={{ padding: "8px 12px", textAlign: "left", color: "var(--text-3)", fontWeight: 600, fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { cls: "DOS Flood",         stage: "ML Stage 2",     color: "var(--red)",    ind: "packet_rate > 10/s",          lim: "None — detects easily",         sol: "Random Forest (97% conf.)" },
                        { cls: "Replay Attack",     stage: "ML Stage 2",     color: "var(--amber)",  ind: "duplicate_ratio > 0.8",        lim: "None — detects easily",         sol: "Random Forest (91% conf.)" },
                        { cls: "Topic Bomb",        stage: "ML Stage 2",     color: "var(--purple)", ind: "packet_rate > 50/s",           lim: "None — detects easily",         sol: "Random Forest (89% conf.)" },
                        { cls: "Evasion Attack",    stage: "ML Stage 2",     color: "var(--cyan)",   ind: "std_inter_arrival_ms spike",   lim: "Low confidence (~58%)",         sol: "RF on timing variance" },
                        { cls: "Slow Rate Attack",  stage: "Profiler Stage 1",color: "var(--blue)",  ind: "median IAT > 10,000ms",        lim: "10s window goes empty (blind)", sol: "Global packet IAT tracker" },
                        { cls: "Data Poisoning",    stage: "Profiler Stage 1",color: "var(--green)", ind: "Z-Score > 3.0 on payload",     lim: "Normal timing — invisible",     sol: "EMA Z-Score on temp/payload" },
                      ].map(r => (
                        <tr key={r.cls} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "10px 12px" }}><span style={{ fontFamily: "var(--mono)", fontSize: 11, padding: "2px 7px", borderRadius: 4, background: `color-mix(in srgb, ${r.color} 12%, var(--surface2))`, color: r.color, border: `1px solid color-mix(in srgb, ${r.color} 25%, transparent)` }}>{r.cls}</span></td>
                          <td style={{ padding: "10px 12px", color: "var(--text-2)", fontWeight: 500 }}>{r.stage}</td>
                          <td style={{ padding: "10px 12px", fontFamily: "var(--mono)", color: "var(--text-3)", fontSize: 11 }}>{r.ind}</td>
                          <td style={{ padding: "10px 12px", color: "var(--text-3)" }}>{r.lim}</td>
                          <td style={{ padding: "10px 12px", color: "var(--green)", fontWeight: 500 }}>{r.sol}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Data Flow */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              <div className="card">
                <div className="card-header"><span className="card-title">Data Flow</span><span className="card-tag blue">END-TO-END</span></div>
                <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                  {[
                    { step: "1", label: "ESP32 Nodes", desc: "DHT22 / LDR / Attacker publish MQTT packets to broker.hivemq.com", color: "var(--green)" },
                    { step: "2", label: "HiveMQ Broker", desc: "Public cloud MQTT broker — routes netguard/# wildcard to all subscribers", color: "var(--blue)" },
                    { step: "3", label: "FastAPI Backend", desc: "Subscribes via Paho, buffers packets in a 60-second deque, runs pipeline every 5s", color: "var(--purple)" },
                    { step: "4", label: "Statistical Profiler", desc: "EMA Z-Score on payloads, global IAT tracking — catches Data Poison & Slow Rate", color: "var(--amber)" },
                    { step: "5", label: "Random Forest ML", desc: "9-feature vector fed to Random Forest → SHAP explanation generated in thread pool", color: "var(--blue)" },
                    { step: "6", label: "WebSocket Broadcast", desc: "Inference result + SHAP values pushed to all connected browsers via /ws/live", color: "var(--cyan)" },
                    { step: "7", label: "Next.js Dashboard", desc: "useLiveData() hook parses WS messages → React state → live UI updates", color: "var(--green)" },
                  ].map((s, i, arr) => (
                    <div key={s.step} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <div style={{ width: 28, height: 28, borderRadius: "50%", background: `color-mix(in srgb, ${s.color} 15%, var(--surface2))`, border: `2px solid ${s.color}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: s.color, flexShrink: 0 }}>{s.step}</div>
                        {i < arr.length - 1 && <div style={{ width: 2, height: 24, background: "var(--border)" }} />}
                      </div>
                      <div style={{ paddingTop: 4, paddingBottom: i < arr.length - 1 ? 0 : 0 }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", marginBottom: 2 }}>{s.label}</div>
                        <div style={{ fontSize: 11, color: "var(--text-3)", lineHeight: 1.5, marginBottom: i < arr.length - 1 ? 12 : 0 }}>{s.desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="card">
                <div className="card-header"><span className="card-title">Tech Stack</span><span className="card-tag green">COMPONENTS</span></div>
                <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {[
                    { layer: "Hardware", items: "ESP32 × 3 · DHT22 sensor · LDR sensor · 16×2 I2C LCD · Push button (GPIO 14)" },
                    { layer: "Firmware", items: "Arduino IDE · PubSubClient · LiquidCrystal_I2C · WiFiClient" },
                    { layer: "Protocol", items: "MQTT over TCP · HiveMQ public broker · netguard/# wildcard topics" },
                    { layer: "Backend", items: "Python 3.12 · FastAPI · Uvicorn · Paho MQTT · scikit-learn · SHAP · Groq API · Gemini API" },
                    { layer: "ML Model", items: "Random Forest (7-class) · 9 flow features · SHAP TreeExplainer · asyncio.to_thread offload" },
                    { layer: "Frontend", items: "Next.js 15 · React 19 · TypeScript · Recharts · Vanilla CSS · DM Sans / JetBrains Mono" },
                    { layer: "Dev Tools", items: "node_simulator.py · real_time_collector.py · augment_and_train.py · .env secrets" },
                  ].map(r => (
                    <div key={r.layer} style={{ display: "flex", gap: 10, borderBottom: "1px solid var(--border)", paddingBottom: 10 }}>
                      <span style={{ fontSize: 10, fontWeight: 600, color: "var(--blue)", textTransform: "uppercase", letterSpacing: 0.5, minWidth: 70, paddingTop: 1 }}>{r.layer}</span>
                      <span style={{ fontSize: 11.5, color: "var(--text-2)", lineHeight: 1.6 }}>{r.items}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Feature Vector */}
            <div className="card">
              <div className="card-header"><span className="card-title">ML Feature Vector (10 Features)</span><span className="card-tag blue">RANDOM FOREST INPUT</span></div>
              <div className="card-body">
                <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
                  {[
                    { f: "packet_count", desc: "Total packets in 10s window" },
                    { f: "packet_rate", desc: "Packets per second" },
                    { f: "mean_inter_arrival_ms", desc: "Avg time between packets" },
                    { f: "std_inter_arrival_ms", desc: "Timing jitter / variance" },
                    { f: "min_inter_arrival_ms", desc: "Fastest consecutive packet" },
                    { f: "max_inter_arrival_ms", desc: "Slowest consecutive packet" },
                    { f: "duplicate_ratio", desc: "Fraction of duplicate seqs" },
                    { f: "seq_increment_mean", desc: "Avg sequence step size" },
                    { f: "seq_increment_std", desc: "Seq step variance" },
                  ].map(ft => (
                    <div key={ft.f} style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "10px 12px" }}>
                      <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--blue)", fontWeight: 600, marginBottom: 4 }}>{ft.f}</div>
                      <div style={{ fontSize: 11, color: "var(--text-3)", lineHeight: 1.4 }}>{ft.desc}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

          </div>
        )}

        {/* ── AI ANALYST TAB ────────────────────────────────────────────── */}
        {tab === "chat" && (
          <div className="card" style={{ display: "flex", flexDirection: "row", padding: 0, overflow: "hidden", minHeight: "560px", marginBottom: 20 }}>
            {/* Left Context Pane */}
            <div style={{ width: "260px", borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", background: "var(--surface)" }}>
              <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
                <span className="card-title" style={{ fontSize: 13, fontWeight: 600 }}>System Context</span>
              </div>
              <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: 18, overflowY: "auto", flex: 1 }}>
                {/* Status Indicator */}
                <div>
                  <div style={{ fontSize: 10, color: "var(--text-3)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Model Threat Level</div>
                  <div className={`status-badge ${anomalyLabel.toLowerCase()}`} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600, padding: "5px 10px", borderRadius: 4, background: latestAnomaly > 70 ? "var(--red-bg)" : latestAnomaly > 30 ? "var(--amber-bg)" : "var(--green-bg)", color: latestAnomaly > 70 ? "var(--red)" : latestAnomaly > 30 ? "var(--amber)" : "var(--green)", border: `1px solid ${latestAnomaly > 70 ? "var(--red-mid)" : latestAnomaly > 30 ? "var(--amber-mid)" : "var(--green-mid)"}` }}>
                    <div className="live-dot" style={{ background: latestAnomaly > 70 ? "var(--red)" : latestAnomaly > 30 ? "var(--amber)" : "var(--green)", width: 6, height: 6 }} />
                    {anomalyLabel}
                  </div>
                </div>

                {/* Score */}
                <div>
                  <div style={{ fontSize: 10, color: "var(--text-3)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>Anomaly Score</div>
                  <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--mono)", color: latestAnomaly > 70 ? "var(--red)" : latestAnomaly > 30 ? "var(--amber)" : "var(--green)" }}>{latestAnomaly.toFixed(0)}%</div>
                </div>

                {/* Inference features summary */}
                <div>
                  <div style={{ fontSize: 10, color: "var(--text-3)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>Live Telemetry</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5 }}>
                      <span style={{ color: "var(--text-3)" }}>Label:</span>
                      <span style={{ fontFamily: "var(--mono)", fontWeight: 600, color: ml.isAttack ? "var(--red)" : "var(--green)" }}>{ml.label}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5 }}>
                      <span style={{ color: "var(--text-3)" }}>Pkt Rate:</span>
                      <span style={{ fontFamily: "var(--mono)" }}>{ml.pktRate.toFixed(2)} /s</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5 }}>
                      <span style={{ color: "var(--text-3)" }}>Mean IAT:</span>
                      <span style={{ fontFamily: "var(--mono)" }}>{ml.iatMean.toFixed(0)} ms</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5 }}>
                      <span style={{ color: "var(--text-3)" }}>Dup Ratio:</span>
                      <span style={{ fontFamily: "var(--mono)" }}>{(ml.dupRatio * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                </div>

                {/* SHAP indicator */}
                {ml.shap && ml.shap.length > 0 && (() => {
                  const top3 = ml.shap.slice(0, 3);
                  const maxAbs = Math.max(...top3.map(s => Math.abs(s.value)), 0.001);
                  return (
                  <div>
                    <div style={{ fontSize: 10, color: "var(--text-3)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>Visual SHAP Analysis</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10, background: "var(--surface2)", padding: "12px", borderRadius: 6, border: "1px solid var(--border)" }}>
                      {top3.map((s, idx) => {
                        const pct = Math.abs(s.value) / maxAbs * 100;
                        const pos = s.value > 0;
                        return (
                          <div key={idx} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10 }}>
                              <span style={{ fontFamily: "var(--mono)", color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "70%" }} title={s.feature}>{s.feature.replace(/_/g, " ")}</span>
                              <span style={{ fontWeight: 600, color: pos ? "var(--red)" : "var(--green)" }}>{pos ? "+" : ""}{s.value.toFixed(2)}</span>
                            </div>
                            <div style={{ width: "100%", height: 6, background: "color-mix(in srgb, var(--border) 50%, transparent)", borderRadius: 3, overflow: "hidden", position: "relative" }}>
                               <div style={{ position: "absolute", left: pos ? "50%" : `${50 - (pct/2)}%`, width: `${pct/2}%`, height: "100%", background: pos ? "var(--red)" : "var(--green)", borderRadius: 3 }} />
                               <div style={{ position: "absolute", left: "50%", width: 1, height: "100%", background: "var(--border)" }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );})()}

                {/* Compact Heatmap */}
                <div>
                  <div style={{ fontSize: 10, color: "var(--text-3)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8, marginTop: 4 }}>Device Trust Heatmap</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {[
                      { id: "ESP32_1", tr: nodes.esp32_1?.trust ?? 100 },
                      { id: "ESP32_2", tr: nodes.esp32_2?.trust ?? 100 },
                      { id: "ESP32_3", tr: nodes.esp32_3?.trust ?? 100 },
                    ].map(n => (
                       <div key={n.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
                         <span style={{ width: 45, fontWeight: 500, color: "var(--text-2)" }}>{n.id}</span>
                         <div style={{ flex: 1, height: 6, background: "var(--surface2)", borderRadius: 3, overflow: "hidden", border: "1px solid var(--border)" }}>
                           <div style={{ height: "100%", width: `${n.tr}%`, background: n.tr < 40 ? "var(--red)" : n.tr < 70 ? "var(--amber)" : "var(--green)" }} />
                         </div>
                         <span style={{ width: 28, textAlign: "right", fontFamily: "var(--mono)", color: "var(--text-3)" }}>{n.tr}%</span>
                       </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Right Chat Pane */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", height: "560px" }}>
              {/* Header bar */}
              <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="card-title" style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
                  Explainable AI Analyst
                </span>
                <span className="card-tag blue" style={{ margin: 0 }}>RAG ENGINE ACTIVE</span>
              </div>

              {/* Message scroll area */}
              <div className="chat-messages" style={{ flex: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
                {chatMsgs.map((m, i) => (
                  <div key={i} className="chat-msg" style={{ alignSelf: m.from === "You" ? "flex-end" : "flex-start", maxWidth: "80%" }}>
                    <span className="chat-from" style={{ alignSelf: m.from === "You" ? "flex-end" : "flex-start" }}>{m.from}</span>
                    {m.from === "You" ? (
                      <div className="chat-bubble user" style={{ fontSize: 13 }}>{m.text}</div>
                    ) : (
                      <div className="chat-bubble ai" style={{ fontSize: 13 }} dangerouslySetInnerHTML={renderMarkdown(m.text)} />
                    )}
                  </div>
                ))}
              </div>

              {/* Suggestions chips row */}
              {chatMsgs.length === 1 && (
                <div style={{ padding: "0 24px", display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                  <button className="atk-select" style={{ fontSize: 11, padding: "5px 12px", borderRadius: 14 }} onClick={() => sendChat("Why is ESP32_3 flagged as suspicious right now?")}>
                    🔍 Why is ESP32_3 suspicious?
                  </button>
                  <button className="atk-select" style={{ fontSize: 11, padding: "5px 12px", borderRadius: 14 }} onClick={() => sendChat("What are the current DHT, LDR, and MQ135 sensor readings?")}>
                    🌡️ Show active sensor readings
                  </button>
                  <button className="atk-select" style={{ fontSize: 11, padding: "5px 12px", borderRadius: 14 }} onClick={() => sendChat("What features does the Random Forest model evaluate?")}>
                    📊 Explain model features
                  </button>
                </div>
              )}

              {/* Chat Input Row */}
              <div className="chat-input-row" style={{ display: "flex", borderTop: "1px solid var(--border)", background: "var(--surface)" }}>
                <input className="chat-input" style={{ padding: "14px 20px" }} placeholder="Ask about live anomalies, SHAP features, or sensor health..." value={chatInput}
                  onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === "Enter" && sendChat()} />
                <button className="chat-send-btn" style={{ padding: "0 24px" }} onClick={() => sendChat()}>Send Question</button>
              </div>
            </div>
          </div>
        )}

        <div style={{ textAlign: "center", marginTop: 8, fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)" }}>
          NetGuard AI · 2025–26
        </div>
      </main>
    </>
  );
}
