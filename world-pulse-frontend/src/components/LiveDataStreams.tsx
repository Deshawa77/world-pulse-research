import { useEffect, useRef, useState } from "react";

interface LiveDataStreamsProps {
  isActive?: boolean;
  threatLevel?: "stable" | "guarded" | "elevated" | "critical";
  streamCount?: number;
  className?: string;
}

interface DataPacket {
  id: number;
  x: number;
  y: number;
  targetX: number;
  targetY: number;
  speed: number;
  size: number;
  color: string;
  pulsePhase: number;
}

export default function LiveDataStreams({
  isActive = true,
  threatLevel = "stable",
  streamCount = 5,
  className = "",
}: LiveDataStreamsProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>(0);
  const packetsRef = useRef<DataPacket[]>([]);
  const [dimensions, setDimensions] = useState({ width: 300, height: 200 });

  const getStreamColor = () => {
    switch (threatLevel) {
      case "critical": return "#ff3366";
      case "elevated": return "#ff9500";
      case "guarded": return "#ffd600";
      default: return "#00e0ff";
    }
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const updateDimensions = () => {
      const rect = canvas.getBoundingClientRect();
      setDimensions({ width: rect.width, height: rect.height });
      canvas.width = rect.width;
      canvas.height = rect.height;
    };

    updateDimensions();
    window.addEventListener("resize", updateDimensions);

    return () => {
      window.removeEventListener("resize", updateDimensions);
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !isActive) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const color = getStreamColor();
    let time = 0;

    // Initialize data packets
    const initPackets = () => {
      packetsRef.current = [];
      for (let i = 0; i < streamCount * 3; i++) {
        const streamIndex = i % streamCount;
        packetsRef.current.push({
          id: i,
          x: Math.random() * dimensions.width,
          y: (streamIndex + 0.5) * (dimensions.height / streamCount),
          targetX: dimensions.width * 0.5,
          targetY: dimensions.height * 0.5,
          speed: 1 + Math.random() * 2,
          size: 2 + Math.random() * 3,
          color,
          pulsePhase: Math.random() * Math.PI * 2,
        });
      }
    };

    initPackets();

    const draw = () => {
      ctx.fillStyle = "rgba(11, 18, 32, 0.1)";
      ctx.fillRect(0, 0, dimensions.width, dimensions.height);

      const centerX = dimensions.width * 0.5;
      const centerY = dimensions.height * 0.5;

      // Draw stream lines
      for (let i = 0; i < streamCount; i++) {
        const y = (i + 0.5) * (dimensions.height / streamCount);
        
        // Main stream line
        const gradient = ctx.createLinearGradient(0, y, centerX, centerY);
        gradient.addColorStop(0, `${color}00`);
        gradient.addColorStop(0.5, `${color}40`);
        gradient.addColorStop(1, `${color}80`);

        ctx.strokeStyle = gradient;
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 10]);
        ctx.lineDashOffset = -time * 2;
        
        ctx.beginPath();
        ctx.moveTo(0, y);
        
        // Curved path to center
        const cp1x = centerX * 0.3;
        const cp1y = y;
        const cp2x = centerX * 0.7;
        const cp2y = centerY;
        
        ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, centerX, centerY);
        ctx.stroke();
        
        ctx.setLineDash([]);
      }

      // Draw and update data packets
      packetsRef.current.forEach((packet) => {
        // Move packet towards center
        const dx = packet.targetX - packet.x;
        const dy = packet.targetY - packet.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        
        if (dist > 5) {
          packet.x += (dx / dist) * packet.speed;
          packet.y += (dy / dist) * packet.speed;
        } else {
          // Reset packet to edge
          packet.x = 0;
          packet.y = (Math.floor(Math.random() * streamCount) + 0.5) * (dimensions.height / streamCount);
        }

        // Draw packet glow
        const pulseSize = packet.size * (1 + Math.sin(time * 0.1 + packet.pulsePhase) * 0.3);
        const glowGradient = ctx.createRadialGradient(
          packet.x, packet.y, 0,
          packet.x, packet.y, pulseSize * 4
        );
        glowGradient.addColorStop(0, `${color}80`);
        glowGradient.addColorStop(0.5, `${color}40`);
        glowGradient.addColorStop(1, `${color}00`);

        ctx.fillStyle = glowGradient;
        ctx.beginPath();
        ctx.arc(packet.x, packet.y, pulseSize * 4, 0, Math.PI * 2);
        ctx.fill();

        // Draw packet core
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(packet.x, packet.y, packet.size, 0, Math.PI * 2);
        ctx.fill();

        // Draw trail
        ctx.strokeStyle = `${color}60`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(packet.x, packet.y);
        ctx.lineTo(packet.x - (dx / dist) * 20, packet.y - (dy / dist) * 20);
        ctx.stroke();
      });

      // Draw center pulse (map entry point)
      const centerPulse = 15 + Math.sin(time * 0.15) * 5;
      const centerGlow = ctx.createRadialGradient(
        centerX, centerY, 0,
        centerX, centerY, centerPulse * 3
      );
      centerGlow.addColorStop(0, `${color}60`);
      centerGlow.addColorStop(0.5, `${color}30`);
      centerGlow.addColorStop(1, `${color}00`);

      ctx.fillStyle = centerGlow;
      ctx.beginPath();
      ctx.arc(centerX, centerY, centerPulse * 3, 0, Math.PI * 2);
      ctx.fill();

      // Center core
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(centerX, centerY, 6, 0, Math.PI * 2);
      ctx.fill();

      // Draw incoming data indicators
      const indicatorCount = 8;
      for (let i = 0; i < indicatorCount; i++) {
        const angle = (i / indicatorCount) * Math.PI * 2 + time * 0.02;
        const radius = 40 + Math.sin(time * 0.1 + i) * 5;
        const ix = centerX + Math.cos(angle) * radius;
        const iy = centerY + Math.sin(angle) * radius;
        
        ctx.fillStyle = `${color}${Math.floor(40 + Math.sin(time * 0.2 + i) * 30).toString(16).padStart(2, "0")}`;
        ctx.beginPath();
        ctx.arc(ix, iy, 2, 0, Math.PI * 2);
        ctx.fill();
      }

      time++;
      animationRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(animationRef.current);
    };
  }, [isActive, threatLevel, streamCount, dimensions]);

  const color = getStreamColor();

  return (
    <div
      className={`live-data-streams ${className}`}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        minHeight: "150px",
      }}
    >
      <canvas
        ref={canvasRef}
        style={{
          width: "100%",
          height: "100%",
          filter: `drop-shadow(0 0 20px ${color}40)`,
        }}
      />
      <div
        className="streams-overlay"
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(ellipse at center, transparent 30%, rgba(11, 18, 32, 0.8) 100%)`,
          pointerEvents: "none",
        }}
      />
      <div
        className="streams-label"
        style={{
          position: "absolute",
          bottom: "8px",
          right: "12px",
          fontSize: "10px",
          color: `${color}80`,
          textTransform: "uppercase",
          letterSpacing: "2px",
          fontWeight: 600,
        }}
      >
        Live Data Streams
      </div>
    </div>
  );
}
