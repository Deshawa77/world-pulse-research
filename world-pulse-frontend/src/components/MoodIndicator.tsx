import { useMemo } from "react";
import { Shield, Activity, AlertTriangle, AlertOctagon } from "lucide-react";

interface MoodIndicatorProps {
  threatLevel: "stable" | "guarded" | "elevated" | "critical";
  size?: "small" | "medium" | "large";
  showAnimation?: boolean;
  className?: string;
}

export default function MoodIndicator({
  threatLevel,
  size = "medium",
  showAnimation = true,
  className = "",
}: MoodIndicatorProps) {
  const moodConfig = useMemo(() => {
    switch (threatLevel) {
      case "critical":
        return {
          label: "CRITICAL",
          icon: AlertOctagon,
          color: "#ff3366",
          bgColor: "rgba(255, 51, 102, 0.15)",
          borderColor: "rgba(255, 51, 102, 0.5)",
          glowColor: "rgba(255, 51, 102, 0.6)",
          shape: "polygon(20% 0%, 80% 0%, 100% 20%, 100% 80%, 80% 100%, 20% 100%, 0% 80%, 0% 20%)",
          animation: "mood-pulse-critical",
        };
      case "elevated":
        return {
          label: "MONITORING",
          icon: AlertTriangle,
          color: "#ff9500",
          bgColor: "rgba(255, 149, 0, 0.15)",
          borderColor: "rgba(255, 149, 0, 0.5)",
          glowColor: "rgba(255, 149, 0, 0.6)",
          shape: "polygon(50% 0%, 100% 38%, 82% 100%, 18% 100%, 0% 38%)",
          animation: "mood-pulse-elevated",
        };
      case "guarded":
        return {
          label: "ATTENTION",
          icon: Activity,
          color: "#ffd600",
          bgColor: "rgba(255, 214, 0, 0.15)",
          borderColor: "rgba(255, 214, 0, 0.5)",
          glowColor: "rgba(255, 214, 0, 0.6)",
          shape: "polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)",
          animation: "mood-pulse-guarded",
        };
      case "stable":
      default:
        return {
          label: "STABLE",
          icon: Shield,
          color: "#00e0ff",
          bgColor: "rgba(0, 224, 255, 0.15)",
          borderColor: "rgba(0, 224, 255, 0.5)",
          glowColor: "rgba(0, 224, 255, 0.6)",
          shape: "polygon(10% 0, 100% 0%, 100% 90%, 90% 100%, 0 100%, 0% 10%)",
          animation: "mood-pulse-stable",
        };
    }
  }, [threatLevel]);

  const sizeClasses = {
    small: {
      container: "px-2 py-1 text-[10px]",
      gap: "4px",
      icon: 12,
      badge: "w-16 h-6",
    },
    medium: {
      container: "px-3 py-1.5 text-xs",
      gap: "8px",
      icon: 14,
      badge: "w-20 h-7",
    },
    large: {
      container: "px-4 py-2 text-sm",
      gap: "8px",
      icon: 16,
      badge: "w-24 h-8",
    },
  };


  const Icon = moodConfig.icon;

  return (
    <div
      className={`mood-indicator ${className} ${showAnimation ? moodConfig.animation : ""}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: sizeClasses[size].gap,
        padding: sizeClasses[size].container.split(" ").slice(1, 3).join(" "),

        background: moodConfig.bgColor,
        border: `1px solid ${moodConfig.borderColor}`,
        borderRadius: "8px",
        color: moodConfig.color,
        fontSize: sizeClasses[size].container.split(" ")[2],
        fontWeight: 700,
        letterSpacing: "1.5px",
        textTransform: "uppercase" as const,
        textShadow: `0 0 10px ${moodConfig.glowColor}`,
        boxShadow: `0 0 20px ${moodConfig.glowColor}, inset 0 0 10px ${moodConfig.bgColor}`,
        position: "relative",
        overflow: "hidden",
        clipPath: moodConfig.shape,
        transition: "all 0.3s ease",
      }}
    >
      {/* Holographic shimmer effect */}
      <div
        className="mood-shimmer"
        style={{
          position: "absolute",
          inset: 0,
          background: `linear-gradient(90deg, transparent, ${moodConfig.glowColor}, transparent)`,
          transform: "translateX(-100%)",
          animation: showAnimation ? "mood-shimmer 2s infinite" : "none",
        }}
      />
      
      <Icon size={sizeClasses[size].icon} />
      <span className="mood-label">{moodConfig.label}</span>
      
      {/* Decorative corner accents */}
      <div
        className="corner-accent top-left"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "6px",
          height: "6px",
          borderTop: `2px solid ${moodConfig.color}`,
          borderLeft: `2px solid ${moodConfig.color}`,
        }}
      />
      <div
        className="corner-accent top-right"
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          width: "6px",
          height: "6px",
          borderTop: `2px solid ${moodConfig.color}`,
          borderRight: `2px solid ${moodConfig.color}`,
        }}
      />
      <div
        className="corner-accent bottom-left"
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          width: "6px",
          height: "6px",
          borderBottom: `2px solid ${moodConfig.color}`,
          borderLeft: `2px solid ${moodConfig.color}`,
        }}
      />
      <div
        className="corner-accent bottom-right"
        style={{
          position: "absolute",
          bottom: 0,
          right: 0,
          width: "6px",
          height: "6px",
          borderBottom: `2px solid ${moodConfig.color}`,
          borderRight: `2px solid ${moodConfig.color}`,
        }}
      />
    </div>
  );
}
