"use client";

import { useState } from "react";

export interface GlossaryTerm {
  term: string;
  definition: string;
  related_terms?: string[];
}

interface GlossaryProps {
  items: GlossaryTerm[];
  onTermClick?: (term: GlossaryTerm) => void;
}

export default function Glossary({ items, onTermClick }: GlossaryProps) {
  const [search, setSearch] = useState("");
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const filtered = items.filter(
    (i) =>
      !search ||
      i.term.toLowerCase().includes(search.toLowerCase()) ||
      i.definition.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="h-full flex flex-col">
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Szukaj terminów..."
        className="bg-buddy-surface border border-buddy-border-dark rounded-md text-buddy-text px-3 py-1.5 text-xs font-sans mb-2.5 outline-none w-full focus:border-buddy-gold"
      />
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="text-center text-buddy-text-faint text-xs pt-6">
            Brak wyników
          </div>
        )}
        {filtered.map((item, i) => (
          <div
            key={i}
            role={onTermClick ? "button" : undefined}
            tabIndex={onTermClick ? 0 : undefined}
            onClick={() => onTermClick?.(item)}
            onKeyDown={onTermClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onTermClick(item); } } : undefined}
            onMouseEnter={() => setHoveredIdx(i)}
            onMouseLeave={() => setHoveredIdx(null)}
            className="px-3.5 py-2.5 mb-1.5 bg-buddy-elevated rounded-lg transition-[border-color] duration-150"
            style={{
              border: `1px solid ${hoveredIdx === i ? "#c8902a" : "#2a2520"}`,
              cursor: onTermClick ? "pointer" : "default",
            }}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold text-buddy-gold-light text-[13px]">{item.term}</span>
            </div>
            <p className="text-[#c8b89a] text-xs leading-relaxed m-0 mb-1.5">
              {item.definition}
            </p>
            {item.related_terms && item.related_terms.length > 0 && (
              <div className="flex gap-1.5 flex-wrap">
                {item.related_terms.map((t, j) => (
                  <span
                    key={j}
                    className="text-[10px] px-1.5 py-px border border-buddy-border-dark rounded-sm text-buddy-text-dim font-mono"
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
