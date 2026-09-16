"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

interface FlowPath {
  curve: THREE.CatmullRomCurve3;
  pulse: THREE.Mesh;
  offset: number;
  speed: number;
}

const COLORS = {
  amber: 0xf0b35c,
  aqua: 0x66e3c4,
  blue: 0x57a7e8,
  coral: 0xed806f,
  dark: 0x07130f,
  green: 0x1d8f75,
  ink: 0x0d211b
};

function physical(
  color: number,
  options: Partial<THREE.MeshPhysicalMaterialParameters> = {}
) {
  return new THREE.MeshPhysicalMaterial({
    color,
    metalness: 0.54,
    roughness: 0.34,
    ...options
  });
}

function addEdges(mesh: THREE.Mesh, color: number, opacity = 0.32) {
  const outline = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry),
    new THREE.LineBasicMaterial({ color, opacity, transparent: true })
  );
  outline.position.copy(mesh.position);
  outline.rotation.copy(mesh.rotation);
  mesh.parent?.add(outline);
  return outline;
}

function createCampus() {
  const campus = new THREE.Group();

  const foundation = new THREE.Mesh(
    new THREE.CylinderGeometry(9.4, 10.2, 0.34, 6),
    physical(0x102b23, { metalness: 0.76, roughness: 0.48 })
  );
  foundation.position.y = -0.3;
  campus.add(foundation);

  const foundationRing = new THREE.Mesh(
    new THREE.TorusGeometry(8.35, 0.055, 8, 96),
    new THREE.MeshBasicMaterial({ color: COLORS.aqua, opacity: 0.38, transparent: true })
  );
  foundationRing.rotation.x = Math.PI / 2;
  foundationRing.position.y = -0.08;
  campus.add(foundationRing);

  const coreShell = new THREE.Mesh(
    new THREE.CylinderGeometry(2.15, 2.6, 7.8, 6, 1, true),
    physical(0x174f41, {
      emissive: COLORS.green,
      emissiveIntensity: 0.18,
      opacity: 0.18,
      side: THREE.DoubleSide,
      transparent: true,
      transmission: 0.48,
      depthWrite: false
    })
  );
  coreShell.position.y = 4;
  campus.add(coreShell);
  addEdges(coreShell, COLORS.aqua, 0.5);

  for (let level = 0; level < 5; level += 1) {
    const platform = new THREE.Mesh(
      new THREE.CylinderGeometry(2.38 - level * 0.08, 2.38 - level * 0.08, 0.12, 6),
      physical(0x163e34, {
        emissive: level % 2 === 0 ? COLORS.green : COLORS.blue,
        emissiveIntensity: 0.22,
        opacity: 0.88,
        transparent: true
      })
    );
    platform.position.y = 0.55 + level * 1.72;
    campus.add(platform);
  }

  const core = new THREE.Mesh(
    new THREE.OctahedronGeometry(1.05, 0),
    physical(COLORS.aqua, {
      emissive: COLORS.green,
      emissiveIntensity: 0.88,
      opacity: 0.86,
      transparent: true,
      transmission: 0.22
    })
  );
  core.position.y = 4.2;
  campus.add(core);
  addEdges(core, 0xe7fff8, 0.78);
  core.userData.role = "core";

  const orbitRings: THREE.Mesh[] = [];
  for (const [index, radius] of [3.2, 4.55, 6.3].entries()) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(radius, index === 0 ? 0.04 : 0.025, 7, 128),
      new THREE.MeshBasicMaterial({
        color: index === 2 ? COLORS.amber : COLORS.aqua,
        opacity: 0.18 + index * 0.07,
        transparent: true
      })
    );
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.03 + index * 0.06;
    ring.userData.phase = index * 0.42;
    campus.add(ring);
    orbitRings.push(ring);
  }

  const nodeColors = [COLORS.blue, COLORS.amber, COLORS.aqua, COLORS.coral, COLORS.blue, COLORS.aqua];
  const nodeHeights = [2.5, 3.2, 2.15, 2.85, 2.3, 3.45];
  const nodes: THREE.Vector3[] = [];
  for (let index = 0; index < 6; index += 1) {
    const angle = index / 6 * Math.PI * 2 + Math.PI / 6;
    const radius = index % 2 === 0 ? 6.25 : 7.05;
    const x = Math.cos(angle) * radius;
    const z = Math.sin(angle) * radius;
    const height = nodeHeights[index];
    const node = new THREE.Group();
    node.position.set(x, 0, z);
    node.rotation.y = -angle + Math.PI / 2;

    const base = new THREE.Mesh(
      new THREE.BoxGeometry(2.15, 0.22, 1.7),
      physical(0x16342d, { metalness: 0.66, roughness: 0.45 })
    );
    base.position.y = 0.02;
    node.add(base);

    const building = new THREE.Mesh(
      new THREE.BoxGeometry(1.65, height, 1.24),
      physical(0x173d34, {
        emissive: nodeColors[index],
        emissiveIntensity: 0.1,
        opacity: 0.44,
        transparent: true,
        transmission: 0.24
      })
    );
    building.position.y = height / 2 + 0.17;
    node.add(building);
    addEdges(building, nodeColors[index], 0.62);

    for (let floor = 1; floor < Math.ceil(height / 0.54); floor += 1) {
      const line = new THREE.Mesh(
        new THREE.BoxGeometry(1.72, 0.025, 1.3),
        new THREE.MeshBasicMaterial({ color: nodeColors[index], opacity: 0.35, transparent: true })
      );
      line.position.y = 0.2 + floor * 0.5;
      node.add(line);
    }

    const antenna = new THREE.Mesh(
      new THREE.BoxGeometry(0.055, 0.78, 0.055),
      new THREE.MeshBasicMaterial({ color: nodeColors[index] })
    );
    antenna.position.y = height + 0.68;
    node.add(antenna);
    campus.add(node);
    nodes.push(new THREE.Vector3(x, 0.35, z));
  }

  return { campus, core, nodes, orbitRings };
}

function createFlowPaths(nodes: THREE.Vector3[]) {
  const paths: FlowPath[] = [];

  nodes.forEach((node, index) => {
    const targetY = 1.5 + index % 4 * 1.42;
    const curve = new THREE.CatmullRomCurve3([
      node,
      node.clone().multiplyScalar(0.72).setY(0.5 + index % 2 * 0.28),
      node.clone().multiplyScalar(0.34).setY(targetY * 0.62),
      new THREE.Vector3(0, targetY, 0)
    ]);
    const pulse = new THREE.Mesh(
      new THREE.BoxGeometry(0.16, 0.16, 0.34),
      new THREE.MeshBasicMaterial({
        color: index === 1 || index === 3 ? COLORS.amber : COLORS.aqua,
        transparent: true,
        opacity: 0.96
      })
    );
    paths.push({ curve, offset: index / nodes.length, pulse, speed: 0.065 + index * 0.004 });
  });
  return paths;
}

function disposeScene(scene: THREE.Scene) {
  scene.traverse((object) => {
    if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Points) {
      object.geometry?.dispose();
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach((item) => item.dispose());
    }
  });
}

export function LoginDataScene() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(COLORS.dark);
    scene.fog = new THREE.FogExp2(COLORS.dark, 0.025);

    const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 160);
    camera.position.set(16, 12.5, 25);
    camera.lookAt(-2.2, 2.8, 0);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        alpha: false,
        antialias: true,
        powerPreference: "high-performance",
        preserveDrawingBuffer: true
      });
    } catch {
      container.dataset.renderState = "fallback";
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.65));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    renderer.domElement.setAttribute("aria-hidden", "true");
    container.appendChild(renderer.domElement);

    scene.add(new THREE.HemisphereLight(0xb9fff0, 0x06110d, 1.35));
    const keyLight = new THREE.DirectionalLight(0xc9fff3, 3.1);
    keyLight.position.set(7, 15, 12);
    scene.add(keyLight);
    const warmLight = new THREE.PointLight(COLORS.amber, 16, 30, 1.7);
    warmLight.position.set(-8, 5, 4);
    scene.add(warmLight);
    const blueLight = new THREE.PointLight(COLORS.blue, 12, 28, 1.8);
    blueLight.position.set(7, 4, -7);
    scene.add(blueLight);

    const world = new THREE.Group();
    world.position.set(-3.5, -1.35, 0);
    world.rotation.y = -0.28;
    scene.add(world);

    const grid = new THREE.GridHelper(52, 52, COLORS.green, 0x17352b);
    grid.position.y = -0.5;
    const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material];
    gridMaterials.forEach((item) => {
      item.opacity = 0.22;
      item.transparent = true;
    });
    world.add(grid);

    const { campus, core, nodes, orbitRings } = createCampus();
    world.add(campus);
    const paths = createFlowPaths(nodes);
    paths.forEach(({ curve, pulse }, index) => {
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(curve.getPoints(60)),
        new THREE.LineBasicMaterial({
          color: index === 1 || index === 3 ? COLORS.amber : COLORS.aqua,
          opacity: 0.22,
          transparent: true
        })
      );
      world.add(line, pulse);
    });

    const dataColumns: THREE.Mesh[] = [];
    nodes.forEach((node, index) => {
      const column = new THREE.Mesh(
        new THREE.BoxGeometry(0.055, 3.8 + index % 3, 0.055),
        new THREE.MeshBasicMaterial({
          color: index % 2 ? COLORS.blue : COLORS.aqua,
          opacity: 0.18,
          transparent: true
        })
      );
      column.position.copy(node).setY(2.1 + index % 3 * 0.5);
      world.add(column);
      dataColumns.push(column);
    });

    const pointer = new THREE.Vector2();
    const handlePointer = (event: PointerEvent) => {
      const bounds = container.getBoundingClientRect();
      pointer.x = (event.clientX - bounds.left) / Math.max(bounds.width, 1) * 2 - 1;
      pointer.y = (event.clientY - bounds.top) / Math.max(bounds.height, 1) * 2 - 1;
    };
    if (!reducedMotion) container.addEventListener("pointermove", handlePointer, { passive: true });

    const resize = () => {
      const { width, height } = container.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.position.set(width < 720 ? 12.5 : 16, width < 720 ? 11 : 12.5, width < 720 ? 28 : 25);
      camera.lookAt(width < 720 ? -3.5 : -2.2, width < 720 ? 3.2 : 2.8, 0);
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    const clock = new THREE.Clock();
    let animationFrame = 0;
    const render = () => {
      const elapsed = clock.getElapsedTime();
      if (!reducedMotion) {
        world.rotation.y += ((-0.28 + pointer.x * 0.055) - world.rotation.y) * 0.025;
        world.rotation.x += ((pointer.y * 0.018) - world.rotation.x) * 0.025;
        core.rotation.y = elapsed * 0.58;
        core.rotation.x = elapsed * 0.23;
        core.position.y = 4.2 + Math.sin(elapsed * 1.2) * 0.12;
        orbitRings.forEach((ring, index) => {
          ring.rotation.z = elapsed * (index % 2 ? -0.035 : 0.045) + ring.userData.phase;
        });
        paths.forEach((path) => {
          const progress = (elapsed * path.speed + path.offset) % 1;
          path.pulse.position.copy(path.curve.getPointAt(progress));
          const tangent = path.curve.getTangentAt(progress);
          path.pulse.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent.normalize());
        });
        dataColumns.forEach((column, index) => {
          const opacity = 0.12 + (Math.sin(elapsed * 1.4 + index) + 1) * 0.08;
          (column.material as THREE.MeshBasicMaterial).opacity = opacity;
        });
      }
      renderer.render(scene, camera);
      if (!reducedMotion) animationFrame = requestAnimationFrame(render);
    };
    render();

    return () => {
      cancelAnimationFrame(animationFrame);
      observer.disconnect();
      container.removeEventListener("pointermove", handlePointer);
      disposeScene(scene);
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, []);

  return <div aria-label="企业数据中枢实时空间" className="login-data-scene" ref={containerRef} role="img" />;
}
