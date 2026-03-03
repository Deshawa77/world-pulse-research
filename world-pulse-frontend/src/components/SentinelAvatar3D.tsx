import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

interface SentinelAvatar3DProps {
  isSpeaking?: boolean;
  threatLevel?: "stable" | "guarded" | "elevated" | "critical";
  className?: string;
  modelUrl?: string;
  modelYawOffsetDeg?: number;
  isProcessing?: boolean;
}

const resolvePublicAssetUrl = (url: string) => {
  if (/^(https?:)?\/\//i.test(url) || url.startsWith("data:") || url.startsWith("blob:")) {
    return url;
  }
  const base = import.meta.env.BASE_URL || "/";
  const normalizedBase = base.endsWith("/") ? base : `${base}/`;
  return `${normalizedBase}${url.replace(/^\/+/, "")}`;
};

const orientModelForFrontalView = (model: THREE.Object3D) => {
  const initialBox = new THREE.Box3().setFromObject(model);
  const initialSize = initialBox.getSize(new THREE.Vector3());

  if (initialSize.z > initialSize.y * 1.2) {
    model.rotateX(-Math.PI / 2);
  }

  const centerBox = new THREE.Box3().setFromObject(model);
  const center = centerBox.getCenter(new THREE.Vector3());
  model.position.sub(center);

  const originalQuat = model.quaternion.clone();
  const yawCandidates = [0, Math.PI / 2, Math.PI, -Math.PI / 2];
  let bestYaw = 0;
  let bestScore = -Infinity;
  for (const yaw of yawCandidates) {
    model.quaternion.copy(originalQuat);
    model.rotateY(yaw);
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3());
    const score = size.x / Math.max(size.z, 0.0001);
    if (score > bestScore) {
      bestScore = score;
      bestYaw = yaw;
    }
  }
  model.quaternion.copy(originalQuat);
  model.rotateY(bestYaw);

  const frontalBox = new THREE.Box3().setFromObject(model);
  const protrusionX = frontalBox.max.x - Math.abs(frontalBox.min.x);
  const protrusionZ = frontalBox.max.z - Math.abs(frontalBox.min.z);
  const absX = Math.abs(protrusionX);
  const absZ = Math.abs(protrusionZ);

  if (absX > absZ * 1.15) {
    model.rotateY(protrusionX >= 0 ? -Math.PI / 2 : Math.PI / 2);
  } else if (protrusionZ < 0) {
    model.rotateY(Math.PI);
  }
};

export default function SentinelAvatar3D({
  isSpeaking = false,
  threatLevel = "stable",
  className = "",
  modelUrl = "/models/sentinel-scan.glb",
  modelYawOffsetDeg = 0,
  isProcessing = false,
}: SentinelAvatar3DProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const speakingRef = useRef(isSpeaking);
  const threatLevelRef = useRef(threatLevel);
  const isProcessingRef = useRef(isProcessing);

  useEffect(() => {
    speakingRef.current = isSpeaking;
  }, [isSpeaking]);

  useEffect(() => {
    threatLevelRef.current = threatLevel;
  }, [threatLevel]);

  useEffect(() => {
    isProcessingRef.current = isProcessing;
  }, [isProcessing]);

  const resolvedModelUrl = useMemo(() => resolvePublicAssetUrl(modelUrl), [modelUrl]);

  useEffect(() => {
    if (!hostRef.current || !canvasRef.current) return;

    const host = hostRef.current;
    const canvas = canvasRef.current;
    const width = host.clientWidth;
    const height = host.clientHeight;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 100);
    camera.position.set(0, 0.16, 1.55);

    const renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;

    // Brighter cool hologram lighting inspired by the reference projection
    const ambientLight = new THREE.AmbientLight(0xa9dfff, 0.85);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0xd8f3ff, 1.05);
    keyLight.position.set(2, 2.6, 2.2);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x8dd5ff, 0.72);
    fillLight.position.set(-2.5, 1.4, 1.4);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xb9ebff, 0.62);
    rimLight.position.set(0, 2.4, -2);
    scene.add(rimLight);

    const topLight = new THREE.PointLight(0xe5f9ff, 0.92, 4, 2);
    topLight.position.set(0, 1.7, 0.8);
    scene.add(topLight);

    const loader = new GLTFLoader();
    let model: THREE.Object3D | null = null;
    let initialScale = 1;
    const disposableGeometries: THREE.BufferGeometry[] = [];
    const animatedBaseMaterials: THREE.MeshStandardMaterial[] = [];
    const animatedWireMaterials: THREE.MeshBasicMaterial[] = [];

    const contentRoot = new THREE.Group();
    scene.add(contentRoot);

    const headGroup = new THREE.Group();
    contentRoot.add(headGroup);

    loader.load(
      resolvedModelUrl,
      (gltf) => {
        model = gltf.scene;
        
        // Orient model and apply offset
        orientModelForFrontalView(model);
        const yawOffsetRad = THREE.MathUtils.degToRad(modelYawOffsetDeg);
        model.rotateY(yawOffsetRad);

        const box = new THREE.Box3().setFromObject(model);
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        // Keep the head large but allow camera-fit pass to keep it inside the frame.
        initialScale = (1.0 / maxDim) * 1.08;
        model.scale.setScalar(initialScale);

        box.setFromObject(model);
        const center = box.getCenter(new THREE.Vector3());
        model.position.sub(center);
        // Push projection down so the crown stays inside frame while the neck is slightly clipped.
        model.position.y = -0.44;

        // Fit camera to keep the enlarged head fully inside the frame with small padding.
        const fittedBox = new THREE.Box3().setFromObject(model);
        const fittedSize = fittedBox.getSize(new THREE.Vector3());
        const halfV = THREE.MathUtils.degToRad(camera.fov * 0.5);
        const halfH = Math.atan(Math.tan(halfV) * camera.aspect);
        const distForHeight = (fittedSize.y * 0.5) / Math.tan(halfV);
        const distForWidth = (fittedSize.x * 0.5) / Math.tan(halfH);
        const fitDistance = Math.max(distForHeight, distForWidth) * 1.12;
        camera.position.z = THREE.MathUtils.clamp(fitDistance, 1.35, 2.15);
        camera.near = 0.05;
        camera.far = 40;
        camera.lookAt(0, 0.14, 0);
        camera.updateProjectionMatrix();

        headGroup.add(model);

        model.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            const mesh = child as THREE.Mesh;
            
            if (Array.isArray(mesh.material)) {
              mesh.material = mesh.material.map((mat) => {
                if (mat instanceof THREE.MeshStandardMaterial) {
                  const clonedMat = mat.clone();
                  clonedMat.color = new THREE.Color(0xd4f3ff);
                  clonedMat.transparent = true;
                  clonedMat.opacity = 0.66;
                  clonedMat.roughness = 0.22;
                  clonedMat.metalness = 0.05;
                  clonedMat.depthWrite = true;
                  clonedMat.blending = THREE.NormalBlending;
                  clonedMat.emissive = new THREE.Color(0x7bd6ff);
                  clonedMat.emissiveIntensity = 0.36;
                  animatedBaseMaterials.push(clonedMat);
                  return clonedMat;
                }
                return mat;
              });
            } else if (mesh.material instanceof THREE.MeshStandardMaterial) {
              const mat = mesh.material as THREE.MeshStandardMaterial;
              const clonedMat = mat.clone();
               clonedMat.color = new THREE.Color(0xd4f3ff);
               clonedMat.transparent = true;
               clonedMat.opacity = 0.66;
               clonedMat.roughness = 0.22;
               clonedMat.metalness = 0.05;
               clonedMat.depthWrite = true;
               clonedMat.blending = THREE.NormalBlending;
               clonedMat.emissive = new THREE.Color(0x7bd6ff);
               clonedMat.emissiveIntensity = 0.36;
               animatedBaseMaterials.push(clonedMat);
               mesh.material = clonedMat;
            } else if (mesh.material instanceof THREE.MeshBasicMaterial) {
              const mat = mesh.material as THREE.MeshBasicMaterial;
              const clonedMat = mat.clone();
               clonedMat.color = new THREE.Color(0xc4f0ff);
               clonedMat.transparent = true;
               clonedMat.opacity = 0.24;
               clonedMat.blending = THREE.AdditiveBlending;
               clonedMat.depthWrite = false;
               animatedWireMaterials.push(clonedMat);
               mesh.material = clonedMat;
            }

            if (mesh.geometry) {
              disposableGeometries.push(mesh.geometry);
            }
          }
        });
      },
      undefined,
      () => {
        setLoadFailed(true);
      }
    );

    // Create subtle holographic base platform (integrated with existing style)
    const baseGeometry = new THREE.CylinderGeometry(0.48, 0.56, 0.015, 32);
    const baseMaterial = new THREE.MeshStandardMaterial({
      color: 0x101a29,
      emissive: 0x89e2ff,
      emissiveIntensity: 0.62,
      transparent: true,
      opacity: 0.7,
      metalness: 0.9,
      roughness: 0.1,
    });
    const basePlatform = new THREE.Mesh(baseGeometry, baseMaterial);
    basePlatform.position.y = -0.7;
    scene.add(basePlatform);
    animatedBaseMaterials.push(baseMaterial);

    // Create subtle data ring effects (integrated holographic rings)
    const ringGroup = new THREE.Group();
    scene.add(ringGroup);
    const ringMaterials: THREE.MeshBasicMaterial[] = [];
    
    for (let i = 0; i < 2; i++) {
      const ringGeometry = new THREE.TorusGeometry(0.47 + i * 0.14, 0.002, 8, 48);
      const ringMaterial = new THREE.MeshBasicMaterial({
        color: 0x00aacc,
        transparent: true,
         opacity: 0.2 + i * 0.08,
      });
      const ring = new THREE.Mesh(ringGeometry, ringMaterial);
      ring.rotation.x = Math.PI / 2;
       ring.position.y = -0.66 + i * 0.04;
      ringGroup.add(ring);
      ringMaterials.push(ringMaterial);
    }

    // Create subtle data particles (data reading effect - more subtle)
    const particleCount = 60;
    const particleGeometry = new THREE.BufferGeometry();
    const particlePositions = new Float32Array(particleCount * 3);
    const particleSizes = new Float32Array(particleCount);
    
    for (let i = 0; i < particleCount; i++) {
      const angle = Math.random() * Math.PI * 2;
      const radius = 0.6 + Math.random() * 0.4;
      particlePositions[i * 3] = Math.cos(angle) * radius;
      particlePositions[i * 3 + 1] = (Math.random() - 0.5) * 1.0;
      particlePositions[i * 3 + 2] = Math.sin(angle) * radius - 0.2;
      particleSizes[i] = Math.random() * 2 + 0.5;
    }
    
    particleGeometry.setAttribute("position", new THREE.BufferAttribute(particlePositions, 3));
    particleGeometry.setAttribute("size", new THREE.BufferAttribute(particleSizes, 1));
    
    const particleMaterial = new THREE.PointsMaterial({
      color: 0x00ccff,
      size: 0.012,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });
    
    const dataParticles = new THREE.Points(particleGeometry, particleMaterial);
    scene.add(dataParticles);

    // Create subtle scanning beam effect (more integrated)
    const scanLineGeometry = new THREE.PlaneGeometry(0.68, 0.003);
    const scanLineMaterial = new THREE.MeshBasicMaterial({
      color: 0x00ddff,
      transparent: true,
      opacity: 0.25,
      side: THREE.DoubleSide,
    });
    const scanLine = new THREE.Mesh(scanLineGeometry, scanLineMaterial);
    scanLine.position.z = 0.32;
    scanLine.position.y = 0.2;
    scene.add(scanLine);

    // Eye glow effect (subtle)
    const eyeGlowGeometry = new THREE.SphereGeometry(0.025, 12, 12);
    const eyeGlowMaterial = new THREE.MeshBasicMaterial({
      color: 0x00eeff,
      transparent: true,
      opacity: 0.5,
    });
    const eyeGlow = new THREE.Mesh(eyeGlowGeometry, eyeGlowMaterial);
    eyeGlow.position.set(0, 0.12, 0.3);
    scene.add(eyeGlow);

    // Processing indicator light (subtle)
    const processingLightGeometry = new THREE.SphereGeometry(0.015, 8, 8);
    const processingLightMaterial = new THREE.MeshBasicMaterial({
      color: 0xff8844,
      transparent: true,
      opacity: 0,
    });
    const processingLight = new THREE.Mesh(processingLightGeometry, processingLightMaterial);
    processingLight.position.set(0.25, 0.25, 0.25);
    scene.add(processingLight);

    let raf: number;
    const startTime = performance.now();

    const getThreatTint = () => {
      switch (threatLevelRef.current) {
        case "critical": return new THREE.Color(0xff0033);
        case "elevated": return new THREE.Color(0xff6600);
        case "guarded": return new THREE.Color(0xffcc00);
        default: return new THREE.Color(0x00ff88);
      }
    };

    const animate = () => {
      const elapsed = (performance.now() - startTime) / 1000;
      
      // Head movement - subtle scanning like reading data
      if (model) {
        const headRotationY = Math.sin(elapsed * 0.6) * 0.08 + Math.sin(elapsed * 0.25) * 0.04;
        const headRotationX = Math.sin(elapsed * 0.4) * 0.03;
        headGroup.rotation.y = headRotationY;
        headGroup.rotation.x = headRotationX;
        
        // Very subtle breathing
        const breathe = Math.sin(elapsed * 1.0) * 0.006;
        model.scale.setScalar(initialScale * (1 + breathe));
      }

      // Camera subtle movement
       camera.position.x = Math.sin(elapsed * 0.2) * 0.016;
       camera.position.y = 0.16 + Math.sin(elapsed * 0.3) * 0.01;
       camera.lookAt(0, 0.14, 0);

      // Eye glow pulsation
      const eyePulse = 0.6 + Math.sin(elapsed * 2) * 0.3 + (speakingRef.current ? 0.2 : 0);
      eyeGlowMaterial.opacity = eyePulse;
      eyeGlow.scale.setScalar(1 + Math.sin(elapsed * 3) * 0.1);

      // Processing light - only active when processing
      if (isProcessingRef.current) {
        processingLightMaterial.opacity = 0.5 + Math.sin(elapsed * 8) * 0.4;
        processingLight.scale.setScalar(1 + Math.sin(elapsed * 6) * 0.3);
      } else {
        processingLightMaterial.opacity = Math.max(0, processingLightMaterial.opacity - 0.05);
      }

      // Data particles - ALWAYS ACTIVE for reading data effect
      dataParticles.material.opacity = 0.4 + Math.sin(elapsed * 1.5) * 0.2;
      
      const positions = dataParticles.geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < particleCount; i++) {
        const idx = i * 3;
        // Move particles toward center (data ingestion effect)
        positions[idx] += -positions[idx] * 0.008;
        positions[idx + 1] += -positions[idx + 1] * 0.008;
        positions[idx + 2] += -positions[idx + 2] * 0.008;
        
        // Add slight random movement
        positions[idx] += (Math.random() - 0.5) * 0.005;
        positions[idx + 1] += (Math.random() - 0.5) * 0.005;
        positions[idx + 2] += (Math.random() - 0.5) * 0.005;
        
        // Reset particles that get too close to center
        const dist = Math.sqrt(positions[idx]**2 + positions[idx+1]**2 + positions[idx+2]**2);
        if (dist < 0.15) {
          const angle = Math.random() * Math.PI * 2;
          const radius = 0.8 + Math.random() * 0.6;
          positions[idx] = Math.cos(angle) * radius;
          positions[idx + 1] = (Math.random() - 0.5) * 1.5;
          positions[idx + 2] = Math.sin(angle) * radius - 0.3;
        }
      }
      dataParticles.geometry.attributes.position.needsUpdate = true;

      // Data rings - ALWAYS ACTIVE
      for (let i = 0; i < ringMaterials.length; i++) {
        const ring = ringGroup.children[i] as THREE.Mesh;
        ring.rotation.z = elapsed * (0.2 + i * 0.1);
        
        const ringOpacity = 0.15 + Math.sin(elapsed * 1.2 + i) * 0.1;
        ringMaterials[i].opacity = ringOpacity;
      }

      // Scanning beam - ALWAYS ACTIVE
      scanLineMaterial.opacity = 0.15 + Math.sin(elapsed * 3) * 0.08;
      scanLine.position.x = Math.sin(elapsed * 0.6) * 0.2;
      scanLine.position.y = 0.12 + Math.sin(elapsed * 0.4) * 0.1;

      // Base platform glow
      const tint = getThreatTint();
      const speakingBoost = speakingRef.current ? 0.3 : 0;
      const pulseIntensity = 0.3 + Math.sin(elapsed * 2) * 0.1 * (1 + speakingBoost);
      baseMaterial.emissive = tint;
      baseMaterial.emissiveIntensity = pulseIntensity;

      // Content scale pulse when speaking
      const speakPulse = speakingRef.current ? 1 + Math.sin(elapsed * 4) * 0.02 : 1;
      contentRoot.scale.setScalar(speakPulse);

      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    };

    animate();

    const resizeObserver = new ResizeObserver(() => {
      const w = host.clientWidth;
      const h = host.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    resizeObserver.observe(host);

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      renderer.dispose();
      for (const geom of disposableGeometries) {
        geom.dispose();
      }
      for (const mat of animatedBaseMaterials) {
        mat.dispose();
      }
      for (const mat of animatedWireMaterials) {
        mat.dispose();
      }
      particleGeometry.dispose();
      particleMaterial.dispose();
      scanLineGeometry.dispose();
      scanLineMaterial.dispose();
      eyeGlowGeometry.dispose();
      eyeGlowMaterial.dispose();
      processingLightGeometry.dispose();
      processingLightMaterial.dispose();
      baseGeometry.dispose();
      baseMaterial.dispose();
      scene.clear();
    };
  }, [resolvedModelUrl, modelYawOffsetDeg]);

  return (
    <div ref={hostRef} className={`sentinel-avatar-3d ${className}`} style={{
      width: '100%',
      height: '100%',
      position: 'relative',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    }}>
      <canvas ref={canvasRef} style={{
        width: '100%',
        height: '100%',
        display: 'block',
      }} />
    </div>
  );
}
