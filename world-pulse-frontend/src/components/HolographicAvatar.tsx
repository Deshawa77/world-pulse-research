import { useEffect, useRef, useState } from "react";

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
  
  // JARVIS/FRIDAY-style color palette
  const getHologramColor = () => {
    switch (threatLevel) {
      case "critical": return { 
        primary: "#ff3366", 
        secondary: "#ff6b6b",
        glow: "rgba(255, 51, 102, 0.8)",
        core: "#ff1744"
      };
      case "elevated": return { 
        primary: "#ff9500", 
        secondary: "#ffb74d",
        glow: "rgba(255, 149, 0, 0.8)",
        core: "#ff6f00"
      };
      case "guarded": return { 
        primary: "#ffd600", 
        secondary: "#ffea00",
        glow: "rgba(255, 214, 0, 0.8)",
        core: "#ffab00"
      };
      default: return { 
        primary: "#00e0ff", 
        secondary: "#00b8d4",
        glow: "rgba(0, 224, 255, 0.8)",
        core: "#00d4ff"
      };
    }
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let time = 0;
    const particles: Array<{
      x: number;
      y: number;
      z: number;
      vx: number;
      vy: number;
      vz: number;
      size: number;
      connections: number[];
    }> = [];
    
    // Initialize particle cloud
    const initParticles = () => {
      particles.length = 0;
      for (let i = 0; i < 80; i++) {
        particles.push({
          x: (Math.random() - 0.5) * 200,
          y: (Math.random() - 0.5) * 250,
          z: (Math.random() - 0.5) * 100,
          vx: (Math.random() - 0.5) * 0.3,
          vy: (Math.random() - 0.5) * 0.3,
          vz: (Math.random() - 0.5) * 0.2,
          size: Math.random() * 2 + 1,
          connections: [],
        });
      }
    };
    initParticles();

    const draw = () => {
      const width = canvas.width;
      const height = canvas.height;
      const color = getHologramColor();
      
      // Clear with fade effect
      ctx.fillStyle = "rgba(11, 18, 32, 0.15)";
      ctx.fillRect(0, 0, width, height);
      
      const centerX = width / 2;
      const centerY = height / 2;
      
      ctx.save();
      ctx.translate(centerX, centerY);
      
      // === JARVIS-STYLE CORE ORB ===
      const pulseIntensity = isSpeaking ? 1.2 : 1 + Math.sin(time * 0.05) * 0.15;
      
      // Outer glow rings
      for (let i = 3; i >= 0; i--) {
        const ringRadius = 60 + i * 25 + Math.sin(time * 0.03 + i) * 5;
        const alpha = (0.3 - i * 0.06) * pulseIntensity;
        
        const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, ringRadius);
        gradient.addColorStop(0, `rgba(0, 224, 255, 0)`);
        gradient.addColorStop(0.5, `${color.glow.replace('0.8', String(alpha))}`);
        gradient.addColorStop(1, `rgba(0, 224, 255, 0)`);
        
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(0, 0, ringRadius, 0, Math.PI * 2);
        ctx.fill();
      }
      
      // Core energy orb
      const coreGradient = ctx.createRadialGradient(0, 0, 0, 0, 0, 45);
      coreGradient.addColorStop(0, `rgba(255, 255, 255, ${0.9 * pulseIntensity})`);
      coreGradient.addColorStop(0.3, `${color.primary}`);
      coreGradient.addColorStop(0.6, `${color.secondary}`);
      coreGradient.addColorStop(1, `rgba(0, 224, 255, 0)`);
      
      ctx.fillStyle = coreGradient;
      ctx.shadowBlur = 40 * pulseIntensity;
      ctx.shadowColor = color.primary;
      ctx.beginPath();
      ctx.arc(0, 0, 45, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
      
      // Inner core pulse
      const innerPulse = 20 + Math.sin(time * 0.08) * 5;
      ctx.fillStyle = `rgba(255, 255, 255, ${0.6 * pulseIntensity})`;
      ctx.beginPath();
      ctx.arc(0, 0, innerPulse, 0, Math.PI * 2);
      ctx.fill();
      
      // === PARTICLE CLOUD / DATA MATRIX ===
      
      // Update and draw particles
      particles.forEach((p, i) => {
        // Update position with floating motion
        p.x += p.vx + Math.sin(time * 0.01 + i) * 0.1;
        p.y += p.vy + Math.cos(time * 0.012 + i) * 0.1;
        p.z += p.vz;
        
        // Boundary check - wrap around
        if (Math.abs(p.x) > 120) p.vx *= -1;
        if (Math.abs(p.y) > 150) p.vy *= -1;
        if (Math.abs(p.z) > 60) p.vz *= -1;
        
        // Calculate 3D projection
        const scale = 200 / (200 + p.z);
        const x2d = p.x * scale;
        const y2d = p.y * scale;
        const size = p.size * scale;
        
        // Draw particle
        const alpha = Math.max(0.2, scale * 0.8);
        ctx.fillStyle = `${color.primary.replace(')', `, ${alpha})`).replace('rgb', 'rgba')}`;
        ctx.beginPath();
        ctx.arc(x2d, y2d, size, 0, Math.PI * 2);
        ctx.fill();
        
        // Draw connections to nearby particles
        let connections = 0;
        particles.forEach((p2, j) => {
          if (i >= j || connections >= 3) return;
          
          const dx = p2.x - p.x;
          const dy = p2.y - p.y;
          const dz = p2.z - p.z;
          const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
          
          if (dist < 50) {
            connections++;
            const scale2 = 200 / (200 + p2.z);
            const x2d2 = p2.x * scale2;
            const y2d2 = p2.y * scale2;
            
            const lineAlpha = (1 - dist / 50) * 0.4 * scale * scale2;
            ctx.strokeStyle = `${color.secondary.replace(')', `, ${lineAlpha})`).replace('rgb', 'rgba')}`;
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(x2d, y2d);
            ctx.lineTo(x2d2, y2d2);
            ctx.stroke();
          }
        });
      });
      
      // === GEOMETRIC HOLOGRAPHIC SHAPES ===
      
      // Rotating hexagon frame
      ctx.strokeStyle = `${color.primary}`;
      ctx.lineWidth = 1.5;
      ctx.globalAlpha = 0.4;
      
      const hexRadius = 90 + Math.sin(time * 0.02) * 5;
      const rotation = time * 0.01;
      
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const angle = (i * Math.PI) / 3 + rotation;
        const x = Math.cos(angle) * hexRadius;
        const y = Math.sin(angle) * hexRadius;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
      
      // Inner rotating triangle
      const triRadius = 50 + Math.cos(time * 0.025) * 3;
      const triRotation = -time * 0.015;
      
      ctx.beginPath();
      for (let i = 0; i < 3; i++) {
        const angle = (i * Math.PI * 2) / 3 + triRotation;
        const x = Math.cos(angle) * triRadius;
        const y = Math.sin(angle) * triRadius;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
      
      ctx.globalAlpha = 1;
      
      // === ENERGY WAVES ===
      
      // Concentric wave rings
      for (let i = 0; i < 3; i++) {
        const waveRadius = 70 + i * 30 + (time * 0.5 + i * 20) % 40;
        const waveAlpha = 1 - ((time * 0.5 + i * 20) % 40) / 40;
        
        ctx.strokeStyle = `${color.primary.replace(')', `, ${waveAlpha * 0.3})`).replace('rgb', 'rgba')}`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(0, 0, waveRadius, 0, Math.PI * 2);
        ctx.stroke();
      }
      
      // === DATA STREAMS ===
      
      // Vertical data columns
      for (let i = -2; i <= 2; i++) {
        const colX = i * 35;
        const streamHeight = 80 + Math.sin(time * 0.05 + i) * 20;
        const streamY = -streamHeight / 2;
        
        // Data blocks
        for (let j = 0; j < 5; j++) {
          const blockY = streamY + j * 18;
          const blockAlpha = 0.3 + Math.sin(time * 0.1 + i + j) * 0.2;
          
          ctx.fillStyle = `${color.secondary.replace(')', `, ${blockAlpha})`).replace('rgb', 'rgba')}`;
          ctx.fillRect(colX - 3, blockY, 6, 8);
        }
      }
      
      // === THINKING INDICATOR ===
      
      if (isSpeaking) {
        // Waveform visualization
        ctx.strokeStyle = color.primary;
        ctx.lineWidth = 2;
        ctx.beginPath();
        
        for (let x = -80; x <= 80; x += 2) {
          const y = Math.sin((x + time * 3) * 0.1) * 15 * Math.sin(time * 0.2);
          if (x === -80) ctx.moveTo(x, 100 + y);
          else ctx.lineTo(x, 100 + y);
        }
        ctx.stroke();
        
        // Energy burst
        const burstRadius = 100 + Math.sin(time * 0.3) * 20;
        const burstGradient = ctx.createRadialGradient(0, 0, 50, 0, 0, burstRadius);
        burstGradient.addColorStop(0, `rgba(0, 224, 255, 0)`);
        burstGradient.addColorStop(0.5, `${color.glow.replace('0.8', '0.2')}`);
        burstGradient.addColorStop(1, `rgba(0, 224, 255, 0)`);
        
        ctx.fillStyle = burstGradient;
        ctx.beginPath();
        ctx.arc(0, 0, burstRadius, 0, Math.PI * 2);
        ctx.fill();
      }
      
      // === SCANNING EFFECT ===
      
      // Horizontal scan line
      const scanY = ((time * 2) % 300) - 150;
      ctx.strokeStyle = `rgba(0, 224, 255, 0.15)`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(-120, scanY);
      ctx.lineTo(120, scanY);
      ctx.stroke();
      
      // === HOLOGRAPHIC GLITCH ===
      
      if (Math.random() > 0.97) {
        ctx.fillStyle = `rgba(0, 224, 255, 0.1)`;
        const glitchY = (Math.random() - 0.5) * 200;
        ctx.fillRect(-100, glitchY - 2, 200, 4);
      }
      
      ctx.restore();
      
      time++;
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
        width={300}
        height={380}
        style={{
          filter: "drop-shadow(0 0 50px rgba(0, 224, 255, 0.5))",
        }}
      />
      <div 
        className="avatar-glow jarvis-glow"
        style={{
          position: "absolute",
          inset: "-50px",
          background: `radial-gradient(ellipse at center, ${color.glow} 0%, transparent 50%)`,
          pointerEvents: "none",
          animation: "jarvis-pulse 3s ease-in-out infinite",
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
            transparent 3px,
            rgba(0, 224, 255, 0.03) 3px,
            rgba(0, 224, 255, 0.03) 6px
          )`,
          pointerEvents: "none",
          mixBlendMode: "screen",
        }}
      />
    </div>
  );
}
