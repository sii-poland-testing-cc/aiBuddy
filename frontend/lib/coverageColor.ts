/**
 * Canonical coverage-percentage → colour mapping.
 * Single source of truth used by AuditHistory, AuditResultCard, AuditModePanel.
 *
 * Thresholds:  ≥ 80 → green | ≥ 50 → amber | < 50 → red
 */
export function coverageColor(pct: number): string {
  if (pct >= 80) return "#4a9e6b";
  if (pct >= 50) return "#c8902a";
  return "#c85a3a";
}

/** Background colour matching the same thresholds (semi-transparent fills). */
export function coverageBg(pct: number): string {
  if (pct >= 80) return "rgba(74,158,107,0.2)";
  if (pct >= 50) return "rgba(200,144,42,0.2)";
  return "rgba(192,80,74,0.2)";
}
