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
  const HOLO_CORE_COLOR = 0xe9f8ff;
  const HOLO_EMISSIVE_COLOR = 0xa6e5ff;
  const HOLO_WIREFRAME_COLOR = 0xc8f1ff;

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
    camera.position.set(0, 0.08, 1.55);

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
    renderer.toneMappingExposure = 0.67;

    // Brighter cool hologram lighting inspired by the reference projection
    const ambientLight = new THREE.AmbientLight(0xbfdff6, 0.82);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0xeaf6ff, 0.94);
    keyLight.position.set(2, 2.6, 2.2);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0xa8d8f8, 0.72);
    fillLight.position.set(-2.5, 1.4, 1.4);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xcde9ff, 0.66);
    rimLight.position.set(0, 2.4, -2);
    scene.add(rimLight);

    const topLight = new THREE.PointLight(0xe9f8ff, 0.82, 4, 2);
    topLight.position.set(0, 1.7, 0.8);
    scene.add(topLight);

    const loader = new GLTFLoader();
    let model: THREE.Object3D | null = null;
    let initialScale = 1;
    const disposableGeometries: THREE.BufferGeometry[] = [];
    const animatedBaseMaterials: THREE.MeshStandardMaterial[] = [];
    const animatedWireMaterials: THREE.MeshBasicMaterial[] = [];
    const faceCoreMaterials: THREE.MeshStandardMaterial[] = [];
    const faceWireframeMaterials: THREE.MeshBasicMaterial[] = [];

    const contentRoot = new THREE.Group();
    scene.add(contentRoot);

    const headGroup = new THREE.Group();
    contentRoot.add(headGroup);
    setLoadFailed(false);

    const loadCandidates = Array.from(new Set([
      resolvedModelUrl,
      resolvePublicAssetUrl("/models/sentinel-scan.glb"),
      "/models/sentinel-scan.glb",
      "models/sentinel-scan.glb",
    ]));

    const applyLoadedModel = (gltf: { scene: THREE.Object3D }) => {
      setLoadFailed(false);
      model = gltf.scene;

      // Orient model and apply offset
      orientModelForFrontalView(model);
      const yawOffsetRad = THREE.MathUtils.degToRad(modelYawOffsetDeg);
      model.rotateY(yawOffsetRad);
      model.rotateX(THREE.MathUtils.degToRad(-5));

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
      camera.lookAt(0, 0.05, 0);
      camera.updateProjectionMatrix();

      headGroup.add(model);

      model.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          const mesh = child as THREE.Mesh;

          if (Array.isArray(mesh.material)) {
            mesh.material = mesh.material.map((mat) => {
              if (mat instanceof THREE.MeshStandardMaterial) {
                const clonedMat = mat.clone();
                clonedMat.color = new THREE.Color(HOLO_CORE_COLOR);
                clonedMat.transparent = true;
                clonedMat.opacity = 0.63;
                clonedMat.roughness = 0.16;
                clonedMat.metalness = 0.03;
                clonedMat.depthWrite = true;
                clonedMat.blending = THREE.NormalBlending;
                clonedMat.emissive = new THREE.Color(HOLO_EMISSIVE_COLOR);
                clonedMat.emissiveIntensity = 0.2;
                faceCoreMaterials.push(clonedMat);
                animatedBaseMaterials.push(clonedMat);
                return clonedMat;
              }
              return mat;
            });
          } else if (mesh.material instanceof THREE.MeshStandardMaterial) {
            const mat = mesh.material as THREE.MeshStandardMaterial;
            const clonedMat = mat.clone();
             clonedMat.color = new THREE.Color(HOLO_CORE_COLOR);
             clonedMat.transparent = true;
             clonedMat.opacity = 0.63;
             clonedMat.roughness = 0.16;
             clonedMat.metalness = 0.03;
             clonedMat.depthWrite = true;
             clonedMat.blending = THREE.NormalBlending;
             clonedMat.emissive = new THREE.Color(HOLO_EMISSIVE_COLOR);
             clonedMat.emissiveIntensity = 0.2;
             faceCoreMaterials.push(clonedMat);
             animatedBaseMaterials.push(clonedMat);
             mesh.material = clonedMat;
           } else if (mesh.material instanceof THREE.MeshBasicMaterial) {
            const mat = mesh.material as THREE.MeshBasicMaterial;
            const clonedMat = mat.clone();
             clonedMat.color = new THREE.Color(HOLO_WIREFRAME_COLOR);
             clonedMat.transparent = true;
              clonedMat.opacity = 0.2;
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
    };

    const tryLoadModel = (index: number) => {
      const candidateUrl = loadCandidates[index];
      loader.load(
        candidateUrl,
        applyLoadedModel,
        undefined,
        (error) => {
          console.error(
            `[SentinelAvatar3D] Failed to load model (attempt ${index + 1}/${loadCandidates.length}) from "${candidateUrl}"`,
            error
          );

          if (index + 1 < loadCandidates.length) {
            tryLoadModel(index + 1);
            return;
          }

          setLoadFailed(true);
        }
      );
    };

    tryLoadModel(0);

    // Create subtle holographic base platform (integrated with existing style)
    const baseGeometry = new THREE.CylinderGeometry(0.48, 0.56, 0.015, 32);
    const baseMaterial = new THREE.MeshStandardMaterial({
      color: 0x101a29,
      emissive: 0xb3ecff,
      emissiveIntensity: 0.36,
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
        color: 0x9edfff,
        transparent: true,
         opacity: 0.14 + i * 0.05,
      });
      const ring = new THREE.Mesh(ringGeometry, ringMaterial);
      ring.rotation.x = Math.PI / 2;
       ring.position.y = -0.66 + i * 0.04;
      ringGroup.add(ring);
      ringMaterials.push(ringMaterial);
    }

    // Create subtle data particles (data reading effect - more subtle)
    const particleCount = 110;
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
      color: 0xbcecff,
      size: 0.01,
      transparent: true,
      opacity: 0.28,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });
    
    const dataParticles = new THREE.Points(particleGeometry, particleMaterial);
    scene.add(dataParticles);

    // Create subtle scanning beam effect (more integrated)
    const scanLineGeometry = new THREE.PlaneGeometry(0.68, 0.003);
    const scanLineMaterial = new THREE.MeshBasicMaterial({
      color: 0xbbeeff,
      transparent: true,
      opacity: 0.16,
      side: THREE.DoubleSide,
    });
    const scanLine = new THREE.Mesh(scanLineGeometry, scanLineMaterial);
    scanLine.position.z = 0.32;
    scanLine.position.y = 0.2;
    scene.add(scanLine);

    const coreGlowGeometry = new THREE.SphereGeometry(0.34, 28, 28);
    const coreGlowMaterial = new THREE.MeshBasicMaterial({
      color: 0xe7f8ff,
      transparent: true,
      opacity: 0.08,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const coreGlow = new THREE.Mesh(coreGlowGeometry, coreGlowMaterial);
    coreGlow.position.set(0, 0.08, 0.08);
    headGroup.add(coreGlow);

    // Bottom-to-brain energy conduit.
    const energyColumnGeometry = new THREE.CylinderGeometry(0.026, 0.05, 1.04, 20, 1, true);
    const energyColumnMaterial = new THREE.MeshStandardMaterial({
      color: 0x49a9ff,
      emissive: 0x7cc5ff,
      emissiveIntensity: 0.18,
      transparent: true,
      opacity: 0.16,
      metalness: 0,
      roughness: 0.2,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const energyColumn = new THREE.Mesh(energyColumnGeometry, energyColumnMaterial);
    energyColumn.position.set(0, -0.2, 0.08);
    headGroup.add(energyColumn);

    const pulseNodeGeometry = new THREE.SphereGeometry(0.028, 16, 16);
    const pulseNodeMaterials: THREE.MeshBasicMaterial[] = [];
    const pulseNodes: THREE.Mesh[] = [];
    const pulseNodeOffsets = new Float32Array(5);
    for (let i = 0; i < 5; i++) {
      pulseNodeOffsets[i] = i / 5;
      const pulseMat = new THREE.MeshBasicMaterial({
        color: 0x95d6ff,
        transparent: true,
        opacity: 0.22,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const node = new THREE.Mesh(pulseNodeGeometry, pulseMat);
      node.position.set(0, -0.66, 0.08);
      pulseNodes.push(node);
      pulseNodeMaterials.push(pulseMat);
      headGroup.add(node);
    }

    const brainGlowGeometry = new THREE.SphereGeometry(0.09, 20, 20);
    const brainGlowMaterial = new THREE.MeshBasicMaterial({
      color: 0xb9e5ff,
      transparent: true,
      opacity: 0.05,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const brainGlow = new THREE.Mesh(brainGlowGeometry, brainGlowMaterial);
    brainGlow.position.set(0, 0.40, 0.1);
    headGroup.add(brainGlow);

    const dataBandGeometry = new THREE.PlaneGeometry(0.62, 0.02);
    const dataBandMaterial = new THREE.MeshBasicMaterial({
      color: 0xf2fbff,
      transparent: true,
      opacity: 0.14,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const dataBand = new THREE.Mesh(dataBandGeometry, dataBandMaterial);
    dataBand.position.set(0, 0.14, 0.34);
    scene.add(dataBand);

    // Processing indicator light (subtle)
    const processingLightGeometry = new THREE.SphereGeometry(0.015, 8, 8);
    const processingLightMaterial = new THREE.MeshBasicMaterial({
      color: 0xc2efff,
      transparent: true,
      opacity: 0,
    });
    const processingLight = new THREE.Mesh(processingLightGeometry, processingLightMaterial);
    processingLight.position.set(0.25, 0.25, 0.25);
    scene.add(processingLight);

    // Reference-style horizontal projection bars crossing the eye line.
    const bridgeBarGeometry = new THREE.PlaneGeometry(0.24, 0.012);
    const bridgeBarMaterial = new THREE.MeshBasicMaterial({
      color: 0xf4fcff,
      transparent: true,
      opacity: 0.16,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const leftBridgeBar = new THREE.Mesh(bridgeBarGeometry, bridgeBarMaterial);
    const rightBridgeBar = new THREE.Mesh(bridgeBarGeometry, bridgeBarMaterial.clone());
    leftBridgeBar.position.set(-0.15, 0.125, 0.34);
    rightBridgeBar.position.set(0.15, 0.125, 0.34);
    scene.add(leftBridgeBar);
    scene.add(rightBridgeBar);

    // Fine network particles inside the head volume.
    const faceNodeCount = 180;
    const faceNodeGeometry = new THREE.BufferGeometry();
    const faceNodePositions = new Float32Array(faceNodeCount * 3);
    for (let i = 0; i < faceNodeCount; i++) {
      faceNodePositions[i * 3] = (Math.random() - 0.5) * 0.48;
      faceNodePositions[i * 3 + 1] = (Math.random() - 0.5) * 0.82 + 0.03;
      faceNodePositions[i * 3 + 2] = (Math.random() - 0.5) * 0.34 + 0.08;
    }
    faceNodeGeometry.setAttribute("position", new THREE.BufferAttribute(faceNodePositions, 3));
    const faceNodeMaterial = new THREE.PointsMaterial({
      color: 0xeefdff,
      size: 0.006,
      transparent: true,
      opacity: 0.16,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    });
    const faceNodes = new THREE.Points(faceNodeGeometry, faceNodeMaterial);
    headGroup.add(faceNodes);

    // Large animated halo rings to make the avatar feel active and "thinking".
    const haloGroup = new THREE.Group();
    scene.add(haloGroup);
    const haloMaterials: THREE.MeshBasicMaterial[] = [];
    const haloRings: THREE.Mesh[] = [];
    for (let i = 0; i < 3; i++) {
      const haloGeometry = new THREE.TorusGeometry(0.76 + i * 0.09, 0.004, 10, 100);
      const haloMaterial = new THREE.MeshBasicMaterial({
        color: i === 1 ? 0xe9f7ff : 0x9fd6ff,
        transparent: true,
        opacity: 0.16 + i * 0.04,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const haloRing = new THREE.Mesh(haloGeometry, haloMaterial);
      haloRing.position.y = 0.05 + i * 0.03;
      haloRing.rotation.x = Math.PI * (0.46 + i * 0.08);
      haloRing.rotation.z = i * 0.5;
      haloGroup.add(haloRing);
      haloMaterials.push(haloMaterial);
      haloRings.push(haloRing);
    }

    // Vertical data streams around the head.
    const streamCount = 26;
    const streamGeometry = new THREE.BufferGeometry();
    const streamPositions = new Float32Array(streamCount * 3);
    const streamSpeed = new Float32Array(streamCount);
    const streamRadius = new Float32Array(streamCount);
    for (let i = 0; i < streamCount; i++) {
      const angle = (i / streamCount) * Math.PI * 2;
      const radius = 0.82 + Math.random() * 0.24;
      const y = -0.55 + Math.random() * 1.5;
      streamPositions[i * 3] = Math.cos(angle) * radius;
      streamPositions[i * 3 + 1] = y;
      streamPositions[i * 3 + 2] = Math.sin(angle) * radius;
      streamSpeed[i] = 0.16 + Math.random() * 0.18;
      streamRadius[i] = radius;
    }
    streamGeometry.setAttribute("position", new THREE.BufferAttribute(streamPositions, 3));
    const streamMaterial = new THREE.PointsMaterial({
      color: 0xaedfff,
      size: 0.02,
      transparent: true,
      opacity: 0.2,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    });
    const streams = new THREE.Points(streamGeometry, streamMaterial);
    scene.add(streams);

    // Sweeping orbital sparks.
    const orbCount = 42;
    const orbGeometry = new THREE.BufferGeometry();
    const orbPositions = new Float32Array(orbCount * 3);
    const orbAngles = new Float32Array(orbCount);
    const orbRadii = new Float32Array(orbCount);
    const orbOffsets = new Float32Array(orbCount);
    for (let i = 0; i < orbCount; i++) {
      orbAngles[i] = Math.random() * Math.PI * 2;
      orbRadii[i] = 0.9 + Math.random() * 0.35;
      orbOffsets[i] = (Math.random() - 0.5) * 0.7;
      orbPositions[i * 3] = Math.cos(orbAngles[i]) * orbRadii[i];
      orbPositions[i * 3 + 1] = orbOffsets[i];
      orbPositions[i * 3 + 2] = Math.sin(orbAngles[i]) * orbRadii[i];
    }
    orbGeometry.setAttribute("position", new THREE.BufferAttribute(orbPositions, 3));
    const orbMaterial = new THREE.PointsMaterial({
      color: 0xeefdff,
      size: 0.012,
      transparent: true,
      opacity: 0.24,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    });
    const orbitalSparks = new THREE.Points(orbGeometry, orbMaterial);
    scene.add(orbitalSparks);

    // Arc lightning trails between ring layers.
    const boltCount = 7;
    const boltPointCount = 6;
    const lightningGeometries: THREE.BufferGeometry[] = [];
    const lightningMaterials: THREE.LineBasicMaterial[] = [];
    const boltPhase = new Float32Array(boltCount);
    const boltPointPhase = new Float32Array(boltCount * boltPointCount);
    for (let i = 0; i < boltCount; i++) {
      const boltGeometry = new THREE.BufferGeometry();
      const boltPositions = new Float32Array(boltPointCount * 3);
      boltGeometry.setAttribute("position", new THREE.BufferAttribute(boltPositions, 3));
      const boltMaterial = new THREE.LineBasicMaterial({
        color: 0xeefdff,
        transparent: true,
        opacity: 0.06,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const bolt = new THREE.Line(boltGeometry, boltMaterial);
      scene.add(bolt);
      lightningGeometries.push(boltGeometry);
      lightningMaterials.push(boltMaterial);
      boltPhase[i] = Math.random() * Math.PI * 2;
      for (let p = 0; p < boltPointCount; p++) {
        boltPointPhase[i * boltPointCount + p] = Math.random() * Math.PI * 2;
      }
    }

    // Expanding shockwave pulses from the projection base.
    const shockwaveCount = 3;
    const shockwaveGeometries: THREE.RingGeometry[] = [];
    const shockwaveMaterials: THREE.MeshBasicMaterial[] = [];
    const shockwaves: THREE.Mesh[] = [];
    const shockwaveOffsets = [0, 0.33, 0.66];
    for (let i = 0; i < shockwaveCount; i++) {
      const shockGeom = new THREE.RingGeometry(0.24, 0.3, 64);
      const shockMat = new THREE.MeshBasicMaterial({
        color: 0xbcecff,
        transparent: true,
        opacity: 0.0,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const shock = new THREE.Mesh(shockGeom, shockMat);
      shock.rotation.x = Math.PI / 2;
      shock.position.y = -0.63;
      shock.position.z = 0.02;
      scene.add(shock);
      shockwaveGeometries.push(shockGeom);
      shockwaveMaterials.push(shockMat);
      shockwaves.push(shock);
    }

    let raf: number;
    const startTime = performance.now();
    const attentionTarget = new THREE.Vector2(0, 0);
    const attentionCurrent = new THREE.Vector2(0, 0);
    let nextSaccadeAt = 0.45 + Math.random() * 1.1;
    const headIntentPhase = Math.random() * Math.PI * 2;
    let smoothedThreatSpeed = 0.8;
    let smoothedThreatIntensity = 0.8;
    let smoothedCriticalSpike = 0;

    const animate = () => {
      const elapsed = (performance.now() - startTime) / 1000;
      const threatLevelNow = threatLevelRef.current;
      const baseThreatSpeedMul =
        threatLevelNow === "critical" ? 1.04 :
        threatLevelNow === "elevated" ? 0.9 :
        threatLevelNow === "guarded" ? 0.78 : 0.68;
      const baseThreatIntensityMul =
        threatLevelNow === "critical" ? 0.98 :
        threatLevelNow === "elevated" ? 0.88 :
        threatLevelNow === "guarded" ? 0.76 : 0.64;
      const criticalSpikeTarget = threatLevelNow === "critical"
        ? Math.pow(Math.max(0, Math.sin(elapsed * 1.7)), 2)
        : 0;
      smoothedCriticalSpike += (criticalSpikeTarget - smoothedCriticalSpike) * 0.08;

      const targetThreatSpeed = Math.min(baseThreatSpeedMul + smoothedCriticalSpike * 0.22, 1.16);
      const targetThreatIntensity = Math.min(baseThreatIntensityMul + smoothedCriticalSpike * 0.72, 1.25);
      smoothedThreatSpeed += (targetThreatSpeed - smoothedThreatSpeed) * 0.07;
      smoothedThreatIntensity += (targetThreatIntensity - smoothedThreatIntensity) * 0.06;
      const threatSpeedMul = smoothedThreatSpeed;
      const threatIntensityMul = smoothedThreatIntensity;
      let brainImpact = 0;

      // Living behavior: gaze shifts and saccades.
      if (elapsed >= nextSaccadeAt) {
        const saccadeScale = threatLevelNow === "critical" ? 0.05 : threatLevelNow === "elevated" ? 0.042 : 0.034;
        attentionTarget.set(
          (Math.random() - 0.5) * saccadeScale,
          (Math.random() - 0.5) * saccadeScale * 0.7
        );
        nextSaccadeAt = elapsed + (threatLevelNow === "critical" ? 0.2 : 0.35) + Math.random() * (threatLevelNow === "critical" ? 0.55 : 1.05);
      }
      attentionCurrent.lerp(attentionTarget, Math.min(0.12 + 0.03 * threatSpeedMul, 0.16));

      const pulseSpeed = (isProcessingRef.current ? 0.32 : 0.22) * threatSpeedMul;
      for (let i = 0; i < pulseNodes.length; i++) {
        const t = (elapsed * pulseSpeed + pulseNodeOffsets[i]) % 1;
        const y = -0.66 + t * 1.02;
        const swirl = elapsed * 2.6 + i * 1.7;
        pulseNodes[i].position.set(Math.sin(swirl) * 0.03, y, 0.08 + Math.cos(swirl * 0.9) * 0.025);
        const pulseBody = Math.max(0, 1 - Math.abs(t - 0.5) * 2);
        pulseNodes[i].scale.setScalar(0.75 + pulseBody * 0.9);
        pulseNodeMaterials[i].opacity = (0.13 + pulseBody * 0.32) * threatIntensityMul;
        if (t > 0.83) {
          brainImpact = Math.max(brainImpact, (t - 0.83) / 0.17);
        }
      }
      const processBoost = isProcessingRef.current ? 0.08 : 0;
      energyColumnMaterial.opacity = (0.12 + Math.sin(elapsed * 1.4 * threatSpeedMul) * 0.03 + processBoost) * threatIntensityMul;
      energyColumnMaterial.emissiveIntensity = 0.14 + brainImpact * 0.85 + (isProcessingRef.current ? 0.2 : 0);
      brainGlowMaterial.opacity = (0.06 + brainImpact * 0.46 + processBoost) * threatIntensityMul;
      brainGlow.scale.setScalar(1 + brainImpact * 0.65);
      
      // Head movement - subtle scanning like reading data
      if (model) {
        const headMotionMul = Math.min(threatSpeedMul, 1.05);
        const headRotationY = Math.sin(elapsed * 0.9 * headMotionMul) * 0.12 + Math.sin(elapsed * 0.45 * headMotionMul) * 0.05;
        const headRotationX = -0.01 + Math.sin(elapsed * 0.65 * headMotionMul) * 0.02;
        const intentYaw = attentionCurrent.x * 1.4;
        const intentPitch = attentionCurrent.y * 1.05 + Math.sin(elapsed * 0.32 + headIntentPhase) * 0.004;
        headGroup.rotation.y = headRotationY + intentYaw;
        headGroup.rotation.x = headRotationX + intentPitch;
        
        // Very subtle breathing
        const breathe = Math.sin(elapsed * 1.35 * threatSpeedMul) * 0.01;
        model.scale.setScalar(initialScale * (1 + breathe));
      }

      for (let i = 0; i < faceCoreMaterials.length; i++) {
        const flicker = 0.105 + Math.sin(elapsed * 2.7 * threatSpeedMul + i * 0.09) * 0.035;
        faceCoreMaterials[i].emissiveIntensity = flicker + brainImpact * 0.32 + (speakingRef.current ? 0.055 : 0);
      }

      for (let i = 0; i < faceWireframeMaterials.length; i++) {
        faceWireframeMaterials[i].opacity = 0.1 + Math.sin(elapsed * 1.6 + i * 0.14) * 0.04;
      }

      // Camera subtle movement
       camera.position.x = Math.sin(elapsed * 0.14) * 0.012;
       camera.position.y = 0.08 + Math.sin(elapsed * 0.22) * 0.006;
       camera.lookAt(0, 0.05, 0);

      coreGlowMaterial.opacity = 0.034 + Math.sin(elapsed * 1.6 * threatSpeedMul) * 0.012 + brainImpact * 0.1 + (speakingRef.current ? 0.02 : 0);

      dataBand.position.x = Math.sin(elapsed * 0.95 * threatSpeedMul) * 0.11;
      dataBandMaterial.opacity = 0.09 + Math.sin(elapsed * 2.8 * threatSpeedMul) * 0.035;
      bridgeBarMaterial.opacity = 0.095 + Math.sin(elapsed * 3.6 * threatSpeedMul) * 0.03;
      (rightBridgeBar.material as THREE.MeshBasicMaterial).opacity = bridgeBarMaterial.opacity;
      leftBridgeBar.scale.x = 0.95 + Math.sin(elapsed * 2.4 * threatSpeedMul) * 0.04;
      rightBridgeBar.scale.x = 0.95 + Math.sin(elapsed * 2.4 * threatSpeedMul + 0.65) * 0.04;

      // Processing light - only active when processing
      if (isProcessingRef.current) {
        processingLightMaterial.opacity = 0.28 + Math.sin(elapsed * 9 * threatSpeedMul) * 0.2;
        processingLight.scale.setScalar(1 + Math.sin(elapsed * 7 * threatSpeedMul) * 0.2);
      } else {
        processingLightMaterial.opacity = Math.max(0, processingLightMaterial.opacity - 0.05);
      }

      // Data particles - ALWAYS ACTIVE for reading data effect
      dataParticles.material.opacity = (0.24 + Math.sin(elapsed * 1.9 * threatSpeedMul) * 0.1) * threatIntensityMul;
      
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
      faceNodeMaterial.opacity = (0.12 + Math.sin(elapsed * 2.4 * threatSpeedMul) * 0.06 + (speakingRef.current ? 0.04 : 0)) * threatIntensityMul;

      // Data rings - ALWAYS ACTIVE
      for (let i = 0; i < ringMaterials.length; i++) {
        const ring = ringGroup.children[i] as THREE.Mesh;
        ring.rotation.z = elapsed * (0.2 + i * 0.1);
        
        const ringOpacity = (0.12 + Math.sin(elapsed * 1.2 * threatSpeedMul + i) * 0.08) * threatIntensityMul;
        ringMaterials[i].opacity = ringOpacity;
      }

      // Big surrounding halo animation.
      haloGroup.rotation.y = elapsed * 0.18 * Math.min(threatSpeedMul, 1.12);
      for (let i = 0; i < haloRings.length; i++) {
        const ringSpeedMul = Math.min(threatSpeedMul, 1.15);
        haloRings[i].rotation.y += (0.0015 + i * 0.001) * ringSpeedMul;
        haloRings[i].rotation.z += ((i % 2 === 0 ? 1 : -1) * 0.0012) * ringSpeedMul;
        haloMaterials[i].opacity = (0.1 + Math.sin(elapsed * threatSpeedMul * (1.1 + i * 0.33) + i) * 0.08) * threatIntensityMul;
      }

      // Vertical stream animation.
      const streamArr = streams.geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < streamCount; i++) {
        const idx = i * 3;
        streamArr[idx + 1] += streamSpeed[i] * 0.012 * threatSpeedMul;
        if (streamArr[idx + 1] > 0.98) {
          streamArr[idx + 1] = -0.62;
        }
        const swirl = elapsed * threatSpeedMul * (0.36 + i * 0.003);
        streamArr[idx] = Math.cos(swirl + i * 0.38) * streamRadius[i];
        streamArr[idx + 2] = Math.sin(swirl + i * 0.38) * streamRadius[i];
      }
      streams.geometry.attributes.position.needsUpdate = true;
      streamMaterial.opacity = (0.1 + Math.sin(elapsed * 1.8 * threatSpeedMul) * 0.05) * threatIntensityMul;

      // Orbital sparks.
      const orbArr = orbitalSparks.geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < orbCount; i++) {
        orbAngles[i] += (0.007 + i * 0.00004) * threatSpeedMul;
        const idx = i * 3;
        orbArr[idx] = Math.cos(orbAngles[i]) * orbRadii[i];
        orbArr[idx + 1] = orbOffsets[i] + Math.sin(elapsed * 1.8 * threatSpeedMul + i * 0.4) * 0.08;
        orbArr[idx + 2] = Math.sin(orbAngles[i]) * orbRadii[i];
      }
      orbitalSparks.geometry.attributes.position.needsUpdate = true;
      orbMaterial.opacity = (0.14 + Math.sin(elapsed * 2.6 * threatSpeedMul) * 0.05) * threatIntensityMul;

      // Arc lightning update.
      for (let b = 0; b < boltCount; b++) {
        const boltGeometry = lightningGeometries[b];
        const boltMaterial = lightningMaterials[b];
        const boltPos = boltGeometry.attributes.position.array as Float32Array;
        const a = elapsed * threatSpeedMul * 1.6 + boltPhase[b];
        const startRadius = 0.76 + (b % 2) * 0.09;
        const endRadius = 0.94;
        const startY = 0.04 + (b % 3) * 0.03;
        const endY = 0.08 + ((b + 1) % 3) * 0.04;
        const startX = Math.cos(a) * startRadius;
        const startZ = Math.sin(a) * startRadius;
        const endX = Math.cos(a + 0.42) * endRadius;
        const endZ = Math.sin(a + 0.42) * endRadius;

        for (let p = 0; p < boltPointCount; p++) {
          const t = p / (boltPointCount - 1);
          const idx = p * 3;
          const jitter = (0.016 + (1 - t) * 0.01) * threatIntensityMul;
          const phase = boltPointPhase[b * boltPointCount + p];
          const wobble = elapsed * threatSpeedMul * 6.2 + phase;
          const jx = Math.sin(wobble) * jitter * 0.55;
          const jy = Math.cos(wobble * 1.17) * jitter * 0.42;
          const jz = Math.sin(wobble * 0.83 + 1.2) * jitter * 0.55;
          boltPos[idx] = THREE.MathUtils.lerp(startX, endX, t) + jx;
          boltPos[idx + 1] = THREE.MathUtils.lerp(startY, endY, t) + jy;
          boltPos[idx + 2] = THREE.MathUtils.lerp(startZ, endZ, t) + jz;
        }
        boltGeometry.attributes.position.needsUpdate = true;
        const flash = Math.max(0, Math.sin(elapsed * threatSpeedMul * 9 + boltPhase[b] * 2.3));
        boltMaterial.opacity = (0.02 + flash * 0.17) * threatIntensityMul;
      }

      // Expanding shockwave pulses.
      for (let i = 0; i < shockwaveCount; i++) {
        const t = (elapsed * 0.42 * threatSpeedMul + shockwaveOffsets[i]) % 1;
        const scale = 0.45 + t * 1.9;
        shockwaves[i].scale.setScalar(scale);
        shockwaveMaterials[i].opacity = Math.max(0, (1 - t) * (1 - t) * 0.14 * threatIntensityMul);
      }

      // Scanning beam - ALWAYS ACTIVE
      scanLineMaterial.opacity = (0.11 + Math.sin(elapsed * 3 * threatSpeedMul) * 0.06) * threatIntensityMul;
      scanLine.position.x = Math.sin(elapsed * 0.6 * threatSpeedMul) * 0.2;
      scanLine.position.y = 0.12 + Math.sin(elapsed * 0.4 * threatSpeedMul) * 0.1;

      // Base platform glow
      const speakingBoost = speakingRef.current ? 0.3 : 0;
      const pulseIntensity = (0.21 + Math.sin(elapsed * 2 * threatSpeedMul) * 0.07 * (1 + speakingBoost)) * threatIntensityMul;
      baseMaterial.emissive = new THREE.Color(0xbcecff);
      baseMaterial.emissiveIntensity = pulseIntensity * 0.42;

      // Content scale pulse when speaking
      const speakPulse = speakingRef.current ? 1 + Math.sin(elapsed * 4 * threatSpeedMul) * 0.02 : 1;
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
      coreGlowGeometry.dispose();
      coreGlowMaterial.dispose();
      dataBandGeometry.dispose();
      dataBandMaterial.dispose();
      processingLightGeometry.dispose();
      processingLightMaterial.dispose();
      bridgeBarGeometry.dispose();
      bridgeBarMaterial.dispose();
      (rightBridgeBar.material as THREE.Material).dispose();
      faceNodeGeometry.dispose();
      faceNodeMaterial.dispose();
      energyColumnGeometry.dispose();
      energyColumnMaterial.dispose();
      pulseNodeGeometry.dispose();
      for (const mat of pulseNodeMaterials) {
        mat.dispose();
      }
      brainGlowGeometry.dispose();
      brainGlowMaterial.dispose();
      for (const ring of haloRings) {
        ((ring.geometry) as THREE.BufferGeometry).dispose();
      }
      for (const mat of haloMaterials) {
        mat.dispose();
      }
      for (const geom of lightningGeometries) {
        geom.dispose();
      }
      for (const mat of lightningMaterials) {
        mat.dispose();
      }
      for (const geom of shockwaveGeometries) {
        geom.dispose();
      }
      for (const mat of shockwaveMaterials) {
        mat.dispose();
      }
      streamGeometry.dispose();
      streamMaterial.dispose();
      orbGeometry.dispose();
      orbMaterial.dispose();
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
      {loadFailed && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "radial-gradient(circle at center, rgba(37, 73, 112, 0.24), rgba(6, 12, 22, 0.7))",
            color: "#b7dcff",
            fontSize: "0.82rem",
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            border: "1px solid rgba(122, 192, 255, 0.2)",
            pointerEvents: "none",
          }}
        >
          3D signal unavailable
        </div>
      )}
    </div>
  );
}
