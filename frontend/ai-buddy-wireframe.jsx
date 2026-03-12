import { useState, useRef, useEffect } from "react";

const PROJECTS = [
  { id: 1, name: "ICE Services – DIF v16", files: 3, date: "2 mar" },
  { id: 2, name: "Regression Suite – Payment Module", files: 7, date: "28 lut" },
  { id: 3, name: "API Contract Tests – v3", files: 2, date: "20 lut" },
];

const INIT_MESSAGES = [
  {
    role: "assistant",
    text: "Cześć! Jestem **AI Buddy** — Twój asystent QA. Wgraj zestaw testów lub zacznij od audytu istniejącego projektu.\n\nMogę:\n- 🔍 **Audytować** suite testów i wskazać luki\n- ⚙️ **Optymalizować** tagi, priorytety i pokrycie\n- 🔄 **Regenerować** przypadki testowe na podstawie dokumentacji",
  },
];

function MarkdownText({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <span>
      {parts.map((p, i) =>
        p.startsWith("**") && p.endsWith("**") ? (
          <strong key={i} style={{ color: "#f0c060" }}>
            {p.slice(2, -2)}
          </strong>
        ) : (
          <span key={i}>{p}</span>
        )
      )}
    </span>
  );
}

function Message({ msg, isNew }) {
  const isUser = msg.role === "user";
  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 18,
        opacity: 1,
        animation: isNew ? "fadeUp 0.3s ease" : "none",
      }}
    >
      {!isUser && (
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: "linear-gradient(135deg, #c8902a, #f0c060)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 14,
            fontWeight: 700,
            color: "#1a1612",
            marginRight: 10,
            flexShrink: 0,
            marginTop: 2,
          }}
        >
          Q
        </div>
      )}
      <div
        style={{
          maxWidth: "72%",
          background: isUser ? "linear-gradient(135deg,#c8902a,#f0c060)" : "#2a2520",
          color: isUser ? "#1a1612" : "#e8dcc8",
          borderRadius: isUser ? "18px 18px 4px 18px" : "4px 18px 18px 18px",
          padding: "10px 16px",
          fontSize: 14,
          lineHeight: 1.65,
          border: isUser ? "none" : "1px solid #3a3028",
          fontFamily: "'DM Sans', sans-serif",
          whiteSpace: "pre-wrap",
        }}
      >
        {msg.text.split("\n").map((line, i) => (
          <div key={i}>
            <MarkdownText text={line} />
          </div>
        ))}
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <div style={{ display: "flex", gap: 5, padding: "8px 16px" }}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: "#c8902a",
            animation: `bounce 1.2s ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </div>
  );
}

function FileChip({ name, onRemove }) {
  const ext = name.split(".").pop().toUpperCase();
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        background: "#2a2520",
        border: "1px solid #4a3c2a",
        borderRadius: 6,
        padding: "3px 8px",
        fontSize: 12,
        color: "#c8902a",
        fontFamily: "monospace",
      }}
    >
      <span style={{ opacity: 0.7 }}>{ext}</span>
      <span style={{ color: "#e8dcc8" }}>{name}</span>
      <button
        onClick={onRemove}
        style={{
          background: "none",
          border: "none",
          color: "#c8902a",
          cursor: "pointer",
          padding: 0,
          fontSize: 13,
          lineHeight: 1,
        }}
      >
        ×
      </button>
    </div>
  );
}

export default function AIBuddy() {
  const [activeProject, setActiveProject] = useState(PROJECTS[0]);
  const [messages, setMessages] = useState(INIT_MESSAGES);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [files, setFiles] = useState([]);
  const [sidebarTab, setSidebarTab] = useState("projects");
  const [newMsg, setNewMsg] = useState(false);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const mockReplies = [
    "Analizuję zestaw testów **ICE Services DIF v16**...\n\n🔍 Znalazłem **12 przypadków testowych** bez przypisanych tagów priorytetowych.\n⚠️ **3 scenariusze regresji** nakładają się na siebie (duplikaty).\n\nChcesz, żebym wygenerował raport audytu w formacie Excel?",
    "Na podstawie przesłanej dokumentacji Confluence:\n\n✅ Wygenerowałem **8 nowych przypadków testowych** dla modułu płatności.\n🏷️ Automatycznie przypisałem tagi: `smoke`, `regression`, `payment`.\n\nZapisać je do projektu?",
    "Optymalizacja suite'u zakończona:\n\n- Usunięto **5 duplikatów**\n- Poprawiono priorytety w **23 przypadkach**\n- Pokrycie funkcjonalne wzrosło z **67%** do **84%**",
  ];
  const [replyIdx, setReplyIdx] = useState(0);

  const sendMessage = () => {
    const text = input.trim();
    if (!text && files.length === 0) return;
    const userMsg = { role: "user", text: text || `[Wgrano: ${files.map((f) => f.name).join(", ")}]` };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setFiles([]);
    setLoading(true);
    setNewMsg(true);

    setTimeout(() => {
      const reply = mockReplies[replyIdx % mockReplies.length];
      setReplyIdx((i) => i + 1);
      setMessages((m) => [...m, { role: "assistant", text: reply }]);
      setLoading(false);
    }, 1800);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleFileChange = (e) => {
    setFiles((prev) => [...prev, ...Array.from(e.target.files)]);
  };

  const css = `
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #141210; }
    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #3a3028; border-radius: 4px; }
    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes bounce {
      0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
      40%            { transform: scale(1);   opacity: 1;   }
    }
    .proj-item:hover { background: #2a2520 !important; cursor: pointer; }
    .proj-item.active { background: #2a2520 !important; border-left: 2px solid #c8902a !important; }
    .tab-btn { transition: color 0.2s, border-color 0.2s; }
    .tab-btn:hover { color: #f0c060 !important; }
    .send-btn:hover { background: #f0c060 !important; }
    .upload-btn:hover { background: #3a3028 !important; }
    textarea { resize: none; }
    textarea:focus { outline: none; }
  `;

  return (
    <>
      <style>{css}</style>
      <div
        style={{
          display: "flex",
          height: "100vh",
          background: "#141210",
          fontFamily: "'DM Sans', sans-serif",
          color: "#e8dcc8",
          overflow: "hidden",
        }}
      >
        {/* SIDEBAR */}
        <div
          style={{
            width: 260,
            background: "#1a1612",
            borderRight: "1px solid #2a2520",
            display: "flex",
            flexDirection: "column",
            flexShrink: 0,
          }}
        >
          {/* Logo */}
          <div
            style={{
              padding: "20px 18px 16px",
              borderBottom: "1px solid #2a2520",
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <div
              style={{
                width: 30,
                height: 30,
                borderRadius: 8,
                background: "linear-gradient(135deg, #c8902a, #f0c060)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 14,
                fontWeight: 700,
                color: "#1a1612",
              }}
            >
              Q
            </div>
            <span style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.3px", color: "#f0c060" }}>
              AI Buddy
            </span>
            <span
              style={{
                marginLeft: "auto",
                fontSize: 10,
                background: "#2a2520",
                color: "#c8902a",
                padding: "2px 6px",
                borderRadius: 4,
                fontFamily: "DM Mono",
                border: "1px solid #3a3028",
              }}
            >
              BETA
            </span>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", padding: "10px 12px 0", gap: 4 }}>
            {["projects", "files"].map((t) => (
              <button
                key={t}
                className="tab-btn"
                onClick={() => setSidebarTab(t)}
                style={{
                  flex: 1,
                  padding: "6px 0",
                  background: "none",
                  border: "none",
                  borderBottom: sidebarTab === t ? "2px solid #c8902a" : "2px solid transparent",
                  color: sidebarTab === t ? "#f0c060" : "#8a7a68",
                  fontSize: 12,
                  fontWeight: 500,
                  cursor: "pointer",
                  fontFamily: "'DM Sans', sans-serif",
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                }}
              >
                {t === "projects" ? "Projekty" : "Pliki"}
              </button>
            ))}
          </div>

          {sidebarTab === "projects" ? (
            <>
              <button
                style={{
                  margin: "12px 12px 4px",
                  padding: "8px 12px",
                  background: "linear-gradient(135deg,#c8902a,#f0c060)",
                  color: "#1a1612",
                  border: "none",
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span style={{ fontSize: 16 }}>+</span> Nowy projekt
              </button>
              <div style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}>
                <div style={{ padding: "8px 14px 4px", fontSize: 10, color: "#5a4e42", textTransform: "uppercase", letterSpacing: "0.8px", fontWeight: 600 }}>
                  Ostatnie
                </div>
                {PROJECTS.map((p) => (
                  <div
                    key={p.id}
                    className={`proj-item${activeProject.id === p.id ? " active" : ""}`}
                    onClick={() => setActiveProject(p)}
                    style={{
                      padding: "10px 16px",
                      borderLeft: "2px solid transparent",
                      transition: "background 0.15s",
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 500, color: "#e8dcc8", marginBottom: 3 }}>{p.name}</div>
                    <div style={{ fontSize: 11, color: "#6a5e52", display: "flex", gap: 8 }}>
                      <span>📄 {p.files} pliki</span>
                      <span>· {p.date}</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
              <button
                onClick={() => fileInputRef.current?.click()}
                style={{
                  width: "100%",
                  padding: "28px 12px",
                  background: "#1e1a16",
                  border: "2px dashed #3a3028",
                  borderRadius: 10,
                  color: "#8a7a68",
                  fontSize: 13,
                  cursor: "pointer",
                  textAlign: "center",
                  lineHeight: 1.8,
                }}
              >
                <div style={{ fontSize: 24, marginBottom: 6 }}>📁</div>
                Wgraj pliki do projektu
                <div style={{ fontSize: 11, marginTop: 4, color: "#5a4e42" }}>.xlsx, .csv, .json, .pdf</div>
              </button>
              <input ref={fileInputRef} type="file" multiple style={{ display: "none" }} onChange={handleFileChange} />
              <div style={{ marginTop: 14 }}>
                {["test_suite_v16.xlsx", "confluence_export.pdf", "requirements.json"].map((f, i) => (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "8px 10px",
                      background: "#1e1a16",
                      borderRadius: 6,
                      marginBottom: 6,
                      border: "1px solid #2a2520",
                      fontSize: 12,
                      color: "#c8902a",
                      fontFamily: "DM Mono",
                    }}
                  >
                    <span style={{ opacity: 0.6 }}>{f.split(".").pop().toUpperCase()}</span>
                    <span style={{ color: "#e8dcc8", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* User */}
          <div
            style={{
              padding: "12px 16px",
              borderTop: "1px solid #2a2520",
              display: "flex",
              alignItems: "center",
              gap: 10,
              fontSize: 13,
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: "50%",
                background: "#3a3028",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                fontWeight: 600,
                color: "#c8902a",
              }}
            >
              TK
            </div>
            <span style={{ color: "#8a7a68" }}>Tom K.</span>
            <span
              style={{
                marginLeft: "auto",
                fontSize: 10,
                color: "#5a4e42",
                background: "#1e1a16",
                padding: "2px 6px",
                borderRadius: 4,
                border: "1px solid #2a2520",
              }}
            >
              PRO
            </span>
          </div>
        </div>

        {/* MAIN */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {/* Header */}
          <div
            style={{
              padding: "14px 24px",
              borderBottom: "1px solid #2a2520",
              display: "flex",
              alignItems: "center",
              gap: 14,
              background: "#1a1612",
            }}
          >
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: "#e8dcc8" }}>{activeProject.name}</div>
              <div style={{ fontSize: 12, color: "#6a5e52" }}>Test Suite Audit & Optimization</div>
            </div>

            {/* Pipeline steps */}
            <div style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
              {[
                { label: "Audit", icon: "🔍", active: true },
                { label: "Optimize", icon: "⚙️", active: false },
                { label: "Regenerate", icon: "🔄", active: false },
              ].map((step, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  {i > 0 && <span style={{ color: "#3a3028", fontSize: 12 }}>→</span>}
                  <div
                    style={{
                      padding: "4px 10px",
                      borderRadius: 6,
                      background: step.active ? "rgba(200,144,42,0.15)" : "#1e1a16",
                      border: `1px solid ${step.active ? "#c8902a" : "#2a2520"}`,
                      fontSize: 12,
                      color: step.active ? "#f0c060" : "#5a4e42",
                      fontWeight: step.active ? 500 : 400,
                    }}
                  >
                    {step.icon} {step.label}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: "auto", padding: "24px 60px" }}>
            {messages.map((m, i) => (
              <Message key={i} msg={m} isNew={newMsg && i === messages.length - 1} />
            ))}
            {loading && (
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: "50%",
                    background: "linear-gradient(135deg, #c8902a, #f0c060)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 14,
                    fontWeight: 700,
                    color: "#1a1612",
                  }}
                >
                  Q
                </div>
                <div style={{ background: "#2a2520", borderRadius: "4px 18px 18px 18px", border: "1px solid #3a3028" }}>
                  <Spinner />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div style={{ padding: "16px 60px 24px", background: "#141210" }}>
            {files.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                {files.map((f, i) => (
                  <FileChip key={i} name={f.name} onRemove={() => setFiles((prev) => prev.filter((_, j) => j !== i))} />
                ))}
              </div>
            )}
            <div
              style={{
                display: "flex",
                gap: 10,
                alignItems: "flex-end",
                background: "#1e1a16",
                border: "1px solid #3a3028",
                borderRadius: 14,
                padding: "12px 14px",
                boxShadow: "0 0 0 1px rgba(200,144,42,0.05)",
              }}
            >
              <button
                className="upload-btn"
                onClick={() => fileInputRef.current?.click()}
                title="Wgraj plik"
                style={{
                  background: "#2a2520",
                  border: "none",
                  borderRadius: 8,
                  width: 36,
                  height: 36,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                  fontSize: 16,
                  flexShrink: 0,
                  transition: "background 0.15s",
                }}
              >
                📎
              </button>
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Zadaj pytanie, wgraj suite testów, poproś o audyt..."
                rows={1}
                style={{
                  flex: 1,
                  background: "none",
                  border: "none",
                  color: "#e8dcc8",
                  fontSize: 14,
                  fontFamily: "'DM Sans', sans-serif",
                  lineHeight: 1.6,
                  maxHeight: 140,
                  overflowY: "auto",
                  paddingTop: 8,
                }}
                onInput={(e) => {
                  e.target.style.height = "auto";
                  e.target.style.height = Math.min(e.target.scrollHeight, 140) + "px";
                }}
              />
              <button
                className="send-btn"
                onClick={sendMessage}
                disabled={loading || (!input.trim() && files.length === 0)}
                style={{
                  background: loading || (!input.trim() && files.length === 0) ? "#2a2520" : "linear-gradient(135deg,#c8902a,#f0c060)",
                  border: "none",
                  borderRadius: 9,
                  width: 36,
                  height: 36,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: loading ? "wait" : "pointer",
                  fontSize: 15,
                  flexShrink: 0,
                  transition: "background 0.2s",
                }}
              >
                ↑
              </button>
            </div>
            <div style={{ textAlign: "center", marginTop: 8, fontSize: 11, color: "#3a3028" }}>
              Enter — wyślij · Shift+Enter — nowa linia · Obsługuje: .xlsx .csv .pdf .json .feature
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
