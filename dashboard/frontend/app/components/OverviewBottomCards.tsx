"use client";

import React, { useEffect, useState } from 'react';

// Generates a deterministic-looking heatmap matching the mockup
function generateHeatmap() {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const grid: { day: string, hours: string[] }[] = [];
  
  // Seed colors: 0: very light green, 1: light green, 2: medium green, 3: dark green, 4: amber, 5: red
  const colors = ["#d6ede0", "#a8d4b8", "#5aaa80", "#00884a", "#c07800", "#cc1122"];
  
  const seed = [
    [2,3,4,4,4,1,1,1,2,0,4,4,2,3,4,0,3,4,1,1,2,3,0,1], // Mon
    [5,5,0,0,3,1,0,5,1,1,3,3,5,1,3,1,3,5,0,0,3,5,1,1], // Tue
    [1,1,5,5,3,3,0,5,4,4,3,1,5,4,5,5,3,3,4,0,1,1,3,3], // Wed
    [0,0,4,4,5,5,4,5,5,4,0,5,2,0,4,4,5,5,4,4,3,3,5,5], // Thu
    [4,4,3,3,5,5,3,4,5,5,1,5,3,0,5,5,5,5,3,3,3,4,3,3], // Fri
    [1,2,1,4,4,3,1,4,4,2,0,5,4,1,5,0,3,1,5,1,4,5,0,0], // Sat
    [5,0,5,5,4,4,3,1,3,2,4,0,3,2,4,5,0,5,4,0,0,4,5,5]  // Sun
  ];

  for (let i = 0; i < 7; i++) {
    const hours = [];
    for (let j = 0; j < 24; j++) {
      hours.push(colors[seed[i][j]]);
    }
    grid.push({ day: days[i], hours });
  }
  return grid;
}

export function OverviewBottomCards() {
  const [heatmap, setHeatmap] = useState<{day: string, hours: string[]}[]>([]);

  useEffect(() => {
    setHeatmap(generateHeatmap());
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", marginTop: "2rem" }}>
      
      {/* Heatmap Card */}
      <div className="card">
        <div style={{ fontFamily: "'Orbitron', monospace", fontSize: "0.7rem", color: "var(--text-muted)", letterSpacing: "2px", marginBottom: "1.5rem", textTransform: "uppercase" }}>
          Attack Heatmap — Last 7 Days × 24 Hours
        </div>
        
        <div style={{ overflowX: "auto" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: "800px" }}>
            {/* Header row for hours */}
            <div style={{ display: "flex", paddingLeft: "40px", marginBottom: "4px" }}>
              {[0, 6, 12, 18].map(h => (
                <div key={h} style={{ width: "25%", fontFamily: "'Share Tech Mono', monospace", fontSize: "0.65rem", color: "var(--text-muted)" }}>
                  {h}
                </div>
              ))}
            </div>
            
            {/* Grid */}
            {heatmap.map((row, i) => (
              <div key={row.day} style={{ display: "flex", alignItems: "center" }}>
                <div style={{ width: "40px", fontFamily: "'Share Tech Mono', monospace", fontSize: "0.65rem", color: "var(--text-muted)", textAlign: "right", paddingRight: "8px" }}>
                  {row.day}
                </div>
                <div style={{ display: "flex", flex: 1, gap: "2px" }}>
                  {row.hours.map((color, j) => (
                    <div 
                      key={j} 
                      style={{ 
                        flex: 1, 
                        height: "14px", 
                        backgroundColor: color, 
                        borderRadius: "2px",
                        transition: "transform 0.1s",
                        cursor: "default"
                      }} 
                      onMouseEnter={(e) => e.currentTarget.style.transform = "scale(1.3)"}
                      onMouseLeave={(e) => e.currentTarget.style.transform = "scale(1)"}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        
        <div style={{ display: "flex", gap: "1rem", marginTop: "1rem", alignItems: "center", fontFamily: "'Share Tech Mono', monospace", fontSize: "0.7rem", color: "var(--text-muted)" }}>
          <span>Intensity:</span>
          <div style={{ display: "flex", gap: "3px" }}>
            <div style={{ width: "12px", height: "12px", background: "#d6ede0", borderRadius: "2px" }} />
            <div style={{ width: "12px", height: "12px", background: "#a8d4b8", borderRadius: "2px" }} />
            <div style={{ width: "12px", height: "12px", background: "#5aaa80", borderRadius: "2px" }} />
            <div style={{ width: "12px", height: "12px", background: "#c07800", borderRadius: "2px" }} />
            <div style={{ width: "12px", height: "12px", background: "#cc1122", borderRadius: "2px" }} />
          </div>
          <span>Low → Critical</span>
        </div>
      </div>

      {/* Two columns for Donut and Trust Scores */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        
        {/* Threat Breakdown */}
        <div className="card">
          <div style={{ fontFamily: "'Orbitron', monospace", fontSize: "0.7rem", color: "var(--text-muted)", letterSpacing: "2px", marginBottom: "1.5rem", textTransform: "uppercase" }}>
            Threat Breakdown
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "2.5rem", padding: "10px 0" }}>
            <svg width="140" height="140" viewBox="0 0 140 140" style={{ filter: "drop-shadow(0 4px 6px rgba(0,0,0,0.05))" }}>
              {/* DoS Flood: 45% = 141.3 dash length */}
              <circle cx="70" cy="70" r="50" fill="none" stroke="#cc1122" strokeWidth="20" strokeDasharray="141.3 172.8" strokeDashoffset="0"/>
              {/* Replay: 30% = 94.2 dash length */}
              <circle cx="70" cy="70" r="50" fill="none" stroke="#c07800" strokeWidth="20" strokeDasharray="94.2 219.9" strokeDashoffset="-141.3"/>
              {/* Slow-Rate: 25% = 78.5 dash length */}
              <circle cx="70" cy="70" r="50" fill="none" stroke="#006699" strokeWidth="20" strokeDasharray="78.5 235.6" strokeDashoffset="-235.5"/>
              <circle cx="70" cy="70" r="35" fill="var(--card-bg)"/>
              <text x="70" y="66" textAnchor="middle" fontFamily="Orbitron, monospace" fontSize="10" fill="var(--primary)" fontWeight="700">THREATS</text>
              <text x="70" y="80" textAnchor="middle" fontFamily="Share Tech Mono, monospace" fontSize="9" fill="var(--text-muted)">7-Day</text>
            </svg>
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", fontFamily: "'Share Tech Mono', monospace", fontSize: "0.85rem", color: "var(--text-dim)" }}>
                <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#cc1122", flexShrink: 0 }} />
                DoS Flood — 45%
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", fontFamily: "'Share Tech Mono', monospace", fontSize: "0.85rem", color: "var(--text-dim)" }}>
                <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#c07800", flexShrink: 0 }} />
                Replay — 30%
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", fontFamily: "'Share Tech Mono', monospace", fontSize: "0.85rem", color: "var(--text-dim)" }}>
                <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#006699", flexShrink: 0 }} />
                Slow-Rate — 25%
              </div>
            </div>
          </div>
        </div>

        {/* Device Trust Scores */}
        <div className="card">
          <div style={{ fontFamily: "'Orbitron', monospace", fontSize: "0.7rem", color: "var(--text-muted)", letterSpacing: "2px", marginBottom: "2rem", textTransform: "uppercase" }}>
            Device Trust Scores
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "'Share Tech Mono', monospace", fontSize: "0.85rem", color: "var(--text-dim)", alignItems: "center" }}>
              <span>ESP32 #1 — 192.168.1.101</span>
              <span style={{ color: "var(--green)" }}>94%</span>
            </div>
            
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "'Share Tech Mono', monospace", fontSize: "0.85rem", color: "var(--text-dim)", alignItems: "center" }}>
              <span>ESP32 #2 — 192.168.1.102</span>
              <span style={{ color: "var(--green)" }}>91%</span>
            </div>
            
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "'Share Tech Mono', monospace", fontSize: "0.85rem", color: "var(--text-dim)", alignItems: "center" }}>
              <span>ESP32 #3 — 192.168.1.103</span>
              <span style={{ color: "var(--red)" }}>22%</span>
            </div>

          </div>
        </div>
        
      </div>
    </div>
  );
}
