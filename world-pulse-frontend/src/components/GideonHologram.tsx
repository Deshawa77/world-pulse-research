import { useEffect, useRef } from "react";

interface GideonHologramProps {
  isSpeaking?: boolean;
  isProcessing?: boolean;
  isDataStreaming?: boolean;
  threatLevel?: "stable" | "guarded" | "elevated" | "critical";
  className?: string;
}

export default function GideonHologram({
  isSpeaking = false,
  isProcessing = false,
  isDataStreaming = false,
  threatLevel = "stable",
  className = "",
}: GideonHologramProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>(0);

  // Gideon colors - glowing light blue
  const getGideonColor = () => {
    switch (threatLevel) {
      case "critical":
        return {
          primary: "#4da6ff",
          secondary: "#80bfff",
          glow: "rgba(77, 166, 255, 0.6)",
          core: "#b3d9ff",
          accent: "#ff6b6b", // Red for critical
        };
      case "elevated":
        return {
          primary: "#4da6ff",
          secondary: "#80bfff",
          glow: "rgba(77, 166, 255, 0.55)",
          core: "#b3d9ff",
          accent: "#ffa500", // Orange for elevated
        };
      case "guarded":
        return {
          primary: "#4da6ff",
          secondary: "#80bfff",
          glow: "rgba(77, 166, 255, 0.5)",
          core: "#b3d9ff",
          accent: "#ffd700", // Yellow for guarded
        };
      default:
        return {
          primary: "#4da6ff",
          secondary: "#80bfff",
          glow: "rgba(77, 166, 255, 0.5)",
          core: "#b3d9ff",
          accent: "#00ffcc", // Cyan for stable
        };
    }
  };

  const hexToRgba = (hex: string, alpha: number) => {
    const normalized = hex.replace("#", "");
    const chunk = normalized.length === 3
      ? normalized.split("").map((c) => c + c).join("")
      : normalized;
    const value = Number.parseInt(chunk, 16);
    const r = (value >> 16) & 255;
    const g = (value >> 8) & 255;
    const b = value & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let time = 0;

    // Abstract interface nodes - representing AI consciousness
    interface Node {
      x: number;
      y: number;
      targetX: number;
      targetY: number;
      size: number;
      phase: number;
      speed: number;
    }

    const nodes: Node[] = [];
    const numNodes = 60;

    // Initialize nodes in a circular pattern (AI consciousness visualization)
    for (let i = 0; i < numNodes; i++) {
      const angle = (i / numNodes) * Math.PI * 2;
      const radius = 80 + Math.random() * 40;
      nodes.push({
        x: canvas.width / 2 + Math.cos(angle) * radius,
        y: canvas.height / 2 + Math.sin(angle) * radius,
        targetX: canvas.width / 2 + Math.cos(angle) * radius,
        targetY: canvas.height / 2 + Math.sin(angle) * radius,
        size: 2 + Math.random() * 4,
        phase: Math.random() * Math.PI * 2,
        speed: 0.5 + Math.random() * 1.5,
      });
    }

    // Central core nodes
    const coreNodes: Node[] = [];
    for (let i = 0; i < 12; i++) {
      const angle = (i / 12) * Math.PI * 2;
      coreNodes.push({
        x: canvas.width / 2,
        y: canvas.height / 2,
        targetX: canvas.width / 2 + Math.cos(angle) * 25,
        targetY: canvas.height / 2 + Math.sin(angle) * 25,
        size: 3 + Math.random() * 3,
        phase: Math.random() * Math.PI * 2,
        speed: 1 + Math.random() * 2,
      });
    }

    const drawBackground = (color: ReturnType<typeof getGideonColor>) => {
      // Dark background to make blue glow stand out (like Time Vault)
      const bgGradient = ctx.createRadialGradient(
        canvas.width / 2, canvas.height / 2, 0,
        canvas.width / 2, canvas.height / 2, canvas.width * 0.7
      );
      bgGradient.addColorStop(0, "rgba(10, 25, 47, 0.95)");
      bgGradient.addColorStop(0.5, "rgba(5, 15, 30, 0.98)");
      bgGradient.addColorStop(1, "rgba(0, 5, 15, 1)");
      ctx.fillStyle = bgGradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Subtle ambient fog
      const fogGradient = ctx.createRadialGradient(
        canvas.width / 2, canvas.height / 2, 0,
        canvas.width / 2, canvas.height / 2, canvas.width * 0.5
      );
      fogGradient.addColorStop(0, hexToRgba(color.primary, 0.03));
      fogGradient.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = fogGradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    };

    const drawOuterRing = (color: ReturnType<typeof getGideonColor>) => {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const baseRadius = 120;

      // Multiple rings
      for (let ring = 0; ring < 3; ring++) {
        const radius = baseRadius + ring * 15;
        const alpha = 0.15 - ring * 0.03;
        
        ctx.strokeStyle = hexToRgba(color.secondary, alpha);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.stroke();

        // Rotating dashes
        const numDashes = 24 + ring * 8;
        for (let i = 0; i < numDashes; i++) {
          const angle = (i / numDashes) * Math.PI * 2 + time * 0.002 * (ring + 1);
          const dashLength = 8 + ring * 2;
          const innerRadius = radius - 2;
          const outerRadius = radius + dashLength;
          
          ctx.strokeStyle = hexToRgba(color.primary, 0.2 - ring * 0.05);
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(
            centerX + Math.cos(angle) * innerRadius,
            centerY + Math.sin(angle) * innerRadius
          );
          ctx.lineTo(
            centerX + Math.cos(angle) * outerRadius,
            centerY + Math.sin(angle) * outerRadius
          );
          ctx.stroke();
        }
      }
    };

    const drawInnerRing = (color: ReturnType<typeof getGideonColor>) => {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const radius = 60;

      // Dotted inner ring
      ctx.strokeStyle = hexToRgba(color.primary, 0.3);
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 8]);
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);

      // Rotating inner ring
      ctx.strokeStyle = hexToRgba(color.secondary, 0.25);
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius - 8, time * 0.003, time * 0.003 + Math.PI * 1.5);
      ctx.stroke();
    };

    const drawCore = (color: ReturnType<typeof getGideonColor>) => {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;

      // Pulsing core glow
      const pulse = isSpeaking ? 1.3 : 1 + Math.sin(time * 0.04) * 0.2;
      const coreSize = 18 * pulse;

      // Core gradient
      const coreGradient = ctx.createRadialGradient(
        centerX, centerY, 0,
        centerX, centerY, coreSize * 2
      );
      coreGradient.addColorStop(0, hexToRgba(color.core, 0.8));
      coreGradient.addColorStop(0.3, hexToRgba(color.primary, 0.5));
      coreGradient.addColorStop(0.6, hexToRgba(color.secondary, 0.2));
      coreGradient.addColorStop(1, "rgba(0, 0, 0, 0)");
      
      ctx.fillStyle = coreGradient;
      ctx.beginPath();
      ctx.arc(centerX, centerY, coreSize * 2, 0, Math.PI * 2);
      ctx.fill();

      // Bright center
      ctx.fillStyle = hexToRgba("#ffffff", 0.9);
      ctx.beginPath();
      ctx.arc(centerX, centerY, coreSize * 0.3, 0, Math.PI * 2);
      ctx.fill();
    };

    const drawNodes = (color: ReturnType<typeof getGideonColor>) => {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;

      // Draw outer consciousness nodes
      for (const node of nodes) {
        // Orbit animation
        const angle = Math.atan2(node.targetY - centerY, node.targetX - centerX);
        const radius = 80 + Math.sin(time * 0.02 + node.phase) * 40;
        node.x = centerX + Math.cos(angle + time * node.speed * 0.001) * radius;
        node.y = centerY + Math.sin(angle + time * node.speed * 0.001) * radius;

        // Node glow
        const nodePulse = 0.5 + Math.sin(time * 0.05 + node.phase) * 0.3;
        const nodeSize = node.size * (isSpeaking ? 1.3 : 1);

        // Glow effect
        const glowGradient = ctx.createRadialGradient(
          node.x, node.y, 0,
          node.x, node.y, nodeSize * 4
        );
        glowGradient.addColorStop(0, hexToRgba(color.primary, 0.4 * nodePulse));
        glowGradient.addColorStop(0.5, hexToRgba(color.secondary, 0.15 * nodePulse));
        glowGradient.addColorStop(1, "rgba(0, 0, 0, 0)");
        ctx.fillStyle = glowGradient;
        ctx.beginPath();
        ctx.arc(node.x, node.y, nodeSize * 4, 0, Math.PI * 2);
        ctx.fill();

        // Node core
        ctx.fillStyle = hexToRgba(color.primary, 0.8 * nodePulse);
        ctx.beginPath();
        ctx.arc(node.x, node.y, nodeSize, 0, Math.PI * 2);
        ctx.fill();

        // Bright center
        ctx.fillStyle = hexToRgba("#ffffff", 0.9);
        ctx.beginPath();
        ctx.arc(node.x, node.y, nodeSize * 0.3, 0, Math.PI * 2);
        ctx.fill();
      }

      // Draw core nodes
      for (const node of coreNodes) {
        const angle = node.phase + time * node.speed * 0.003;
        const radius = 25 + Math.sin(time * 0.03 + node.phase) * 8;
        node.x = centerX + Math.cos(angle) * radius;
        node.y = centerY + Math.sin(angle) * radius;

        const nodePulse = 0.6 + Math.sin(time * 0.06 + node.phase) * 0.4;

        ctx.fillStyle = hexToRgba(color.primary, 0.7 * nodePulse);
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.size * 0.7, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const drawScanningLines = (color: ReturnType<typeof getGideonColor>) => {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;

      // Vertical scanning line
      const scanY = ((time * 1.5) % (canvas.height + 40)) - 20;
      const scanGradient = ctx.createLinearGradient(0, scanY - 20, 0, scanY + 20);
      scanGradient.addColorStop(0, "rgba(0, 0, 0, 0)");
      scanGradient.addColorStop(0.5, hexToRgba(color.secondary, 0.15));
      scanGradient.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.strokeStyle = scanGradient;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(centerX - 130, scanY);
      ctx.lineTo(centerX + 130, scanY);
      ctx.stroke();

      // Horizontal scan
      const scanX = ((time * 1.2) % (canvas.width + 40)) - 20;
      const hScanGradient = ctx.createLinearGradient(scanX - 20, 0, scanX + 20, 0);
      hScanGradient.addColorStop(0, "rgba(0, 0, 0, 0)");
      hScanGradient.addColorStop(0.5, hexToRgba(color.secondary, 0.1));
      hScanGradient.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.strokeStyle = hScanGradient;
      ctx.beginPath();
      ctx.moveTo(scanX, centerY - 120);
      ctx.lineTo(scanX, centerY + 120);
      ctx.stroke();
    };

    const drawWaveform = (color: ReturnType<typeof getGideonColor>) => {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2 + 90;

      if (isSpeaking) {
        // Animated waveform when speaking
        ctx.beginPath();
        ctx.moveTo(centerX - 80, centerY);
        
        for (let x = -80; x <= 80; x += 4) {
          const y = Math.sin((x + time * 8) * 0.1) * 15 + 
                    Math.sin((x + time * 12) * 0.05) * 8;
          ctx.lineTo(centerX + x, centerY + y);
        }
        
        ctx.strokeStyle = hexToRgba(color.primary, 0.6);
        ctx.lineWidth = 2;
        ctx.stroke();
      } else {
        // Static waveform when idle
        ctx.beginPath();
        for (let x = -80; x <= 80; x += 2) {
          const y = Math.sin(x * 0.05 + time * 0.02) * 5;
          if (x === -80) ctx.moveTo(centerX + x, centerY + y);
          else ctx.lineTo(centerX + x, centerY + y);
        }
        ctx.strokeStyle = hexToRgba(color.secondary, 0.3);
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    };

    const drawStatusIndicator = (color: ReturnType<typeof getGideonColor>) => {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2 + 140;

      // Status dot
      const statusColor = isDataStreaming ? color.accent : color.secondary;
      const statusPulse = isDataStreaming ? 1 + Math.sin(time * 0.2) * 0.3 : 0.5;

      // Glow
      const glowGradient = ctx.createRadialGradient(
        centerX, centerY, 0,
        centerX, centerY, 12
      );
      glowGradient.addColorStop(0, hexToRgba(statusColor, 0.6 * statusPulse));
      glowGradient.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = glowGradient;
      ctx.beginPath();
      ctx.arc(centerX, centerY, 12, 0, Math.PI * 2);
      ctx.fill();

      // Core
      ctx.fillStyle = hexToRgba(statusColor, statusPulse);
      ctx.beginPath();
      ctx.arc(centerX, centerY, 4, 0, Math.PI * 2);
      ctx.fill();

      // Status text simulation (abstract lines)
      const textY = centerY - 25;
      for (let i = 0; i < 3; i++) {
        const lineWidth = 20 + i * 15 + Math.sin(time * 0.03 + i) * 5;
        ctx.strokeStyle = hexToRgba(color.secondary, 0.2 - i * 0.05);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(centerX - lineWidth / 2, textY + i * 6);
        ctx.lineTo(centerX + lineWidth / 2, textY + i * 6);
        ctx.stroke();
      }
    };

    const drawHexPattern = (color: ReturnType<typeof getGideonColor>) => {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      
      // Subtle hex grid in background
      ctx.strokeStyle = hexToRgba(color.secondary, 0.05);
      ctx.lineWidth = 0.5;
      
      const hexSize = 20;
      const rows = 8;
      const cols = 8;
      
      for (let row = -rows; row <= rows; row++) {
        for (let col = -cols; col <= cols; col++) {
          const x = centerX + col * hexSize * 1.5 + (row % 2) * hexSize * 0.75;
          const y = centerY + row * hexSize * 0.866;
          
          // Only draw if within canvas
          if (x > -20 && x < canvas.width + 20 && y > -20 && y < canvas.height + 20) {
            ctx.beginPath();
            for (let i = 0; i < 6; i++) {
              const angle = (Math.PI / 3) * i;
              const px = x + Math.cos(angle) * hexSize * 0.4;
              const py = y + Math.sin(angle) * hexSize * 0.4;
              if (i === 0) ctx.moveTo(px, py);
              else ctx.lineTo(px, py);
            }
            ctx.closePath();
            ctx.stroke();
          }
        }
      }
    };

    const drawProcessingIndicator = (color: ReturnType<typeof getGideonColor>) => {
      if (!isProcessing) return;
      
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      
      // Rotating processing arcs
      for (let i = 0; i < 3; i++) {
        const startAngle = time * 0.05 + (i * Math.PI * 2 / 3);
        const endAngle = startAngle + Math.PI * 0.5;
        
        ctx.strokeStyle = hexToRgba(color.accent, 0.5);
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(centerX, centerY, 35 + i * 8, startAngle, endAngle);
        ctx.stroke();
      }
    };

    const draw = () => {
      const color = getGideonColor();
      
      drawBackground(color);
      drawHexPattern(color);
      drawOuterRing(color);
      drawInnerRing(color);
      drawCore(color);
      drawNodes(color);
      drawScanningLines(color);
      drawWaveform(color);
      drawStatusIndicator(color);
      drawProcessingIndicator(color);

      // Random glitch effect occasionally
      if (Math.random() > 0.995) {
        const glitchY = Math.random() * canvas.height;
        const glitchHeight = 2 + Math.random() * 4;
        ctx.fillStyle = hexToRgba(color.primary, 0.3);
        ctx.fillRect(0, glitchY, canvas.width, glitchHeight);
      }

      time += 1;
      animationRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(animationRef.current);
    };
  }, [isSpeaking, isProcessing, isDataStreaming, threatLevel]);

  const color = getGideonColor();

  return (
    <div 
      className={`gideon-hologram ${className}`} 
      style={{ 
        position: "relative",
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center"
      }}
    >
      <canvas
        ref={canvasRef}
        width={320}
        height={320}
        style={{
          filter: `drop-shadow(0 0 30px ${color.glow})`,
          opacity: 0.95,
        }}
      />
      
      {/* Outer glow effect */}
      <div
        style={{
          position: "absolute",
          inset: "-20px",
          background: `radial-gradient(ellipse at center, ${color.glow} 0%, transparent 70%)`,
          pointerEvents: "none",
          animation: "gideon-pulse 4s ease-in-out infinite",
        }}
      />
      
      {/* Scanline overlay for digital effect */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(77, 166, 255, 0.015) 2px,
            rgba(77, 166, 255, 0.015) 4px
          )`,
          pointerEvents: "none",
          mixBlendMode: "screen",
        }}
      />
    </div>
  );
}
