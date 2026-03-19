"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import ErrorBanner from "@/components/ErrorBanner";
import MindMap from "@/components/MindMap";
import Glossary, { type GlossaryTerm } from "@/components/Glossary";
import MessageList from "@/components/MessageList";
import { useProjectFiles } from "@/lib/useProjectFiles";
import { useContextBuilder } from "@/lib/useContextBuilder";
import type { ChatMessage } from "@/lib/useAIBuddyChat";

// -- Constants ----------------------------------------------------------------

const STAGES = [
  { id: "parse",    label: "Parsowanie dokumentów",  icon: "📄" },
  { id: "embed",    label: "Budowanie indeksu RAG", icon: "🧠" },
  { id: "extract",  label: "Ekstrakcja encji",      icon: "🔍" },
  { id: "assemble", label: "Składanie artefaktów",  icon: "⚙️" },
];

const MONTHS = ["sty","lut","mar","kwi","maj","cze","lip","sie","wrz","paź","lis","gru"];

function fmtDate(iso: string) {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
}

// -- File chip ----------------------------------------------------------------

function FileChip({ file, onRemove }: { file: File; onRemove: () => void }) {
  const ext = file.name.split(".").pop()?.toUpperCase() ?? "FILE";
  return (
    <div className="flex items-center gap-1.5 bg-buddy-elevated border border-buddy-border rounded-md px-2 py-1 text-xs">
      <span className="font-mono text-buddy-gold opacity-70">{ext}</span>
      <span className="text-buddy-text max-w-[120px] truncate font-mono">{file.name}</span>
      <button onClick={onRemove} className="text-buddy-text-dim hover:text-buddy-gold ml-0.5">×</button>
    </div>
  );
}

// -- RAG chat -----------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface RagChatProps {
  projectId: string;
  prefillQuery?: { text: string; seq: number } | null;
  onTermClick?: (term: GlossaryTerm) => void;
  glossary?: GlossaryTerm[];
}

function RagChat({ projectId, prefillQuery, onTermClick, glossary }: RagChatProps) {
  const msgSeq = useRef(0);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: "0", role: "assistant", content: "Baza wiedzy gotowa ✅ Zapytaj o cokolwiek dotyczącego domeny.", timestamp: new Date() },
  ]);
  const [lastId, setLastId] = useState<string | undefined>();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const send = async (overrideQuery?: string) => {
    const q = (overrideQuery ?? input).trim();
    if (!q) return;
    setInput("");
    const userId = String(++msgSeq.current);
    setMessages((prev) => [...prev, { id: userId, role: "user", content: q, timestamp: new Date() }]);
    setLastId(userId);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, message: q, file_paths: [], tier: "rag_chat" }),
      });
      const text = await res.text();
      let reply = "";
      let sources: ChatMessage["sources"] = [];
      for (const line of text.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const p = line.slice(6).trim();
        if (p === "[DONE]") break;
        try {
          const ev = JSON.parse(p);
          if (ev.type === "result" && ev.data?.message) {
            reply = ev.data.message;
            sources = ev.data.rag_sources ?? [];
          }
        } catch { /* skip */ }
      }
      const botId = String(++msgSeq.current);
      setMessages((prev) => [...prev, { id: botId, role: "assistant", content: reply || "...", sources, timestamp: new Date() }]);
      setLastId(botId);
    } catch (err: any) {
      const errId = String(++msgSeq.current);
      setMessages((prev) => [...prev, { id: errId, role: "assistant", content: `❌ ${err.message}`, timestamp: new Date() }]);
      setLastId(errId);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (prefillQuery) send(prefillQuery.text);
  }, [prefillQuery?.seq]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-col h-full gap-2 overflow-hidden">
      <div className="px-2.5 py-2 bg-emerald-900/20 border border-emerald-700/30 rounded-lg text-xs text-emerald-400 shrink-0">
        ✅ Baza wiedzy gotowa — zapytaj o cokolwiek dotyczącego domeny
      </div>
      <div className="flex-1 overflow-hidden">
        <MessageList
          messages={messages}
          isLoading={loading}
          lastMessageId={lastId}
          onTermClick={onTermClick}
          glossary={glossary}
        />
      </div>
      <div className="flex gap-1.5 shrink-0">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !loading && send()}
          placeholder="Zapytaj o domenę..."
          className="flex-1 bg-buddy-elevated border border-buddy-border-dark rounded-lg text-xs text-buddy-text placeholder:text-buddy-text-faint px-2.5 py-2 focus:outline-none focus:border-buddy-gold"
        />
        <button
          onClick={() => send()}
          disabled={loading || !input.trim()}
          className="px-3 py-2 bg-gradient-to-br from-buddy-gold to-buddy-gold-light text-buddy-surface text-sm font-bold rounded-lg disabled:opacity-40"
        >
          ↑
        </button>
      </div>
    </div>
  );
}

// -- Rebuild confirmation modal -----------------------------------------------

function RebuildModal({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  return (
    <div
      className="fixed inset-0 bg-black/65 flex items-center justify-center z-50"
      onClick={onCancel}
      role="dialog"
      aria-labelledby="rebuild-modal-title"
    >
      <div
        className="bg-buddy-elevated border border-buddy-border-dark rounded-xl p-6 max-w-[360px] w-[90%] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div id="rebuild-modal-title" className="text-[15px] font-semibold text-buddy-gold-light mb-2.5">
          Przebudować kontekst?
        </div>
        <div className="text-[13px] text-[#c8b89a] leading-relaxed mb-5">
          Ta operacja usunie istniejący indeks RAG oraz artefakty
          (mind mapa, słownik) dla tego projektu.
        </div>
        <div className="flex gap-2.5 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-[7px] rounded-lg border border-buddy-border-dark bg-transparent text-[#c8b89a] text-[13px] cursor-pointer hover:bg-buddy-border transition-colors"
          >
            Anuluj
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-[7px] rounded-lg border-none bg-buddy-gold text-buddy-surface text-[13px] font-semibold cursor-pointer hover:opacity-90 transition-opacity"
          >
            Przebuduj
          </button>
        </div>
      </div>
    </div>
  );
}

// -- Main page ----------------------------------------------------------------

interface DiffSummary {
  mode: "append" | "rebuild";
  entities: number;
  terms: number;
  deltaEntities?: number;
  deltaTerms?: number;
}

export default function ContextPage({ params }: { params: { projectId: string } }) {
  const projectId = decodeURIComponent(params.projectId);
  const router = useRouter();

  const { files: projectFiles, uploading, uploadFiles, uploadError, clearUploadError } = useProjectFiles(projectId);
  const { isBuilding, stage, progress, log, result, status, error, clearError, buildContext } =
    useContextBuilder(projectId);

  const [pendingFiles, setPendingFiles]         = useState<File[]>([]);
  const [activeTab, setActiveTab]               = useState<"mindmap" | "glossary">("mindmap");
  const [isDragging, setIsDragging]             = useState(false);
  const [dismissed, setDismissed]               = useState(false);
  const [buildMode, setBuildMode]               = useState<"append" | "rebuild">("append");
  const [showRebuildModal, setShowRebuildModal] = useState(false);
  const [diffSummary, setDiffSummary]           = useState<DiffSummary | null>(null);
  const [termQuery, setTermQuery]               = useState<{ text: string; seq: number } | null>(null);

  const handleTermClick = (term: GlossaryTerm) => {
    setDismissed(false);
    setTermQuery((prev) => ({ text: `Wyjaśnij termin: "${term.term}"`, seq: (prev?.seq ?? 0) + 1 }));
  };

  const fileInputRef   = useRef<HTMLInputElement>(null);
  const logEndRef      = useRef<HTMLDivElement>(null);
  const prevStatsRef   = useRef<{ entities: number; terms: number } | null>(null);
  const pendingModeRef = useRef<"append" | "rebuild">("append");

  useEffect(() => { if (result) setDismissed(false); }, [result]);
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [log]);

  // Compute post-build diff when result arrives
  useEffect(() => {
    if (!result || !prevStatsRef.current) return;
    const { entities: prevE, terms: prevT } = prevStatsRef.current;
    const entities = result.stats.entity_count;
    const terms    = result.stats.term_count;
    if (pendingModeRef.current === "append") {
      setDiffSummary({ mode: "append", entities, terms, deltaEntities: entities - prevE, deltaTerms: terms - prevT });
    } else {
      setDiffSummary({ mode: "rebuild", entities, terms });
    }
    prevStatsRef.current = null;
  }, [result]);

  const addFiles = useCallback((incoming: File[]) => {
    const allowed = incoming.filter((f) => f.name.endsWith(".docx") || f.name.endsWith(".pdf"));
    setPendingFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name));
      return [...prev, ...allowed.filter((f) => !existing.has(f.name))];
    });
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    addFiles(Array.from(e.dataTransfer.files));
  }, [addFiles]);

  const startBuild = useCallback((mode: "append" | "rebuild") => {
    prevStatsRef.current = {
      entities: status?.stats?.entity_count ?? result?.stats?.entity_count ?? 0,
      terms:    status?.stats?.term_count    ?? result?.stats?.term_count    ?? 0,
    };
    pendingModeRef.current = mode;
    setDiffSummary(null);
    buildContext(pendingFiles, mode);
  }, [pendingFiles, status, result, buildContext]);

  const handleBuild = () => {
    if (!pendingFiles.length) return;
    if (buildMode === "rebuild") {
      setShowRebuildModal(true);
    } else {
      startBuild("append");
    }
  };

  const stageIndex   = STAGES.findIndex((s) => s.id === stage);
  const contextReady = status?.rag_ready ?? result?.rag_ready ?? false;
  const hasContext   = !!status?.context_built_at;

  const builtAt      = status?.context_built_at;
  const builtAtLabel = builtAt ? `Kontekst zbudowany: ${fmtDate(builtAt)}` : null;
  const showChat     = contextReady && !dismissed;

  return (
    <div className="flex h-screen overflow-hidden bg-buddy-base text-buddy-text font-sans">
      {showRebuildModal && (
        <RebuildModal
          onConfirm={() => { setShowRebuildModal(false); startBuild("rebuild"); }}
          onCancel={() => setShowRebuildModal(false)}
        />
      )}

      <Sidebar
        activeProjectId={projectId}
        projectFiles={projectFiles}
        onUploadFiles={uploadFiles}
        isUploading={uploading}
        contextReady={contextReady}
        activeModule="m1"
      />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <div className="pl-14 md:pl-6 pr-6 py-3.5 border-b border-buddy-border bg-buddy-surface flex items-center gap-3 shrink-0">
          <div className="flex-1 min-w-0">
            <div className="text-[15px] font-semibold text-buddy-text">🧠 M1 — Context Builder</div>
            {builtAtLabel ? (
              <div className="text-[11px] text-emerald-400/80">{builtAtLabel}</div>
            ) : (
              <div className="text-xs text-buddy-text-dim">Prześlij dokumentację — baza wiedzy RAG + mapa myśli + glosariusz</div>
            )}
          </div>
          {contextReady && result && (
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-emerald-400/10 text-emerald-400 border border-emerald-400/20">RAG GOTOWY</span>
              {result.stats?.entity_count != null && (
                <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-buddy-gold/10 text-buddy-gold border border-buddy-gold/20">
                  {result.stats.entity_count} encji
                </span>
              )}
              {result.stats?.term_count != null && (
                <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-buddy-border text-buddy-text-muted border border-buddy-border-dark">
                  {result.stats.term_count} terminów
                </span>
              )}
            </div>
          )}
          <button
            onClick={() => router.push(`/chat/${encodeURIComponent(projectId)}`)}
            className="text-xs text-buddy-text-muted hover:text-buddy-gold-light border border-buddy-border rounded-lg px-3 py-1.5 transition-colors shrink-0"
          >
            → Suite Analyzer
          </button>
        </div>

        {/* Body: two-panel */}
        <div className="flex-1 flex overflow-hidden">

          {/* Left panel: 320px */}
          <div className="w-80 border-r border-buddy-border flex flex-col p-4 gap-3 overflow-y-auto">
            {showChat ? (
              <>
                <RagChat
                  projectId={projectId}
                  prefillQuery={termQuery}
                  onTermClick={handleTermClick}
                  glossary={result?.glossary ?? []}
                />
                <button
                  onClick={() => { setDismissed(true); setPendingFiles([]); setDiffSummary(null); }}
                  className="shrink-0 text-xs text-buddy-text-faint hover:text-buddy-gold-light border border-buddy-border rounded-lg px-3 py-1.5 transition-colors"
                >
                  ↺ Przebuduj kontekst
                </button>
              </>
            ) : (
              <>
                {/* A: Indexed documents */}
                {hasContext && status?.context_files && status.context_files.length > 0 && (
                  <div className="bg-buddy-elevated border border-buddy-border rounded-lg px-3 py-2.5">
                    <div className="text-[11px] text-[#c8b89a] font-semibold mb-[7px]">
                      Zaindeksowane dokumenty
                    </div>
                    <div className="flex flex-col gap-[5px]">
                      {status.context_files.map((filename, i) => {
                        const ext = filename.split(".").pop()?.toUpperCase() ?? "FILE";
                        return (
                          <div key={i} className="flex items-center gap-[7px] text-[11px]">
                            <span className="font-mono text-buddy-gold text-[10px] px-1.5 py-px bg-[#c8902a18] border border-[#c8902a33] rounded-sm">
                              {ext}
                            </span>
                            <span className="text-[#c8b89a] font-mono overflow-hidden text-ellipsis whitespace-nowrap">
                              {filename}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                    {builtAt && (
                      <div className="mt-2 text-[10px] text-buddy-text-faint">
                        Ostatnia aktualizacja: {fmtDate(builtAt)}
                      </div>
                    )}
                  </div>
                )}

                {/* B: Mode selector */}
                {hasContext && (
                  <div className="bg-buddy-elevated border border-buddy-border rounded-lg px-3 py-2.5">
                    <div className="text-[11px] text-[#c8b89a] font-semibold mb-2">Tryb</div>
                    <div className="flex flex-col gap-1.5">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="build-mode"
                          checked={buildMode === "append"}
                          onChange={() => setBuildMode("append")}
                          style={{ accentColor: "#c8902a" }}
                        />
                        <span className="text-xs text-[#c8b89a]">➕ Dodaj dokumenty</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="build-mode"
                          checked={buildMode === "rebuild"}
                          onChange={() => setBuildMode("rebuild")}
                          style={{ accentColor: "#c8902a" }}
                        />
                        <span className="text-xs text-[#c8b89a]">🔄 Przebuduj kontekst</span>
                      </label>
                    </div>
                    {buildMode === "rebuild" && (
                      <div className="text-[10px] text-buddy-gold mt-[7px] leading-relaxed">
                        Uwaga: usunie istniejący kontekst i indeks wektorowy projektu
                      </div>
                    )}
                  </div>
                )}

                {/* Upload zone */}
                {(!result || dismissed) && (
                  <div
                    onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={handleDrop}
                    onClick={() => !isBuilding && fileInputRef.current?.click()}
                    className={`bg-buddy-elevated border-2 border-dashed rounded-xl p-5 text-center transition-[border-color] duration-200 ${
                      isDragging ? "border-buddy-gold" : "border-buddy-border-dark"
                    } ${isBuilding ? "cursor-not-allowed" : "cursor-pointer"}`}
                  >
                    <div className="text-[32px] mb-1.5">📂</div>
                    <div className="text-[#c8b89a] text-[13px] font-medium">Upuść pliki Word / PDF tutaj</div>
                    <div className="text-buddy-text-faint text-[11px] mt-1">lub kliknij, aby przeglądać</div>
                  </div>
                )}
                <input ref={fileInputRef} type="file" multiple accept=".docx,.pdf" className="hidden"
                  onChange={(e) => { addFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />

                {/* File chips + build button */}
                {pendingFiles.length > 0 && (!result || dismissed) && (
                  <div className="space-y-1.5">
                    {pendingFiles.map((f, i) => (
                      <FileChip key={i} file={f} onRemove={() => setPendingFiles((prev) => prev.filter((_, j) => j !== i))} />
                    ))}
                    <button
                      onClick={handleBuild}
                      disabled={isBuilding}
                      style={{
                        background: buildMode === "rebuild"
                          ? "linear-gradient(135deg, #a06020, #c8902a)"
                          : "linear-gradient(135deg, #c8902a, #f0c060)",
                      }}
                      className="w-full p-2.5 rounded-lg border-none text-buddy-surface font-semibold text-[13px] font-sans mt-1 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
                    >
                      {isBuilding
                        ? "Budowanie..."
                        : buildMode === "rebuild"
                          ? `🔄 Przebuduj kontekst (${pendingFiles.length} plik${pendingFiles.length > 1 ? "i" : ""})`
                          : `Zbuduj kontekst z ${pendingFiles.length} pliku(ów)`}
                    </button>
                  </div>
                )}

                {/* Progress */}
                {isBuilding && (
                  <div className="p-3.5 bg-buddy-elevated rounded-[10px] border border-buddy-border">
                    <div className="flex gap-1.5 mb-3">
                      {STAGES.map((s, i) => (
                        <div
                          key={s.id}
                          className="flex-1 p-[5px] rounded-md text-center text-[10px] font-semibold transition-all duration-300"
                          style={{
                            background: i <= stageIndex ? "#c8902a22" : "#1a1612",
                            color: i <= stageIndex ? "#c8902a" : "#3a3028",
                            border: `1px solid ${i === stageIndex ? "#c8902a" : "#2a2520"}`,
                          }}
                        >
                          {s.icon}<br />{s.id}
                        </div>
                      ))}
                    </div>
                    <div className="mb-2">
                      <div className="flex justify-between text-xs mb-1 text-buddy-gold">
                        <span>{log[log.length - 1] ?? "Inicjalizacja..."}</span>
                        <span className="font-mono text-buddy-text-faint">{Math.round(progress * 100)}%</span>
                      </div>
                      <div className="h-1 bg-buddy-border rounded-sm overflow-hidden">
                        <div className="h-full bg-buddy-gold rounded-sm transition-[width] duration-400 ease-out shadow-[0_0_8px_#c8902a88]" style={{ width: `${progress * 100}%` }} />
                      </div>
                    </div>
                    <div className="max-h-20 overflow-y-auto font-mono text-[11px] text-buddy-text-faint leading-[1.7]">
                      {log.map((msg, i) => <div key={i}>{msg}</div>)}
                      <div ref={logEndRef} />
                    </div>
                  </div>
                )}

                {/* D: Post-build diff summary */}
                {diffSummary && !isBuilding && (
                  <div className="px-3 py-2.5 bg-[#1a2e1a] border border-[#2a4a2a] rounded-lg">
                    {diffSummary.mode === "append" ? (
                      <div className="text-xs text-buddy-success">
                        ✅ Dodano do kontekstu:{" "}
                        <strong>+{diffSummary.deltaEntities ?? 0} encji</strong>,{" "}
                        <strong>+{diffSummary.deltaTerms ?? 0} terminów</strong>
                      </div>
                    ) : (
                      <div className="text-xs text-buddy-success">
                        ✅ Kontekst przebudowany:{" "}
                        <strong>{diffSummary.entities} encji</strong>,{" "}
                        <strong>{diffSummary.terms} terminów</strong>
                      </div>
                    )}
                  </div>
                )}

                {/* Error */}
                {error && (
                  <ErrorBanner message={error} onDismiss={clearError} />
                )}
                {uploadError && (
                  <ErrorBanner message={uploadError} onDismiss={clearUploadError} />
                )}

                {/* Result stats */}
                {result && !dismissed && (
                  <div className="flex items-center justify-between bg-buddy-surface border border-buddy-border rounded-lg px-3 py-2 text-xs">
                    <span className="text-buddy-text-muted">
                      <span className="text-buddy-gold-light font-semibold">{result.stats.entity_count}</span> encji ·{" "}
                      <span className="text-buddy-gold-light font-semibold">{result.stats.term_count}</span> terminów
                    </span>
                    <button
                      onClick={() => { setDismissed(true); setPendingFiles([]); }}
                      className="text-buddy-text-faint hover:text-buddy-gold-light transition-colors"
                    >
                      Przebuduj
                    </button>
                  </div>
                )}

                {/* Empty state */}
                {!isBuilding && (!result || dismissed) && pendingFiles.length === 0 && !hasContext && (
                  <p className="text-[11px] text-buddy-text-faint text-center pt-1">
                    Prześlij pliki .docx lub .pdf, a następnie kliknij <strong className="text-buddy-text-dim">Zbuduj kontekst</strong>.
                  </p>
                )}
              </>
            )}
          </div>

          {/* Right panel: artefacts */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex px-5 pt-2.5 pb-0 border-b border-buddy-border bg-buddy-surface gap-1">
              {([
                { id: "mindmap",  label: "🗺 Mapa myśli" },
                { id: "glossary", label: "📖 Glosariusz" },
              ] as const).map((t) => (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  className={`px-3.5 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
                    activeTab === t.id
                      ? "border-buddy-gold text-buddy-gold-light"
                      : "border-transparent text-buddy-text-muted hover:text-buddy-gold-light"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <div className="flex-1 p-5 overflow-hidden flex flex-col">
              {!contextReady || (!result && !status?.rag_ready) ? (
                <div className="flex-1 flex flex-col items-center justify-center gap-3 text-buddy-text-ghost">
                  <div className="text-[40px]">📭</div>
                  <div className="text-[13px]">Prześlij dokumenty i zbuduj kontekst, aby zobaczyć artefakty</div>
                </div>
              ) : activeTab === "mindmap" ? (
                <div className="flex-1 rounded-xl overflow-hidden bg-buddy-surface border border-buddy-border">
                  <MindMap
                    nodes={result?.mind_map?.nodes ?? []}
                    edges={result?.mind_map?.edges ?? []}
                  />
                </div>
              ) : (
                <Glossary items={result?.glossary ?? []} onTermClick={handleTermClick} />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
