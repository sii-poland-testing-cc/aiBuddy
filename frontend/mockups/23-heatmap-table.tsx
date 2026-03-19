/**
 * MOCKUP: HeatmapTable
 *
 * Compact coverage heatmap for the Requirements side panel.
 * Shows module-level coverage with color indicators.
 *
 * Columns: Module | Requirements | Covered | Avg Score | Status
 * Status icons: 🟢 80-100 | 🟡 60-79 | 🟠 30-59 | 🔴 0-29
 */

export default function HeatmapTableMockup() {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="border-b border-buddy-border">
          <th className="text-left px-2 py-1.5 text-buddy-text-faint font-medium">Modul</th>
          <th className="text-right px-2 py-1.5 text-buddy-text-faint font-medium">Wym.</th>
          <th className="text-right px-2 py-1.5 text-buddy-text-faint font-medium">Pokr.</th>
          <th className="text-right px-2 py-1.5 text-buddy-text-faint font-medium">Sr.</th>
          <th className="text-center px-2 py-1.5 text-buddy-text-faint font-medium">St.</th>
        </tr>
      </thead>
      <tbody>
        <tr className="border-b border-buddy-border hover:bg-buddy-elevated/50">
          <td className="px-2 py-1.5 text-buddy-text font-medium font-mono">Payment</td>
          <td className="px-2 py-1.5 text-right text-buddy-text-muted">12</td>
          <td className="px-2 py-1.5 text-right text-buddy-text-muted">10</td>
          <td className="px-2 py-1.5 text-right font-mono text-buddy-text-muted">82.5</td>
          <td className="px-2 py-1.5 text-center">🟢</td>
        </tr>
        <tr className="border-b border-buddy-border hover:bg-buddy-elevated/50">
          <td className="px-2 py-1.5 text-buddy-text font-medium font-mono">Auth</td>
          <td className="px-2 py-1.5 text-right text-buddy-text-muted">8</td>
          <td className="px-2 py-1.5 text-right text-buddy-text-muted">5</td>
          <td className="px-2 py-1.5 text-right font-mono text-buddy-text-muted">55.0</td>
          <td className="px-2 py-1.5 text-center">🟠</td>
        </tr>
        <tr className="hover:bg-buddy-elevated/50">
          <td className="px-2 py-1.5 text-buddy-text font-medium font-mono">Reporting</td>
          <td className="px-2 py-1.5 text-right text-buddy-text-muted">5</td>
          <td className="px-2 py-1.5 text-right text-buddy-text-muted">1</td>
          <td className="px-2 py-1.5 text-right font-mono text-buddy-text-muted">18.0</td>
          <td className="px-2 py-1.5 text-center">🔴</td>
        </tr>
      </tbody>
    </table>
  );
}
