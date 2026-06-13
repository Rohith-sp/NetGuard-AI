"use client";
import { useEffect, useState, useRef, useCallback } from "react";

export interface NodeData {
  id: string; label: string; ip: string;
  temp?: number; humidity?: number; light?: number;
  mode?: string; seq?: number;
  pktRate: number; trust: number;
  lastSeen: string; online: boolean;
}
export interface PacketEntry  { id: number; time: string; label: string; device: string; iat: number; }
export interface AlertEntry   { id: number; time: string; title: string; severity: "CRITICAL"|"HIGH"|"MEDIUM"|"LOW"; device: string; meta: string; }
export interface TemporalPoint{ t: string; anomaly: number; r1: number; r2: number; r3: number; }
export interface MLState       { label: string; confidence: number; isAttack: boolean; pktRate: number; iatMean: number; dupRatio: number; seqGap: number; shap: {feature:string;value:number;raw:number}[]; baseline?: { label: string; confidence: number; isAttack: boolean; }; }
export interface SensorPoint  { t: string; temp?: number; humidity?: number; light?: number; }
export interface IncidentState { text: string; label: string; ts: string; }
export interface EvaluationState {
  hybrid_cm: number[][];
  baseline_cm: number[][];
  hybrid_metrics: { accuracy: number; precision: number; recall: number; f1: number; };
  baseline_metrics: { accuracy: number; precision: number; recall: number; f1: number; };
  drift_score: number;
  drift_history: { time: string; score: number; }[];
  total_samples: number;
  classes: string[];
}

// 50-Node Simulator types
export interface SimTopology {
  nodes: { id: number; label: string; type: string; }[];
  links: { source: number; target: number; }[];
}
export interface SimNodeStates {
  [nodeId: string]: string; // "NORMAL" | "DOS_FLOOD" | etc.
}

const ATTACKS = ["DOS_FLOOD", "REPLAY_ATTACK", "SLOW_RATE_ATTACK", "DATA_POISON", "TOPIC_BOMB", "EVASION_ATTACK"];

export function useLiveData() {
  const [nodes, setNodes]       = useState<Record<string, NodeData>>({
    esp32_1: { id:"esp32_1", label:"ESP32_1 · DHT22",    ip:"netguard_rohit_77/device1",  pktRate:0, trust:94, lastSeen:"—", online:false, temp:0,   humidity:0 },
    esp32_2: { id:"esp32_2", label:"ESP32_2 · LDR",      ip:"netguard_rohit_77/device2",  pktRate:0, trust:91, lastSeen:"—", online:false, light:0 },
    esp32_3: { id:"esp32_3", label:"ESP32_3 · Attacker", ip:"netguard_rohit_77/attacker", pktRate:0, trust:95, lastSeen:"—", online:false, mode:"AWAITING", seq:0 },
  });
  const [packets, setPackets]   = useState<PacketEntry[]>([]);
  const [alerts,  setAlerts]    = useState<AlertEntry[]>([]);
  const [temporal,setTemporal]        = useState<TemporalPoint[]>([]);
  const [sensorTemporal,setSensorTemporal] = useState<SensorPoint[]>([]);
  const [ml,      setML]               = useState<MLState>({ label:"AWAITING", confidence:0, isAttack:false, pktRate:0, iatMean:0, dupRatio:0, seqGap:1, shap:[], baseline: { label: "AWAITING", confidence: 0, isAttack: false } });
  const [evaluation, setEvaluation]    = useState<EvaluationState>({
    hybrid_cm: Array(7).fill(null).map(() => Array(7).fill(0)),
    baseline_cm: Array(7).fill(null).map(() => Array(7).fill(0)),
    hybrid_metrics: { accuracy: 0, precision: 0, recall: 0, f1: 0 },
    baseline_metrics: { accuracy: 0, precision: 0, recall: 0, f1: 0 },
    drift_score: 0.0,
    drift_history: [],
    total_samples: 0,
    classes: ["NORMAL", "DOS_FLOOD", "REPLAY_ATTACK", "SLOW_RATE_ATTACK", "DATA_POISON", "TOPIC_BOMB", "EVASION_ATTACK"]
  });
  const [incident, setIncident]        = useState<IncidentState>({ text:"", label:"", ts:"" });
  const [totalPkts,setTotal]           = useState(0);
  const [wsReady, setWsReady]          = useState(false);

  // 50-Node Simulator state
  const [simTopology, setSimTopology]     = useState<SimTopology | null>(null);
  const [simNodeStates, setSimNodeStates] = useState<SimNodeStates>({});
  const [showSimulated, setShowSimulated] = useState(false);

  const pktIdRef   = useRef(0);
  const alertIdRef = useRef(0);
  const pktRateRef = useRef<Record<string,number>>({ esp32_1:0, esp32_2:0, esp32_3:0 });

  useEffect(() => {
    let ws: WebSocket;

    function connect() {
      try {
        ws = new WebSocket("ws://localhost:8000/ws/live");

        ws.onopen  = () => { setWsReady(true);  console.log("[WS] Connected"); };
        ws.onclose = () => { setWsReady(false); console.log("[WS] Disconnected, retrying..."); setTimeout(connect, 3000); };
        ws.onerror = (e) => { console.error("[WS] Error", e); ws.close(); };

        ws.onmessage = (e) => {
          const d = JSON.parse(e.data);
          const now = new Date().toLocaleTimeString("en-GB");

          // ── Real ML inference result (every 5s from model) ───────────────
          if (d.topic === "netguard_rohit_77/inference") {
            const isAtk = d.isAttack as boolean;
            setML({
              label:      d.label,
              confidence: d.confidence,
              isAttack:   isAtk,
              pktRate:    d.pkt_rate ?? 0,
              iatMean:    d.iat_mean ?? 0,
              dupRatio:   d.dup_ratio ?? 0,
              seqGap:     d.seq_gap ?? 1,
              shap:       d.shap ?? [],
              baseline:   d.baseline,
            });

            // Anomaly score from model confidence
            const anomaly = isAtk ? d.confidence : Math.max(0, 100 - d.confidence);
            setTemporal(t => [...t, {
              t: now, anomaly,
              r1: pktRateRef.current.esp32_1,
              r2: pktRateRef.current.esp32_2,
              r3: pktRateRef.current.esp32_3,
            }].slice(-60));

            if (isAtk) {
              const sev: AlertEntry["severity"] =
                d.label === "DOS_FLOOD" ? "CRITICAL" :
                d.label === "REPLAY_ATTACK" ? "HIGH" : "MEDIUM";
              setAlerts(a => [{
                id: ++alertIdRef.current, time: now,
                title: `${d.label.replace(/_/g," ")} detected on ESP32_3`,
                severity: sev, device: "esp32_3",
                meta: `rate:${d.pkt_rate}pkt/s · iat:${d.iat_mean}ms · dup:${(d.dup_ratio*100).toFixed(0)}% · conf:${d.confidence}%`
              }, ...a].slice(0, 80));
            }
            return;
          }

          // ── Incident narrative (auto-generated by RAG on attack) ──────────
          if (d.topic === "netguard_rohit_77/incident") {
            setIncident({ text: d.text ?? "", label: d.label ?? "", ts: d.ts ?? "" });
            return;
          }

          // ── Real-time evaluation and concept drift payload ─────────────
          if (d.topic === "netguard_rohit_77/evaluation") {
            setEvaluation({
              hybrid_cm: d.hybrid_cm ?? [],
              baseline_cm: d.baseline_cm ?? [],
              hybrid_metrics: d.hybrid_metrics ?? { accuracy: 0, precision: 0, recall: 0, f1: 0 },
              baseline_metrics: d.baseline_metrics ?? { accuracy: 0, precision: 0, recall: 0, f1: 0 },
              drift_score: d.drift_score ?? 0.0,
              drift_history: d.drift_history ?? [],
              total_samples: d.total_samples ?? 0,
              classes: d.classes ?? []
            });
            return;
          }

          // ── Simulator toggle state ────────────────────────────────────
          if (d.topic === "netguard_toggle/simulated") {
            setShowSimulated(d.show ?? false);
            return;
          }

          // ── 50-Node Simulator: Topology ───────────────────────────────
          if (d.topic === "netguard_50node/topology") {
            setSimTopology({ nodes: d.nodes ?? [], links: d.links ?? [] });
            return;
          }

          // ── 50-Node Simulator: Status (per-node attack state) ─────────
          if (d.topic === "netguard_50node/status") {
            setSimNodeStates(d.node_states ?? {});
            return;
          }

          // ── 50-Node Simulator: Attacker packets (just update node states) ─
          if (d.topic === "netguard_50node/attacker") {
            // Update the specific node's state based on attacker messages
            const device = d.device ?? "";
            const nodeId = device.replace("esp32_", "");
            if (nodeId && d.mode) {
              setSimNodeStates(prev => ({ ...prev, [nodeId]: d.mode }));
            }
            return;
          }

          // ── Attacker packet — update node card only (ML comes from inference) ──
          if (d.topic === "netguard_rohit_77/attacker") {
            const pktRate = d.pkt_rate ?? 0;
            pktRateRef.current.esp32_3 = pktRate;
            setNodes(n => ({
              ...n,
              esp32_3: { ...n.esp32_3, mode: d.mode, seq: d.seq, pktRate, lastSeen: now, online: true }
            }));
            const entry: PacketEntry = { id: ++pktIdRef.current, time: now, label: d.mode, device: "netguard_rohit_77/attacker", iat: 0 };
            setPackets(p => [entry, ...p].slice(0, 120));
            setTotal(p => p + 1);
          }

          else if (d.topic === "netguard_rohit_77/device1") {
            pktRateRef.current.esp32_1 = +(pktRateRef.current.esp32_1 * 0.8 + 0.5).toFixed(1);
            setNodes(n => ({ ...n, esp32_1: { ...n.esp32_1, temp: d.temp, humidity: d.humidity, pktRate: +pktRateRef.current.esp32_1.toFixed(1), lastSeen: now, online: true } }));
            setSensorTemporal(s => [...s, { t: now, temp: d.temp, humidity: d.humidity }].slice(-80));
            const entry: PacketEntry = { id: ++pktIdRef.current, time: now, label:"LEGITIMATE", device:"netguard_rohit_77/device1", iat:0 };
            setPackets(p => [entry, ...p].slice(0, 120));
            setTotal(p => p + 1);
          }

          // ── LDR packet ───────────────────────────────────────────────────
          else if (d.topic === "netguard_rohit_77/device2") {
            pktRateRef.current.esp32_2 = +(pktRateRef.current.esp32_2 * 0.8 + 0.5).toFixed(1);
            setNodes(n => ({ ...n, esp32_2: { ...n.esp32_2, light: d.light, pktRate: +pktRateRef.current.esp32_2.toFixed(1), lastSeen: now, online: true } }));
            setSensorTemporal(s => [...s, { t: now, light: d.light }].slice(-80));
            const entry: PacketEntry = { id: ++pktIdRef.current, time: now, label:"LEGITIMATE", device:"netguard_rohit_77/device2", iat:0 };
            setPackets(p => [entry, ...p].slice(0, 120));
            setTotal(p => p + 1);
          }
        };
      } catch(err) {
        console.error("[WS] Failed to connect:", err);
        setTimeout(connect, 3000);
      }
    }

    connect();
    return () => { try { ws?.close(); } catch {} };
  }, []);

  const triggerAttack = useCallback(async (mode: string) => {
    try {
      await fetch("http://localhost:8000/attacker/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
    } catch (e) {
      console.error("Backend offline:", e);
    }
  }, []);

  const simulate = useCallback(async (mode: string) => {
    try {
      await fetch("http://localhost:8000/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
    } catch (e) {
      console.error("Simulate offline:", e);
    }
  }, []);

  const resetEvaluation = useCallback(async () => {
    try {
      await fetch("http://localhost:8000/evaluation/reset", {
        method: "POST",
      });
    } catch (e) {
      console.error("Reset evaluation offline:", e);
    }
  }, []);

  const toggleSimulated = useCallback(async (show: boolean) => {
    try {
      await fetch("http://localhost:8000/toggle/simulated", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ show }),
      });
    } catch (e) {
      console.error("Toggle simulated offline:", e);
    }
  }, []);

  const simAttack = useCallback(async (mode: string, targetNode?: number) => {
    try {
      await fetch("http://localhost:8000/simulator/attack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, target_node: targetNode }),
      });
    } catch (e) {
      console.error("Sim attack offline:", e);
    }
  }, []);

  const simRelease = useCallback(async () => {
    try {
      await fetch("http://localhost:8000/simulator/release", {
        method: "POST",
      });
    } catch (e) {
      console.error("Sim release offline:", e);
    }
  }, []);

  return {
    nodes, packets, alerts, temporal, sensorTemporal, ml, evaluation, resetEvaluation,
    incident, totalPkts, wsReady, triggerAttack, simulate,
    // 50-node simulator
    simTopology, simNodeStates, showSimulated, toggleSimulated, simAttack, simRelease,
  };
}
