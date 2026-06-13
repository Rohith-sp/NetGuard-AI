"use client";
import React, { useRef, useEffect, useMemo, useState } from "react";
import * as d3 from "d3";
import type { SimTopology, SimNodeStates } from "../hooks/useLiveData";
import { RefreshIcon, LightningIcon, CheckIcon } from "./Icons";

interface Network50TabProps {
  topology: SimTopology | null;
  nodeStates: SimNodeStates;
  simAttack: (mode: string, targetNode?: number) => Promise<void>;
  simRelease: () => Promise<void>;
}

const NODE_COLORS: Record<string, string> = {
  gateway: "#a855f7",
  router:  "#3b82f6",
  dht:     "#10b981",
  ldr:     "#f59e0b",
  pir:     "#ef4444",
};

const ATTACK_COLORS: Record<string, string> = {
  NORMAL:           "#10b981",
  DOS_FLOOD:        "#ef4444",
  REPLAY_ATTACK:    "#f97316",
  SLOW_RATE_ATTACK: "#3b82f6",
  DATA_POISON:      "#a855f7",
  TOPIC_BOMB:       "#ec4899",
  EVASION_ATTACK:   "#06b6d4",
};

const ATTACKS = ["DOS_FLOOD", "REPLAY_ATTACK", "SLOW_RATE_ATTACK", "DATA_POISON", "TOPIC_BOMB", "EVASION_ATTACK"];

export default function Network50Tab({ topology, nodeStates, simAttack, simRelease }: Network50TabProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoveredNode, setHoveredNode] = useState<{ id: number; label: string; type: string; state: string } | null>(null);
  const [selectedAttack, setSelectedAttack] = useState<string>("DOS_FLOOD");

  // Keep a ref of nodeStates to avoid stale closures in mouse events
  const nodeStatesRef = useRef(nodeStates);
  useEffect(() => {
    nodeStatesRef.current = nodeStates;
  }, [nodeStates]);

  // Compute attack distribution
  const attackDist = useMemo(() => {
    const dist: Record<string, number> = { NORMAL: 0 };
    ATTACKS.forEach(a => { dist[a] = 0; });
    Object.values(nodeStates).forEach(s => {
      if (dist[s] !== undefined) dist[s]++;
      else dist["NORMAL"]++;
    });
    return dist;
  }, [nodeStates]);

  const totalNodes = Object.keys(nodeStates).length || 47;
  const attackedCount = totalNodes - (attackDist["NORMAL"] || 0);

  // Compute static topology key to avoid recreating force simulation on reference changes
  const topoKey = useMemo(() => {
    if (!topology) return "";
    const nodeIds = topology.nodes.map(n => n.id).sort().join(",");
    const linkIds = topology.links.map(l => `${l.source}-${l.target}`).sort().join(",");
    return `${nodeIds}|${linkIds}`;
  }, [topology]);

  // D3 Force Graph Initialization (only runs when topology structure changes)
  useEffect(() => {
    if (!svgRef.current || !topology || topology.nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    const width = 900;
    const height = 520;

    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const defs = svg.append("defs");
    // Glow filter
    const filter = defs.append("filter").attr("id", "glow");
    filter.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "coloredBlur");
    const feMerge = filter.append("feMerge");
    feMerge.append("feMergeNode").attr("in", "coloredBlur");
    feMerge.append("feMergeNode").attr("in", "SourceGraphic");

    // Attack pulse filter
    const pulseFilter = defs.append("filter").attr("id", "attack-pulse");
    pulseFilter.append("feGaussianBlur").attr("stdDeviation", "5").attr("result", "blur");
    const pulseMerge = pulseFilter.append("feMerge");
    pulseMerge.append("feMergeNode").attr("in", "blur");
    pulseMerge.append("feMergeNode").attr("in", "SourceGraphic");

    const g = svg.append("g");

    // Zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 4])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });
    svg.call(zoom);

    // Prepare data (shallow copy to prevent mutating the original props)
    const nodesData = topology.nodes.map(n => ({ ...n, x: width / 2, y: height / 2 }));
    const linksData = topology.links.map(l => ({ source: l.source, target: l.target }));

    // Force simulation
    const simulation = d3.forceSimulation(nodesData as any)
      .force("link", d3.forceLink(linksData as any).id((d: any) => d.id).distance(55).strength(0.6))
      .force("charge", d3.forceManyBody().strength(-120))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(18));

    // Links
    const link = g.append("g")
      .selectAll("line")
      .data(linksData)
      .join("line")
      .attr("stroke", "rgba(255,255,255,0.08)")
      .attr("stroke-width", 1);

    // Nodes
    const node = g.append("g")
      .selectAll("g")
      .data(nodesData)
      .join("g")
      .attr("class", "node-group")
      .attr("cursor", "pointer")
      .call(d3.drag<any, any>()
        .on("start", (event, d: any) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d: any) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d: any) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        }) as any
      );

    // Node circles
    node.append("circle")
      .attr("class", "node-circle")
      .attr("r", (d: any) => d.type === "gateway" ? 14 : d.type === "router" ? 10 : 7)
      .attr("fill", (d: any) => {
        const state = nodeStatesRef.current[String(d.id)] || "NORMAL";
        if (state !== "NORMAL") return ATTACK_COLORS[state] || "#ef4444";
        return NODE_COLORS[d.type] || "#10b981";
      })
      .attr("stroke", (d: any) => {
        const state = nodeStatesRef.current[String(d.id)] || "NORMAL";
        if (state !== "NORMAL") return "#fff";
        return "rgba(255,255,255,0.15)";
      })
      .attr("stroke-width", (d: any) => {
        const state = nodeStatesRef.current[String(d.id)] || "NORMAL";
        return state !== "NORMAL" ? 2.5 : 1;
      })
      .attr("filter", (d: any) => {
        const state = nodeStatesRef.current[String(d.id)] || "NORMAL";
        return state !== "NORMAL" ? "url(#attack-pulse)" : "none";
      });

    // Labels for gateway and routers
    node.filter((d: any) => d.type === "gateway" || d.type === "router")
      .append("text")
      .text((d: any) => d.label)
      .attr("font-size", 8)
      .attr("fill", "rgba(255,255,255,0.7)")
      .attr("text-anchor", "middle")
      .attr("dy", -16)
      .attr("font-family", "var(--mono)");

    // Node ID labels
    node.filter((d: any) => d.type !== "gateway" && d.type !== "router")
      .append("text")
      .text((d: any) => d.id)
      .attr("font-size", 7)
      .attr("fill", "rgba(255,255,255,0.4)")
      .attr("text-anchor", "middle")
      .attr("dy", -12)
      .attr("font-family", "var(--mono)");

    // Mouse events
    node.on("mouseenter", (event, d: any) => {
      const state = nodeStatesRef.current[String(d.id)] || "NORMAL";
      setHoveredNode({ id: d.id, label: d.label, type: d.type, state });
    });
    node.on("mouseleave", () => setHoveredNode(null));

    // Tick update
    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);

      node.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
  }, [topoKey]);

  // Update styles and colors without restarting/recreating force simulation
  useEffect(() => {
    if (!svgRef.current || !topology || topology.nodes.length === 0) return;
    const svg = d3.select(svgRef.current);

    svg.selectAll("circle.node-circle")
      .transition()
      .duration(200)
      .attr("fill", (d: any) => {
        const state = nodeStates[String(d.id)] || "NORMAL";
        if (state !== "NORMAL") return ATTACK_COLORS[state] || "#ef4444";
        return NODE_COLORS[d.type] || "#10b981";
      })
      .attr("stroke", (d: any) => {
        const state = nodeStates[String(d.id)] || "NORMAL";
        if (state !== "NORMAL") return "#fff";
        return "rgba(255,255,255,0.15)";
      })
      .attr("stroke-width", (d: any) => {
        const state = nodeStates[String(d.id)] || "NORMAL";
        return state !== "NORMAL" ? 2.5 : 1;
      })
      .attr("filter", (d: any) => {
        const state = nodeStates[String(d.id)] || "NORMAL";
        return state !== "NORMAL" ? "url(#attack-pulse)" : "none";
      });
  }, [nodeStates, topoKey]);

  if (!topology) {
    return (
      <div style={{ textAlign: "center", padding: 60, color: "var(--text-3)" }}>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
          <RefreshIcon width={36} height={36} className="spin" color="var(--text-3)" />
        </div>
        <div style={{ fontSize: 14 }}>Waiting for 50-node simulator to connect...</div>
        <div style={{ fontSize: 11, marginTop: 6 }}>Run <code style={{ fontFamily: "var(--mono)", background: "var(--surface2)", padding: "2px 6px", borderRadius: 4 }}>python large_scale_simulator.py</code> to start</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Top: Attack Controls */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">50-Node Simulator Attack Controls</span>
          <span className="card-tag red">{attackedCount > 0 ? `${attackedCount} UNDER ATTACK` : "ALL CLEAR"}</span>
        </div>
        <div className="card-body" style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          {ATTACKS.map(atk => (
            <button
              key={atk}
              className={`atk-select ${selectedAttack === atk ? "active" : ""}`}
              onClick={() => setSelectedAttack(atk)}
              style={{
                fontSize: 10,
                padding: "5px 10px",
                borderRadius: 6,
                background: selectedAttack === atk ? ATTACK_COLORS[atk] : "var(--surface2)",
                color: selectedAttack === atk ? "#fff" : "var(--text-2)",
                border: `1px solid ${selectedAttack === atk ? ATTACK_COLORS[atk] : "var(--border)"}`,
                cursor: "pointer",
                transition: "all 0.2s",
              }}
            >
              {atk.replace(/_/g, " ")}
            </button>
          ))}
          <div style={{ flex: 1 }} />
          <button
            onClick={() => simAttack(selectedAttack)}
            style={{
              fontSize: 11, fontWeight: 600, padding: "6px 16px", borderRadius: 6,
              background: "var(--red)", color: "#fff", border: "none", cursor: "pointer",
              display: "flex", alignItems: "center", gap: 6
            }}
          >
            <LightningIcon width={12} height={12} color="#fff" /> Launch {selectedAttack.replace(/_/g, " ")}
          </button>
          <button
            onClick={simRelease}
            style={{
              fontSize: 11, fontWeight: 600, padding: "6px 16px", borderRadius: 6,
              background: "var(--green)", color: "#fff", border: "none", cursor: "pointer",
              display: "flex", alignItems: "center", gap: 6
            }}
          >
            <CheckIcon width={12} height={12} color="#fff" /> Release All
          </button>
        </div>
      </div>

      {/* Middle: Graph + Sidebar */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 16 }}>
        {/* D3 Graph */}
        <div className="card" style={{ overflow: "hidden" }}>
          <div className="card-header">
            <span className="card-title">Network Topology — 50 Nodes</span>
            <span className="card-tag blue">{topology.nodes.length} NODES · {topology.links.length} EDGES</span>
          </div>
          <div className="card-body" style={{ padding: 0, background: "#0a0f1a", position: "relative" }}>
            <svg
              ref={svgRef}
              style={{ width: "100%", height: 520 }}
            />
            {/* Hover tooltip */}
            {hoveredNode && (
              <div style={{
                position: "absolute", top: 12, right: 12,
                background: "rgba(10,15,26,0.9)", border: "1px solid var(--border)",
                borderRadius: 8, padding: "10px 14px", fontSize: 11,
                backdropFilter: "blur(8px)",
              }}>
                <div style={{ fontWeight: 600, color: "var(--text)", marginBottom: 4 }}>{hoveredNode.label}</div>
                <div style={{ color: "var(--text-3)" }}>
                  ID: <span style={{ fontFamily: "var(--mono)" }}>{hoveredNode.id}</span>
                </div>
                <div style={{ color: "var(--text-3)" }}>
                  Type: <span style={{ fontFamily: "var(--mono)", color: NODE_COLORS[hoveredNode.type] }}>{hoveredNode.type.toUpperCase()}</span>
                </div>
                <div style={{ color: "var(--text-3)" }}>
                  Status: <span style={{
                    fontFamily: "var(--mono)", fontWeight: 600,
                    color: hoveredNode.state !== "NORMAL" ? ATTACK_COLORS[hoveredNode.state] : "var(--green)"
                  }}>{hoveredNode.state}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Sidebar: Stats & Legend */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Attack Distribution */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Attack Distribution</span>
            </div>
            <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {Object.entries(attackDist).map(([label, count]) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{
                    width: 8, height: 8, borderRadius: "50%",
                    background: ATTACK_COLORS[label] || "#666",
                    flexShrink: 0,
                  }} />
                  <span style={{ flex: 1, fontSize: 10, color: "var(--text-2)", fontFamily: "var(--mono)" }}>
                    {label.replace(/_/g, " ")}
                  </span>
                  <span style={{
                    fontSize: 11, fontWeight: 600, fontFamily: "var(--mono)",
                    color: count > 0 && label !== "NORMAL" ? ATTACK_COLORS[label] : "var(--text-3)",
                  }}>
                    {count}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Node Type Legend */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Node Types</span>
            </div>
            <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { type: "gateway", label: "Gateway", count: 1 },
                { type: "router", label: "Cluster Head", count: 3 },
                { type: "dht", label: "DHT Sensor", count: 17 },
                { type: "ldr", label: "LDR Sensor", count: 15 },
                { type: "pir", label: "PIR / Attacker", count: 15 },
              ].map(item => (
                <div key={item.type} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{
                    width: 10, height: 10, borderRadius: "50%",
                    background: NODE_COLORS[item.type],
                    flexShrink: 0,
                  }} />
                  <span style={{ flex: 1, fontSize: 11, color: "var(--text-2)" }}>{item.label}</span>
                  <span style={{ fontSize: 10, fontFamily: "var(--mono)", color: "var(--text-3)" }}>×{item.count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Summary Stats */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Network Health</span>
            </div>
            <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 11, color: "var(--text-3)" }}>Total Nodes</span>
                <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--mono)", color: "var(--text)" }}>{topology.nodes.length}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 11, color: "var(--text-3)" }}>Normal</span>
                <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--mono)", color: "var(--green)" }}>{attackDist["NORMAL"] || totalNodes}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 11, color: "var(--text-3)" }}>Under Attack</span>
                <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--mono)", color: attackedCount > 0 ? "var(--red)" : "var(--text-3)" }}>{attackedCount}</span>
              </div>
              {/* Progress bar */}
              <div style={{ height: 6, borderRadius: 3, background: "var(--surface2)", overflow: "hidden" }}>
                <div style={{
                  height: "100%", borderRadius: 3,
                  width: `${((totalNodes - attackedCount) / Math.max(totalNodes, 1)) * 100}%`,
                  background: "linear-gradient(90deg, var(--green), #34d399)",
                  transition: "width 0.5s ease",
                }} />
              </div>
              <div style={{ fontSize: 10, color: "var(--text-3)", textAlign: "center" }}>
                {((totalNodes - attackedCount) / Math.max(totalNodes, 1) * 100).toFixed(0)}% network healthy
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
