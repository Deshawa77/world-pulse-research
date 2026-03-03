import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import HolographicAvatar from "./HolographicAvatar";

interface ScannedHologramAvatarProps {
  isSpeaking?: boolean;
  threatLevel?: "stable" | "guarded" | "elevated" | "critical";
  className?: string;
  modelUrl?: string;
  modelYawOffsetDeg?: number;
  isProcessing?: boolean;
  isDataStreaming?: boolean;
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

  const finalBox = new THREE.Box3().setFromObject(model);
  const finalCenter = finalBox.getCenter(new THREE.Vector3());
  model.position.sub(finalCenter);
  return finalBox.getSize(new THREE.Vector3());
};

export default function ScannedHologramAvatar({
  isSpeaking = false,
  threatLevel = "stable",
  className = "",
  modelUrl = "/models/sentinel-scan.glb",
  modelYawOffsetDeg = 0,
  isProcessing = false,
  isDataStreaming = false,
}: ScannedHologramAvatarProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const resolvedModelUrl = useMemo(() => resolvePublicAssetUrl(modelUrl), [modelUrl]);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x111111);

    const renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;

    const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 20);
    camera.position.set(0, 0.15, 2.0);

    // Simple lighting
    const ambientLight = new THREE.AmbientLight(0x404040, 0.5);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0xffffff, 1.0);
    keyLight.position.set(1, 1, 1);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0xffffff, 0.5);
    fillLight.position.set(-1, 0, 1);
    scene.add(fillLight);

    const contentRoot = new THREE.Group();
    scene.add(contentRoot);

    const headRoot = new THREE.Group();
    contentRoot.add(headRoot);

    const loader = new GLTFLoader();
    const disposableGeometries: THREE.BufferGeometry[] = [];

    setLoadFailed(false);

    loader.load(
      resolvedModelUrl,
      (gltf) => {
        setLoadFailed(false);
        const model = gltf.scene;

        const size = orientModelForFrontalView(model);
        const referenceHeight = size.y > 0.0001 ? size.y : Math.max(size.x, size.z, 1);
        const yScale = 2.6 / referenceHeight;
        model.scale.setScalar(yScale);
        
        if (modelYawOffsetDeg !== 0) {
          model.rotateY(THREE.MathUtils.degToRad(modelYawOffsetDeg));
        }

        const scaledBox = new THREE.Box3().setFromObject(model);
        model.position.y += -0.6 - scaledBox.min.y;

        const fittedBox = new THREE.Box3().setFromObject(model);
        const fittedSphere = fittedBox.getBoundingSphere(new THREE.Sphere());
        if (Number.isFinite(fittedSphere.radius) && fittedSphere.radius > 0) {
          const fovRadians = THREE.MathUtils.degToRad(camera.fov);
          const fitDistance = fittedSphere.radius / Math.sin(fovRadians * 0.5);
          camera.position.z = Math.max(1.3, fitDistance * 0.85);
          camera.near = Math.max(0.01, fitDistance * 0.03);
          camera.far = Math.max(20, fitDistance * 8);
          camera.lookAt(0, 0.1, 0);
          camera.updateProjectionMatrix();
        }

        model.traverse((obj) => {
          if (!(obj instanceof THREE.Mesh)) return;

          const geom = obj.geometry.clone();
          geom.computeVertexNormals();
          obj.geometry = geom;
          disposableGeometries.push(geom);
          obj.frustumCulled = false;
        });

        headRoot.add(model);
      },
      undefined,
      (error) => {
        console.error(`Failed to load model at "${resolvedModelUrl}"`, error);
        setLoadFailed(true);
      },
    );

    const resize = () => {
      const rect = host.getBoundingClientRect();
      const w = Math.max(1, Math.floor(rect.width));
      const h = Math.max(1, Math.floor(rect.height));
      renderer.setSize(w, h, false);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();

    const observer = new ResizeObserver(() => resize());
    observer.observe(host);

    const clock = new THREE.Clock();
    let raf = 0;

    const animate = () => {
      const elapsed = clock.getElapsedTime();

      // Simple floating animation
      headRoot.rotation.y = Math.sin(elapsed * 0.1) * 0.02;
      headRoot.position.y = Math.sin(elapsed * 0.5) * 0.005;

      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      renderer.dispose();
      
      for (const geom of disposableGeometries) {
        geom.dispose();
      }
      
      scene.clear();
    };
  }, [modelYawOffsetDeg, resolvedModelUrl]);

  if (loadFailed) {
    return (
      <HolographicAvatar
        className={className}
        isSpeaking={isSpeaking}
        threatLevel={threatLevel}
      />
    );
  }

  return (
    <div ref={hostRef} className={`scan-avatar-host ${className}`}>
      <canvas ref={canvasRef} className="scan-avatar-canvas" />
    </div>
  );
}
