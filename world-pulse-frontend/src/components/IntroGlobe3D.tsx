import { useEffect, useRef } from "react";
import * as THREE from "three";

type IntroGlobe3DProps = {
  autoRotate?: boolean;
  rotationSpeed?: number;
  height?: number | string;
};

type GeoPoint = {
  lat: number;
  lon: number;
};

function seeded(seed: number): number {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
}

function latLonToVector3(lat: number, lon: number, radius: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  const x = -radius * Math.sin(phi) * Math.cos(theta);
  const z = radius * Math.sin(phi) * Math.sin(theta);
  const y = radius * Math.cos(phi);
  return new THREE.Vector3(x, y, z);
}

function gaussian(seedA: number, seedB: number): number {
  const u = Math.max(1e-8, seeded(seedA));
  const v = Math.max(1e-8, seeded(seedB));
  return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
}

function cityCenters(): Array<{ lat: number; lon: number; spread: number; weight: number }> {
  return [
    { lat: 35.6, lon: 139.7, spread: 2.6, weight: 1.0 },
    { lat: 31.2, lon: 121.4, spread: 3.0, weight: 1.0 },
    { lat: 22.3, lon: 114.1, spread: 2.4, weight: 0.95 },
    { lat: 13.7, lon: 100.5, spread: 3.2, weight: 0.75 },
    { lat: 1.3, lon: 103.8, spread: 2.2, weight: 0.65 },
    { lat: 28.6, lon: 77.2, spread: 3.6, weight: 0.82 },
    { lat: 19.1, lon: 72.8, spread: 3.8, weight: 0.8 },
    { lat: 24.8, lon: 67.0, spread: 3.5, weight: 0.62 },
    { lat: 25.2, lon: 55.2, spread: 2.8, weight: 0.5 },
    { lat: 30.0, lon: 31.2, spread: 2.9, weight: 0.48 },
    { lat: -6.2, lon: 106.8, spread: 4.4, weight: 0.75 },
    { lat: -1.2, lon: 36.8, spread: 3.1, weight: 0.42 },
    { lat: 6.5, lon: 3.3, spread: 3.7, weight: 0.5 },
    { lat: -26.2, lon: 28.0, spread: 3.4, weight: 0.5 },
    { lat: -33.9, lon: 151.2, spread: 3.4, weight: 0.45 },
    { lat: 37.5, lon: 126.9, spread: 2.8, weight: 0.8 },
  ];
}

function buildWeightedCenters() {
  const centers = cityCenters();
  const total = centers.reduce((sum, c) => sum + c.weight, 0);
  return { centers, total };
}

function pickCenter(seedValue: number, centers: ReturnType<typeof cityCenters>, totalWeight: number) {
  let cursor = seeded(seedValue) * totalWeight;
  for (const center of centers) {
    cursor -= center.weight;
    if (cursor <= 0) return center;
  }
  return centers[0];
}

function createGlowTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return new THREE.CanvasTexture(canvas);
  }

  const gradient = ctx.createRadialGradient(256, 256, 16, 256, 256, 245);
  gradient.addColorStop(0, "rgba(130, 210, 255, 0.82)");
  gradient.addColorStop(0.28, "rgba(70, 160, 255, 0.42)");
  gradient.addColorStop(0.58, "rgba(40, 95, 220, 0.2)");
  gradient.addColorStop(1, "rgba(0, 0, 0, 0)");

  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 512, 512);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export default function IntroGlobe3D({ autoRotate = true, rotationSpeed = 0.2, height = "100%" }: IntroGlobe3DProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
    camera.position.set(0, 0.12, 4.75);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    mount.appendChild(renderer.domElement);

    const resize = () => {
      if (!mount) return;
      const width = Math.max(1, mount.clientWidth);
      const h = Math.max(1, mount.clientHeight);
      camera.aspect = width / h;
      camera.updateProjectionMatrix();
      renderer.setSize(width, h, false);
    };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mount);
    resize();

    const globeRoot = new THREE.Group();
    const globeRadius = 0.8;
    scene.add(globeRoot);

    const ambient = new THREE.AmbientLight(0x7ab5ff, 0.32);
    scene.add(ambient);

    const keyLight = new THREE.DirectionalLight(0x70beff, 1.35);
    keyLight.position.set(-3.8, 1.6, 3.2);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x4a86e8, 0.48);
    fillLight.position.set(2.2, -1.0, 1.4);
    scene.add(fillLight);

    const earthGeometry = new THREE.SphereGeometry(globeRadius, 128, 128);
    const earthMaterial = new THREE.MeshStandardMaterial({
      color: 0x050f21,
      emissive: 0x071a38,
      emissiveIntensity: 0.32,
      roughness: 0.84,
      metalness: 0.06,
    });
    const earth = new THREE.Mesh(earthGeometry, earthMaterial);
    globeRoot.add(earth);

    const rimGeometry = new THREE.SphereGeometry(globeRadius * 1.03, 96, 96);
    const rimMaterial = new THREE.MeshBasicMaterial({
      color: 0x4ab8ff,
      transparent: true,
      opacity: 0.2,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      depthWrite: false,
    });
    const rim = new THREE.Mesh(rimGeometry, rimMaterial);
    globeRoot.add(rim);

    const auraTexture = createGlowTexture();
    const auraMaterial = new THREE.SpriteMaterial({
      map: auraTexture,
      color: 0x6abfff,
      transparent: true,
      opacity: 0.8,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const aura = new THREE.Sprite(auraMaterial);
    aura.scale.set(2.75, 2.75, 1);
    aura.position.set(-0.15, 0.2, -0.45);
    scene.add(aura);

    const { centers, total } = buildWeightedCenters();
    const cityCount = 1650;
    const cityPositions = new Float32Array(cityCount * 3);
    const cityColors = new Float32Array(cityCount * 3);

    for (let i = 0; i < cityCount; i++) {
      const center = pickCenter(i * 1.37 + 9.21, centers, total);
      const lat = center.lat + gaussian(i * 1.73 + 3.2, i * 2.11 + 7.8) * center.spread;
      const lon = center.lon + gaussian(i * 2.77 + 9.4, i * 1.17 + 11.3) * center.spread;
      const p = latLonToVector3(lat, lon, globeRadius * (1.004 + seeded(i * 3.21) * 0.012));
      cityPositions[i * 3] = p.x;
      cityPositions[i * 3 + 1] = p.y;
      cityPositions[i * 3 + 2] = p.z;

      const warm = seeded(i * 4.41);
      if (warm > 0.56) {
        cityColors[i * 3] = 1.0;
        cityColors[i * 3 + 1] = 0.79;
        cityColors[i * 3 + 2] = 0.58;
      } else {
        cityColors[i * 3] = 1.0;
        cityColors[i * 3 + 1] = 0.65;
        cityColors[i * 3 + 2] = 0.43;
      }
    }

    const cityGeometry = new THREE.BufferGeometry();
    cityGeometry.setAttribute("position", new THREE.BufferAttribute(cityPositions, 3));
    cityGeometry.setAttribute("color", new THREE.BufferAttribute(cityColors, 3));
    const cityMaterial = new THREE.PointsMaterial({
      size: 0.011,
      vertexColors: true,
      transparent: true,
      opacity: 0.95,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    });
    const cityPoints = new THREE.Points(cityGeometry, cityMaterial);
    globeRoot.add(cityPoints);

    const nodeCount = 90;
    const nodePoints: GeoPoint[] = [];
    for (let i = 0; i < nodeCount; i++) {
      nodePoints.push({ lat: -58 + seeded(i + 2.7) * 126, lon: -176 + seeded(i * 2.71) * 352 });
    }

    const nodePositions = new Float32Array(nodeCount * 3);
    for (let i = 0; i < nodeCount; i++) {
      const p = latLonToVector3(nodePoints[i].lat, nodePoints[i].lon, globeRadius * 1.03);
      nodePositions[i * 3] = p.x;
      nodePositions[i * 3 + 1] = p.y;
      nodePositions[i * 3 + 2] = p.z;
    }

    const nodeGeometry = new THREE.BufferGeometry();
    nodeGeometry.setAttribute("position", new THREE.BufferAttribute(nodePositions, 3));
    const nodeMaterial = new THREE.PointsMaterial({
      color: 0xb9e9ff,
      size: 0.012,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    });
    const nodeCloud = new THREE.Points(nodeGeometry, nodeMaterial);
    globeRoot.add(nodeCloud);

    const arcVertices: number[] = [];
    for (let i = 0; i < nodePoints.length; i++) {
      const from = nodePoints[i];
      const nearest: Array<{ idx: number; d: number }> = [];
      for (let j = 0; j < nodePoints.length; j++) {
        if (i === j) continue;
        const to = nodePoints[j];
        const dLat = from.lat - to.lat;
        const dLon = (from.lon - to.lon) * 0.7;
        nearest.push({ idx: j, d: dLat * dLat + dLon * dLon });
      }

      nearest.sort((a, b) => a.d - b.d);
      const links = 1 + Math.floor(seeded(i * 1.11) * 2);

      for (let k = 0; k < links; k++) {
        const n = nearest[k];
        if (!n || i > n.idx) continue;

        const a = latLonToVector3(from.lat, from.lon, globeRadius * 1.024);
        const b = latLonToVector3(nodePoints[n.idx].lat, nodePoints[n.idx].lon, globeRadius * 1.024);
        const mid = a
          .clone()
          .add(b)
          .multiplyScalar(0.5)
          .normalize()
          .multiplyScalar(globeRadius * (1.12 + seeded((i + 1) * (k + 2)) * 0.02));

        const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
        const samples = curve.getPoints(18);
        for (let p = 0; p < samples.length - 1; p++) {
          const s = samples[p];
          const e = samples[p + 1];
          arcVertices.push(s.x, s.y, s.z, e.x, e.y, e.z);
        }
      }
    }

    const arcGeometry = new THREE.BufferGeometry();
    arcGeometry.setAttribute("position", new THREE.Float32BufferAttribute(arcVertices, 3));
    const arcMaterial = new THREE.LineBasicMaterial({ color: 0xa5deff, transparent: true, opacity: 0.42, blending: THREE.AdditiveBlending });
    const arcs = new THREE.LineSegments(arcGeometry, arcMaterial);
    globeRoot.add(arcs);

    const starsCount = 900;
    const starPositions = new Float32Array(starsCount * 3);
    for (let i = 0; i < starsCount; i++) {
      const radius = 5.5 + seeded(i * 1.77) * 4.8;
      const theta = seeded(i * 2.91 + 0.8) * Math.PI * 2;
      const phi = Math.acos(2 * seeded(i * 3.47 + 2.2) - 1);
      starPositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      starPositions[i * 3 + 1] = radius * Math.cos(phi);
      starPositions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
    }

    const starGeometry = new THREE.BufferGeometry();
    starGeometry.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
    const starMaterial = new THREE.PointsMaterial({
      color: 0xb8ddff,
      size: 0.03,
      transparent: true,
      opacity: 0.88,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });
    const stars = new THREE.Points(starGeometry, starMaterial);
    scene.add(stars);

    globeRoot.rotation.y = -1.24;
    globeRoot.rotation.x = 0.11;
    globeRoot.position.y = 0.22;

    const clock = new THREE.Clock();
    let raf = 0;

    const animate = () => {
      const delta = clock.getDelta();
      if (autoRotate) {
        globeRoot.rotation.y += delta * rotationSpeed;
      }

      aura.material.opacity = 0.68 + Math.sin(clock.elapsedTime * 0.85) * 0.06;
      stars.rotation.y += delta * 0.01;

      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    };

    raf = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      mount.removeChild(renderer.domElement);

      earthGeometry.dispose();
      earthMaterial.dispose();
      rimGeometry.dispose();
      rimMaterial.dispose();
      cityGeometry.dispose();
      cityMaterial.dispose();
      nodeGeometry.dispose();
      nodeMaterial.dispose();
      arcGeometry.dispose();
      arcMaterial.dispose();
      starGeometry.dispose();
      starMaterial.dispose();
      auraTexture.dispose();
      auraMaterial.dispose();
      renderer.dispose();
    };
  }, [autoRotate, rotationSpeed]);

  return <div ref={mountRef} style={{ width: "100%", height }} />;
}
