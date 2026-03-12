import { useState, useRef, useEffect } from "react";

/* ─── Mock data ─────────────────────────────────────────────────────────────── */
const MOCK_NODES = [
  { id: "e1", label: "Test Case",        type: "data",    x: 400, y: 200 },
  { id: "e2", label: "Test Suite",       type: "data",    x: 220, y: 130 },
  { id: "e3", label: "QA Engineer",      type: "actor",   x: 150, y: 300 },
  { id: "e4", label: "Regression Cycle", type: "process", x: 300, y: 360 },
  { id: "e5", label: "Defect",           type: "data",    x: 530, y: 330 },
  { id: "e6", label: "Requirements",     type: "data",    x: 560, y: 130 },
  { id: "e7", label: "Release",          type: "process", x: 680, y: 240 },
  { id: "e8", label: "Environment",      type: "system",  x: 420, y: 420 },
];
const MOCK_EDGES = [
  { source: "e2", target: "e1", label: "contains" },
  { source: "e3", target: "e2", label: "maintains" },
  { source: "e4", target: "e2", label: "executes" },
  { source: "e1", target: "e6", label: "validates" },
  { source: "e4", target: "e5", label: "reveals" },
  { source: "e5", target: "e7", label: "blocks" },
  { source: "e4", target: "e8", label: "runs on" },
];
const MOCK_GLOSSARY = [
  { term: "Test Case",         definition: "A set of conditions to verify a specific system behaviour.", related_terms: ["Test Suite", "Scenario"] },
  { term: "Regression Cycle",  definition: "Scheduled re-execution of tests after code changes to catch regressions.", related_terms: ["Test Suite", "Release"] },
  { term: "Coverage",          definition: "The fraction of requirements or code paths exercised by existing tests.", related_terms: ["Test Case", "Requirements"] },
  { term: "Defect",            definition: "A deviation from expected system behaviour identified during testing.", related_terms: ["Bug", "Issue", "Release"] },
  { term: "Smoke Test",        definition: "A minimal set of tests verifying basic system functionality before full regression.", related_terms: ["Test Suite", "Environment"] },
  { term: "Bus Factor",        definition: "Number of team members whose absence would critically impact the project.", related_terms: ["QA Engineer"] },
];

const TYPE_COLORS = {
  data:    "#c8902a",
  actor:   "#4a9e6b",
  process: "#5b7fba",
  system:  "#9b6bbf",
  concept: "#ba7a5b",
};

/* ─── Tiny components ───────────────────────────────────────────────────────── */
function Badge({ label, color }) {
  return (
    <span style={{
      fontSize: 10, padding: "2px 7px", borderRadius: 4, fontWeight: 600,
      background: color + "22", color, border: `1px solid ${color}44`,
      fontFamily: "monospace", letterSpacing: "0.3px",
    }}>{label.toUpperCase()}</span>
  );
}

function ProgressBar({ value, label, stage }) {
  const stageColors = { parse: "#5b7fba", embed: "#4a9e6b", extract: "#c8902a", assemble: "#9b6bbf" };
  const color = stageColors[stage] || "#c8902a";
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, fontSize: 12 }}>
        <span style={{ color: "#c8902a" }}>{label}</span>
        <span style={{ color: "#5a4e42", fontFamily: "monospace" }}>{Math.round(value * 100)}%</span>
      </div>
      <div style={{ height: 4, background: "#2a2520", borderRadius: 2, overflow: "hidden" }}>
        <div style={{
          height: "100%", width: `${value * 100}%`, background: color,
          borderRadius: 2, transition: "width 0.4s ease",
          boxShadow: `0 0 8px ${color}88`,
        }} />
      </div>
    </div>
  );
}

/* ─── Mind Map SVG ──────────────────────────────────────────────────────────── */
function MindMap({ nodes, edges }) {
  const [hovered, setHovered] = useState(null);
  return (
    <svg width="100%" height="100%" viewBox="0 0 750 480" style={{ overflow: "visible" }}>
      <defs>
        <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#3a3028" />
        </marker>
      </defs>
      {edges.map((e, i) => {
        const src = nodes.find(n => n.id === e.source);
        const tgt = nodes.find(n => n.id === e.target);
        if (!src || !tgt) return null;
        const mx = (src.x + tgt.x) / 2;
        const my = (src.y + tgt.y) / 2;
        return (
          <g key={i}>
            <line x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
              stroke="#3a3028" strokeWidth="1.5" markerEnd="url(#arrow)" />
            <text x={mx} y={my - 5} textAnchor="middle"
              fill="#5a4e42" fontSize="10" fontFamily="DM Mono, monospace">{e.label}</text>
          </g>
        );
      })}
      {nodes.map(n => {
        const color = TYPE_COLORS[n.type] || "#c8902a";
        const isH = hovered === n.id;
        return (
          <g key={n.id} onMouseEnter={() => setHovered(n.id)} onMouseLeave={() => setHovered(null)}
            style={{ cursor: "pointer" }}>
            <circle cx={n.x} cy={n.y} r={isH ? 36 : 30}
              fill={isH ? color + "33" : color + "18"}
              stroke={color} strokeWidth={isH ? 2 : 1.5}
              style={{ transition: "all 0.2s" }} />
            <text x={n.x} y={n.y + 4} textAnchor="middle"
              fill={color} fontSize="11" fontFamily="DM Sans, sans-serif" fontWeight="600">{n.label}</text>
            {isH && (
              <text x={n.x} y={n.y + 20} textAnchor="middle"
                fill="#8a7a68" fontSize="9" fontFamily="monospace">{n.type}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/* ─── Glossary Table ────────────────────────────────────────────────────────── */
function GlossaryTable({ items }) {
  const [search, setSearch] = useState("");
  const filtered = items.filter(i =>
    i.term.toLowerCase().includes(search.toLowerCase()) ||
    i.definition.toLowerCase().includes(search.toLowerCase())
  );
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <input
        value={search} onChange={e => setSearch(e.target.value)}
        placeholder="Search terms…"
        style={{
          background: "#1a1612", border: "1px solid #3a3028", borderRadius: 6,
          color: "#e8dcc8", padding: "6px 12px", fontSize: 12,
          fontFamily: "DM Sans, sans-serif", marginBottom: 10, outline: "none",
        }}
      />
      <div style={{ flex: 1, overflowY: "auto" }}>
        {filtered.map((item, i) => (
          <div key={i} style={{
            padding: "10px 14px", marginBottom: 6, background: "#1e1a16",
            border: "1px solid #2a2520", borderRadius: 8,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ fontWeight: 600, color: "#f0c060", fontSize: 13 }}>{item.term}</span>
            </div>
            <p style={{ color: "#c8b89a", fontSize: 12, lineHeight: 1.6, margin: "0 0 6px" }}>{item.definition}</p>
            {item.related_terms?.length > 0 && (
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                {item.related_terms.map((t, j) => (
                  <span key={j} style={{
                    fontSize: 10, padding: "1px 6px", border: "1px solid #3a3028",
                    borderRadius: 3, color: "#6a5e52", fontFamily: "monospace",
                  }}>{t}</span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── M1 Upload panel ───────────────────────────────────────────────────────── */
function M1UploadPanel({ onComplete }) {
  const [files, setFiles] = useState([]);
  const [building, setBuilding] = useState(false);
  const [progress, setProgress] = useState(null);
  const [logs, setLogs] = useState([]);
  const fileRef = useRef();

  const STAGES = [
    { key: "parse",    label: "Parsing documents",   icon: "📄" },
    { key: "embed",    label: "Building RAG index",  icon: "🧠" },
    { key: "extract",  label: "Extracting entities", icon: "🔍" },
    { key: "assemble", label: "Assembling artefacts",icon: "⚙️" },
  ];

  const simulateBuild = () => {
    setBuilding(true);
    setLogs([]);
    const steps = [
      { message: "Parsing requirements.docx…",           progress: 0.08, stage: "parse" },
      { message: "✓ Parsed: requirements.docx",          progress: 0.15, stage: "parse" },
      { message: "Parsing test_plan.pdf…",               progress: 0.20, stage: "parse" },
      { message: "✓ Parsed: test_plan.pdf",              progress: 0.25, stage: "parse" },
      { message: "Chunking & embedding documents…",      progress: 0.35, stage: "embed" },
      { message: "✓ Indexed 142 chunks into RAG KB",     progress: 0.45, stage: "embed" },
      { message: "Extracting domain entities…",          progress: 0.55, stage: "extract" },
      { message: "✓ Found 8 concepts, 7 relationships",  progress: 0.70, stage: "extract" },
      { message: "Building glossary…",                   progress: 0.80, stage: "extract" },
      { message: "✓ Built glossary with 6 terms",        progress: 0.85, stage: "extract" },
      { message: "Assembling mind map…",                 progress: 0.92, stage: "assemble" },
      { message: "✅ Context built successfully!",        progress: 1.00, stage: "assemble" },
    ];
    let i = 0;
    const tick = () => {
      if (i >= steps.length) {
        setTimeout(() => onComplete(), 600);
        return;
      }
      const s = steps[i++];
      setProgress(s);
      setLogs(prev => [...prev, s.message]);
      setTimeout(tick, 320 + Math.random() * 200);
    };
    tick();
  };

  const currentStageIdx = progress
    ? STAGES.findIndex(s => s.key === progress.stage)
    : -1;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 16 }}>
      <div style={{
        padding: "20px", background: "#1e1a16", border: "2px dashed #3a3028",
        borderRadius: 12, textAlign: "center", cursor: "pointer",
      }} onClick={() => fileRef.current?.click()}>
        <div style={{ fontSize: 32, marginBottom: 6 }}>📂</div>
        <div style={{ color: "#c8b89a", fontSize: 13, fontWeight: 500 }}>
          Drop Word / PDF files here
        </div>
        <div style={{ color: "#5a4e42", fontSize: 11, marginTop: 4 }}>
          .docx, .pdf — SRS, test plans, process docs, specs
        </div>
        <input ref={fileRef} type="file" multiple accept=".docx,.pdf" style={{ display: "none" }}
          onChange={e => setFiles(Array.from(e.target.files))} />
      </div>

      {/* Staged progress */}
      {building && progress && (
        <div style={{ padding: 14, background: "#1e1a16", borderRadius: 10, border: "1px solid #2a2520" }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
            {STAGES.map((s, i) => (
              <div key={s.key} style={{
                flex: 1, padding: "5px 4px", borderRadius: 6, textAlign: "center",
                fontSize: 10, fontWeight: 600,
                background: i <= currentStageIdx ? "#c8902a22" : "#1a1612",
                color: i <= currentStageIdx ? "#c8902a" : "#3a3028",
                border: `1px solid ${i === currentStageIdx ? "#c8902a" : "#2a2520"}`,
                transition: "all 0.3s",
              }}>
                {s.icon}<br/>{s.label}
              </div>
            ))}
          </div>
          <ProgressBar value={progress.progress} label={progress.message} stage={progress.stage} />
          <div style={{
            maxHeight: 80, overflowY: "auto", fontFamily: "monospace",
            fontSize: 11, color: "#5a4e42", lineHeight: 1.7,
          }}>
            {logs.map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </div>
      )}

      {/* File chips */}
      {files.length > 0 && !building && (
        <div>
          {files.map((f, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "7px 12px", background: "#1e1a16",
              border: "1px solid #2a2520", borderRadius: 6, marginBottom: 5,
              fontSize: 12, color: "#c8b89a",
            }}>
              <span style={{ color: "#c8902a", fontFamily: "monospace", fontSize: 10 }}>
                {f.name.split(".").pop().toUpperCase()}
              </span>
              <span style={{ flex: 1 }}>{f.name}</span>
            </div>
          ))}
        </div>
      )}

      {!building && (
        <button onClick={simulateBuild} disabled={files.length === 0}
          style={{
            padding: "10px", borderRadius: 8, border: "none", cursor: files.length ? "pointer" : "default",
            background: files.length
              ? "linear-gradient(135deg, #c8902a, #f0c060)"
              : "#2a2520",
            color: files.length ? "#1a1612" : "#4a3c2a",
            fontWeight: 600, fontSize: 13, fontFamily: "DM Sans, sans-serif",
          }}>
          {files.length ? `Build Context from ${files.length} file(s)` : "Select files first"}
        </button>
      )}
    </div>
  );
}

/* ─── Main App ──────────────────────────────────────────────────────────────── */
export default function AIBuddy() {
  const [activeModule, setActiveModule] = useState("m1");  // "m1" | "m2"
  const [m1Done, setM1Done] = useState(false);
  const [rightTab, setRightTab] = useState("mindmap");  // "mindmap" | "glossary"
  const [chatInput, setChatInput] = useState("");
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Context ready ✅ I've indexed **142 chunks** from 2 documents.\n\nI found **8 domain concepts** and built a **6-term glossary**.\n\nYou can now query the knowledge base — or switch to M2 to analyse your test suite." }
  ]);
  const [loading, setLoading] = useState(false);
  const msgEnd = useRef();

  useEffect(() => { msgEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  const send = () => {
    if (!chatInput.trim()) return;
    const q = chatInput;
    setChatInput("");
    setMessages(prev => [...prev, { role: "user", text: q }]);
    setLoading(true);
    setTimeout(() => {
      setMessages(prev => [...prev, {
        role: "assistant",
        text: "Based on the indexed documentation, **Regression Cycle** is a periodic process that executes the full Test Suite against a specific Environment.\n\nThe docs mention it runs **every sprint** (2 weeks) and is owned by the QA Engineer role. Coverage target is set at **85%** for critical paths.\n\n_Source: test_plan.pdf, section 3.2_"
      }]);
      setLoading(false);
    }, 1600);
  };

  const css = `
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');
    * { box-sizing: border-box; margin: 0; padding: 0; }
    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #3a3028; border-radius: 4px; }
    @keyframes fadeIn { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:translateY(0); } }
    @keyframes pulse { 0%,100% { opacity:.4; } 50% { opacity:1; } }
    .mod-btn:hover { background: #2a2520 !important; }
    .tab-btn:hover { color: #f0c060 !important; }
  `;

  return (
    <>
      <style>{css}</style>
      <div style={{ display: "flex", height: "100vh", background: "#141210", fontFamily: "DM Sans, sans-serif", color: "#e8dcc8", overflow: "hidden" }}>

        {/* ── Sidebar ── */}
        <div style={{ width: 220, background: "#1a1612", borderRight: "1px solid #2a2520", display: "flex", flexDirection: "column", flexShrink: 0 }}>
          {/* Logo */}
          <div style={{ padding: "18px 16px 14px", borderBottom: "1px solid #2a2520", display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 28, height: 28, borderRadius: 7, background: "linear-gradient(135deg,#c8902a,#f0c060)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 13, color: "#1a1612" }}>Q</div>
            <span style={{ fontWeight: 600, fontSize: 14, color: "#f0c060" }}>AI Buddy</span>
          </div>

          {/* Module switcher */}
          <div style={{ padding: "12px 10px", borderBottom: "1px solid #2a2520" }}>
            <div style={{ fontSize: 9, color: "#4a3c2a", textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 8, fontWeight: 600 }}>Modules</div>
            {[
              { id: "m1", icon: "🧠", label: "Context Builder", done: m1Done },
              { id: "m2", icon: "🔍", label: "Suite Analyzer", done: false, locked: !m1Done },
            ].map(m => (
              <button key={m.id} className="mod-btn"
                onClick={() => !m.locked && setActiveModule(m.id)}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 8,
                  padding: "8px 10px", borderRadius: 7, border: "none", cursor: m.locked ? "default" : "pointer",
                  background: activeModule === m.id ? "#2a2520" : "transparent",
                  marginBottom: 3,
                  borderLeft: activeModule === m.id ? "2px solid #c8902a" : "2px solid transparent",
                  opacity: m.locked ? 0.4 : 1,
                }}>
                <span style={{ fontSize: 14 }}>{m.icon}</span>
                <span style={{ fontSize: 12, color: activeModule === m.id ? "#f0c060" : "#8a7a68", fontWeight: activeModule === m.id ? 600 : 400 }}>{m.label}</span>
                {m.done && <span style={{ marginLeft: "auto", fontSize: 10, color: "#4a9e6b" }}>✓</span>}
                {m.locked && <span style={{ marginLeft: "auto", fontSize: 10 }}>🔒</span>}
              </button>
            ))}
          </div>

          {/* Project */}
          <div style={{ padding: "12px 12px", flex: 1 }}>
            <div style={{ fontSize: 9, color: "#4a3c2a", textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 8, fontWeight: 600 }}>Current project</div>
            <div style={{ padding: "8px 10px", background: "#1e1a16", borderRadius: 7, border: "1px solid #2a2520" }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#e8dcc8", marginBottom: 3 }}>ICE Services DIF v16</div>
              <div style={{ display: "flex", gap: 6 }}>
                <Badge label={m1Done ? "Context ✓" : "No context"} color={m1Done ? "#4a9e6b" : "#c8902a"} />
              </div>
            </div>
          </div>

          {/* User */}
          <div style={{ padding: "10px 14px", borderTop: "1px solid #2a2520", display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 26, height: 26, borderRadius: "50%", background: "#3a3028", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600, color: "#c8902a" }}>TK</div>
            <span style={{ fontSize: 12, color: "#6a5e52" }}>Tom K.</span>
          </div>
        </div>

        {/* ── M1: Context Builder ── */}
        {activeModule === "m1" && (
          <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
            {/* Header */}
            <div style={{ padding: "14px 24px", borderBottom: "1px solid #2a2520", background: "#1a1612", display: "flex", alignItems: "center", gap: 12 }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 600 }}>🧠 M1 — Context Builder</div>
                <div style={{ fontSize: 11, color: "#6a5e52" }}>Upload documentation → RAG knowledge base + mind map + glossary</div>
              </div>
              {m1Done && (
                <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                  <Badge label="RAG ready" color="#4a9e6b" />
                  <Badge label="8 entities" color="#5b7fba" />
                  <Badge label="6 terms" color="#c8902a" />
                </div>
              )}
            </div>

            {/* Body */}
            <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
              {/* Left: upload + chat */}
              <div style={{ width: 320, borderRight: "1px solid #2a2520", display: "flex", flexDirection: "column", padding: 16, gap: 12 }}>
                {!m1Done ? (
                  <M1UploadPanel onComplete={() => { setM1Done(true); }} />
                ) : (
                  /* RAG chat after context is built */
                  <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 10 }}>
                    <div style={{ padding: "8px 10px", background: "#1a3a28", border: "1px solid #2a4a38", borderRadius: 7, fontSize: 12, color: "#4a9e6b" }}>
                      ✅ Knowledge base ready — ask anything about the domain
                    </div>
                    <div style={{ flex: 1, overflowY: "auto" }}>
                      {messages.map((m, i) => (
                        <div key={i} style={{
                          display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start",
                          marginBottom: 10, animation: "fadeIn 0.3s ease",
                        }}>
                          <div style={{
                            maxWidth: "90%", padding: "8px 12px", fontSize: 12, lineHeight: 1.6,
                            background: m.role === "user" ? "linear-gradient(135deg,#c8902a,#f0c060)" : "#2a2520",
                            color: m.role === "user" ? "#1a1612" : "#c8b89a",
                            borderRadius: m.role === "user" ? "14px 14px 3px 14px" : "3px 14px 14px 14px",
                            border: m.role === "user" ? "none" : "1px solid #3a3028",
                            whiteSpace: "pre-wrap",
                          }}>
                            {m.text.split("**").map((t, j) => j % 2 === 1
                              ? <strong key={j} style={{ color: m.role === "user" ? "#1a1612" : "#f0c060" }}>{t}</strong>
                              : t
                            )}
                          </div>
                        </div>
                      ))}
                      {loading && <div style={{ padding: 8, color: "#5a4e42", fontSize: 12, animation: "pulse 1.2s infinite" }}>Searching knowledge base…</div>}
                      <div ref={msgEnd} />
                    </div>
                    <div style={{ display: "flex", gap: 6 }}>
                      <input value={chatInput} onChange={e => setChatInput(e.target.value)}
                        onKeyDown={e => e.key === "Enter" && send()}
                        placeholder="Ask about the domain…"
                        style={{
                          flex: 1, background: "#1e1a16", border: "1px solid #3a3028", borderRadius: 7,
                          color: "#e8dcc8", padding: "7px 10px", fontSize: 12,
                          fontFamily: "DM Sans", outline: "none",
                        }} />
                      <button onClick={send} style={{
                        padding: "7px 12px", borderRadius: 7, border: "none", cursor: "pointer",
                        background: "linear-gradient(135deg,#c8902a,#f0c060)", color: "#1a1612", fontWeight: 600, fontSize: 13,
                      }}>↑</button>
                    </div>
                  </div>
                )}
              </div>

              {/* Right: artefacts */}
              <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
                {/* Tabs */}
                <div style={{ display: "flex", padding: "10px 20px 0", borderBottom: "1px solid #2a2520", gap: 4, background: "#1a1612" }}>
                  {[
                    { id: "mindmap",  label: "🗺 Mind Map" },
                    { id: "glossary", label: "📖 Glossary" },
                  ].map(t => (
                    <button key={t.id} className="tab-btn"
                      onClick={() => setRightTab(t.id)}
                      style={{
                        padding: "6px 14px", background: "none", border: "none", cursor: "pointer",
                        borderBottom: rightTab === t.id ? "2px solid #c8902a" : "2px solid transparent",
                        color: rightTab === t.id ? "#f0c060" : "#6a5e52",
                        fontSize: 12, fontWeight: rightTab === t.id ? 600 : 400,
                        fontFamily: "DM Sans", transition: "color 0.2s",
                      }}>{t.label}</button>
                  ))}
                </div>

                <div style={{ flex: 1, padding: 20, overflow: "hidden", display: "flex", flexDirection: "column" }}>
                  {!m1Done ? (
                    <div style={{
                      flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
                      color: "#3a3028", fontSize: 13, flexDirection: "column", gap: 10,
                    }}>
                      <div style={{ fontSize: 36 }}>📭</div>
                      <div>Upload documents and build context to see artefacts here</div>
                    </div>
                  ) : rightTab === "mindmap" ? (
                    <div style={{ flex: 1, background: "#1a1612", borderRadius: 10, border: "1px solid #2a2520", overflow: "hidden" }}>
                      <MindMap nodes={MOCK_NODES} edges={MOCK_EDGES} />
                    </div>
                  ) : (
                    <GlossaryTable items={MOCK_GLOSSARY} />
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── M2 placeholder ── */}
        {activeModule === "m2" && (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 16, color: "#5a4e42" }}>
            <div style={{ fontSize: 48 }}>🔍</div>
            <div style={{ fontSize: 16, color: "#8a7a68", fontWeight: 600 }}>M2 — Test Suite Analyzer</div>
            <div style={{ fontSize: 13, color: "#4a3c2a" }}>Context is ready — drop your test scripts here to begin analysis</div>
            <div style={{ padding: "8px 16px", background: "#1a3a28", border: "1px solid #2a4a38", borderRadius: 7, fontSize: 12, color: "#4a9e6b" }}>
              ✅ RAG knowledge base loaded — M1 context available
            </div>
          </div>
        )}
      </div>
    </>
  );
}
