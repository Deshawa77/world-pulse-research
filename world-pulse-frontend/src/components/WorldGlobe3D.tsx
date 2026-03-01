import { useEffect, useRef, useState, useMemo } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls";

interface CountryRisk {
  country: string;
  countryCode: string;
  risk: number;
  lat: number;
  lng: number;
}

interface WorldGlobe3DProps {
  data: CountryRisk[];
  onCountryClick?: (country: CountryRisk) => void;
  autoRotate?: boolean;
  height?: number;
}

// Country coordinates mapping (ISO3 code to lat/lng)
const COUNTRY_COORDS: Record<string, [number, number]> = {
  USA: [37.0902, -95.7129],
  CHN: [35.8617, 104.1954],
  RUS: [61.524, 105.3188],
  IND: [20.5937, 78.9629],
  BRA: [-14.235, -51.9253],
  CAN: [56.1304, -106.3468],
  AUS: [-25.2744, 133.7751],
  GBR: [55.3781, -3.436],
  FRA: [46.2276, 2.2137],
  DEU: [51.1657, 10.4515],
  ITA: [41.8719, 12.5674],
  ESP: [40.4637, -3.7492],
  JPN: [36.2048, 138.2529],
  KOR: [35.9078, 127.7669],
  MEX: [23.6345, -102.5528],
  IDN: [-0.7893, 113.9213],
  SAU: [23.8859, 45.0792],
  ZAF: [-30.5595, 22.9375],
  NGA: [9.082, 8.6753],
  EGY: [26.8206, 30.8025],
  TUR: [38.9637, 35.2433],
  IRN: [32.4279, 53.688],
  PAK: [30.3753, 69.3451],
  BGD: [23.685, 90.3563],
  RWA: [-1.9403, 29.8739],
  UKR: [48.3794, 31.1656],
  SYR: [34.8021, 38.9968],
  YEM: [15.5527, 48.5164],
  ET: [9.145, 40.4897],
};

function getCountryCoords(countryCode: string): [number, number] {
  return COUNTRY_COORDS[countryCode] || [0, 0];
}

export default function WorldGlobe3D({
  data,
  onCountryClick,
  autoRotate = true,
  height = 500,
}: WorldGlobe3DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const markersRef = useRef<THREE.Group | null>(null);
  const globeRef = useRef<THREE.Mesh | null>(null);
  const [hoveredCountry, setHoveredCountry] = useState<CountryRisk | null>(null);
  const animationRef = useRef<number>(0);

  // Create risk color gradient
  const getRiskColor = (risk: number): THREE.Color => {
    const normalizedRisk = Math.max(0, Math.min(100, risk)) / 100;
    if (normalizedRisk < 0.4) {
      return new THREE.Color(0x22c55e); // Green
    } else if (normalizedRisk < 0.7) {
      return new THREE.Color(0xfacc15); // Yellow
    } else {
      return new THREE.Color(0xef4444); // Red
    }
  };

  useEffect(() => {
    if (!containerRef.current) return;

    // Scene setup
    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(0x0a0a0f);

    // Camera
    const camera = new THREE.PerspectiveCamera(
      60,
      containerRef.current.clientWidth / height,
      0.1,
      1000
    );
    camera.position.z = 2.5;
    cameraRef.current = camera;

    // Renderer
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
    });
    renderer.setSize(containerRef.current.clientWidth, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    containerRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.enablePan = false;
    controls.minDistance = 1.5;
    controls.maxDistance = 5;
    controlsRef.current = controls;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0x404040, 0.5);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
    directionalLight.position.set(5, 3, 5);
    scene.add(directionalLight);

    const pointLight = new THREE.PointLight(0x00d4ff, 0.5, 10);
    pointLight.position.set(-2, 1, 2);
    scene.add(pointLight);

    // Create Globe (sphere with wireframe)
    const globeGeometry = new THREE.SphereGeometry(1, 64, 64);
    const globeMaterial = new THREE.MeshPhongMaterial({
      color: 0x1a1a2e,
      emissive: 0x0a0a1a,
      specular: 0x111111,
      shininess: 30,
      transparent: true,
      opacity: 0.9,
    });
    const globe = new THREE.Mesh(globeGeometry, globeMaterial);
    scene.add(globe);
    globeRef.current = globe;

    // Add wireframe overlay
    const wireframeGeometry = new THREE.SphereGeometry(1.002, 32, 32);
    const wireframeMaterial = new THREE.MeshBasicMaterial({
      color: 0x00d4ff,
      wireframe: true,
      transparent: true,
      opacity: 0.1,
    });
    const wireframe = new THREE.Mesh(wireframeGeometry, wireframeMaterial);
    scene.add(wireframe);

    // Add atmosphere glow
    const atmosphereGeometry = new THREE.SphereGeometry(1.05, 32, 32);
    const atmosphereMaterial = new THREE.ShaderMaterial({
      vertexShader: `
        varying vec3 vNormal;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec3 vNormal;
        void main() {
          float intensity = pow(0.7 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 2.0);
          gl_FragColor = vec4(0.0, 0.8, 1.0, 1.0) * intensity;
        }
      `,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true,
    });
    const atmosphere = new THREE.Mesh(atmosphereGeometry, atmosphereMaterial);
    scene.add(atmosphere);

    // Markers group
    const markersGroup = new THREE.Group();
    scene.add(markersGroup);
    markersRef.current = markersGroup;

    // Animation loop
    const animate = () => {
      animationRef.current = requestAnimationFrame(animate);

      if (autoRotate && globeRef.current) {
        globeRef.current.rotation.y += 0.001;
        wireframe.rotation.y += 0.001;
        atmosphere.rotation.y += 0.001;
      }

      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // Handle resize
    const handleResize = () => {
      if (!containerRef.current) return;
      const width = containerRef.current.clientWidth;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationRef.current);
      renderer.dispose();
      if (containerRef.current && renderer.domElement) {
        containerRef.current.removeChild(renderer.domElement);
      }
    };
  }, [autoRotate, height]);

  // Update markers when data changes
  useEffect(() => {
    if (!markersRef.current || !sceneRef.current) return;

    // Clear existing markers
    while (markersRef.current.children.length > 0) {
      const child = markersRef.current.children[0];
      markersRef.current.remove(child);
      if (child instanceof THREE.Mesh) {
        child.geometry.dispose();
        if (child.material instanceof THREE.Material) {
          child.material.dispose();
        }
      }
    }

    // Add new markers
    data.forEach((country) => {
      const [lat, lng] = getCountryCoords(country.countryCode);
      if (lat === 0 && lng === 0) return;

      // Convert lat/lng to 3D coordinates
      const phi = (90 - lat) * (Math.PI / 180);
      const theta = (lng + 180) * (Math.PI / 180);
      const radius = 1.01;

      const x = -radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.cos(phi);
      const z = radius * Math.sin(phi) * Math.sin(theta);

      // Create marker
      const markerGeometry = new THREE.SphereGeometry(0.02 + (country.risk / 100) * 0.03, 16, 16);
      const markerMaterial = new THREE.MeshBasicMaterial({
        color: getRiskColor(country.risk),
        transparent: true,
        opacity: 0.8,
      });
      const marker = new THREE.Mesh(markerGeometry, markerMaterial);
      marker.position.set(x, y, z);
      marker.userData = country;

      // Add glow effect
      const glowGeometry = new THREE.SphereGeometry(0.04 + (country.risk / 100) * 0.04, 16, 16);
      const glowMaterial = new THREE.MeshBasicMaterial({
        color: getRiskColor(country.risk),
        transparent: true,
        opacity: 0.3,
      });
      const glow = new THREE.Mesh(glowGeometry, glowMaterial);
      marker.add(glow);

      markersRef.current?.add(marker);
    });
  }, [data]);

  // Raycaster for hover detection
  const handleMouseMove = (event: React.MouseEvent) => {
    if (!containerRef.current || !cameraRef.current || !sceneRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const mouse = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1
    );

    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(mouse, cameraRef.current);

    if (markersRef.current) {
      const intersects = raycaster.intersectObjects(markersRef.current.children);
      if (intersects.length > 0) {
        const country = intersects[0].object.userData as CountryRisk;
        setHoveredCountry(country);
      } else {
        setHoveredCountry(null);
      }
    }
  };

  const handleClick = (event: React.MouseEvent) => {
    if (!containerRef.current || !cameraRef.current || !sceneRef.current || !onCountryClick) return;

    const rect = containerRef.current.getBoundingClientRect();
    const mouse = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1
    );

    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(mouse, cameraRef.current);

    if (markersRef.current) {
      const intersects = raycaster.intersectObjects(markersRef.current.children);
      if (intersects.length > 0) {
        const country = intersects[0].object.userData as CountryRisk;
        onCountryClick(country);
      }
    }
  };

  return (
    <div style={{ position: "relative", width: "100%", height }}>
      <div
        ref={containerRef}
        style={{ width: "100%", height: "100%", cursor: "grab" }}
        onMouseMove={handleMouseMove}
        onClick={handleClick}
      />
      
      {/* Hover tooltip */}
      {hoveredCountry && (
        <div
          style={{
            position: "absolute",
            top: "10px",
            left: "10px",
            background: "rgba(0, 0, 0, 0.8)",
            border: `1px solid ${getRiskColor(hoveredCountry.risk).getHexString()}`,
            borderRadius: "8px",
            padding: "12px",
            color: "#fff",
            fontSize: "14px",
            zIndex: 10,
            backdropFilter: "blur(10px)",
          }}
        >
          <div style={{ fontWeight: "bold", marginBottom: "4px" }}>
            {hoveredCountry.country}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span>Risk Score:</span>
            <span
              style={{
                color: getRiskColor(hoveredCountry.risk).getStyle(),
                fontWeight: "bold",
              }}
            >
              {hoveredCountry.risk.toFixed(1)}
            </span>
          </div>
        </div>
      )}

      {/* Legend */}
      <div
        style={{
          position: "absolute",
          bottom: "10px",
          right: "10px",
          background: "rgba(0, 0, 0, 0.7)",
          borderRadius: "8px",
          padding: "10px",
          fontSize: "12px",
          zIndex: 10,
        }}
      >
        <div style={{ color: "#888", marginBottom: "6px" }}>Risk Level</div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
          <div style={{ width: "12px", height: "12px", borderRadius: "50%", background: "#22c55e" }} />
          <span style={{ color: "#aaa" }}>Low (0-40)</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
          <div style={{ width: "12px", height: "12px", borderRadius: "50%", background: "#facc15" }} />
          <span style={{ color: "#aaa" }}>Medium (40-70)</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div style={{ width: "12px", height: "12px", borderRadius: "50%", background: "#ef4444" }} />
          <span style={{ color: "#aaa" }}>High (70-100)</span>
        </div>
      </div>
    </div>
  );
}
