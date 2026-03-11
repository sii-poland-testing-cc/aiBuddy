"use client";

import { useState } from "react";

export interface GlossaryTerm {
  term: string;
  definition: string;
  related_terms?: string[];
}

interface GlossaryProps {
  items: GlossaryTerm[];
}

export default function Glossary({ items }: GlossaryProps) {
  const [search, setSearch] = useState("");
  const filtered = items.filter(
    (i) =>
      !search ||
      i.term.toLowerCase().includes(search.toLowerCase()) ||
      i.definition.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search terms…"
        style={{
          background: "#1a1612",
          border: "1px solid #3a3028",
          borderRadius: 6,
          color: "#e8dcc8",
          padding: "6px 12px",
          fontSize: 12,
          fontFamily: "DM Sans, sans-serif",
          marginBottom: 10,
          outline: "none",
          width: "100%",
        }}
      />
      <div style={{ flex: 1, overflowY: "auto" }}>
        {filtered.length === 0 && (
          <div style={{ textAlign: "center", color: "#5a4e42", fontSize: 12, paddingTop: 24 }}>
            Brak wyników
          </div>
        )}
        {filtered.map((item, i) => (
          <div
            key={i}
            style={{
              padding: "10px 14px",
              marginBottom: 6,
              background: "#1e1a16",
              border: "1px solid #2a2520",
              borderRadius: 8,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ fontWeight: 600, color: "#f0c060", fontSize: 13 }}>{item.term}</span>
            </div>
            <p style={{ color: "#c8b89a", fontSize: 12, lineHeight: 1.6, margin: "0 0 6px" }}>
              {item.definition}
            </p>
            {item.related_terms && item.related_terms.length > 0 && (
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                {item.related_terms.map((t, j) => (
                  <span
                    key={j}
                    style={{
                      fontSize: 10,
                      padding: "1px 6px",
                      border: "1px solid #3a3028",
                      borderRadius: 3,
                      color: "#6a5e52",
                      fontFamily: "monospace",
                    }}
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
