import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

interface BrainModelViewerProps {
  className?: string;
  modelUrl?: string;
}

const PARTICLE_COLOR_1 = 0x12e7ff;
const PARTICLE_COLOR_2 = 0xff3cff;

const resolvePublicAssetUrl = (url: string) => {
  if (/^(https?:)?\/\//i.test(url) || url.startsWith("data:") || url.startsWith("blob:")) {
    return url;
  }

  const base = import.meta.env.BASE_URL || "/";
  const normalizedBase = base.endsWith("/") ? base : `${base}/`;
  return `${normalizedBase}${url.replace(/^\/+/, "")}`;
};

const resolveParticleColor = (meshName: string, materialName: string) => {
  const signature = `${meshName} ${materialName}`;
  if (signature.includes("Particle_1")) return PARTICLE_COLOR_1;
  if (signature.includes("Particle_2")) return PARTICLE_COLOR_2;
  return 0xffffff;
};

export default function BrainModelViewer({
  className = "",
  modelUrl = "/models/brain_hologram.glb",
}: BrainModelViewerProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [isInteracting, setIsInteracting] = useState(false);
  const resolvedModelUrl = useMemo(() => resolvePublicAssetUrl(modelUrl), [modelUrl]);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(0, 0.06, 2.05);

    const renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.NoToneMapping;
    renderer.setClearColor(0x000000, 0);

    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 1.25;
    controls.enablePan = false;
    controls.enableZoom = true;
    controls.zoomSpeed = 0.88;
    controls.rotateSpeed = 0.78;
    controls.minDistance = 1.0;
    controls.maxDistance = 4.8;
    controls.minPolarAngle = Math.PI * 0.22;
    controls.maxPolarAngle = Math.PI * 0.78;
    controls.target.set(0, 0.03, 0);
    controls.update();

    const handleStart = () => setIsInteracting(true);
    const handleEnd = () => setIsInteracting(false);
    controls.addEventListener("start", handleStart);
    controls.addEventListener("end", handleEnd);

    const root = new THREE.Group();
    scene.add(root);

    const modelRoot = new THREE.Group();
    modelRoot.rotation.x = THREE.MathUtils.degToRad(10);
    root.add(modelRoot);

    const baseRingGeometry = new THREE.TorusGeometry(1.02, 0.014, 16, 96);
    const baseRingMaterial = new THREE.MeshBasicMaterial({
      color: 0x27dfff,
      transparent: true,
      opacity: 0.1,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      toneMapped: false,
    });
    const baseRing = new THREE.Mesh(baseRingGeometry, baseRingMaterial);
    baseRing.rotation.x = Math.PI / 2;
    baseRing.position.y = -1.02;
    root.add(baseRing);

    const haloGeometry = new THREE.RingGeometry(0.68, 0.96, 96);
    const haloMaterial = new THREE.MeshBasicMaterial({
      color: 0xff4bff,
      transparent: true,
      opacity: 0.035,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
      toneMapped: false,
    });
    const halo = new THREE.Mesh(haloGeometry, haloMaterial);
    halo.position.y = 0.02;
    root.add(halo);

    const loader = new GLTFLoader();
    const disposableGeometries: THREE.BufferGeometry[] = [baseRingGeometry, haloGeometry];
    const disposableMaterials: THREE.Material[] = [baseRingMaterial, haloMaterial];
    let loadedModel: THREE.Object3D | null = null;

    setLoadFailed(false);

    loader.load(
      resolvedModelUrl,
      (gltf) => {
        setLoadFailed(false);
        const model = gltf.scene;
        loadedModel = model;

        const initialBox = new THREE.Box3().setFromObject(model);
        const center = initialBox.getCenter(new THREE.Vector3());
        model.position.sub(center);

        const size = initialBox.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z, 0.001);
        const scale = 1.92 / maxDim;
        model.scale.setScalar(scale);

        const fittedBox = new THREE.Box3().setFromObject(model);
        const fittedCenter = fittedBox.getCenter(new THREE.Vector3());
        model.position.sub(fittedCenter);
        model.position.y = -0.01;

        model.traverse((child) => {
          if (!(child instanceof THREE.Mesh)) return;

          const mesh = child as THREE.Mesh;
          mesh.geometry = mesh.geometry.clone();
          disposableGeometries.push(mesh.geometry);
          mesh.frustumCulled = false;

          const sourceMaterials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          const nextMaterials = sourceMaterials.map((material) => {
            disposableMaterials.push(material);

            const nextMaterial = new THREE.MeshBasicMaterial({
              color: resolveParticleColor(mesh.name, material.name),
              transparent: true,
              opacity: 0.96,
              blending: THREE.AdditiveBlending,
              depthWrite: false,
              toneMapped: false,
            });
            disposableMaterials.push(nextMaterial);
            return nextMaterial;
          });

          mesh.material = Array.isArray(mesh.material) ? nextMaterials : nextMaterials[0];
        });

        const sphere = new THREE.Box3().setFromObject(model).getBoundingSphere(new THREE.Sphere());
        if (Number.isFinite(sphere.radius) && sphere.radius > 0) {
          const fov = THREE.MathUtils.degToRad(camera.fov);
          const fitDistance = sphere.radius / Math.sin(fov * 0.5);
          camera.position.set(0, 0.08, THREE.MathUtils.clamp(fitDistance * 0.92, 1.28, 3.0));
          camera.near = Math.max(0.05, fitDistance * 0.035);
          camera.far = Math.max(20, fitDistance * 8);
          controls.minDistance = Math.max(0.9, fitDistance * 0.62);
          controls.maxDistance = Math.max(3.2, fitDistance * 2.15);
          controls.target.set(0, 0.03, 0);
          controls.update();
          camera.updateProjectionMatrix();
        }

        modelRoot.add(model);
      },
      undefined,
      (error) => {
        console.error(`Failed to load brain model at "${resolvedModelUrl}"`, error);
        setLoadFailed(true);
      },
    );

    const resize = () => {
      const rect = host.getBoundingClientRect();
      const width = Math.max(1, Math.floor(rect.width));
      const height = Math.max(1, Math.floor(rect.height));
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);

    const clock = new THREE.Clock();
    let raf = 0;

    const animate = () => {
      const elapsed = clock.getElapsedTime();

      modelRoot.position.y = Math.sin(elapsed * 1.2) * 0.03;
      baseRing.rotation.z = elapsed * 0.42;
      halo.rotation.z = -elapsed * 0.22;
      haloMaterial.opacity = 0.03 + Math.sin(elapsed * 1.3) * 0.01;
      controls.update();

      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      controls.removeEventListener("start", handleStart);
      controls.removeEventListener("end", handleEnd);
      controls.dispose();

      if (loadedModel) {
        modelRoot.remove(loadedModel);
      }

      renderer.dispose();
      for (const geometry of disposableGeometries) {
        geometry.dispose();
      }
      for (const material of disposableMaterials) {
        material.dispose();
      }
      scene.clear();
    };
  }, [resolvedModelUrl]);

  return (
    <div
      ref={hostRef}
      className={`brain-model-viewer ${isInteracting ? "is-interacting" : ""} ${className}`.trim()}
    >
      <canvas ref={canvasRef} className="brain-model-canvas" />
      {loadFailed && (
        <div className="brain-model-fallback">
          3D brain model unavailable
        </div>
      )}
    </div>
  );
}
