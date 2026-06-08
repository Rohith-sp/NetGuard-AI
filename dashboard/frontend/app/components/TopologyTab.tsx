"use client";
import { useEffect, useRef, useCallback, useState } from "react";
import type { NodeData, MLState } from "../hooks/useLiveData";

export type SimKey = "NORMAL" | "DOS_FLOOD" | "REPLAY_ATTACK" | "SLOW_RATE_ATTACK" | "DATA_POISON" | "TOPIC_BOMB" | "EVASION_ATTACK";

interface Props {
  n1: NodeData; n2: NodeData; n3: NodeData;
  ml: MLState; wsReady: boolean;
  triggerAttack?: (mode: string) => Promise<void>;
  simKey: SimKey;
  setSimKey: (k: SimKey) => void;
}

// ── Fix 2: expanded viewBox for breathing room ─────────────────────────────
const SVG_W = 900;
const SVG_H = 520;

// ── Fix 5 (Option B): all dots use SVG-native animateMotion + mpath ─────────
// Edges recomputed proportionally from original 520×360 to 900×520
// Original scale: x *= 900/520 ≈ 1.731,  y *= 520/360 ≈ 1.444
// router centre:  260,40  → 450,58
// esp1 centre:    130,161 → 225,232
// esp2 centre:    260,161 → 450,232
// esp3 centre:    390,161 → 675,232
// backend centre: 260,271 → 450,391
// dash centre:    260,345 → 450,474
const EDGES = [
  { id: 0, x1: 450, y1:  86, x2: 225, y2: 210, atkEdge: false },
  { id: 1, x1: 450, y1:  86, x2: 450, y2: 210, atkEdge: false },
  { id: 2, x1: 450, y1:  86, x2: 675, y2: 210, atkEdge: true  },
  { id: 3, x1: 225, y1: 258, x2: 404, y2: 368, atkEdge: false },
  { id: 4, x1: 450, y1: 258, x2: 450, y2: 368, atkEdge: false },
  { id: 5, x1: 675, y1: 258, x2: 496, y2: 368, atkEdge: true  },
  { id: 6, x1: 450, y1: 412, x2: 450, y2: 452, atkEdge: false },
];
const EDGE_DURS = [1.8, 2.2, 2.0, 2.4, 1.9, 1.6, 1.4];

// ── Simulation modes — local only, never touches backend ─────────────────────
// (SimKey is now exported above)

const SIM_MODES: {
  key: SimKey; label: string; cls: string; desc: string;
  isAttack: boolean;
  animStyle: "normal" | "flood" | "slow" | "poison" | "bomb" | "evasion";
  pred: { label: string; confidence: number; pktRate: number; iatMean: number; dupRatio: number; };
  esp3Sub: string;
}[] = [
  {
    key: "NORMAL", label: "Normal", cls: "normal",
    desc: "Legitimate sensor traffic — ~2–5 s intervals",
    isAttack: false, animStyle: "normal",
    pred: { label: "NORMAL", confidence: 94, pktRate: 0.3, iatMean: 3500, dupRatio: 0 },
    esp3Sub: "PIR · 0.3 pkt/s · Normal",
  },
  {
    key: "DOS_FLOOD", label: "DoS Flood", cls: "dos",
    desc: "Rapid-fire flood — one packet every 150–350 ms",
    isAttack: true, animStyle: "flood",
    pred: { label: "DOS_FLOOD", confidence: 97, pktRate: 48, iatMean: 240, dupRatio: 0 },
    esp3Sub: "PIR · 48 pkt/s · DoS Flood",
  },
  {
    key: "REPLAY_ATTACK", label: "Replay", cls: "replay",
    desc: "Frozen seq replayed — 82 % duplicate ratio",
    isAttack: true, animStyle: "flood",
    pred: { label: "REPLAY_ATTACK", confidence: 91, pktRate: 4, iatMean: 1100, dupRatio: 0.82 },
    esp3Sub: "PIR · 4 pkt/s · Replay Attack",
  },
  {
    key: "SLOW_RATE_ATTACK", label: "Slow-Rate", cls: "slow",
    desc: "Ghost packets every 15–30 s — evades basic detection",
    isAttack: true, animStyle: "slow",
    pred: { label: "SLOW_RATE_ATTACK", confidence: 76, pktRate: 0.05, iatMean: 22000, dupRatio: 0 },
    esp3Sub: "PIR · 0.05 pkt/s · Slow Probe",
  },
  {
    key: "DATA_POISON", label: "Data Poison", cls: "poison",
    desc: "Spoofs ESP32_1 — injects temp:999°C & humidity:-100",
    isAttack: true, animStyle: "poison",
    pred: { label: "DATA_POISON", confidence: 82, pktRate: 0.3, iatMean: 3200, dupRatio: 0 },
    esp3Sub: "Spoofing device1 · 0.3 pkt/s",
  },
  {
    key: "TOPIC_BOMB", label: "Topic Bomb", cls: "bomb",
    desc: "Floods broker with random topics — exhausts routing memory",
    isAttack: true, animStyle: "bomb",
    pred: { label: "TOPIC_BOMB", confidence: 89, pktRate: 120, iatMean: 75, dupRatio: 0 },
    esp3Sub: "junk/* · 120 pkt/s · Bombing",
  },
  {
    key: "EVASION_ATTACK", label: "Evasion", cls: "evasion",
    desc: "Smart flood — injects random delays to trick the AI model",
    isAttack: true, animStyle: "evasion",
    pred: { label: "EVASION_ATTACK", confidence: 58, pktRate: 6, iatMean: 800, dupRatio: 0 },
    esp3Sub: "AI Evasion · 6 pkt/s · Camouflage",
  },
];

function trustColor(trust: number, online: boolean) {
  if (!online) return "var(--border2)";
  if (trust < 40) return "var(--red)";
  if (trust < 70) return "var(--amber)";
  return "var(--green)";
}

// Colors per attack animation style
const ANIM_COLOR: Record<string, string> = {
  normal:  "var(--blue)",
  flood:   "var(--red)",
  slow:    "var(--amber)",
  poison:  "#f97316",   // orange — spoofed payload
  bomb:    "#d946ef",   // fuchsia — topic explosion
  evasion: "#facc15",   // yellow — camouflaged evasion
};

export default function TopologyTab({ n1, n2, n3, ml: _realMl, wsReady, triggerAttack, simKey, setSimKey }: Props) {
  const simCfg   = SIM_MODES.find(m => m.key === simKey)!;
  const isAttack = simCfg.isAttack;
  const pred     = simCfg.pred;
  const anim     = simCfg.animStyle;

  // Fix 5: no div-based dots — pure SVG animateMotion via <mpath> below
  // (pktLayerRef kept for backward compat but unused)
  const svgRef = useRef<SVGSVGElement>(null);

  const esp1C  = anim === "poison" ? "#f97316" : trustColor(n1.trust, n1.online);
  const esp2C  = anim === "bomb"   ? "#d946ef" : trustColor(n2.trust, n2.online);
  const esp3C  = isAttack ? (ANIM_COLOR[anim] ?? "var(--red)") : trustColor(n3.trust, n3.online);
  const routeC = wsReady ? "var(--blue)" : "var(--border2)";
  const backC  = wsReady ? "#8b5cf6"    : "var(--border2)";
  const confColor = isAttack ? "var(--red)" : "var(--green)";

  return (
    // Fix 1: single parent card with horizontal flex — SVG left, sidebar right (220px)
    <div className="topo-wrap">

      {/* Fix 1: unified header inside the single card */}
      <div className="topo-header">
        <span className="topo-title">Network topology</span>
        <span className={`topo-badge ${wsReady ? "live" : "offline"}`}>
          {wsReady ? "LIVE" : "OFFLINE"}
        </span>
        {/* Fix 6: SIM MODE badge only when not normal */}
        {isAttack && (
          <span className="topo-sim-chip">SIM MODE</span>
        )}
        <span className={`topo-status-hint${isAttack ? " danger" : ""}`}>
          {isAttack
            ? `⚠ ${pred.label.replace(/_/g, " ")} — simulated`
            : "Network nominal — no active threats"}
        </span>
      </div>

      {/* Fix 1: body is flex row — SVG takes remaining width, sidebar fixed 220px */}
      <div className="topo-body">

        {/* SVG panel */}
        <div className="topo-svg-wrap">
          <svg ref={svgRef} id="topo-svg"
            viewBox={`0 0 ${SVG_W} ${SVG_H}`}
            className="topo-svg"
          >
            <defs>
              <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5"
                markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke"
                  strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </marker>
              <marker id="arr-red" viewBox="0 0 10 10" refX="8" refY="5"
                markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke"
                  strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </marker>

              {/* Fix 5 (Option B): edge paths for mpath */}
              {EDGES.map(ep => (
                <path key={`ep-${ep.id}`}
                  id={`edge-path-${ep.id}`}
                  d={`M${ep.x1},${ep.y1} L${ep.x2},${ep.y2}`}
                  fill="none" stroke="none"
                />
              ))}
            </defs>

            {/* Edges — color and speed vary per attack animation style */}
            {EDGES.map((ep) => {
              // For BOMB, all edges are attack edges; for POISON only edge 0 (attacker→device1 reverse) and edge 2/5
              const isAtkEdge =
                anim === "bomb"   ? true :
                anim === "poison" ? (ep.id === 0 || ep.id === 2 || ep.id === 5) :
                (isAttack && ep.atkEdge);
              const edgeColor =
                isAtkEdge ? (ANIM_COLOR[anim] ?? "var(--red)") : "var(--border2)";
              return (
                <line key={ep.id} className="topo-edge"
                  x1={ep.x1} y1={ep.y1} x2={ep.x2} y2={ep.y2}
                  stroke={edgeColor}
                  strokeWidth={isAtkEdge ? 1.8 : 1}
                  strokeDasharray={isAtkEdge ? "4 3" : "5 4"}
                  markerEnd={isAtkEdge ? "url(#arr-red)" : "url(#arr)"}
                >
                  <animate attributeName="stroke-dashoffset"
                    from="0" to={isAtkEdge ? "-12" : "-18"}
                    dur={`${EDGE_DURS[ep.id]}s`} repeatCount="indefinite"/>
                </line>
              );
            })}

            {/* SVG-native packet dots — animation params driven by attack style */}
            {EDGES.map((ep) => {
              // Determine if this edge should have attack-style dots
              const isAtkEdge =
                anim === "bomb"   ? true :
                anim === "poison" ? (ep.id === 0 || ep.id === 2 || ep.id === 5) :
                (isAttack && ep.atkEdge);

              // Dot count per edge
              const count =
                anim === "bomb"    ? 6 :
                anim === "flood"   ? 4 :
                anim === "evasion" ? 2 :
                isAtkEdge ? 2 : 1;

              // Animation duration (lower = faster)
              const baseDur =
                anim === "bomb"    ? 0.35 :
                anim === "flood"   ? 0.45 :
                anim === "poison"  ? 1.6  :
                anim === "evasion" ? 0.6  :
                anim === "slow"    ? 6.0  :
                isAtkEdge ? 0.45 : (2.2 + ep.id * 0.28);

              const dotColor = isAtkEdge ? (ANIM_COLOR[anim] ?? "var(--blue)") : "var(--blue)";
              const dotR     = isAtkEdge ? 4 : 3;

              return Array.from({ length: count }, (_, k) => {
                const dur   = isAtkEdge ? baseDur : (2.2 + ep.id * 0.28);
                // Evasion: stagger delays unevenly to simulate irregular timing
                const begin = anim === "evasion" && k % 2 === 1
                  ? k * (dur / count) + 1.8   // every 2nd dot delayed 1.8s extra
                  : k * (dur / count);
                return (
                  <circle key={`dot-${ep.id}-${k}`}
                    r={dotR}
                    fill={dotColor}
                    opacity={0.9}
                  >
                    <animateMotion
                      dur={`${dur}s`}
                      begin={`${begin}s`}
                      repeatCount="indefinite"
                    >
                      <mpath href={`#edge-path-${ep.id}`}/>
                    </animateMotion>
                  </circle>
                );
              });
            })}

            {/* Pulse ring on ESP32_3 — color matches attack style */}
            <circle cx={675} cy={234} r={34} fill="none"
              stroke={ANIM_COLOR[anim] ?? "var(--red)"} strokeWidth="1.2"
              opacity="0">
              {isAttack && (
                <>
                  <animate attributeName="r"       from="34" to="52" dur={anim === "slow" ? "3s" : anim === "bomb" ? "0.5s" : "1s"} repeatCount="indefinite"/>
                  <animate attributeName="opacity" from="0.7" to="0"  dur={anim === "slow" ? "3s" : anim === "bomb" ? "0.5s" : "1s"} repeatCount="indefinite"/>
                </>
              )}
            </circle>
            {/* Extra pulse ring for TOPIC_BOMB — double ripple effect */}
            {anim === "bomb" && (
              <circle cx={675} cy={234} r={34} fill="none"
                stroke="#d946ef" strokeWidth="0.8" opacity="0">
                <animate attributeName="r"       from="34" to="64" dur="0.8s" begin="0.25s" repeatCount="indefinite"/>
                <animate attributeName="opacity" from="0.5" to="0"  dur="0.8s" begin="0.25s" repeatCount="indefinite"/>
              </circle>
            )}
            {/* Extra pulse ring for DATA_POISON — ripple on ESP32_1 too */}
            {anim === "poison" && (
              <circle cx={225} cy={234} r={34} fill="none"
                stroke="#f97316" strokeWidth="1.2" opacity="0">
                <animate attributeName="r"       from="28" to="48" dur="1.2s" repeatCount="indefinite"/>
                <animate attributeName="opacity" from="0.6" to="0"  dur="1.2s" repeatCount="indefinite"/>
              </circle>
            )}

            {/* ── Fix 3+9: Router — ◈ unicode, dominant-baseline="central" ── */}
            <g className="topo-node-card" id="nc-router">
              <rect x={374} y={24} width={152} height={62} rx={8}
                fill="var(--surface2)" stroke={routeC} strokeWidth="0.8"/>
              {/* Fix 3: replace ⌘ emoji with ◈ unicode */}
              <text fontFamily="var(--mono)" fontSize={18} x={450} y={50}
                textAnchor="middle" dominantBaseline="central" fill={routeC}>◈</text>
              <text fontSize={10} fontWeight="500" x={450} y={68}
                textAnchor="middle" dominantBaseline="central" fill="var(--text)">WiFi Router</text>
              <text fontFamily="var(--mono)" fontSize={8} x={450} y={81}
                textAnchor="middle" dominantBaseline="central" fill="var(--text-3)">192.168.1.1</text>
              <circle cx={518} cy={30} r={4.5}
                fill={wsReady ? "var(--green)" : "var(--border2)"}
                stroke="var(--surface)" strokeWidth="1.5"/>
            </g>

            {/* ── Fix 9: ESP32_1 — dominant-baseline="central" on icon ──── */}
            <g className="topo-node-card" id="nc-esp1">
              <rect x={145} y={210} width={160} height={62} rx={8}
                fill="var(--surface2)" stroke={esp1C} strokeWidth="0.8"/>
              <text fontSize={16} x={225} y={232}
                textAnchor="middle" dominantBaseline="central" fill={esp1C}>🌡</text>
              <text fontSize={10} fontWeight="500" x={225} y={252}
                textAnchor="middle" dominantBaseline="central" fill="var(--text)">ESP32_1</text>
              <text fontFamily="var(--mono)" fontSize={8} x={225} y={266}
                textAnchor="middle" dominantBaseline="central" fill="var(--text-3)">
                {n1.online ? `DHT22 · ${n1.temp?.toFixed(1)??"—"}°C  ${n1.humidity?.toFixed(0)??"—"}%` : "DHT22 · Offline"}
              </text>
              <circle cx={299} cy={216} r={4.5}
                fill={n1.online ? "var(--green)" : "var(--border2)"}
                stroke="var(--surface)" strokeWidth="1.5"/>
            </g>

            {/* ── Fix 9: ESP32_2 ─────────────────────────────────────────── */}
            <g className="topo-node-card" id="nc-esp2">
              <rect x={370} y={210} width={160} height={62} rx={8}
                fill="var(--surface2)" stroke={esp2C} strokeWidth="0.8"/>
              <text fontSize={16} x={450} y={232}
                textAnchor="middle" dominantBaseline="central" fill={esp2C}>💡</text>
              <text fontSize={10} fontWeight="500" x={450} y={252}
                textAnchor="middle" dominantBaseline="central" fill="var(--text)">ESP32_2</text>
              <text fontFamily="var(--mono)" fontSize={8} x={450} y={266}
                textAnchor="middle" dominantBaseline="central" fill="var(--text-3)">
                {n2.online ? `LDR · ${n2.light??"—"} LUX` : "LDR · Offline"}
              </text>
              <circle cx={524} cy={216} r={4.5}
                fill={n2.online ? "var(--green)" : "var(--border2)"}
                stroke="var(--surface)" strokeWidth="1.5"/>
            </g>

            {/* ── ESP32_3 — background and icon adapt to attack style ─── */}
            <g className={`topo-node-card${isAttack ? " attack-node" : ""}`} id="nc-esp3">
              <rect x={595} y={210} width={160} height={62} rx={8}
                fill={
                  anim === "poison"  ? "rgba(249,115,22,0.12)" :
                  anim === "bomb"    ? "rgba(217,70,239,0.12)" :
                  anim === "evasion" ? "rgba(250,204,21,0.10)" :
                  isAttack ? "var(--red-bg)" : "var(--surface2)"
                }
                stroke={esp3C} strokeWidth={isAttack ? 1.4 : 0.8}/>
              <text fontSize={16} x={675} y={232}
                textAnchor="middle" dominantBaseline="central" fill={esp3C}>
                {anim === "poison" ? "☠" : anim === "bomb" ? "💣" : anim === "evasion" ? "👻" : "📷"}
              </text>
              <text fontSize={10} fontWeight="500" x={675} y={252}
                textAnchor="middle" dominantBaseline="central"
                fill={isAttack ? (ANIM_COLOR[anim] ?? "var(--red)") : "var(--text)"}>ESP32_3</text>
              <text fontFamily="var(--mono)" fontSize={8} x={675} y={266}
                textAnchor="middle" dominantBaseline="central" fill={esp3C}>{simCfg.esp3Sub}</text>
              <circle cx={749} cy={216} r={4.5}
                fill={esp3C} stroke="var(--surface)" strokeWidth="1.5"/>
            </g>

            {/* ── Backend ─────────────────────────────────────────────────── */}
            <g className="topo-node-card" id="nc-backend">
              <rect x={346} y={368} width={208} height={46} rx={8}
                fill="var(--surface2)" stroke={backC} strokeWidth="0.8"/>
              <text fontSize={9.5} fontWeight="500" x={450} y={388}
                textAnchor="middle" dominantBaseline="central" fill="var(--text)">NetGuard Backend</text>
              <text fontFamily="var(--mono)" fontSize={8} x={450} y={405}
                textAnchor="middle" dominantBaseline="central" fill="var(--text-3)">FastAPI · :8000</text>
              <circle cx={548} cy={374} r={4.5}
                fill={wsReady ? "var(--green)" : "var(--border2)"}
                stroke="var(--surface)" strokeWidth="1.5"/>
            </g>

            {/* ── Fix 7: SOC Dashboard — dot tied to wsReady ──────────────── */}
            <g className="topo-node-card" id="nc-dash">
              <rect x={350} y={452} width={200} height={38} rx={8}
                fill="var(--blue-bg)" stroke="var(--blue)" strokeWidth="0.8"/>
              <text fontSize={9.5} fontWeight="500" x={450} y={468}
                textAnchor="middle" dominantBaseline="central" fill="var(--blue)">SOC Dashboard</text>
              <text fontFamily="var(--mono)" fontSize={8} x={450} y={482}
                textAnchor="middle" dominantBaseline="central" fill="var(--blue)">localhost:3000</text>
              {/* Fix 7: was hardcoded gray — now tied to wsReady */}
              <circle cx={544} cy={458} r={4.5}
                fill={wsReady ? "var(--green)" : "var(--border2)"}
                stroke="var(--surface)" strokeWidth="1.5"/>
            </g>

            {/* ── Legend ──────────────────────────────────────────────────── */}
            <g transform="translate(14, 496)">
              <circle cx={5}   cy={5} r={4} fill="var(--green)"/>
              <text fontSize={8.5} fill="var(--text-3)" x={13}  y={9}>Normal</text>
              <circle cx={68}  cy={5} r={4} fill="var(--amber)"/>
              <text fontSize={8.5} fill="var(--text-3)" x={76}  y={9}>Suspicious</text>
              <circle cx={152} cy={5} r={4} fill="var(--red)"/>
              <text fontSize={8.5} fill="var(--text-3)" x={160} y={9}>Threat</text>
              <circle cx={208} cy={5} r={4} fill="var(--border2)"/>
              <text fontSize={8.5} fill="var(--text-3)" x={216} y={9}>Offline</text>
            </g>
          </svg>
        </div>

        {/* Fix 1+8: side panel — 220px fixed, left border divider */}
        <div className="topo-side-panel">

          {/* Fix 8: sentence case, button adjustments */}
          <div className="topo-sim-section">
            <div className="topo-sim-label">Simulate attack</div>
            <div className="topo-sim-btns">
              {SIM_MODES.map((m) => (
                <button key={m.key}
                  className={`topo-sim-btn ${m.cls}${simKey === m.key ? " active" : ""}`}
                  onClick={() => {
                    setSimKey(m.key);
                    triggerAttack?.(m.key);
                  }}
                  title={m.desc}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <div className="topo-sim-desc">{simCfg.desc}</div>
            {/* Fix 8: 11px, tertiary color, not italic */}
            <div className="topo-sim-note">Visual only — does not affect Overview</div>
          </div>

          <div className="topo-panel-divider"/>

          {/* Fix 8: sentence case */}
          <div className="topo-pred-section">
            <div className="topo-sim-label">Expected prediction</div>

            <div className={`topo-pred-badge${isAttack ? " threat" : ""}`}>
              <span className="topo-pred-label">{pred.label.replace(/_/g, " ")}</span>
              <span className="topo-pred-conf" style={{ color: confColor }}>
                {pred.confidence}%
              </span>
            </div>

            <div className="topo-conf-bar-wrap">
              <div className="topo-conf-bar"
                style={{ width: `${pred.confidence}%`, background: isAttack ? "var(--red)" : "var(--green)" }}/>
            </div>

            <div className="topo-pred-stats">
              <div className="topo-pred-row">
                <span className="topo-pred-key">Pkt rate</span>
                <span className="topo-pred-val"
                  style={{ color: isAttack && pred.pktRate > 10 ? "var(--red)" : "var(--text)" }}>
                  {pred.pktRate} pkt/s
                </span>
              </div>
              <div className="topo-pred-row">
                <span className="topo-pred-key">IAT mean</span>
                <span className="topo-pred-val"
                  style={{ color: isAttack && pred.iatMean < 500 ? "var(--red)" : "var(--text)" }}>
                  {pred.iatMean >= 1000
                    ? `${(pred.iatMean / 1000).toFixed(1)} s`
                    : `${pred.iatMean} ms`}
                </span>
              </div>
              <div className="topo-pred-row">
                <span className="topo-pred-key">Dup ratio</span>
                <span className="topo-pred-val"
                  style={{ color: pred.dupRatio > 0.3 ? "var(--red)" : "var(--text)" }}>
                  {(pred.dupRatio * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Attack banner — message and icon adapt to attack type */}
      {isAttack && (
        <div className="topo-alert-banner" style={{ borderColor: ANIM_COLOR[anim] ?? "var(--red)", background: `${ANIM_COLOR[anim] ?? "var(--red)"}1a` }}>
          <span style={{ fontSize: 14 }}>
            {anim === "poison" ? "☠" : anim === "bomb" ? "💣" : anim === "evasion" ? "👻" : "⚠"}
          </span>
          <span>
            <strong>{pred.label.replace(/_/g, " ")}</strong> simulated on ESP32_3 —{" "}
            <strong style={{ color: ANIM_COLOR[anim] }}>{pred.confidence}%</strong> expected confidence &nbsp;·&nbsp;
            IAT {pred.iatMean >= 1000 ? `${(pred.iatMean/1000).toFixed(1)}s` : `${pred.iatMean}ms`} &nbsp;·&nbsp;
            {pred.pktRate} pkt/s
            {anim === "poison"  && <> &nbsp;·&nbsp; <strong style={{ color: "#f97316" }}>SPOOFING netguard/device1</strong></>}
            {anim === "bomb"    && <> &nbsp;·&nbsp; <strong style={{ color: "#d946ef" }}>FLOODING 1000+ random topics</strong></>}
            {anim === "evasion" && <> &nbsp;·&nbsp; <strong style={{ color: "#facc15" }}>CAMOUFLAGING std_inter_arrival_ms</strong></>}
          </span>
        </div>
      )}
    </div>
  );
}
