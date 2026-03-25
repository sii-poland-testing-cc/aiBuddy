"use client";

import { useState } from "react";

export function PanelCard({
  id,
  icon,
  title,
  badge,
  defaultOpen = false,
  children,
}: {
  id: string;
  icon: string;
  title: string;
  badge?: string | number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      data-testid={`card-${id}`}
      className="border border-buddy-border bg-buddy-base overflow-hidden"
      style={{ borderRadius: 6 }}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => e.key === "Enter" && setOpen((o) => !o)}
        className="flex items-center gap-1.5 cursor-pointer select-none hover:bg-buddy-elevated transition-colors"
        style={{ padding: "9px 12px" }}
      >
        <span style={{ fontSize: 13 }}>{icon}</span>
        <span
          className="flex-1 font-semibold uppercase tracking-widest text-buddy-text-muted"
          style={{ fontSize: 11, letterSpacing: "0.05em" }}
        >
          {title}
        </span>
        {badge !== undefined && (
          <span
            className="bg-buddy-surface2 border border-buddy-border text-buddy-text-dim font-mono"
            style={{ padding: "1px 6px", borderRadius: 4, fontSize: 10 }}
          >
            {badge}
          </span>
        )}
        <span
          className="text-buddy-text-dim"
          style={{
            fontSize: 10,
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
          }}
        >
          ▲
        </span>
      </div>
      {open && (
        <div className="border-t border-buddy-border" style={{ padding: 12 }}>
          {children}
        </div>
      )}
    </div>
  );
}
