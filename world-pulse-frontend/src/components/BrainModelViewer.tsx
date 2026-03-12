import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

interface BrainModelViewerProps {
  className?: string;
  modelUrl?: string;
}

interface LanePacket {
  mesh: THREE.Mesh;
  material: THREE.MeshBasicMaterial;
  speed: number;
  offset: number;
  phase: number;
  wobble: number;
}

interface IntakeLane {
  curve: THREE.CatmullRomCurve3;
  line: THREE.Line;
  material: THREE.LineBasicMaterial;
  packets: LanePacket[];
  phase: number;
}

interface IntakeParticleState {
  progress: number;
  speed: number;
  azimuth: number;
  polar: number;
  orbitSpeed: number;
  twist: number;
  phase: number;
  outerRadius: number;
  verticalScale: number;
  target: THREE.Vector3;
}

const PARTICLE_COLOR_1 = 0x12e7ff;
const PARTICLE_COLOR_2 = 0xff3cff;
const DATA_STREAM_COLOR = 0x69f5ff;
const DATA_STREAM_COLOR_ALT = 0xff74f7;
const DATA_PACKET_COLOR = 0xe7ffff;
const DATA_CORE_COLOR = 0x8ff7ff;
const DATA_LANE_COUNT = 6;
const DATA_FIELD_PARTICLE_COUNT = 132;

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

const createIntakeCurve = (index: number, total: number) => {
  const angle = (index / total) * Math.PI * 2;
  const startRadius = 1.54 + (index % 2) * 0.14;
  const midRadius = 1.08 + ((index + 1) % 3) * 0.08;
  const innerRadius = 0.46 + (index % 3) * 0.05;
  const verticalBias = (index % 2 === 0 ? 1 : -1) * (0.22 + (index % 3) * 0.04);

  return new THREE.CatmullRomCurve3(
    [
      new THREE.Vector3(
        Math.cos(angle) * startRadius,
        verticalBias * 0.9,
        Math.sin(angle) * startRadius * 0.78,
      ),
      new THREE.Vector3(
        Math.cos(angle + 0.34) * midRadius,
        verticalBias * 0.48 + 0.16,
        Math.sin(angle + 0.34) * midRadius * 0.74,
      ),
      new THREE.Vector3(
        Math.cos(angle + 0.78) * innerRadius,
        verticalBias * 0.22 - 0.04,
        Math.sin(angle + 0.78) * innerRadius * 0.62,
      ),
      new THREE.Vector3(
        Math.sin(angle * 1.6) * 0.08,
        verticalBias * 0.06,
        Math.cos(angle * 1.2) * 0.08,
      ),
    ],
    false,
    "catmullrom",
    0.5,
  );
};

const resetIntakeParticle = (state: IntakeParticleState, randomizeProgress = false) => {
  state.progress = randomizeProgress ? Math.random() : 0;
  state.speed = 0.22 + Math.random() * 0.34;
  state.azimuth = Math.random() * Math.PI * 2;
  state.polar = Math.PI * (0.18 + Math.random() * 0.64);
  state.orbitSpeed = 0.4 + Math.random() * 0.95;
  state.twist = 1.8 + Math.random() * 3.2;
  state.phase = Math.random() * Math.PI * 2;
  state.outerRadius = 1.18 + Math.random() * 0.62;
  state.verticalScale = 0.7 + Math.random() * 0.24;
  state.target.set(
    (Math.random() - 0.5) * 0.22,
    (Math.random() - 0.5) * 0.16,
    (Math.random() - 0.5) * 0.22,
  );
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

    const disposableGeometries: THREE.BufferGeometry[] = [];
    const disposableMaterials: THREE.Material[] = [];

    const baseRingGeometry = new THREE.TorusGeometry(1.02, 0.014, 16, 96);
    const baseRingMaterial = new THREE.MeshBasicMaterial({
      color: 0x27dfff,
      transparent: true,
      opacity: 0.1,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      toneMapped: false,
    });
    disposableGeometries.push(baseRingGeometry);
    disposableMaterials.push(baseRingMaterial);
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
    disposableGeometries.push(haloGeometry);
    disposableMaterials.push(haloMaterial);
    const halo = new THREE.Mesh(haloGeometry, haloMaterial);
    halo.position.y = 0.02;
    root.add(halo);

    // Build a lightweight intake field so the brain reads as if it is absorbing live signal traffic.
    const dataField = new THREE.Group();
    dataField.position.y = 0.03;
    dataField.rotation.x = THREE.MathUtils.degToRad(6);
    root.add(dataField);

    const dataLaneGroup = new THREE.Group();
    dataLaneGroup.position.y = 0.04;
    root.add(dataLaneGroup);

    const lanePacketGeometry = new THREE.SphereGeometry(0.024, 12, 12);
    const coreGlowGeometry = new THREE.SphereGeometry(0.22, 18, 18);
    const intakePulseGeometry = new THREE.RingGeometry(0.22, 0.58, 72);
    disposableGeometries.push(lanePacketGeometry, coreGlowGeometry, intakePulseGeometry);

    const coreGlowMaterial = new THREE.MeshBasicMaterial({
      color: DATA_CORE_COLOR,
      transparent: true,
      opacity: 0.12,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      toneMapped: false,
    });
    disposableMaterials.push(coreGlowMaterial);
    const coreGlow = new THREE.Mesh(coreGlowGeometry, coreGlowMaterial);
    coreGlow.position.set(0, 0.04, 0);
    dataField.add(coreGlow);

    const intakePulseMaterial = new THREE.MeshBasicMaterial({
      color: DATA_STREAM_COLOR,
      transparent: true,
      opacity: 0.08,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
      toneMapped: false,
    });
    disposableMaterials.push(intakePulseMaterial);
    const intakePulse = new THREE.Mesh(intakePulseGeometry, intakePulseMaterial);
    intakePulse.position.set(0, 0.04, 0);
    dataField.add(intakePulse);

    const intakeLanes: IntakeLane[] = [];
    for (let laneIndex = 0; laneIndex < DATA_LANE_COUNT; laneIndex += 1) {
      const curve = createIntakeCurve(laneIndex, DATA_LANE_COUNT);
      const lineGeometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(84));
      const lineMaterial = new THREE.LineBasicMaterial({
        color: laneIndex % 2 === 0 ? DATA_STREAM_COLOR : DATA_STREAM_COLOR_ALT,
        transparent: true,
        opacity: 0.12,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      });
      disposableGeometries.push(lineGeometry);
      disposableMaterials.push(lineMaterial);

      const line = new THREE.Line(lineGeometry, lineMaterial);
      dataLaneGroup.add(line);

      const packets: LanePacket[] = [];
      for (let packetIndex = 0; packetIndex < 2; packetIndex += 1) {
        const packetMaterial = new THREE.MeshBasicMaterial({
          color:
            packetIndex === 0
              ? DATA_PACKET_COLOR
              : laneIndex % 2 === 0
                ? DATA_STREAM_COLOR
                : DATA_STREAM_COLOR_ALT,
          transparent: true,
          opacity: 0.42,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          toneMapped: false,
        });
        disposableMaterials.push(packetMaterial);

        const mesh = new THREE.Mesh(lanePacketGeometry, packetMaterial);
        dataLaneGroup.add(mesh);

        packets.push({
          mesh,
          material: packetMaterial,
          speed: 0.16 + Math.random() * 0.18,
          offset: Math.random(),
          phase: Math.random() * Math.PI * 2,
          wobble: 0.02 + Math.random() * 0.04,
        });
      }

      intakeLanes.push({
        curve,
        line,
        material: lineMaterial,
        packets,
        phase: Math.random() * Math.PI * 2,
      });
    }

    const fieldParticleStates: IntakeParticleState[] = Array.from(
      { length: DATA_FIELD_PARTICLE_COUNT },
      () => ({
        progress: 0,
        speed: 0,
        azimuth: 0,
        polar: 0,
        orbitSpeed: 0,
        twist: 0,
        phase: 0,
        outerRadius: 0,
        verticalScale: 1,
        target: new THREE.Vector3(),
      }),
    );
    const fieldParticlePositions = new Float32Array(DATA_FIELD_PARTICLE_COUNT * 3);
    const fieldParticleColors = new Float32Array(DATA_FIELD_PARTICLE_COUNT * 3);
    const fieldParticleGeometry = new THREE.BufferGeometry();
    const fieldParticlePositionAttribute = new THREE.BufferAttribute(fieldParticlePositions, 3);
    fieldParticleGeometry.setAttribute("position", fieldParticlePositionAttribute);
    fieldParticleGeometry.setAttribute("color", new THREE.BufferAttribute(fieldParticleColors, 3));
    disposableGeometries.push(fieldParticleGeometry);

    const fieldParticleMaterial = new THREE.PointsMaterial({
      size: 0.03,
      vertexColors: true,
      transparent: true,
      opacity: 0.76,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
      toneMapped: false,
    });
    disposableMaterials.push(fieldParticleMaterial);
    const fieldParticles = new THREE.Points(fieldParticleGeometry, fieldParticleMaterial);
    fieldParticles.position.y = 0.02;
    dataField.add(fieldParticles);

    const intakeParticlePalette = [
      new THREE.Color(DATA_STREAM_COLOR),
      new THREE.Color(DATA_STREAM_COLOR_ALT),
      new THREE.Color(DATA_PACKET_COLOR),
    ];
    for (let index = 0; index < fieldParticleStates.length; index += 1) {
      resetIntakeParticle(fieldParticleStates[index], true);

      const color = intakeParticlePalette[index % intakeParticlePalette.length];
      const colorOffset = index * 3;
      fieldParticleColors[colorOffset] = color.r;
      fieldParticleColors[colorOffset + 1] = color.g;
      fieldParticleColors[colorOffset + 2] = color.b;
    }

    const loader = new GLTFLoader();
    let loadedModel: THREE.Object3D | null = null;
    let aborted = false;

    setLoadFailed(false);

    const applyLoadedModel = (gltf: { scene: THREE.Object3D }) => {
      if (aborted) return;
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
    };

    const verifyAndLoadModel = async () => {
      try {
        const response = await fetch(resolvedModelUrl, { method: "GET" });
        const contentType = response.headers.get("content-type") || "";
        if (!response.ok || contentType.includes("text/html")) {
          if (!aborted) {
            console.warn(`Brain model asset not found at "${resolvedModelUrl}".`);
            setLoadFailed(true);
          }
          return;
        }
      } catch {
        if (!aborted) {
          setLoadFailed(true);
        }
        return;
      }

      loader.load(
        resolvedModelUrl,
        applyLoadedModel,
        undefined,
        () => {
          if (!aborted) {
            setLoadFailed(true);
          }
        },
      );
    };

    void verifyAndLoadModel();

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
    const tempPoint = new THREE.Vector3();
    const tempOffset = new THREE.Vector3();
    let raf = 0;

    const animate = () => {
      const delta = Math.min(clock.getDelta(), 0.05);
      const elapsed = clock.elapsedTime;
      let arrivalEnergy = 0;

      modelRoot.position.y = Math.sin(elapsed * 1.2) * 0.03;
      modelRoot.rotation.y = Math.sin(elapsed * 0.24) * 0.08;
      dataField.position.y = 0.03 + modelRoot.position.y * 0.45;
      dataLaneGroup.position.y = 0.04 + modelRoot.position.y * 0.3;
      dataField.rotation.y = -elapsed * 0.08;
      dataLaneGroup.rotation.y = elapsed * 0.16;
      baseRing.rotation.z = elapsed * 0.42;
      baseRingMaterial.opacity = 0.08 + Math.sin(elapsed * 1.7) * 0.02;

      for (const lane of intakeLanes) {
        lane.line.rotation.z = Math.sin(elapsed * 0.6 + lane.phase) * 0.05;
        lane.material.opacity = 0.08 + (Math.sin(elapsed * 1.25 + lane.phase) + 1) * 0.03;

        for (const packet of lane.packets) {
          const cycle = (elapsed * packet.speed + packet.offset) % 1;
          const t = THREE.MathUtils.smootherstep(cycle, 0, 1);
          lane.curve.getPoint(t, tempPoint);

          tempOffset.set(
            Math.cos(elapsed * 2.8 + packet.phase) * packet.wobble * (1 - t),
            Math.sin(elapsed * 3.2 + packet.phase) * packet.wobble * 0.65 * (1 - t),
            Math.sin(elapsed * 2.1 + packet.phase) * packet.wobble * (1 - t),
          );

          packet.mesh.position.copy(tempPoint).add(tempOffset);
          packet.mesh.scale.setScalar(
            0.55 + (1 - t) * 1.1 + Math.sin(elapsed * 5.4 + packet.phase) * 0.08,
          );
          packet.material.opacity = 0.18 + (1 - t) * 0.42;

          arrivalEnergy += Math.max(0, t - 0.74) * 0.8;
        }
      }

      for (let index = 0; index < fieldParticleStates.length; index += 1) {
        const state = fieldParticleStates[index];
        state.progress += delta * state.speed;
        if (state.progress >= 1) {
          resetIntakeParticle(state);
        }

        const radiusBlend = 1 - state.progress;
        const orbitAngle = state.azimuth + elapsed * state.orbitSpeed + state.progress * state.twist;
        const sinPolar = Math.sin(state.polar);
        const positionOffset = index * 3;

        tempPoint.set(
          Math.cos(orbitAngle) * sinPolar * state.outerRadius,
          Math.cos(state.polar) * state.outerRadius * state.verticalScale +
            Math.sin(elapsed * 1.8 + state.phase) * 0.06 * radiusBlend,
          Math.sin(orbitAngle) * sinPolar * state.outerRadius * 0.82,
        );
        tempPoint.lerp(state.target, state.progress);
        tempPoint.x += Math.cos(elapsed * 2.4 + state.phase) * 0.045 * radiusBlend;
        tempPoint.z += Math.sin(elapsed * 2.0 + state.phase) * 0.045 * radiusBlend;

        fieldParticlePositions[positionOffset] = tempPoint.x;
        fieldParticlePositions[positionOffset + 1] = tempPoint.y;
        fieldParticlePositions[positionOffset + 2] = tempPoint.z;

        arrivalEnergy += Math.max(0, state.progress - 0.84) * 0.06;
      }
      fieldParticlePositionAttribute.needsUpdate = true;
      fieldParticles.rotation.y = elapsed * 0.14;
      fieldParticles.rotation.z = Math.sin(elapsed * 0.4) * 0.08;

      const coreEnergy = Math.min(arrivalEnergy / 6.5, 1.15);
      coreGlow.scale.setScalar(1 + Math.sin(elapsed * 2.9) * 0.08 + coreEnergy * 0.32);
      coreGlowMaterial.opacity = 0.08 + Math.sin(elapsed * 3.5) * 0.02 + coreEnergy * 0.18;
      intakePulse.lookAt(camera.position);
      intakePulse.scale.setScalar(1.06 + Math.sin(elapsed * 2.2) * 0.05 + coreEnergy * 0.42);
      intakePulseMaterial.opacity = 0.04 + coreEnergy * 0.14;
      halo.rotation.z = -elapsed * 0.22;
      haloMaterial.opacity = 0.03 + Math.sin(elapsed * 1.3) * 0.01 + coreEnergy * 0.025;
      controls.update();

      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      aborted = true;
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
