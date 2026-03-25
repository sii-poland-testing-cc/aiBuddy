"use client";

export function TierButton({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`w-full text-left transition-all ${
        active
          ? "bg-buddy-gold/15 border-buddy-gold/50 text-buddy-gold-light font-medium"
          : disabled
          ? "border-buddy-border text-buddy-text-dim opacity-40 cursor-not-allowed"
          : "border-buddy-border text-buddy-text-muted hover:border-buddy-border-dark hover:text-buddy-text"
      }`}
      style={{
        padding: "8px 12px", borderRadius: 5, fontSize: 12,
        border: "1px solid", background: active ? undefined : "transparent",
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      {children}
    </button>
  );
}
