"use client";
import { useEffect, useRef } from "react";
import type { TemporalPoint } from "../hooks/useLiveData";

// ─── Anomaly SVG Graph ─────────────────────────────────────────────────────────
export function AnomalyGraph({ data }: { data: TemporalPoint[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length < 2) return;
    const W = 800, H = 140, PAD = 30;
    const vals = data.map(d => d.anomaly);
    const latest = vals[vals.length-1] ?? 0;
    const isAtk = latest > 50;
    const color = isAtk ? "#dc2626" : "#059669";
    const grad  = isAtk ? "url(#area-grad-red)" : "url(#area-grad-green)";

    const pts = vals.map((v, i) => {
      const x = PAD + (i / (vals.length - 1)) * (W - PAD);
      const y = (H - 2) - (v / 100) * (H - 12); // Keep line stroke within viewBox
      return [x, y] as [number, number];
    });

    const linePath = pts.map((p, i) => `${i===0?"M":"L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
    const areaPath = linePath + ` L${pts[pts.length-1][0]},${H} L${pts[0][0]},${H} Z`;

    const lineEl = svgRef.current.querySelector("#anomaly-line") as SVGPathElement|null;
    const areaEl = svgRef.current.querySelector("#anomaly-area") as SVGPathElement|null;
    if (lineEl) { lineEl.setAttribute("d", linePath); lineEl.setAttribute("stroke", color); }
    if (areaEl) { areaEl.setAttribute("d", areaPath); areaEl.setAttribute("fill", grad); }
  }, [data]);

  return (
    <div className="anomaly-graph-wrap">
      <svg ref={svgRef} id="anomaly-svg" width="100%" height="100%" viewBox="0 0 800 140" preserveAspectRatio="none">
        <defs>
          <linearGradient id="area-grad-green" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#059669" stopOpacity="0.18"/>
            <stop offset="100%" stopColor="#059669" stopOpacity="0"/>
          </linearGradient>
          <linearGradient id="area-grad-red" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#dc2626" stopOpacity="0.18"/>
            <stop offset="100%" stopColor="#dc2626" stopOpacity="0"/>
          </linearGradient>
        </defs>
        <text x="2" y="14" fontFamily="JetBrains Mono" fontSize="9" fill="#8a9e86">100%</text>
        <text x="2" y="72" fontFamily="JetBrains Mono" fontSize="9" fill="#8a9e86">50%</text>
        <text x="2" y="136" fontFamily="JetBrains Mono" fontSize="9" fill="#8a9e86">0%</text>
        <line x1="28" y1="70" x2="800" y2="70" stroke="#e2e6e0" strokeWidth="1" strokeDasharray="4,4"/>
        <text x="32" y="67" fontFamily="JetBrains Mono" fontSize="8" fill="#cdd4c9">threshold</text>
        <path id="anomaly-area" d="" fill="url(#area-grad-green)"/>
        <path id="anomaly-line" d="" fill="none" stroke="#059669" strokeWidth="1.8"/>
      </svg>
    </div>
  );
}

// ─── Packet Rate SVG Graph ─────────────────────────────────────────────────────
export function PktRateGraph({ data }: { data: TemporalPoint[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length < 2) return;
    const W = 800, H = 80, PAD = 30;
    const maxR = Math.max(...data.map(d => Math.max(d.r1, d.r2, d.r3)), 10);

    function makePts(vals: number[]) {
      return vals.map((v, i) => {
        const x = PAD + (i / (vals.length-1)) * (W-PAD);
        const y = (H - 2) - (v / maxR) * (H - 10); // Prevent bottom clip
        return `${i===0?"M":"L"}${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
    }

    const l1 = svgRef.current.querySelector("#pkt-line1") as SVGPolylineElement|null;
    const l2 = svgRef.current.querySelector("#pkt-line2") as SVGPolylineElement|null;
    const l3 = svgRef.current.querySelector("#pkt-line3") as SVGPolylineElement|null;
    if (l1) l1.setAttribute("points", data.map((d,i)=>{ const x=PAD+(i/(data.length-1))*(W-PAD); const y=(H-2)-(d.r1/maxR)*(H-10); return `${x},${y}`; }).join(" "));
    if (l2) l2.setAttribute("points", data.map((d,i)=>{ const x=PAD+(i/(data.length-1))*(W-PAD); const y=(H-2)-(d.r2/maxR)*(H-10); return `${x},${y}`; }).join(" "));
    if (l3) l3.setAttribute("points", data.map((d,i)=>{ const x=PAD+(i/(data.length-1))*(W-PAD); const y=(H-2)-(d.r3/maxR)*(H-10); return `${x},${y}`; }).join(" "));
  }, [data]);

  return (
    <div className="pktrate-wrap">
      <svg ref={svgRef} id="pktrate-svg" width="100%" height="100%" viewBox="0 0 800 80" preserveAspectRatio="none">
        <text x="2" y="10" fontFamily="JetBrains Mono" fontSize="9" fill="#8a9e86">Max</text>
        <text x="2" y="78" fontFamily="JetBrains Mono" fontSize="9" fill="#8a9e86">0</text>
        <line x1="28" y1="75" x2="800" y2="75" stroke="#e2e6e0" strokeWidth="1"/>
        <polyline id="pkt-line1" points="" fill="none" stroke="#059669" strokeWidth="1.5" opacity="0.85"/>
        <polyline id="pkt-line2" points="" fill="none" stroke="#2563eb" strokeWidth="1.5" opacity="0.85"/>
        <polyline id="pkt-line3" points="" fill="none" stroke="#dc2626" strokeWidth="1.8"/>
      </svg>
    </div>
  );
}
