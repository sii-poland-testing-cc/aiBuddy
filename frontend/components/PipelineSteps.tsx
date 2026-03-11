const STEPS = [
  { id: "audit", icon: "🔍", label: "Audit" },
  { id: "optimize", icon: "⚙️", label: "Optimize" },
  { id: "regenerate", icon: "🔄", label: "Regenerate" },
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
        return (
          <div key={step.id} className="flex items-center gap-1.5">
            {i > 0 && (
              <span className="text-buddy-text-ghost text-xs">→</span>
            )}
            <button
              onClick={() => onTierChange(step.id)}
              className={`px-2.5 py-1 rounded-md text-xs border transition-all ${
                isActive
                  ? "bg-buddy-gold/15 border-buddy-gold text-buddy-gold-light font-medium"
                  : "bg-buddy-elevated border-buddy-border text-buddy-text-faint hover:border-buddy-muted hover:text-buddy-text-muted"
              }`}
            >
              {step.icon} {step.label}
            </button>
          </div>
        );
      })}
    </div>
  );
}
