# UI Redesign Mockups

These are **JSX mockup files** for review only. They are NOT wired to any real hooks or backend.
They show the proposed component structure, layout, styling, and behavior.

## How to review

Open each `.tsx` file to see the proposed design. Each file has:
- Component interface (props)
- Full JSX structure with Tailwind classes
- Comments explaining behavior and interactions

## Files

### Pages
- `00-home-page.tsx` — Simplified home/project selector (Claude-style)
- `01-unified-project-page.tsx` — The main redesign: single page with 3 modes

### New Components
- `10-mode-bar.tsx` — Top-center mode switcher (Context Builder | Requirements | Suite Analyzer)
- `11-unified-input-area.tsx` — Claude-style input with + attachment button
- `12-panel-card.tsx` — Collapsible card wrapper for side panel content
- `13-side-panel.tsx` — Right-side toggleable panel container
- `14-project-switcher.tsx` — Minimal top-left project dropdown
- `15-progress-bar.tsx` — Shared thin progress indicator
- `16-file-chip.tsx` — File attachment badge

### Inline Views (part of unified page)
- `20-requirements-view.tsx` — Requirements registry (replaces separate page)
- `21-context-status-panel.tsx` — Context build status widget for side panel
- `22-tier-selector.tsx` — Audit/Optimize/Regenerate picker for side panel
- `23-heatmap-table.tsx` — Coverage heatmap for side panel

## Design Principles

1. **One page, three modes** — no page navigation between modules
2. **Claude Desktop inspired** — centered content, minimal chrome, + button for uploads
3. **Card-based side panel** — collapsible cards, user-configurable visibility
4. **Existing hooks unchanged** — useAIBuddyChat, useContextBuilder, etc. stay as-is

## What gets removed (after migration)
- `Sidebar.tsx` → replaced by ProjectSwitcher + ModeBar
- `PipelineSteps.tsx` → merged into ModeBar + TierSelector
- `ChatInputArea.tsx` → replaced by UnifiedInputArea
- `/context/[projectId]/page.tsx` → merged into unified page
- `/chat/[projectId]/page.tsx` → merged into unified page
- `/requirements/[projectId]/page.tsx` → merged into unified page
