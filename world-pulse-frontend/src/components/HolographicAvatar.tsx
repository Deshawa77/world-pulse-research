import { useEffect, useRef } from "react";

interface HolographicAvatarProps {
  isSpeaking?: boolean;
  threatLevel?: "stable" | "guarded" | "elevated" | "critical";
  className?: string;
}

export default function HolographicAvatar({
  isSpeaking = false,
  threatLevel = "stable",
  className = "",
}: HolographicAvatarProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>(0);

  const getHologramColor = () => {
    switch (threatLevel) {
      case "critical":
        return {
          primary: "#c4e6ff",
          secondary: "#85cbff",
          glow: "rgba(154, 205, 255, 0.78)",
          core: "#ecf9ff",
        };
      case "elevated":
        return {
          primary: "#c9ebff",
          secondary: "#89d0ff",
          glow: "rgba(162, 212, 255, 0.79)",
          core: "#eefaff",
        };
      case "guarded":
        return {
          primary: "#cfeeff",
          secondary: "#92d4ff",
          glow: "rgba(172, 219, 255, 0.8)",
          core: "#f3fbff",
        };
      default:
        return {
          primary: "#d5f1ff",
          secondary: "#9cdeff",
          glow: "rgba(182, 227, 255, 0.82)",
          core: "#f7fdff",
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

    interface Node {
      x: number;
      y: number;
      anchorX: number;
      anchorY: number;
      size: number;
      depth: number;
      phase: number;
    }

    interface Stud {
      x: number;
      y: number;
      r: number;
      phase: number;
    }

    const nodes: Node[] = [];
    const edges: Array<{ a: number; b: number; base: number }> = [];
    const studs: Stud[] = [];

    const FACE = {
      headRadiusX: 96,
      headRadiusY: 138,
      headOffsetY: 20,
      jawStartY: 0.16,
      jawEndY: 1.12,
      jawBaseWidth: 0.69,
      jawTaper: 0.52,
      neckTop: 108,
      neckBottom: 176,
      neckHalfWidth: 25,
      earXMin: 74,
      earXMax: 112,
      earTop: -66,
      earBottom: 54,
    } as const;

    const inHeadMask = (x: number, y: number) => {
      const nx = x / FACE.headRadiusX;
      const ny = (y + FACE.headOffsetY) / FACE.headRadiusY;
      const skull = nx * nx + ny * ny <= 1;
      const jawWidth = FACE.jawBaseWidth - Math.max(0, ny - FACE.jawStartY) * FACE.jawTaper;
      const jaw = ny > FACE.jawStartY && ny < FACE.jawEndY && Math.abs(nx) <= jawWidth;
      const neck = y > FACE.neckTop && y < FACE.neckBottom && Math.abs(x) < FACE.neckHalfWidth;
      const leftEar = x > -FACE.earXMax && x < -FACE.earXMin && y > FACE.earTop && y < FACE.earBottom;
      const rightEar = x < FACE.earXMax && x > FACE.earXMin && y > FACE.earTop && y < FACE.earBottom;
      return (skull && (ny < 0.88 || jaw)) || neck || leftEar || rightEar;
    };

    const traceHeadPath = () => {
      ctx.beginPath();
      ctx.moveTo(0, -154);
      ctx.bezierCurveTo(68, -146, 108, -78, 104, -5);
      ctx.bezierCurveTo(100, 48, 82, 90, 62, 122);
      ctx.bezierCurveTo(40, 152, 22, 172, 12, 186);
      ctx.lineTo(-12, 186);
      ctx.bezierCurveTo(-22, 172, -40, 152, -62, 122);
      ctx.bezierCurveTo(-82, 90, -100, 48, -104, -5);
      ctx.bezierCurveTo(-108, -78, -68, -146, 0, -154);
      ctx.closePath();
    };

    const addNode = (x: number, y: number, depth: number, size: number, phase: number) => {
      nodes.push({
        x,
        y,
        anchorX: x,
        anchorY: y,
        size,
        depth,
        phase,
      });
    };

    const buildNodes = () => {
      nodes.length = 0;
      const target = 560;
      let attempts = 0;
      while (nodes.length < target && attempts < target * 22) {
        attempts += 1;
        const x = Math.random() * 116;
        const y = -170 + Math.random() * 368;
        if (!inHeadMask(x, y)) continue;
        const depth = 0.22 + Math.random() * 0.78;
        const size = 0.52 + Math.random() * 1.12;
        const phase = Math.random() * Math.PI * 2;
        addNode(x, y, depth, size, phase);
        if (Math.abs(x) > 2.5) {
          addNode(-x, y, depth, size, phase + Math.PI * 0.06);
        }
      }

      for (let i = 0; i < 24; i += 1) {
        const x = (Math.random() - 0.5) * 12;
        const y = -145 + Math.random() * 314;
        if (!inHeadMask(x, y)) continue;
        addNode(x, y, 0.4 + Math.random() * 0.5, 0.6 + Math.random() * 0.75, Math.random() * Math.PI * 2);
      }
    };

    const buildEdges = () => {
      edges.length = 0;
      const edgeSet = new Set<string>();

      for (let i = 0; i < nodes.length; i += 1) {
        const nearby: Array<{ j: number; d: number }> = [];
        for (let j = i + 1; j < nodes.length; j += 1) {
          const dx = nodes[i].anchorX - nodes[j].anchorX;
          const dy = nodes[i].anchorY - nodes[j].anchorY;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist > 7 && dist < 24) nearby.push({ j, d: dist });
        }

        nearby.sort((a, b) => a.d - b.d);
        for (let k = 0; k < Math.min(3, nearby.length); k += 1) {
          const j = nearby[k].j;
          const key = `${i}-${j}`;
          if (edgeSet.has(key)) continue;
          edgeSet.add(key);
          edges.push({ a: i, b: j, base: nearby[k].d });
        }
      }
    };

    const buildStuds = () => {
      studs.length = 0;
      const spacingX = 22;
      const spacingY = 22;
      for (let y = 12; y <= canvas.height - 12; y += spacingY) {
        for (let x = 12; x <= canvas.width - 12; x += spacingX) {
          studs.push({
            x: x + (Math.random() - 0.5) * 1.8,
            y: y + (Math.random() - 0.5) * 1.8,
            r: 3 + Math.random() * 1.2,
            phase: Math.random() * Math.PI * 2,
          });
        }
      }
    };

    buildNodes();
    buildEdges();
    buildStuds();

    const drawStudMatrix = () => {
      for (const stud of studs) {
        const glow = 0.1 + Math.sin(time * 0.03 + stud.phase) * 0.03;

        ctx.fillStyle = `rgba(42, 80, 132, ${0.3 + glow})`;
        ctx.beginPath();
        ctx.arc(stud.x + 0.8, stud.y + 1.2, stud.r + 0.8, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = `rgba(118, 176, 236, ${0.22 + glow})`;
        ctx.beginPath();
        ctx.arc(stud.x, stud.y, stud.r, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = "rgba(220, 245, 255, 0.33)";
        ctx.beginPath();
        ctx.arc(stud.x - stud.r * 0.32, stud.y - stud.r * 0.34, stud.r * 0.32, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const drawFlowLines = (color: ReturnType<typeof getHologramColor>) => {
      for (let i = 0; i < 8; i += 1) {
        const y = 52 + i * 26 + Math.sin(time * 0.02 + i) * 8;
        const alpha = 0.08 + Math.sin(time * 0.03 + i * 0.7) * 0.03;
        ctx.strokeStyle = hexToRgba(color.secondary, alpha);
        ctx.lineWidth = 1.1;

        ctx.beginPath();
        ctx.moveTo(-12, y);
        ctx.bezierCurveTo(58, y - 14, 96, y - 18, 152, y - 12);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(canvas.width + 12, y + 6);
        ctx.bezierCurveTo(canvas.width - 58, y - 8, canvas.width - 96, y - 12, canvas.width - 152, y - 6);
        ctx.stroke();
      }
    };

    const drawFacialContours = (color: ReturnType<typeof getHologramColor>, pulse: number) => {
      ctx.strokeStyle = hexToRgba(color.secondary, 0.38 * pulse);
      ctx.lineWidth = 1;

      ctx.beginPath();
      ctx.moveTo(-66, -18);
      ctx.quadraticCurveTo(-43, -34, -20, -27);
      ctx.moveTo(66, -18);
      ctx.quadraticCurveTo(43, -34, 20, -27);
      ctx.stroke();

      ctx.strokeStyle = hexToRgba(color.secondary, 0.32 * pulse);
      ctx.beginPath();
      ctx.moveTo(0, -44);
      ctx.quadraticCurveTo(-6, -8, -4, 18);
      ctx.moveTo(0, -44);
      ctx.quadraticCurveTo(6, -8, 4, 18);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(-12, 18);
      ctx.quadraticCurveTo(0, 27, 12, 18);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(-38, 58);
      ctx.quadraticCurveTo(0, 79, 38, 58);
      ctx.moveTo(-33, 64);
      ctx.quadraticCurveTo(0, 73, 33, 64);
      ctx.stroke();

      ctx.strokeStyle = hexToRgba(color.secondary, 0.26 * pulse);
      ctx.beginPath();
      ctx.ellipse(-88, -8, 12, 30, -0.2, 0, Math.PI * 2);
      ctx.ellipse(88, -8, 12, 30, 0.2, 0, Math.PI * 2);
      ctx.stroke();
    };

    const drawFace = (color: ReturnType<typeof getHologramColor>, pulse: number) => {
      ctx.save();
      ctx.translate(canvas.width / 2, canvas.height * 0.56);

      const auraGradient = ctx.createRadialGradient(0, -12, 14, 0, 2, 230);
      auraGradient.addColorStop(0, hexToRgba(color.primary, 0.29 * pulse));
      auraGradient.addColorStop(0.63, hexToRgba(color.secondary, 0.14 * pulse));
      auraGradient.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = auraGradient;
      ctx.beginPath();
      ctx.ellipse(0, 20, 150, 210, 0, 0, Math.PI * 2);
      ctx.fill();

      traceHeadPath();
      const shellGradient = ctx.createRadialGradient(0, -30, 18, 0, 8, 190);
      shellGradient.addColorStop(0, hexToRgba(color.core, 0.36 * pulse));
      shellGradient.addColorStop(0.35, hexToRgba(color.primary, 0.21 * pulse));
      shellGradient.addColorStop(0.7, hexToRgba(color.secondary, 0.11 * pulse));
      shellGradient.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = shellGradient;
      ctx.fill();

      ctx.fillStyle = hexToRgba(color.primary, 0.22);
      ctx.beginPath();
      ctx.ellipse(-97, -7, 16, 36, -0.18, 0, Math.PI * 2);
      ctx.ellipse(97, -7, 16, 36, 0.18, 0, Math.PI * 2);
      ctx.fill();

      ctx.save();
      traceHeadPath();
      ctx.clip();

      for (let y = -162; y <= 188; y += 12) {
        const alpha = 0.05 + (Math.sin(time * 0.018 + y * 0.03) + 1) * 0.022;
        ctx.strokeStyle = hexToRgba(color.secondary, alpha);
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.moveTo(-130, y);
        ctx.lineTo(130, y + Math.sin(time * 0.02 + y * 0.02) * 1.8);
        ctx.stroke();
      }

      for (let x = -126; x <= 126; x += 14) {
        const alpha = 0.03 + Math.cos(time * 0.015 + x * 0.04) * 0.012;
        ctx.strokeStyle = hexToRgba(color.primary, Math.max(0.015, alpha));
        ctx.lineWidth = 0.55;
        ctx.beginPath();
        ctx.moveTo(x, -168);
        ctx.lineTo(x + 6, 194);
        ctx.stroke();
      }

      for (const node of nodes) {
        const driftX = Math.sin(time * 0.014 + node.phase) * (0.5 + node.depth * 1.4);
        const driftY = Math.cos(time * 0.012 + node.phase * 1.07) * (0.45 + node.depth * 1.2);
        node.x = node.anchorX + driftX;
        node.y = node.anchorY + driftY;
      }

      ctx.lineWidth = 0.52;
      for (const edge of edges) {
        const a = nodes[edge.a];
        const b = nodes[edge.b];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const edgeAlpha = Math.max(0.02, 0.16 - Math.abs(dist - edge.base) * 0.02);
        const depthAlpha = (a.depth + b.depth) * 0.5;
        ctx.strokeStyle = hexToRgba(color.secondary, edgeAlpha * depthAlpha);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      for (const node of nodes) {
        const shimmer = 0.4 + Math.sin(time * 0.03 + node.phase) * 0.2;
        ctx.fillStyle = hexToRgba(color.primary, shimmer * node.depth);
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.size * (0.76 + node.depth * 0.42), 0, Math.PI * 2);
        ctx.fill();
      }

      const coreFog = ctx.createRadialGradient(0, 12, 24, 0, 28, 128);
      coreFog.addColorStop(0, hexToRgba(color.core, 0.24));
      coreFog.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = coreFog;
      ctx.beginPath();
      ctx.ellipse(0, 26, 76, 96, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();

      drawFacialContours(color, pulse);

      const eyeY = -19;
      const eyeOffset = 25;
      const eyePulse = 0.84 + Math.sin(time * 0.06) * 0.14;
      ctx.fillStyle = "rgba(240, 250, 255, 0.66)";
      ctx.beginPath();
      ctx.ellipse(-eyeOffset, eyeY, 8, 5.2, 0, 0, Math.PI * 2);
      ctx.ellipse(eyeOffset, eyeY, 8, 5.2, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = hexToRgba(color.primary, 0.46 * eyePulse);
      ctx.lineWidth = 1.7;
      ctx.beginPath();
      ctx.moveTo(-74, eyeY + 2);
      ctx.lineTo(-15, eyeY + 2);
      ctx.moveTo(15, eyeY + 2);
      ctx.lineTo(74, eyeY + 2);
      ctx.stroke();

      if (isSpeaking) {
        ctx.strokeStyle = hexToRgba(color.primary, 0.5);
        ctx.lineWidth = 1.15;
        ctx.beginPath();
        for (let x = -24; x <= 24; x += 2) {
          const y = 60 + Math.sin((x + time * 3.5) * 0.2) * 2;
          if (x === -24) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      const chinGlow = ctx.createRadialGradient(0, 118, 0, 0, 118, 34);
      chinGlow.addColorStop(0, hexToRgba(color.core, 0.44));
      chinGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = chinGlow;
      ctx.beginPath();
      ctx.arc(0, 118, 34, 0, Math.PI * 2);
      ctx.fill();

      const scanY = -164 + ((time * 1.34) % 350);
      const scanGradient = ctx.createLinearGradient(-138, scanY, 138, scanY);
      scanGradient.addColorStop(0, "rgba(0, 0, 0, 0)");
      scanGradient.addColorStop(0.5, hexToRgba(color.secondary, 0.32));
      scanGradient.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.strokeStyle = scanGradient;
      ctx.lineWidth = 1.05;
      ctx.beginPath();
      ctx.moveTo(-138, scanY);
      ctx.lineTo(138, scanY);
      ctx.stroke();

      ctx.restore();
    };

    const draw = () => {
      const color = getHologramColor();
      const width = canvas.width;
      const height = canvas.height;

      const bgGradient = ctx.createLinearGradient(0, 0, 0, height);
      bgGradient.addColorStop(0, "rgba(42, 92, 150, 0.45)");
      bgGradient.addColorStop(0.45, "rgba(30, 73, 126, 0.4)");
      bgGradient.addColorStop(1, "rgba(14, 36, 72, 0.52)");
      ctx.fillStyle = bgGradient;
      ctx.fillRect(0, 0, width, height);

      const fog = ctx.createRadialGradient(width * 0.5, height * 0.45, 30, width * 0.5, height * 0.45, width * 0.58);
      fog.addColorStop(0, "rgba(188, 227, 255, 0.13)");
      fog.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = fog;
      ctx.fillRect(0, 0, width, height);

      drawStudMatrix();
      drawFlowLines(color);

      const pulse = isSpeaking ? 1.12 : 1 + Math.sin(time * 0.04) * 0.06;
      drawFace(color, pulse);

      if (Math.random() > 0.986) {
        const y = 30 + Math.random() * (height - 60);
        ctx.fillStyle = hexToRgba(color.secondary, 0.09);
        ctx.fillRect(0, y, width, 2);
      }

      time += 1;
      animationRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(animationRef.current);
    };
  }, [isSpeaking, threatLevel]);

  const color = getHologramColor();

  return (
    <div className={`holographic-avatar jarvis-style ${className}`} style={{ position: "relative" }}>
      <canvas
        ref={canvasRef}
        width={420}
        height={320}
        style={{
          filter: "drop-shadow(0 0 48px rgba(170, 226, 255, 0.45))",
        }}
      />
      <div
        className="avatar-glow jarvis-glow"
        style={{
          position: "absolute",
          inset: "-34px -24px -42px",
          background: `radial-gradient(ellipse at center, ${color.glow} 0%, transparent 52%)`,
          pointerEvents: "none",
          animation: "jarvis-pulse 3.6s ease-in-out infinite",
        }}
      />
      <div
        className="holographic-overlay"
        style={{
          position: "absolute",
          inset: 0,
          background: `repeating-linear-gradient(
            0deg,
            transparent,
            transparent 5px,
            rgba(190, 232, 255, 0.02) 5px,
            rgba(190, 232, 255, 0.02) 8px
          )`,
          pointerEvents: "none",
          mixBlendMode: "screen",
        }}
      />
    </div>
  );
}
