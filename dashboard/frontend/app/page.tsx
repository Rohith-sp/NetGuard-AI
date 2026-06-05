"use client";
import { useState, useEffect } from "react";
import { useLiveData } from "./hooks/useLiveData";
import { AnomalyGraph, PktRateGraph } from "./components/Graphs";
import { KpiRow, NodeRow, MLPanel, AlertLog, PacketFeed, HeatmapPanel } from "./components/Panels";
import TopologyTab from "./components/TopologyTab";
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
  const [tab, setTab] = useState<"overview" | "analytics" | "topology" | "chat">("analytics");
  const [demoMode, setDemoMode] = useState("NORMAL");
  const [demoActive, setDemoActive] = useState(false);
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
      const res = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
          <div>
            <div className="page-title">{tab === "analytics" ? "Live Sensor Analytics" : tab === "overview" ? "Network Overview" : tab === "topology" ? "Network Topology" : "AI Security Analyst"}</div>
            <div className="page-subtitle">{tab === "analytics" ? "Real-time temperature, humidity & light readings from your IoT nodes" : "Semester IV · 3 nodes monitored"}</div>
          </div>
        </div>

        {/* ── OVERVIEW ──────────────────────────────────────────────────── */}
        {tab === "overview" && (
          <>
            <KpiRow totalPkts={totalPkts} alertCount={alerts.length} anomaly={latestAnomaly} nodesOnline={nodesOnline} />

            {/* Demo Mode Panel */}
            <div className="demo-bar">
              <div className="demo-bar-label">
                <span className="demo-icon">⚡</span>
                <span>Demo Mode</span>
                {demoActive && <span className="demo-active-pill">SIMULATING</span>}
              </div>
              <div className="demo-bar-btns">
                {(["NORMAL","DOS_FLOOD","REPLAY_ATTACK","SLOW_RATE_ATTACK"] as const).map(m => {
                  const colors: Record<string,string> = { NORMAL:"var(--green)", DOS_FLOOD:"var(--red)", REPLAY_ATTACK:"var(--amber)", SLOW_RATE_ATTACK:"var(--blue)" };
                  const labels: Record<string,string> = { NORMAL:"Normal", DOS_FLOOD:"DoS Flood", REPLAY_ATTACK:"Replay", SLOW_RATE_ATTACK:"Slow Rate" };
                  const active = demoMode === m && demoActive;
                  return (
                    <button key={m}
                      className="demo-btn"
                      style={{ borderColor: active ? colors[m] : "var(--border)", color: active ? colors[m] : "var(--text-2)", background: active ? `${colors[m]}18` : "var(--surface2)" }}
                      onClick={() => { setDemoMode(m); setDemoActive(true); simulate(m); }}>
                      {labels[m]}
                    </button>
                  );
                })}
                {demoActive && (
                  <button className="demo-btn" style={{ borderColor: "var(--border)", color: "var(--text-3)" }}
                    onClick={() => setDemoActive(false)}>
                    ✕ Clear
                  </button>
                )}
              </div>
            </div>

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
          <AnalyticsTab data={sensorTemporal} n1={nodes.esp32_1} n2={nodes.esp32_2} />
        )}

        {/* ── TOPOLOGY TAB ──────────────────────────────────────────────── */}
        {tab === "topology" && (
          <div className="card" style={{ padding: 24 }}>
            <TopologyTab
              n1={nodes.esp32_1} n2={nodes.esp32_2} n3={nodes.esp32_3}
              ml={ml} wsReady={wsReady}
              triggerAttack={triggerAttack}
            />
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
                {ml.shap && ml.shap.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, color: "var(--text-3)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>Primary SHAP Drivers</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {ml.shap.slice(0, 3).map((item, idx) => (
                        <div key={idx} style={{ background: "var(--surface2)", padding: "6px 10px", borderRadius: 4, border: "1px solid var(--border)", fontSize: 11 }}>
                          <div style={{ fontFamily: "var(--mono)", fontWeight: 500, color: "var(--text-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.feature}</div>
                          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2 }}>
                            <span style={{ color: "var(--text-3)", fontSize: 10 }}>SHAP:</span>
                            <span style={{ fontWeight: 600, color: item.value > 0 ? "var(--red)" : "var(--green)" }}>{item.value > 0 ? "+" : ""}{item.value.toFixed(3)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
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
                  <button className="atk-select" style={{ fontSize: 11, padding: "5px 12px", borderRadius: 14 }} onClick={() => sendChat("What are the current DHT and LDR sensor readings?")}>
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
