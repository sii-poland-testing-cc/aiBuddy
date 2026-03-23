"use client";

/**
 * Mockup Preview Page — /mockup
 *
 * Renders all UI redesign mockups one below the other.
 * NOT wired to any real hooks or backend.
 * For review only — remove before production.
 */

import { useState } from "react";

import HomePageMockup from "../../mockups/00-home-page";
import UnifiedProjectPageMockup from "../../mockups/01-unified-project-page";
import ModeBarMockup from "../../mockups/10-mode-bar";
import UnifiedInputAreaMockup from "../../mockups/11-unified-input-area";
import PanelCardMockup from "../../mockups/12-panel-card";
import SidePanelMockup from "../../mockups/13-side-panel";
import ProjectSwitcherMockup from "../../mockups/14-project-switcher";
import ProgressBarMockup from "../../mockups/15-progress-bar";
import FileChipMockup from "../../mockups/16-file-chip";
import RequirementsViewMockup from "../../mockups/20-requirements-view";
import ContextStatusPanelMockup from "../../mockups/21-context-status-panel";
import TierSelectorMockup from "../../mockups/22-tier-selector";
import HeatmapTableMockup from "../../mockups/23-heatmap-table";

const SECTIONS = [
  { id: "home", label: "00 — Home Page", fullPage: true, Component: HomePageMockup },
  { id: "unified", label: "01 — Unified Project Page", fullPage: true, Component: UnifiedProjectPageMockup },
  { id: "modebar", label: "10 — ModeBar", fullPage: false, Component: ModeBarMockup },
  { id: "input", label: "11 — UnifiedInputArea", fullPage: false, Component: UnifiedInputAreaMockup },
  { id: "panelcard", label: "12 — PanelCard", fullPage: false, Component: PanelCardMockup },
  { id: "sidepanel", label: "13 — SidePanel", fullPage: false, Component: SidePanelMockup },
  { id: "switcher", label: "14 — ProjectSwitcher", fullPage: false, Component: ProjectSwitcherMockup },
  { id: "progress", label: "15 — ProgressBar", fullPage: false, Component: ProgressBarMockup },
  { id: "filechip", label: "16 — FileChip", fullPage: false, Component: FileChipMockup },
  { id: "reqs", label: "20 — RequirementsView", fullPage: false, Component: RequirementsViewMockup },
  { id: "context-status", label: "21 — ContextStatusPanel", fullPage: false, Component: ContextStatusPanelMockup },
  { id: "tier", label: "22 — TierSelector", fullPage: false, Component: TierSelectorMockup },
  { id: "heatmap", label: "23 — HeatmapTable", fullPage: false, Component: HeatmapTableMockup },
];

export default function MockupPreviewPage() {
  const [active, setActive] = useState<string | null>(null);

  const shown = active ? SECTIONS.filter((s) => s.id === active) : SECTIONS;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 font-sans">
      {/* Nav bar */}
      <nav className="sticky top-0 z-50 bg-zinc-900 border-b border-zinc-800 px-4 py-2 flex flex-wrap gap-2 items-center">
        <span className="text-zinc-400 text-xs font-mono mr-2">MOCKUP PREVIEW</span>
        <button
          onClick={() => setActive(null)}
          className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
            active === null ? "bg-amber-600 text-white" : "text-zinc-400 hover:text-white hover:bg-zinc-800"
          }`}
        >
          All
        </button>
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => setActive(s.id === active ? null : s.id)}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              active === s.id
                ? "bg-amber-600 text-white"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800"
            }`}
          >
            {s.label.split(" — ")[0]}
          </button>
        ))}
      </nav>

      {/* Sections */}
      <div className="flex flex-col gap-12 py-8 px-4">
        {shown.map(({ id, label, fullPage, Component }) => (
          <section key={id} id={id}>
            <div className="max-w-6xl mx-auto">
              <h2 className="text-xs font-mono text-zinc-500 mb-3 uppercase tracking-widest">
                {label}
              </h2>
              {fullPage ? (
                /* Full-page mockups: render in a fixed-height iframe-like box */
                <div className="rounded-xl overflow-hidden border border-zinc-800" style={{ height: "85vh" }}>
                  <div className="w-full h-full overflow-auto">
                    <Component />
                  </div>
                </div>
              ) : (
                /* Component mockups: render on dark card, natural height */
                <div className="rounded-xl border border-zinc-800 bg-[#141210] p-6">
                  <Component />
                </div>
              )}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
