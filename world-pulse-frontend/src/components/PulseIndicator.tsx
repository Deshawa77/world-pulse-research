import { useMemo } from "react";

interface PulseIndicatorProps {
  threatLevel: "stable" | "guarded" | "elevated" | "critical";
  size?: "small" | "medium" | "large";
  className?: string;
}

export default function PulseIndicator({
  threatLevel,
  size = "small",
  className = "",
}: PulseIndicatorProps) {
  const pulseSpeed = useMemo(() => {
    switch (threatLevel) {
      case "critical":
        return 0.8; // Fast pulse
      case "elevated":
        return 1.5; // Medium pulse
      case "guarded":
        return 2.0; // Normal pulse
      case "stable":
      default:
        return 3.0; // Slow pulse
    }
  }, [threatLevel]);

  const sizeClasses = {
    small: "w-3 h-3",
    medium: "w-4 h-4",
    large: "w-5 h-5",
  };

  const colorClasses = {
    stable: "bg-blue-500 shadow-blue-500/50",
    guarded: "bg-yellow-500 shadow-yellow-500/50",
    elevated: "bg-orange-500 shadow-orange-500/50",
    critical: "bg-red-500 shadow-red-500/50",
  };

  return (
    <div className={`pulse-indicator ${className}`}>
      <div
        className={`relative ${sizeClasses[size]}`}
        style={{ "--pulse-speed": `${pulseSpeed}s` } as React.CSSProperties}
      >
        {/* Core dot */}
        <div
          className={`absolute inset-0 rounded-full ${colorClasses[threatLevel]} shadow-lg`}
        />
        
        {/* Pulse ring 1 */}
        <div
          className={`absolute inset-0 rounded-full ${colorClasses[threatLevel]} opacity-60 animate-pulse-ring-1`}
          style={{ animationDuration: `${pulseSpeed}s` }}
        />
        
        {/* Pulse ring 2 */}
        <div
          className={`absolute inset-0 rounded-full ${colorClasses[threatLevel]} opacity-40 animate-pulse-ring-2`}
          style={{ animationDuration: `${pulseSpeed * 1.2}s` }}
        />
      </div>
    </div>
  );
}
