const STEPS = [
  { id: "audit", icon: "🔍", label: "Audyt" },
  { id: "optimize", icon: "⚙️", label: "Optymalizacja" },
  { id: "regenerate", icon: "🔄", label: "Regeneracja", locked: true },
] as const;

type Tier = (typeof STEPS)[number]["id"];

interface PipelineStepsProps {
  activeTier: Tier;
  onTierChange: (tier: Tier) => void;
}

export default function PipelineSteps({
  activeTier,
  onTierChange,
}: PipelineStepsProps) {
  return (
    <div className="flex items-center gap-1.5 ml-auto">
      {STEPS.map((step, i) => {
        const isActive = step.id === activeTier;
        const isLocked = "locked" in step && step.locked;
        return (
          <div key={step.id} className="flex items-center gap-1.5">
            {i > 0 && (
              <span className="text-buddy-text-ghost text-xs">&rarr;</span>
            )}
            <button
              onClick={() => { if (!isLocked) onTierChange(step.id); }}
              title={isLocked ? "Wkrótce dostępne" : undefined}
              className={`px-2.5 py-1 rounded-md text-xs border transition-all ${
                isLocked
                  ? "opacity-40 cursor-not-allowed bg-buddy-elevated border-buddy-border text-buddy-text-faint"
                  : isActive
                    ? "bg-buddy-gold/15 border-buddy-gold text-buddy-gold-light font-medium"
                    : "bg-buddy-elevated border-buddy-border text-buddy-text-faint hover:border-buddy-muted hover:text-buddy-text-muted"
              }`}
            >
              {step.icon} {step.label}{isLocked ? " 🔒" : ""}
            </button>
          </div>
        );
      })}
    </div>
  );
}
