"use client";
import { useState, useEffect } from "react";
import { useLiveData } from "./hooks/useLiveData";
import { AnomalyGraph, PktRateGraph } from "./components/Graphs";
import { KpiRow, NodeRow, MLPanel, AlertLog, PacketFeed } from "./components/Panels";

const ATTACK_MODES = [
  { key: "NORMAL",           name: "Normal Traffic",   desc: "Mimics legitimate sensor timing ~2–5s intervals", cls: "normal" },
  { key: "DOS_FLOOD",        name: "DoS Flood Attack", desc: "Rapid-fire packets every 0.15–0.35s",             cls: "dos"    },
  { key: "REPLAY_ATTACK",    name: "Replay Attack",    desc: "Frozen seq number repeated 0.8–1.5s intervals",   cls: "replay" },
  { key: "SLOW_RATE_ATTACK", name: "Slow-Rate Probe",  desc: "Ghost packets every 15–30s to evade detection",   cls: "slow"   },
];

export default function Page() {
  const { nodes, packets, alerts, temporal, ml, totalPkts, wsReady, triggerAttack } = useLiveData();
  const [tab, setTab]             = useState<"overview" | "attacker">("overview");
  const [selectedMode, setMode]   = useState("NORMAL");
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

  function sendChat() {
    if (!chatInput.trim()) return;
    const q = chatInput.trim();
    setChatMsgs(m => [...m, { from: "You", text: q }]);
    setChatInput("");
    setTimeout(() => {
      const reply = latestAnomaly > 50
        ? `Anomaly score is ${latestAnomaly.toFixed(0)}%. ESP32_3 is in ${ml.label} mode. IAT of ${ml.iatMean}ms is outside the 2000–5000ms normal baseline — confirmed intrusion.`
        : `Network looks normal. Anomaly score: ${latestAnomaly.toFixed(0)}%. All nodes publishing within expected timing windows.`;
      setChatMsgs(m => [...m, { from: "AI", text: reply }]);
    }, 600);
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
          <span className={`nav-item ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>Overview</span>
          <span className={`nav-item ${tab === "attacker" ? "active" : ""}`} onClick={() => setTab("attacker")}>Attacker Control</span>
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
            <div className="page-title">{tab === "overview" ? "Network Overview" : "Attacker Control Panel"}</div>
            <div className="page-subtitle">RV College of Engineering · CS344AI · Semester IV · 3 nodes monitored</div>
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
                <AlertLog alerts={alerts} />

                {/* RAG Chat */}
                <div className="card">
                  <div className="card-header">
                    <span className="card-title">AI Security Analyst</span>
                    <span className="card-tag blue">RAG</span>
                  </div>
                  <div className="chat-wrap">
                    <div className="chat-messages">
                      {chatMsgs.map((m, i) => (
                        <div key={i} className="chat-msg">
                          <span className="chat-from">{m.from}</span>
                          <div className={`chat-bubble ${m.from === "You" ? "user" : "ai"}`}>{m.text}</div>
                        </div>
                      ))}
                    </div>
                    <div className="chat-input-row">
                      <input className="chat-input" placeholder="Ask about current threats…" value={chatInput}
                        onChange={e => setChatInput(e.target.value)} onKeyDown={e => e.key === "Enter" && sendChat()} />
                      <button className="chat-send-btn" onClick={sendChat}>Send</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}

        {/* ── ATTACKER TAB ──────────────────────────────────────────────── */}
        {tab === "attacker" && (
          <div className="card">
            <div className="card-header">
              <span className="card-title">ESP32_3 — Attack Mode Control</span>
              <span className={`card-tag ${wsReady ? "green" : "amber"}`}>{wsReady ? "CONNECTED" : "BACKEND OFFLINE"}</span>
            </div>
            <div className="atk-panel">
              <div style={{ fontSize: 13, color: "var(--text-3)" }}>
                Select a mode and click <strong>Trigger</strong> to send a command to the Wokwi ESP32_3 via MQTT (<code style={{ fontFamily: "var(--mono)", background: "var(--surface2)", padding: "1px 5px", borderRadius: 3 }}>netguard/cmd</code>).
              </div>

              <div className="atk-mode-grid">
                {ATTACK_MODES.map(m => (
                  <div key={m.key} className={`atk-mode-card ${selectedMode === m.key ? `selected-${m.cls}` : ""}`} onClick={() => setMode(m.key)}>
                    <div className="atk-mode-name" style={{ color: m.key === "NORMAL" ? "var(--green)" : m.key === "DOS_FLOOD" ? "var(--red)" : m.key === "REPLAY_ATTACK" ? "var(--amber)" : "var(--blue)" }}>{m.name}</div>
                    <div className="atk-mode-desc">{m.desc}</div>
                  </div>
                ))}
              </div>

              <div className="atk-action-row">
                <button className={`btn ${selectedMode === "NORMAL" ? "btn-primary" : selectedMode === "DOS_FLOOD" ? "btn-danger" : "btn-amber"}`}
                  onClick={() => triggerAttack(selectedMode)}>
                  ▶ Trigger {selectedMode.replace(/_/g, " ")}
                </button>
                <button className="btn btn-secondary" onClick={() => { triggerAttack("NORMAL"); setMode("NORMAL"); }}>
                  Reset to Normal
                </button>
              </div>

              <div className="atk-status-bar">
                <span style={{ color: "var(--text-3)" }}>Current mode: </span>
                <span style={{ color: nodes.esp32_3?.mode && ["DOS_FLOOD","REPLAY_ATTACK","SLOW_RATE_ATTACK"].includes(nodes.esp32_3.mode) ? "var(--red)" : "var(--green)", fontWeight: 500 }}>
                  {nodes.esp32_3?.mode ?? "—"}
                </span>
                <span style={{ color: "var(--text-3)", marginLeft: 16 }}>Seq: {nodes.esp32_3?.seq ?? 0}</span>
                <span style={{ color: "var(--text-3)", marginLeft: 16 }}>Last seen: {nodes.esp32_3?.lastSeen ?? "—"}</span>
              </div>
            </div>
          </div>
        )}

        <div style={{ textAlign: "center", marginTop: 8, fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)" }}>
          NetGuard AI · RV College of Engineering · CS344AI · 2025–26
        </div>
      </main>
    </>
  );
}
