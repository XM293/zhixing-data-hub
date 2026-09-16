"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

import { resolveCameraPose } from "@/lib/twin-camera";
import type {
  CameraInteractionMode,
  TwinActor,
  TwinHotspot,
  TwinInteraction,
  TwinMeeting,
  TwinRoute,
  TwinScene,
  TwinSceneFocus,
  TwinSpace
} from "@/lib/twin-types";

interface SceneProps {
  scene: TwinScene;
  scenes: TwinScene[];
  spaces: TwinSpace[];
  actors: TwinActor[];
  routes: TwinRoute[];
  meeting: TwinMeeting;
  interactions: TwinInteraction[];
  hotspots: TwinHotspot[];
  detailSceneKey: string | null;
  activeLayerKeys: string[];
  resetCameraToken: number;
  focus: TwinSceneFocus;
  selectedKey: string;
  cameraInteractionMode: CameraInteractionMode;
  onSelect: (key: string) => void;
  onEnter: (spaceKey: string) => void;
}

interface AvatarRig {
  root: THREE.Group;
  leftArm: THREE.Group;
  rightArm: THREE.Group;
  halo: THREE.Mesh;
  route: THREE.CatmullRomCurve3 | null;
  progress: number;
  phase: number;
}

interface FlowPulse {
  mesh: THREE.Mesh;
  curve: THREE.CatmullRomCurve3;
  offset: number;
  speed: number;
}

const SPACE_COLORS: Record<string, number> = {
  campus: 0x68d8bd,
  "data-hall": 0x43a7ff,
  operations: 0x70e1c1,
  warehouse: 0xe4ad58,
  knowledge: 0xa88ee8,
  "twin-studio": 0x5ed0ee,
  "meeting-room": 0xf2c66d
};

function material(color: number, options: Partial<THREE.MeshPhysicalMaterialParameters> = {}) {
  return new THREE.MeshPhysicalMaterial({ color, roughness: 0.42, metalness: 0.42, ...options });
}

function box(size: [number, number, number], meshMaterial: THREE.Material, position: [number, number, number]) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), meshMaterial);
  mesh.position.set(...position);
  return mesh;
}

function labelSprite(label: string, color = "#d9f4ec", width = 512) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = 144;
  const context = canvas.getContext("2d");
  if (context) {
    context.fillStyle = "rgba(5, 14, 20, 0.78)";
    context.roundRect(18, 18, width - 36, 96, 8);
    context.fill();
    context.strokeStyle = "rgba(115, 220, 194, 0.32)";
    context.stroke();
    context.fillStyle = color;
    context.font = '650 40px "Microsoft YaHei UI", sans-serif';
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(label, width / 2, 66, width - 64);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false }));
  sprite.scale.set(Math.min(8.2, Math.max(3.3, label.length * 0.68)), 1.24, 1);
  return sprite;
}

function tagInteractive(object: THREE.Object3D, key: string, priority = 1) {
  object.traverse((child) => {
    child.userData.entityKey = key;
    child.userData.interactionPriority = priority;
  });
}

function createRoom(space: TwinSpace) {
  const root = new THREE.Group();
  root.position.set(...space.position);
  const [width, height, depth] = space.size;
  const color = SPACE_COLORS[space.space_type] ?? 0x6d9b91;
  const floorY = -height / 2;
  const floorMaterial = material(0x102525, {
    emissive: color,
    emissiveIntensity: space.alert_level === "warning" ? 0.2 : 0.08,
    roughness: 0.62,
    metalness: 0.3
  });
  const floor = box([width, 0.18, depth], floorMaterial, [0, floorY, 0]);
  floor.receiveShadow = true;
  root.add(floor);
  root.add(box(
    [width + 0.8, 0.16, depth + 0.8],
    material(0x13272b, { roughness: 0.76, metalness: 0.34 }),
    [0, floorY - 0.14, 0]
  ));
  const wallMaterial = material(0x163535, {
    emissive: color,
    emissiveIntensity: 0.06,
    transparent: true,
    opacity: 0.13,
    transmission: 0.18,
    side: THREE.DoubleSide,
    depthWrite: false
  });
  root.add(box([width, height, 0.08], wallMaterial, [0, 0, -depth / 2]));
  root.add(box([0.08, height, depth], wallMaterial, [-width / 2, 0, 0]));
  root.add(box([0.08, height, depth], wallMaterial, [width / 2, 0, 0]));
  root.add(box([width, height, 0.06], wallMaterial, [0, 0, depth / 2]));
  const structureMaterial = material(0x31585a, { roughness: 0.3, metalness: 0.84 });
  const roofMaterial = material(0x142a2e, {
    emissive: color,
    emissiveIntensity: 0.04,
    roughness: 0.58,
    metalness: 0.48,
    transparent: true,
    opacity: 0.9
  });
  root.add(box([width + 0.18, 0.18, depth + 0.18], roofMaterial, [0, height / 2, 0]));
  for (const x of [-width / 2, width / 2]) {
    for (const z of [-depth / 2, depth / 2]) {
      root.add(box([0.14, height + 0.16, 0.14], structureMaterial, [x, 0, z]));
    }
  }
  const facadeBays = Math.max(3, Math.round(width / 2.8));
  for (let bay = 1; bay < facadeBays; bay += 1) {
    const x = -width / 2 + (width / facadeBays) * bay;
    root.add(box([0.055, height - 0.28, 0.09], structureMaterial, [x, -0.05, depth / 2 + 0.025]));
  }
  const entryMaterial = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.32 });
  root.add(box([Math.min(2.4, width * 0.22), 0.08, 1.15], entryMaterial, [0, floorY + 0.05, depth / 2 + 0.58]));
  const outlineMaterial = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.4 });
  const outline = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(width, height, depth)),
    outlineMaterial
  );
  root.add(outline);
  const selectionFrameMaterial = new THREE.LineBasicMaterial({
    color: 0xc8fff1,
    transparent: true,
    opacity: 0,
    depthTest: false
  });
  const selectionFrame = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-width / 2 - 0.32, floorY + 0.13, -depth / 2 - 0.32),
      new THREE.Vector3(width / 2 + 0.32, floorY + 0.13, -depth / 2 - 0.32),
      new THREE.Vector3(width / 2 + 0.32, floorY + 0.13, depth / 2 + 0.32),
      new THREE.Vector3(-width / 2 - 0.32, floorY + 0.13, depth / 2 + 0.32),
      new THREE.Vector3(-width / 2 - 0.32, floorY + 0.13, -depth / 2 - 0.32)
    ]),
    selectionFrameMaterial
  );
  selectionFrame.renderOrder = 20;
  root.add(selectionFrame);
  const label = labelSprite(space.label, space.alert_level === "warning" ? "#ffdca0" : "#d9f4ec");
  label.position.set(0, height / 2 + 0.54, depth / 2 + 0.18);
  label.scale.multiplyScalar(1.28);
  root.add(label);
  const hit = box([width, height, depth], new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }), [0, 0, 0]);
  root.add(hit);
  tagInteractive(hit, space.key, 1);
  return {
    root,
    hit,
    accent: floorMaterial,
    roof: roofMaterial,
    outline: outlineMaterial,
    selectionFrame: selectionFrameMaterial,
    floorY
  };
}

function addServerHall(root: THREE.Group, floorY: number) {
  const rackMaterial = material(0x275565, { roughness: 0.26, metalness: 0.78 });
  const ledMaterial = new THREE.MeshBasicMaterial({ color: 0x4ebcff });
  for (let row = 0; row < 3; row += 1) {
    for (let column = 0; column < 4; column += 1) {
      const x = -1.6 + column * 1.08;
      const z = -1.7 + row * 1.45;
      root.add(box([0.72, 1.25, 0.62], rackMaterial, [x, floorY + 0.72, z]));
      for (let led = 0; led < 5; led += 1) root.add(box([0.42, 0.035, 0.012], ledMaterial, [x, floorY + 0.33 + led * 0.19, z + 0.318]));
    }
  }
}

function addOperationsCenter(root: THREE.Group, floorY: number) {
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(1.12, 0.055, 10, 64),
    material(0x65dfc0, { emissive: 0x65dfc0, emissiveIntensity: 0.62, transparent: true, opacity: 0.72 })
  );
  ring.rotation.x = Math.PI / 2;
  ring.position.y = floorY + 0.8;
  ring.userData.operationalRing = true;
  root.add(ring);
  const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(0.52, 2),
    material(0x74e8cb, { emissive: 0x54c9ab, emissiveIntensity: 0.45, transparent: true, opacity: 0.86, roughness: 0.2 })
  );
  core.position.y = floorY + 0.88;
  core.userData.operationalCore = true;
  root.add(core);
  for (let index = 0; index < 5; index += 1) {
    const angle = (index / 5) * Math.PI * 2;
    const screen = box([1.05, 0.58, 0.08], material(0x143d46, { emissive: 0x48c8b0, emissiveIntensity: 0.24 }), [Math.cos(angle) * 1.75, floorY + 0.92, Math.sin(angle) * 1.75]);
    screen.lookAt(0, floorY + 0.92, 0);
    root.add(screen);
  }
}

function addWarehouse(root: THREE.Group, floorY: number, roomSize: TwinSpace["size"]) {
  const [width, , depth] = roomSize;
  const rackMaterial = material(0x556169, { roughness: 0.4, metalness: 0.78 });
  const cartonMaterials = [
    material(0xc89b58, { roughness: 0.8, metalness: 0.05 }),
    material(0x4f736d, { roughness: 0.72, metalness: 0.08 }),
    material(0x496673, { roughness: 0.68, metalness: 0.12 })
  ];
  const rackXs = [-width * 0.31, 0, width * 0.31];
  const rackZs = [-depth * 0.3, 0, depth * 0.3];
  for (const [row, z] of rackZs.entries()) {
    for (const [column, x] of rackXs.entries()) {
      const rack = new THREE.Group();
      rack.position.set(x, 0, z);
      for (const postX of [-1.45, 1.45]) {
        for (const postZ of [-0.44, 0.44]) {
          rack.add(box([0.08, 2.05, 0.08], rackMaterial, [postX, floorY + 1.08, postZ]));
        }
      }
      for (let shelf = 0; shelf < 3; shelf += 1) {
        const shelfY = floorY + 0.34 + shelf * 0.72;
        rack.add(box([3, 0.08, 1], rackMaterial, [0, shelfY, 0]));
        for (const crateX of [-0.92, 0, 0.92]) {
          rack.add(box(
            [0.72, 0.46, 0.66],
            cartonMaterials[(row + column + shelf) % cartonMaterials.length],
            [crateX, shelfY + 0.27, 0]
          ));
        }
      }
      root.add(rack);
    }
  }
  const conveyorMaterial = material(0x293e42, { roughness: 0.4, metalness: 0.74 });
  root.add(box([width - 3.4, 0.22, 0.9], conveyorMaterial, [0, floorY + 0.5, depth / 2 - 1.45]));
  for (let x = -width / 2 + 2.1; x < width / 2 - 1.5; x += 1.25) {
    const roller = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.68, 14), rackMaterial);
    roller.rotation.x = Math.PI / 2;
    roller.position.set(x, floorY + 0.66, depth / 2 - 1.45);
    root.add(roller);
  }
  const beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.16, 0.26, 18), new THREE.MeshBasicMaterial({ color: 0xffb85e, transparent: true, opacity: 0.9 }));
  beacon.position.set(width * 0.31, floorY + 2.35, -depth * 0.3);
  beacon.userData.warningBeacon = true;
  root.add(beacon);
}

function addKnowledgeCenter(root: THREE.Group, floorY: number) {
  const shelfMaterial = material(0x554979, { roughness: 0.36, metalness: 0.62 });
  const documentMaterial = material(0xa98de8, { emissive: 0x6d50b9, emissiveIntensity: 0.24 });
  for (let index = 0; index < 5; index += 1) {
    const x = -1.85 + index * 0.92;
    root.add(box([0.62, 1.3, 0.82], shelfMaterial, [x, floorY + 0.72, -1.55]));
    for (let row = 0; row < 4; row += 1) root.add(box([0.4, 0.08, 0.5], documentMaterial, [x, floorY + 0.3 + row * 0.28, -1.1]));
  }
  const evidence = new THREE.Mesh(new THREE.OctahedronGeometry(0.52, 1), material(0xb5a2f4, { emissive: 0x8e72dc, emissiveIntensity: 0.5, transparent: true, opacity: 0.82 }));
  evidence.position.set(0, floorY + 1.05, 1.25);
  evidence.userData.knowledgeCore = true;
  root.add(evidence);
}

function addTwinStudio(root: THREE.Group, floorY: number) {
  const podMaterial = material(0x3bbbd6, { emissive: 0x32b6d2, emissiveIntensity: 0.28, transparent: true, opacity: 0.48 });
  for (const x of [-1.4, 0, 1.4]) {
    const pod = new THREE.Mesh(new THREE.CylinderGeometry(0.58, 0.72, 1.55, 28, 1, true), podMaterial);
    pod.position.set(x, floorY + 0.97, -0.75);
    root.add(pod);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.035, 8, 36), new THREE.MeshBasicMaterial({ color: 0x69dbef, transparent: true, opacity: 0.7 }));
    ring.rotation.x = Math.PI / 2;
    ring.position.set(x, floorY + 0.26, -0.75);
    root.add(ring);
  }
}

function addMeetingRoom(root: THREE.Group, floorY: number) {
  const table = new THREE.Mesh(new THREE.CapsuleGeometry(1.45, 1.7, 8, 28), material(0x263a3e, { roughness: 0.28, metalness: 0.7 }));
  table.rotation.z = Math.PI / 2;
  table.scale.set(1, 0.18, 0.82);
  table.position.set(0.15, floorY + 0.78, 0);
  root.add(table);
  const tableCore = new THREE.Mesh(new THREE.RingGeometry(0.48, 0.55, 48), new THREE.MeshBasicMaterial({ color: 0xf0c46a, transparent: true, opacity: 0.68, side: THREE.DoubleSide }));
  tableCore.rotation.x = -Math.PI / 2;
  tableCore.position.set(0.15, floorY + 1.15, 0);
  tableCore.userData.meetingRing = true;
  root.add(tableCore);
  for (let index = 0; index < 5; index += 1) {
    const angle = -1.45 + index * 0.72;
    const chair = box([0.58, 0.74, 0.58], material(0x31484c, { roughness: 0.5, metalness: 0.4 }), [Math.cos(angle) * 2.05 + 0.15, floorY + 0.7, Math.sin(angle) * 1.55]);
    chair.lookAt(0.15, floorY + 0.8, 0);
    root.add(chair);
  }
  root.add(box([3.9, 1.45, 0.06], material(0x16393f, { emissive: 0x4ec6b0, emissiveIntensity: 0.18, transparent: true, opacity: 0.42 }), [0.15, floorY + 1.82, -2.85]));
}

function createAvatar(actor: TwinActor, route: TwinRoute | undefined): AvatarRig {
  const root = new THREE.Group();
  root.position.set(...actor.position);
  const color = new THREE.Color(actor.color);
  const bodyMaterial = material(color.getHex(), { emissive: color.getHex(), emissiveIntensity: 0.24, roughness: 0.28, metalness: 0.58, transparent: true, opacity: 0.94 });
  const suitMaterial = material(0x172f37, { roughness: 0.38, metalness: 0.62 });
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.24, 0.58, 8, 16), suitMaterial);
  body.position.y = 0.75;
  body.castShadow = true;
  root.add(body);
  root.add(box([0.24, 0.06, 0.03], bodyMaterial, [0, 0.83, 0.245]));
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.22, 24, 18), bodyMaterial);
  head.position.y = 1.36;
  root.add(head);
  root.add(box([0.24, 0.07, 0.035], new THREE.MeshBasicMaterial({ color: 0xd9fbf3 }), [0, 1.38, 0.205]));
  function limb(x: number) {
    const pivot = new THREE.Group();
    pivot.position.set(x, 1.03, 0);
    const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.07, 0.42, 6, 10), suitMaterial);
    arm.position.y = -0.25;
    pivot.add(arm);
    root.add(pivot);
    return pivot;
  }
  const leftArm = limb(-0.31);
  const rightArm = limb(0.31);
  for (const x of [-0.12, 0.12]) {
    const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.075, 0.4, 6, 10), suitMaterial);
    leg.position.set(x, 0.22, 0);
    root.add(leg);
  }
  const halo = new THREE.Mesh(new THREE.RingGeometry(0.38, 0.42, 36), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55, side: THREE.DoubleSide }));
  halo.rotation.x = -Math.PI / 2;
  halo.position.y = 0.015;
  root.add(halo);
  const label = labelSprite(actor.display_name, actor.color, 448);
  label.position.y = 1.92;
  label.scale.multiplyScalar(0.72);
  root.add(label);
  tagInteractive(root, actor.key, 4);
  const curve = route ? new THREE.CatmullRomCurve3(route.path.map((point) => new THREE.Vector3(...point)), false, "centripetal") : null;
  return { root, leftArm, rightArm, halo, route: curve, progress: 0, phase: Math.random() * Math.PI * 2 };
}

function createFlow(world: THREE.Group, points: Array<[number, number, number]>, color: number, pulseOffset: number, pulses: FlowPulse[]) {
  const curve = new THREE.CatmullRomCurve3(points.map((point) => new THREE.Vector3(...point)));
  world.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 80, 0.018, 6, false), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.28 })));
  for (let index = 0; index < 3; index += 1) {
    const pulse = new THREE.Mesh(new THREE.SphereGeometry(0.07, 10, 8), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9 }));
    world.add(pulse);
    pulses.push({ mesh: pulse, curve, offset: pulseOffset + index / 3, speed: 0.08 + index * 0.012 });
  }
}

function addCampus(world: THREE.Group, campusSize: TwinSpace["size"]) {
  const shellMaterials: THREE.Material[] = [];
  const [campusWidth, , campusDepth] = campusSize;
  world.add(box(
    [campusWidth + 4, 0.28, campusDepth + 4],
    material(0x0c1d22, { roughness: 0.82, metalness: 0.18 }),
    [0, -0.25, 0]
  ));
  const gridSize = Math.max(campusWidth, campusDepth) + 12;
  const grid = new THREE.GridHelper(gridSize, Math.round(gridSize), 0x235a55, 0x173a39);
  grid.position.y = -0.09;
  for (const item of Array.isArray(grid.material) ? grid.material : [grid.material]) { item.transparent = true; item.opacity = 0.26; }
  world.add(grid);
  const roadMaterial = material(0x121c22, { roughness: 0.94, metalness: 0.08 });
  world.add(box([campusWidth - 5, 0.09, 7.2], roadMaterial, [0, -0.035, 0]));
  world.add(box([7.2, 0.09, campusDepth - 5], roadMaterial, [8.2, -0.03, 0]));
  const laneMaterial = new THREE.MeshBasicMaterial({ color: 0x5e857d, transparent: true, opacity: 0.34 });
  for (let x = -campusWidth / 2 + 4; x < campusWidth / 2 - 4; x += 3.2) {
    world.add(box([1.45, 0.018, 0.075], laneMaterial, [x, 0.025, 0]));
  }
  for (let z = -campusDepth / 2 + 4; z < campusDepth / 2 - 4; z += 3.2) {
    world.add(box([0.075, 0.018, 1.45], laneMaterial, [8.2, 0.025, z]));
  }

  const plazaMaterial = material(0x173032, { emissive: 0x2d776a, emissiveIntensity: 0.08, roughness: 0.68, metalness: 0.28 });
  const plaza = new THREE.Mesh(new THREE.CylinderGeometry(6.4, 6.4, 0.1, 64), plazaMaterial);
  plaza.position.set(8.2, 0.02, 0);
  plaza.receiveShadow = true;
  world.add(plaza);
  const plazaCore = new THREE.Mesh(
    new THREE.RingGeometry(1.4, 1.55, 64),
    new THREE.MeshBasicMaterial({ color: 0x70e1c1, transparent: true, opacity: 0.58, side: THREE.DoubleSide })
  );
  plazaCore.rotation.x = -Math.PI / 2;
  plazaCore.position.set(8.2, 0.09, 0);
  plazaCore.userData.campusCore = true;
  world.add(plazaCore);
  const capacityMaterial = new THREE.MeshBasicMaterial({ color: 0x77cab8, transparent: true, opacity: 0.2, side: THREE.DoubleSide });
  for (let index = 0; index < 16; index += 1) {
    const angle = (index / 16) * Math.PI * 2;
    const pad = new THREE.Mesh(new THREE.RingGeometry(0.28, 0.34, 24), capacityMaterial);
    pad.rotation.x = -Math.PI / 2;
    pad.position.set(8.2 + Math.cos(angle) * 4.25, 0.085, Math.sin(angle) * 4.25);
    world.add(pad);
  }

  const loadingMaterial = material(0x17252a, { roughness: 0.86, metalness: 0.14 });
  world.add(box([18, 0.08, 5.2], loadingMaterial, [21, -0.01, 3.9]));
  for (let x = 14.5; x <= 27.5; x += 3.25) {
    world.add(box([0.07, 0.02, 3.2], laneMaterial, [x, 0.04, 3.9]));
  }

  const shellMaterial = material(0x173038, { emissive: 0x3ea992, emissiveIntensity: 0.06, transparent: true, opacity: 0.18, transmission: 0.25, side: THREE.DoubleSide, depthWrite: false });
  shellMaterials.push(shellMaterial);
  for (const [x, z] of [[-30, -18], [-30, 18], [30, -18], [30, 18]] as Array<[number, number]>) {
    const beacon = box([0.18, 3.6, 0.18], shellMaterial, [x, 1.8, z]);
    world.add(beacon);
    const cap = new THREE.Mesh(new THREE.SphereGeometry(0.16, 16, 12), new THREE.MeshBasicMaterial({ color: 0x6ee4c8 }));
    cap.position.set(x, 3.65, z);
    world.add(cap);
  }

  const planterMaterial = material(0x19302c, { roughness: 0.9, metalness: 0.05 });
  const foliageMaterial = material(0x31584a, { roughness: 0.94, metalness: 0.02 });
  for (const [x, z] of [[-29, -2.5], [-17, -2.5], [-7, 4.5], [1, 4.5], [28, 6.8], [27, 19]] as Array<[number, number]>) {
    world.add(box([2.6, 0.38, 1.15], planterMaterial, [x, 0.15, z]));
    for (const offset of [-0.75, 0, 0.75]) {
      const shrub = new THREE.Mesh(new THREE.SphereGeometry(0.38, 12, 8), foliageMaterial);
      shrub.scale.set(1, 0.72, 0.8);
      shrub.position.set(x + offset, 0.55, z);
      world.add(shrub);
    }
  }

  const skylineMaterial = material(0x17252e, { emissive: 0x24545a, emissiveIntensity: 0.08, roughness: 0.75 });
  for (let index = 0; index < 18; index += 1) {
    const x = -48 + index * 5.7;
    const height = 5.5 + ((index * 7) % 10);
    world.add(box([3.3, height, 3.6], skylineMaterial, [x, height / 2 - 0.1, -35 - (index % 3) * 3.4]));
  }
  addCampusLighting(world, campusWidth, campusDepth);
  return shellMaterials;
}

function addCampusLighting(world: THREE.Group, campusWidth: number, campusDepth: number) {
  const edgeMaterial = new THREE.MeshBasicMaterial({
    color: 0x3dd7bd,
    transparent: true,
    opacity: 0.42,
    blending: THREE.AdditiveBlending
  });
  const amberMaterial = new THREE.MeshBasicMaterial({
    color: 0xe6b45e,
    transparent: true,
    opacity: 0.5,
    blending: THREE.AdditiveBlending
  });
  for (const z of [-campusDepth / 2 - 0.12, campusDepth / 2 + 0.12]) {
    world.add(box([campusWidth - 4, 0.045, 0.06], edgeMaterial, [0, 0.08, z]));
  }
  for (const x of [-campusWidth / 2 - 0.12, campusWidth / 2 + 0.12]) {
    world.add(box([0.06, 0.045, campusDepth - 4], edgeMaterial, [x, 0.08, 0]));
  }
  for (const x of [-24, -12, 0, 12, 24]) {
    const mast = new THREE.Group();
    mast.position.set(x, 0, 8.8);
    mast.add(box([0.07, 2.3, 0.07], material(0x355c5c, { metalness: 0.78, roughness: 0.26 }), [0, 1.15, 0]));
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.11, 12, 8), amberMaterial);
    lamp.position.y = 2.28;
    lamp.userData.campusLamp = true;
    mast.add(lamp);
    world.add(mast);
  }
  const starGeometry = new THREE.BufferGeometry();
  const positions = new Float32Array(180 * 3);
  for (let index = 0; index < 180; index += 1) {
    positions[index * 3] = -66 + ((index * 37) % 132);
    positions[index * 3 + 1] = 10 + ((index * 19) % 34);
    positions[index * 3 + 2] = -58 + ((index * 53) % 96);
  }
  starGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const stars = new THREE.Points(starGeometry, new THREE.PointsMaterial({
    color: 0x77d9ca,
    size: 0.12,
    transparent: true,
    opacity: 0.34,
    depthWrite: false,
    blending: THREE.AdditiveBlending
  }));
  stars.userData.campusStars = true;
  world.add(stars);
}

function createWarehouseInterior(
  hotspots: TwinHotspot[],
  clickTargets: THREE.Object3D[],
  pulses: FlowPulse[]
) {
  const root = new THREE.Group();
  const layerGroups = new Map<string, THREE.Group>();
  const hotspotRoots = new Map<string, THREE.Group>();
  const automationParts: THREE.Object3D[] = [];
  const floorMaterial = material(0x101d20, { roughness: 0.78, metalness: 0.25 });
  root.add(box([22, 0.24, 14], floorMaterial, [0, -0.14, 0]));
  const floorGrid = new THREE.GridHelper(22, 22, 0x3d7f70, 0x203f3a);
  floorGrid.position.y = 0.01;
  floorGrid.scale.z = 14 / 22;
  for (const item of Array.isArray(floorGrid.material) ? floorGrid.material : [floorGrid.material]) {
    item.transparent = true;
    item.opacity = 0.34;
  }
  root.add(floorGrid);

  const wallMaterial = material(0x163638, {
    emissive: 0x3b9a88,
    emissiveIntensity: 0.07,
    transparent: true,
    opacity: 0.16,
    transmission: 0.28,
    side: THREE.DoubleSide,
    depthWrite: false
  });
  root.add(box([22, 5.8, 0.1], wallMaterial, [0, 2.8, -7]));
  root.add(box([0.1, 5.8, 14], wallMaterial, [-11, 2.8, 0]));
  root.add(box([0.1, 5.8, 14], wallMaterial, [11, 2.8, 0]));
  const frameMaterial = material(0x345d5b, { roughness: 0.34, metalness: 0.8 });
  for (const x of [-11, -7.4, -3.7, 0, 3.7, 7.4, 11]) {
    root.add(box([0.09, 5.9, 0.12], frameMaterial, [x, 2.85, -6.94]));
  }
  root.add(box([22.1, 0.1, 0.14], frameMaterial, [0, 5.75, -6.94]));

  const ceilingLightMaterial = new THREE.MeshBasicMaterial({
    color: 0x72e8d1,
    transparent: true,
    opacity: 0.58,
    blending: THREE.AdditiveBlending
  });
  for (const x of [-7.2, -2.4, 2.4, 7.2]) {
    const strip = box([2.1, 0.035, 0.12], ceilingLightMaterial, [x, 5.58, -1.1]);
    strip.userData.warehouseCeilingLight = true;
    root.add(strip);
  }
  const dockLight = new THREE.PointLight(0x58d7c1, 10, 13);
  dockLight.position.set(0, 4.8, 3.7);
  root.add(dockLight);

  const title = labelSprite("智能仓储 · 东区履约中心", "#e6faf5", 640);
  title.position.set(0, 5.05, -6.78);
  title.scale.multiplyScalar(1.18);
  root.add(title);

  const riskLayer = new THREE.Group();
  const flowLayer = new THREE.Group();
  const automationLayer = new THREE.Group();
  layerGroups.set("inventory-risk", riskLayer);
  layerGroups.set("stock-flow", flowLayer);
  layerGroups.set("automation", automationLayer);
  root.add(riskLayer, flowLayer, automationLayer);

  const rackFrame = material(0x56656a, { roughness: 0.42, metalness: 0.78 });
  const cartonMaterials = [
    material(0x8c6d42, { roughness: 0.82, metalness: 0.03 }),
    material(0x53716b, { roughness: 0.72, metalness: 0.08 }),
    material(0x4b626d, { roughness: 0.68, metalness: 0.16 })
  ];
  for (const [rackIndex, rackX] of [-5.2, -1.8, 1.8, 5.2].entries()) {
    for (const rackZ of [-3.2, 0.25]) {
      const rack = new THREE.Group();
      rack.position.set(rackX, 0, rackZ);
      for (const postX of [-1.05, 1.05]) {
        for (const postZ of [-0.42, 0.42]) rack.add(box([0.08, 3.3, 0.08], rackFrame, [postX, 1.65, postZ]));
      }
      for (let shelf = 0; shelf < 4; shelf += 1) {
        const y = 0.35 + shelf * 0.92;
        rack.add(box([2.2, 0.08, 1], rackFrame, [0, y, 0]));
        for (const crateX of [-0.68, 0, 0.68]) {
          const crate = box([0.56, 0.52, 0.68], cartonMaterials[(rackIndex + shelf) % cartonMaterials.length], [crateX, y + 0.31, 0]);
          rack.add(crate);
        }
      }
      root.add(rack);
    }
  }

  const conveyorMaterial = material(0x31464a, { roughness: 0.38, metalness: 0.72 });
  const beltMaterial = material(0x192629, { roughness: 0.78, metalness: 0.22 });
  root.add(box([15.8, 0.28, 1.15], conveyorMaterial, [0.3, 0.58, 4.35]));
  root.add(box([15.2, 0.08, 0.82], beltMaterial, [0.3, 0.76, 4.35]));
  for (let x = -6.8; x <= 7.4; x += 1.4) {
    const roller = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.11, 0.76, 16), frameMaterial);
    roller.rotation.x = Math.PI / 2;
    roller.position.set(x, 0.82, 4.35);
    root.add(roller);
  }
  root.add(box([2.6, 0.16, 2.8], material(0x203335, { roughness: 0.6, metalness: 0.45 }), [-8.9, 0.05, 4.7]));
  root.add(box([2.6, 0.16, 2.8], material(0x203335, { roughness: 0.6, metalness: 0.45 }), [8.9, 0.05, 4.7]));

  createFlow(flowLayer, [[-9.6, 0.95, 5.2], [-6.8, 0.95, 4.35], [-2.2, 0.95, 4.35], [-1.2, 1.2, 0.25]], 0x57b8ff, 0.1, pulses);
  createFlow(flowLayer, [[-4.8, 1.35, -2.4], [-3.2, 1.35, 1.2], [0.3, 0.95, 4.35], [9.6, 0.95, 4.9]], 0x70e1c1, 0.47, pulses);

  for (const hotspot of hotspots) {
    const hotspotRoot = new THREE.Group();
    hotspotRoot.position.set(...hotspot.position);
    const hit = box([1.35, 1.9, 1.35], new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }), [0, 0.45, 0]);
    tagInteractive(hit, hotspot.key, 5);
    hotspotRoot.add(hit);
    clickTargets.push(hit);
    hotspotRoots.set(hotspot.key, hotspotRoot);
    root.add(hotspotRoot);

    const severityColor = hotspot.severity === "critical" ? 0xec7468 : hotspot.severity === "warning" ? 0xe3ad59 : 0x64d8b8;
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.48, 0.57, 40),
      new THREE.MeshBasicMaterial({ color: severityColor, transparent: true, opacity: 0.78, side: THREE.DoubleSide })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.04;
    ring.userData.hotspotRing = true;
    ring.userData.phase = hotspot.position[0] * 0.3;
    hotspotRoot.add(ring);
    riskLayer.attach(ring);

    if (hotspot.hotspot_type === "sku-slot") {
      const beam = box([0.035, 2.6, 0.035], new THREE.MeshBasicMaterial({ color: severityColor, transparent: true, opacity: 0.5 }), [0, 1.35, 0]);
      beam.userData.hotspotBeam = true;
      hotspotRoot.add(beam);
      riskLayer.attach(beam);
      const hotspotLabel = labelSprite(hotspot.label, hotspot.severity === "critical" ? "#ffb5ad" : "#ffe0a3", 520);
      hotspotLabel.position.set(0, 2.9, 0);
      hotspotLabel.scale.multiplyScalar(0.58);
      hotspotRoot.add(hotspotLabel);
      riskLayer.attach(hotspotLabel);
    }
  }

  const agv = new THREE.Group();
  agv.position.set(0.2, 0.22, 4.3);
  agv.add(box([1.05, 0.28, 0.72], material(0x594680, { emissive: 0x8d71d0, emissiveIntensity: 0.38, roughness: 0.28 }), [0, 0.2, 0]));
  for (const x of [-0.36, 0.36]) for (const z of [-0.28, 0.28]) {
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.09, 16), material(0x11191c));
    wheel.rotation.z = Math.PI / 2;
    wheel.position.set(x, 0.08, z);
    agv.add(wheel);
  }
  const agvLight = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.08, 0.16, 14), new THREE.MeshBasicMaterial({ color: 0xb69cff }));
  agvLight.position.set(0, 0.48, 0);
  agv.add(agvLight);
  tagInteractive(agv, "agv-07", 5);
  clickTargets.push(agv);
  automationParts.push(agv);
  automationLayer.add(agv);

  return { root, layerGroups, hotspotRoots, automationParts };
}

function createMeetingInterior(
  hotspots: TwinHotspot[],
  actors: TwinActor[],
  meeting: TwinMeeting,
  clickTargets: THREE.Object3D[],
  pulses: FlowPulse[]
) {
  const root = new THREE.Group();
  const layerGroups = new Map<string, THREE.Group>();
  const hotspotRoots = new Map<string, THREE.Group>();
  const seatRoots = new Map<string, THREE.Group>();
  const seatIndicators = new Map<string, THREE.MeshBasicMaterial>();
  const avatarRigs = new Map<string, AvatarRig>();
  const decisionMaterials: THREE.MeshPhysicalMaterial[] = [];

  root.add(box([20, 0.22, 13], material(0x101c21, { roughness: 0.72, metalness: 0.32 }), [0, -0.13, 0]));
  const floorGrid = new THREE.GridHelper(20, 20, 0x476e69, 0x203b3a);
  floorGrid.position.y = 0.01;
  floorGrid.scale.z = 13 / 20;
  for (const item of Array.isArray(floorGrid.material) ? floorGrid.material : [floorGrid.material]) {
    item.transparent = true;
    item.opacity = 0.24;
  }
  root.add(floorGrid);

  const ceilingRing = new THREE.Mesh(
    new THREE.TorusGeometry(4.7, 0.045, 8, 96),
    new THREE.MeshBasicMaterial({ color: 0x55d9c0, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending })
  );
  ceilingRing.rotation.x = Math.PI / 2;
  ceilingRing.position.y = 5.45;
  ceilingRing.userData.meetingCeilingRing = true;
  root.add(ceilingRing);
  const ceilingLight = new THREE.PointLight(0x64d9c4, 15, 18);
  ceilingLight.position.set(0, 4.8, 0);
  root.add(ceilingLight);

  const glass = material(0x172f38, {
    emissive: 0x2f8a7b,
    emissiveIntensity: 0.07,
    transparent: true,
    opacity: 0.15,
    transmission: 0.34,
    side: THREE.DoubleSide,
    depthWrite: false
  });
  root.add(box([20, 5.8, 0.1], glass, [0, 2.8, -6.5]));
  root.add(box([0.1, 5.8, 13], glass, [-10, 2.8, 0]));
  root.add(box([0.1, 5.8, 13], glass, [10, 2.8, 0]));
  const frame = material(0x345755, { roughness: 0.3, metalness: 0.82 });
  for (const x of [-10, -6.65, -3.3, 0, 3.3, 6.65, 10]) root.add(box([0.08, 5.9, 0.12], frame, [x, 2.85, -6.44]));
  root.add(box([20.1, 0.1, 0.14], frame, [0, 5.75, -6.44]));
  for (const x of [-7.8, -4.7, -1.6, 1.6, 4.7, 7.8]) {
    const light = box([1.5, 0.035, 0.16], new THREE.MeshBasicMaterial({ color: 0x9cebd8, transparent: true, opacity: 0.38 }), [x, 5.25, -1.1]);
    root.add(light);
  }

  const title = labelSprite("数字决策室 · 预算与库存联动研判", "#f5e4b3", 760);
  title.position.set(0, 5.04, -6.28);
  title.scale.multiplyScalar(1.18);
  root.add(title);

  const tableMaterial = material(0x26383c, { emissive: 0x377f72, emissiveIntensity: 0.13, roughness: 0.27, metalness: 0.76 });
  const table = new THREE.Mesh(new THREE.CylinderGeometry(3.65, 3.65, 0.34, 72), tableMaterial);
  table.scale.z = 0.64;
  table.position.set(0, 0.78, 0.2);
  table.castShadow = true;
  root.add(table);
  const tableCore = new THREE.Mesh(
    new THREE.RingGeometry(0.72, 0.82, 64),
    new THREE.MeshBasicMaterial({ color: 0xf0c46a, transparent: true, opacity: 0.72, side: THREE.DoubleSide })
  );
  tableCore.rotation.x = -Math.PI / 2;
  tableCore.position.set(0, 0.98, 0.2);
  tableCore.userData.meetingInteriorRing = true;
  root.add(tableCore);
  const evidenceCore = new THREE.Mesh(
    new THREE.IcosahedronGeometry(0.5, 2),
    material(0x68d9bc, { emissive: 0x4dbda2, emissiveIntensity: 0.58, transparent: true, opacity: 0.8, roughness: 0.18 })
  );
  evidenceCore.position.set(0, 2.05, 0.2);
  evidenceCore.userData.meetingEvidenceCore = true;
  root.add(evidenceCore);

  const evidenceLayer = new THREE.Group();
  const stanceLayer = new THREE.Group();
  const decisionLayer = new THREE.Group();
  layerGroups.set("evidence-context", evidenceLayer);
  layerGroups.set("stance-map", stanceLayer);
  layerGroups.set("decision-chain", decisionLayer);
  root.add(evidenceLayer, stanceLayer, decisionLayer);

  const occupiedSeatKeys = new Set(
    meeting.participants.flatMap((participant) => participant.seat_key ? [participant.seat_key] : [])
  );
  for (const seat of meeting.seats) {
    const chair = new THREE.Group();
    chair.position.set(...seat.position);
    chair.rotation.y = seat.rotation_y;
    const occupied = occupiedSeatKeys.has(seat.key);
    const chairColor = occupied ? 0x3c605b : 0x2c4447;
    chair.add(box(
      [0.78, 0.18, 0.78],
      material(chairColor, { roughness: 0.46, metalness: 0.48 }),
      [0, 0.22, 0]
    ));
    chair.add(box(
      [0.78, 0.82, 0.16],
      material(occupied ? 0x4b746d : 0x304b4e, { roughness: 0.42, metalness: 0.52 }),
      [0, 0.65, 0.36]
    ));
    const seatRingMaterial = new THREE.MeshBasicMaterial({
      color: occupied ? 0x70e1c1 : 0x597a73,
      transparent: true,
      opacity: occupied ? 0.5 : 0.18,
      side: THREE.DoubleSide
    });
    seatRingMaterial.userData.baseOpacity = occupied ? 0.5 : 0.18;
    seatRingMaterial.userData.baseColor = occupied ? 0x70e1c1 : 0x597a73;
    const seatRing = new THREE.Mesh(
      new THREE.RingGeometry(0.48, 0.56, 36),
      seatRingMaterial
    );
    seatRing.rotation.x = -Math.PI / 2;
    seatRing.position.y = 0.03;
    chair.add(seatRing);
    const seatLabel = labelSprite(seat.label, occupied ? "#cffff2" : "#91aaa4", 400);
    seatLabel.position.set(0, 1.25, 0);
    seatLabel.scale.multiplyScalar(0.43);
    chair.add(seatLabel);
    const hit = box(
      [1.15, 1.35, 1.15],
      new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }),
      [0, 0.58, 0]
    );
    tagInteractive(hit, seat.key, 3);
    chair.add(hit);
    root.add(chair);
    clickTargets.push(hit);
    seatRoots.set(seat.key, chair);
    seatIndicators.set(seat.key, seatRingMaterial);
  }

  const actorByKey = new Map(actors.map((actor) => [actor.key, actor]));
  const seatByKey = new Map(meeting.seats.map((seat) => [seat.key, seat]));
  for (const [index, participant] of meeting.participants.entries()) {
    const actor = actorByKey.get(participant.actor_key);
    const seatRecord = participant.seat_key ? seatByKey.get(participant.seat_key) : undefined;
    if (!actor || !seatRecord) continue;
    const seat = seatRecord.position;
    const entry: [number, number, number] = [
      -7.8 + (index / Math.max(meeting.participants.length - 1, 1)) * 15.6,
      0.08,
      5.35
    ];
    const projectedActor = { ...actor, position: entry };
    const rig = createAvatar(projectedActor, undefined);
    rig.root.scale.setScalar(1.08);
    rig.route = new THREE.CatmullRomCurve3([
      new THREE.Vector3(...entry),
      new THREE.Vector3(entry[0] * 0.62, 0.08, 3.7),
      new THREE.Vector3(seat[0] * 1.15, 0.08, seat[2] + 0.8),
      new THREE.Vector3(...seat)
    ], false, "centripetal");
    rig.progress = 0;
    root.add(rig.root);
    clickTargets.push(rig.root);
    avatarRigs.set(actor.key, rig);

    const stanceColor = new THREE.Color(actor.color).getHex();
    createFlow(
      stanceLayer,
      [[seat[0], 0.82, seat[2]], [seat[0] * 0.55, 1.32, seat[2] * 0.55], [0, 1.72, 0.2]],
      stanceColor,
      index * 0.22,
      pulses
    );
  }

  for (const hotspot of hotspots) {
    const hotspotRoot = new THREE.Group();
    hotspotRoot.position.set(...hotspot.position);
    const hit = box([2.6, 2.4, 0.8], new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }), [0, 0, 0]);
    tagInteractive(hit, hotspot.key, 5);
    hotspotRoot.add(hit);
    clickTargets.push(hit);
    hotspotRoots.set(hotspot.key, hotspotRoot);
    root.add(hotspotRoot);

    const visual = new THREE.Group();
    visual.position.set(...hotspot.position);
    const hotspotLabel = labelSprite(hotspot.label, hotspot.severity === "warning" ? "#ffe0a3" : "#dff9f2", 560);
    hotspotLabel.position.set(0, 1.75, 0.08);
    hotspotLabel.scale.multiplyScalar(0.58);
    visual.add(hotspotLabel);

    if (hotspot.hotspot_type === "evidence-wall") {
      const panel = box([4.25, 2.55, 0.1], material(0x173a43, { emissive: 0x57b8ff, emissiveIntensity: 0.22, transparent: true, opacity: 0.62 }), [0, 0, 0]);
      visual.add(panel);
      for (let row = 0; row < 5; row += 1) {
        const width = 2.9 - (row % 2) * 0.65;
        visual.add(box([width, 0.08, 0.025], new THREE.MeshBasicMaterial({ color: row === 0 ? 0x66c5ff : 0x477b89, transparent: true, opacity: 0.72 }), [-0.35, 0.78 - row * 0.36, 0.08]));
      }
      createFlow(evidenceLayer, [[-5.2, 1.65, -4.75], [-3.4, 1.65, -3.2], [-1.3, 1.8, -1.2], [0, 2.05, 0.2]], 0x57b8ff, 0.12, pulses);
      evidenceLayer.add(visual);
    } else if (hotspot.hotspot_type === "deliberation-map") {
      const conflict = new THREE.Mesh(
        new THREE.OctahedronGeometry(0.74, 1),
        material(0xe3ad59, { emissive: 0xe3ad59, emissiveIntensity: 0.35, transparent: true, opacity: 0.78, roughness: 0.22 })
      );
      conflict.userData.meetingConflict = true;
      visual.add(conflict);
      const orbit = new THREE.Mesh(new THREE.TorusGeometry(1.05, 0.035, 10, 72), new THREE.MeshBasicMaterial({ color: 0xe3ad59, transparent: true, opacity: 0.58 }));
      orbit.userData.meetingConflictOrbit = true;
      visual.add(orbit);
      stanceLayer.add(visual);
    } else if (hotspot.hotspot_type === "decision-output") {
      const decisionMaterial = material(0x3f4539, { emissive: 0x6d6441, emissiveIntensity: 0.12, transparent: true, opacity: 0.62 });
      decisionMaterials.push(decisionMaterial);
      visual.add(box([4.25, 2.55, 0.1], decisionMaterial, [0, 0, 0]));
      for (let row = 0; row < 4; row += 1) {
        visual.add(box([3.05 - row * 0.28, 0.08, 0.025], new THREE.MeshBasicMaterial({ color: 0xb69a5c, transparent: true, opacity: 0.46 }), [-0.28, 0.7 - row * 0.4, 0.08]));
      }
      createFlow(decisionLayer, [[0, 2.05, 0.2], [1.8, 1.8, -1.4], [3.8, 1.65, -3.3], [5.2, 1.65, -4.75]], 0xf2c66d, 0.56, pulses);
      decisionLayer.add(visual);
    } else {
      const gateMaterial = material(0x375247, { emissive: 0x70e1c1, emissiveIntensity: 0.2, roughness: 0.32, metalness: 0.72 });
      visual.add(box([0.18, 2.8, 0.22], gateMaterial, [-1.15, 0, 0]));
      visual.add(box([0.18, 2.8, 0.22], gateMaterial, [1.15, 0, 0]));
      visual.add(box([2.48, 0.18, 0.22], gateMaterial, [0, 1.32, 0]));
      createFlow(decisionLayer, [[5.2, 1.65, -4.75], [6.4, 1.25, -2], [7.2, 0.85, 2.7]], 0x70e1c1, 0.78, pulses);
      decisionLayer.add(visual);
    }
  }

  return {
    root,
    layerGroups,
    hotspotRoots,
    seatRoots,
    seatIndicators,
    avatarRigs,
    decisionMaterials
  };
}

export function EnterpriseTwinScene({
  scene: sceneProjection,
  scenes,
  spaces,
  actors,
  routes,
  meeting,
  interactions,
  hotspots,
  detailSceneKey,
  activeLayerKeys,
  resetCameraToken,
  focus,
  selectedKey,
  cameraInteractionMode,
  onSelect,
  onEnter
}: SceneProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const callbackRef = useRef(onSelect);
  const enterRef = useRef(onEnter);
  const focusRef = useRef(focus);
  const selectedRef = useRef(selectedKey);
  const meetingRef = useRef(meeting.status);
  const meetingDataRef = useRef(meeting);
  const interactionsRef = useRef(interactions);
  const cameraInteractionModeRef = useRef(cameraInteractionMode);
  const detailRef = useRef(detailSceneKey);
  const activeLayersRef = useRef(activeLayerKeys);
  const scenesRef = useRef(scenes);
  const resetRef = useRef(resetCameraToken);
  callbackRef.current = onSelect;
  enterRef.current = onEnter;
  focusRef.current = focus;
  selectedRef.current = selectedKey;
  meetingRef.current = meeting.status;
  meetingDataRef.current = meeting;
  interactionsRef.current = interactions;
  cameraInteractionModeRef.current = cameraInteractionMode;
  detailRef.current = detailSceneKey;
  activeLayersRef.current = activeLayerKeys;
  scenesRef.current = scenes;
  resetRef.current = resetCameraToken;

  useEffect(() => {
    const host = hostRef.current;
    if (!host || spaces.length === 0) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x07171c);
    scene.fog = new THREE.FogExp2(0x07171c, 0.0095);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 180);
    camera.position.set(56, 38, 62);
    const currentLookAt = new THREE.Vector3(0, 2, 0);
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance", preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.7));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.38;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.domElement.setAttribute("aria-label", "企业经营数字孪生三维空间");
    renderer.domElement.setAttribute("data-testid", "enterprise-twin-canvas");
    host.appendChild(renderer.domElement);
    const composer = new EffectComposer(renderer);
    const renderPass = new RenderPass(scene, camera);
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.34, 0.72, 0.82);
    composer.addPass(renderPass);
    composer.addPass(bloomPass);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enabled = false;
    controls.enableDamping = true;
    controls.dampingFactor = 0.075;
    controls.enablePan = true;
    controls.screenSpacePanning = true;
    controls.zoomToCursor = true;
    controls.minPolarAngle = 0.38;
    controls.maxPolarAngle = 1.48;
    controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
    controls.mouseButtons.MIDDLE = THREE.MOUSE.DOLLY;
    controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
    controls.touches.ONE = THREE.TOUCH.ROTATE;
    controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;
    controls.target.copy(currentLookAt);
    scene.add(new THREE.HemisphereLight(0xaadfd4, 0x071117, 2.2));
    const sun = new THREE.DirectionalLight(0xd6fff4, 3.8);
    sun.position.set(14, 22, 18);
    sun.castShadow = true;
    scene.add(sun);
    const cyanLight = new THREE.PointLight(0x4ad8c1, 68, 58);
    cyanLight.position.set(-12, 11, 6);
    scene.add(cyanLight);
    const amberLight = new THREE.PointLight(0xe7b45f, 54, 52);
    amberLight.position.set(22, 10, 4);
    scene.add(amberLight);
    const world = new THREE.Group();
    scene.add(world);
    const campus = spaces.find((item) => item.key === "campus");
    const shellMaterials = addCampus(world, campus?.size ?? [72, 1, 48]);
    const clickTargets: THREE.Object3D[] = [];
    const accentMaterials = new Map<string, THREE.Material>();
    const roofMaterials = new Map<string, THREE.MeshPhysicalMaterial>();
    const outlineMaterials = new Map<string, THREE.LineBasicMaterial>();
    const selectionFrameMaterials = new Map<string, THREE.LineBasicMaterial>();
    const roomRoots = new Map<string, THREE.Group>();
    for (const space of spaces.filter((item) => item.key !== "campus")) {
      const room = createRoom(space);
      world.add(room.root);
      clickTargets.push(room.hit);
      accentMaterials.set(space.key, room.accent);
      roofMaterials.set(space.key, room.roof);
      outlineMaterials.set(space.key, room.outline);
      selectionFrameMaterials.set(space.key, room.selectionFrame);
      roomRoots.set(space.key, room.root);
      if (space.space_type === "data-hall") addServerHall(room.root, room.floorY);
      else if (space.space_type === "operations") addOperationsCenter(room.root, room.floorY);
      else if (space.space_type === "warehouse") addWarehouse(room.root, room.floorY, space.size);
      else if (space.space_type === "knowledge") addKnowledgeCenter(room.root, room.floorY);
      else if (space.space_type === "twin-studio") addTwinStudio(room.root, room.floorY);
      else if (space.space_type === "meeting-room") addMeetingRoom(room.root, room.floorY);
    }
    const campusLabel = labelSprite(sceneProjection.name, "#dff9f2", 640);
    campusLabel.position.set(-25.5, 7.4, 21.5);
    campusLabel.scale.multiplyScalar(1.08);
    world.add(campusLabel);
    const pulses: FlowPulse[] = [];
    createFlow(world, [[-27, 0.34, -10.5], [-21, 0.34, -10.5], [-14, 0.34, -3], [-6, 0.34, 0], [8, 0.34, 0]], 0x52b8ff, 0, pulses);
    createFlow(world, [[-2, 0.4, -10], [1.5, 0.4, -4], [8, 0.4, 0], [14, 0.4, -3], [21, 0.4, -8]], 0x61dfc0, 0.2, pulses);
    createFlow(world, [[-19, 0.46, 12], [-12, 0.46, 6], [-6, 0.46, 4], [6, 0.46, 4], [12, 0.46, 7], [18, 0.46, 12]], 0xaa8ced, 0.42, pulses);
    createFlow(world, [[-21, 0.52, -10.5], [-20, 0.52, 0], [-19, 0.52, 12], [-8, 0.52, 12], [-1, 0.52, 12], [8, 0.52, 6], [18, 0.52, 12]], 0xf2c66d, 0.64, pulses);
    const loadedSceneKeys = new Set([sceneProjection.key]);
    host.dataset.loadedScenes = [...loadedSceneKeys].join(",");
    let warehouseInterior: ReturnType<typeof createWarehouseInterior> | null = null;
    let meetingInterior: ReturnType<typeof createMeetingInterior> | null = null;
    const ensureWarehouseInterior = () => {
      if (warehouseInterior) return warehouseInterior;
      warehouseInterior = createWarehouseInterior(
        hotspots.filter((item) => item.scene_key === "warehouse-interior"),
        clickTargets,
        pulses
      );
      scene.add(warehouseInterior.root);
      loadedSceneKeys.add("warehouse-interior");
      host.dataset.loadedScenes = [...loadedSceneKeys].join(",");
      return warehouseInterior;
    };
    const ensureMeetingInterior = () => {
      if (meetingInterior) return meetingInterior;
      meetingInterior = createMeetingInterior(
        hotspots.filter((item) => item.scene_key === "decision-room-interior"),
        actors,
        meetingDataRef.current,
        clickTargets,
        pulses
      );
      scene.add(meetingInterior.root);
      loadedSceneKeys.add("decision-room-interior");
      host.dataset.loadedScenes = [...loadedSceneKeys].join(",");
      return meetingInterior;
    };
    const routeBySource = new Map(routes.map((route) => [route.source_space_key, route]));
    const avatarRigs = new Map<string, AvatarRig>();
    for (const actor of actors) {
      const rig = createAvatar(actor, routeBySource.get(actor.home_space_key));
      world.add(rig.root);
      clickTargets.push(rig.root);
      avatarRigs.set(actor.key, rig);
    }
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2(2, 2);
    let pointerDownAt: { x: number; y: number } | null = null;
    let dragged = false;
    let hoveredKey: string | null = null;
    let guidedCamera = true;
    let navigationKey = "";
    let cameraPreset = {
      position: new THREE.Vector3(22, 14, 28),
      lookAt: new THREE.Vector3(0, 3.8, 0)
    };
    let frame = 0;
    let firstFrame = true;
    const clock = new THREE.Clock();
    const updatePointer = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    };
    const resolveInteractiveHit = () => {
      const hits = raycaster.intersectObjects(clickTargets, true);
      return hits.sort((left, right) => {
        const priorityDelta = Number(right.object.userData.interactionPriority ?? 0)
          - Number(left.object.userData.interactionPriority ?? 0);
        return priorityDelta || left.distance - right.distance;
      })[0];
    };
    const onPointerMove = (event: PointerEvent) => {
      updatePointer(event);
      if (pointerDownAt && Math.hypot(event.clientX - pointerDownAt.x, event.clientY - pointerDownAt.y) > 6) dragged = true;
      raycaster.setFromCamera(pointer, camera);
      const hit = resolveInteractiveHit();
      hoveredKey = typeof hit?.object.userData.entityKey === "string"
        ? hit.object.userData.entityKey
        : null;
      renderer.domElement.style.cursor = hoveredKey
        ? "pointer"
        : cameraInteractionModeRef.current === "pan" ? "move" : "grab";
    };
    const onPointerLeave = () => {
      pointer.set(2, 2);
      pointerDownAt = null;
      hoveredKey = null;
      renderer.domElement.style.cursor = cameraInteractionModeRef.current === "pan" ? "move" : "grab";
    };
    const onPointerDown = (event: PointerEvent) => {
      updatePointer(event);
      pointerDownAt = { x: event.clientX, y: event.clientY };
      dragged = false;
    };
    const onPointerUp = (event: PointerEvent) => {
      updatePointer(event);
      pointerDownAt = null;
      if (dragged) return;
      raycaster.setFromCamera(pointer, camera);
      const key = resolveInteractiveHit()?.object.userData.entityKey;
      if (typeof key === "string") callbackRef.current(key);
    };
    const onDoubleClick = (event: MouseEvent) => {
      updatePointer(event as PointerEvent);
      raycaster.setFromCamera(pointer, camera);
      const key = resolveInteractiveHit()?.object.userData.entityKey;
      if (typeof key !== "string") return;
      const interaction = interactionsRef.current.find((item) => item.entity_key === key);
      if (interaction?.enter_space_key) enterRef.current(interaction.enter_space_key);
    };
    const onControlsStart = () => { guidedCamera = false; };
    controls.addEventListener("start", onControlsStart);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerleave", onPointerLeave);
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointerup", onPointerUp);
    renderer.domElement.addEventListener("dblclick", onDoubleClick);
    const resize = () => {
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      renderer.setSize(width, height, false);
      composer.setSize(width, height);
      composer.setPixelRatio(Math.min(window.devicePixelRatio, 1.7));
      camera.aspect = width / height;
      camera.fov = camera.aspect < 0.75 ? 53 : 42;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    const animate = () => {
      const delta = Math.min(clock.getDelta(), 0.05);
      const elapsed = clock.elapsedTime;
      const warehouseActive = detailRef.current === "warehouse-interior";
      const meetingActive = detailRef.current === "decision-room-interior";
      const detailActive = warehouseActive || meetingActive;
      controls.mouseButtons.LEFT = cameraInteractionModeRef.current === "pan"
        ? THREE.MOUSE.PAN
        : THREE.MOUSE.ROTATE;
      controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
      host.dataset.cameraInteractionMode = cameraInteractionModeRef.current;
      if (warehouseActive) ensureWarehouseInterior();
      if (meetingActive) ensureMeetingInterior();
      world.visible = !detailActive;
      if (warehouseInterior) {
        warehouseInterior.root.visible = warehouseActive;
        for (const [layerKey, group] of warehouseInterior.layerGroups) {
          group.visible = activeLayersRef.current.includes(layerKey);
        }
      }
      if (meetingInterior) {
        meetingInterior.root.visible = meetingActive;
        for (const [layerKey, group] of meetingInterior.layerGroups) {
          group.visible = activeLayersRef.current.includes(layerKey);
        }
      }
      const nextNavigationKey = `${detailRef.current ?? "campus"}:${focusRef.current}:${resetRef.current}`;
      if (nextNavigationKey !== navigationKey) {
        navigationKey = nextNavigationKey;
        guidedCamera = true;
        controls.enabled = false;
        const pose = resolveCameraPose(scenesRef.current, detailRef.current, focusRef.current);
        cameraPreset = {
          position: new THREE.Vector3(...pose.position),
          lookAt: new THREE.Vector3(...pose.lookAt)
        };
      }
      controls.minDistance = detailActive ? 4.5 : 12;
      controls.maxDistance = detailActive ? 30 : 118;
      const targetPosition = cameraPreset.position.clone().multiplyScalar(camera.aspect < 0.75 ? 1.24 : 1);
      if (guidedCamera) {
        camera.position.lerp(targetPosition, reducedMotion ? 0.16 : 0.055);
        currentLookAt.lerp(cameraPreset.lookAt, reducedMotion ? 0.16 : 0.07);
        controls.target.copy(currentLookAt);
        camera.lookAt(currentLookAt);
        if (camera.position.distanceTo(targetPosition) < 0.08 && currentLookAt.distanceTo(cameraPreset.lookAt) < 0.06) {
          guidedCamera = false;
          controls.enabled = true;
        }
      } else {
        controls.enabled = true;
        controls.update();
        currentLookAt.copy(controls.target);
      }
      if (frame % 12 === 0) {
        host.dataset.cameraPosition = camera.position.toArray().map((value) => value.toFixed(2)).join(",");
        host.dataset.cameraTarget = controls.target.toArray().map((value) => value.toFixed(2)).join(",");
      }
      const interior = focusRef.current !== "campus";
      for (const shellMaterial of shellMaterials) {
        if (shellMaterial instanceof THREE.MeshPhysicalMaterial) shellMaterial.opacity += ((interior ? 0.055 : 0.2) - shellMaterial.opacity) * 0.04;
      }
      for (const [key, accent] of accentMaterials) {
        if (accent instanceof THREE.MeshPhysicalMaterial) {
          const targetIntensity = selectedRef.current === key ? 0.48 : hoveredKey === key ? 0.23 : 0.08;
          accent.emissiveIntensity += (targetIntensity - accent.emissiveIntensity) * 0.08;
        }
      }
      for (const [key, roof] of roofMaterials) {
        const reveal = selectedRef.current === key && focusRef.current !== "campus";
        const targetOpacity = reveal ? 0.16 : hoveredKey === key ? 0.58 : 0.9;
        roof.opacity += (targetOpacity - roof.opacity) * 0.08;
        roof.emissiveIntensity += ((reveal ? 0.16 : 0.04) - roof.emissiveIntensity) * 0.08;
      }
      for (const [key, outline] of outlineMaterials) {
        const targetOpacity = selectedRef.current === key ? 1 : hoveredKey === key ? 0.72 : 0.4;
        outline.opacity += (targetOpacity - outline.opacity) * 0.12;
        outline.color.setHex(selectedRef.current === key ? 0xc8fff1 : SPACE_COLORS[spaces.find((item) => item.key === key)?.space_type ?? ""] ?? 0x6d9b91);
      }
      for (const [key, selectionFrame] of selectionFrameMaterials) {
        const targetOpacity = selectedRef.current === key ? 0.95 : hoveredKey === key ? 0.42 : 0;
        selectionFrame.opacity += (targetOpacity - selectionFrame.opacity) * 0.14;
      }
      for (const [key, root] of roomRoots) {
        const targetScale = selectedRef.current === key ? 1.022 : hoveredKey === key ? 1.008 : 1;
        root.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.08);
      }
      if (warehouseInterior) {
        for (const [key, root] of warehouseInterior.hotspotRoots) {
          const targetScale = selectedRef.current === key ? 1.14 : hoveredKey === key ? 1.06 : 1;
          root.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.1);
        }
      }
      if (meetingInterior) {
        for (const [key, root] of meetingInterior.hotspotRoots) {
          const targetScale = selectedRef.current === key ? 1.14 : hoveredKey === key ? 1.06 : 1;
          root.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.1);
        }
        for (const [key, root] of meetingInterior.seatRoots) {
          const targetScale = selectedRef.current === key ? 1.12 : hoveredKey === key ? 1.05 : 1;
          root.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.1);
        }
        for (const [key, indicator] of meetingInterior.seatIndicators) {
          const baseOpacity = Number(indicator.userData.baseOpacity ?? 0.18);
          const targetOpacity = selectedRef.current === key ? 0.98 : hoveredKey === key ? 0.62 : baseOpacity;
          indicator.opacity += (targetOpacity - indicator.opacity) * 0.12;
          indicator.color.setHex(
            selectedRef.current === key
              ? 0xc8fff1
              : Number(indicator.userData.baseColor ?? 0x597a73)
          );
        }
      }
      const gathering = meetingRef.current === "convening";
      const atMeeting = meetingRef.current === "in_session" || meetingRef.current === "decision_ready";
      let actorIndex = 0;
      for (const [key, rig] of avatarRigs) {
        const targetProgress = gathering || atMeeting ? 1 : 0;
        const travelSpeed = gathering ? 0.21 : 0.36;
        if (rig.progress < targetProgress) rig.progress = Math.min(targetProgress, rig.progress + delta * travelSpeed);
        else if (rig.progress > targetProgress) rig.progress = Math.max(targetProgress, rig.progress - delta * travelSpeed);
        if (rig.route) rig.route.getPoint(rig.progress, rig.root.position);
        const walking = Math.abs(targetProgress - rig.progress) > 0.008;
        rig.root.position.y += walking ? Math.abs(Math.sin(elapsed * 7 + rig.phase)) * 0.08 : Math.sin(elapsed * 1.5 + rig.phase) * 0.018;
        rig.root.rotation.y = walking ? Math.sin(elapsed * 0.9 + rig.phase) * 0.18 : 0;
        rig.leftArm.rotation.x = walking ? Math.sin(elapsed * 7 + rig.phase) * 0.56 : 0;
        rig.rightArm.rotation.x = walking ? -Math.sin(elapsed * 7 + rig.phase) * 0.56 : 0;
        const speaking = atMeeting && Math.floor(elapsed / 3.2) % avatarRigs.size === actorIndex;
        if (speaking) {
          rig.rightArm.rotation.z = -0.42 + Math.sin(elapsed * 4) * 0.08;
          (rig.halo.material as THREE.MeshBasicMaterial).opacity = 0.9;
          rig.halo.scale.setScalar(1 + Math.sin(elapsed * 4) * 0.08);
        } else {
          rig.rightArm.rotation.z *= 0.9;
          (rig.halo.material as THREE.MeshBasicMaterial).opacity = selectedRef.current === key
            ? 0.9
            : hoveredKey === key ? 0.7 : 0.45;
          rig.halo.scale.lerp(new THREE.Vector3(1, 1, 1), 0.1);
        }
        actorIndex += 1;
      }
      if (meetingInterior) {
        let meetingActorIndex = 0;
        for (const [key, rig] of meetingInterior.avatarRigs) {
          const targetProgress = gathering || atMeeting ? 1 : 0;
          const travelSpeed = gathering ? 0.28 : 0.42;
          if (rig.progress < targetProgress) rig.progress = Math.min(targetProgress, rig.progress + delta * travelSpeed);
          else if (rig.progress > targetProgress) rig.progress = Math.max(targetProgress, rig.progress - delta * travelSpeed);
          if (rig.route) rig.route.getPoint(rig.progress, rig.root.position);
          const walking = Math.abs(targetProgress - rig.progress) > 0.008;
          rig.root.position.y += walking ? Math.abs(Math.sin(elapsed * 7.2 + rig.phase)) * 0.07 : Math.sin(elapsed * 1.7 + rig.phase) * 0.018;
          if (walking) rig.root.rotation.y = Math.sin(elapsed * 0.9 + rig.phase) * 0.13;
          else rig.root.lookAt(new THREE.Vector3(0, rig.root.position.y, 0.2));
          rig.leftArm.rotation.x = walking ? Math.sin(elapsed * 7.2 + rig.phase) * 0.56 : 0;
          rig.rightArm.rotation.x = walking ? -Math.sin(elapsed * 7.2 + rig.phase) * 0.56 : 0;
          const speaking = atMeeting && Math.floor(elapsed / 3.2) % meetingInterior.avatarRigs.size === meetingActorIndex;
          if (speaking) {
            rig.rightArm.rotation.z = -0.44 + Math.sin(elapsed * 4.2) * 0.08;
            (rig.halo.material as THREE.MeshBasicMaterial).opacity = 0.94;
            rig.halo.scale.setScalar(1.08 + Math.sin(elapsed * 4.2) * 0.08);
          } else {
            rig.rightArm.rotation.z *= 0.9;
            (rig.halo.material as THREE.MeshBasicMaterial).opacity = selectedRef.current === key
              ? 0.92
              : hoveredKey === key ? 0.72 : 0.48;
            rig.halo.scale.lerp(new THREE.Vector3(1, 1, 1), 0.1);
          }
          meetingActorIndex += 1;
        }
      }
      for (const pulse of pulses) {
        pulse.curve.getPoint((pulse.offset + elapsed * pulse.speed) % 1, pulse.mesh.position);
        pulse.mesh.scale.setScalar(0.8 + Math.sin(elapsed * 5 + pulse.offset * 10) * 0.2);
      }
      world.traverse((object) => {
        if (object.userData.campusStars) object.rotation.y = elapsed * 0.008;
        if (object.userData.campusLamp && object instanceof THREE.Mesh) {
          ((object.material as THREE.MeshBasicMaterial).opacity = 0.32 + Math.sin(elapsed * 2.8) * 0.14);
        }
        if (object.userData.operationalRing) object.rotation.z = elapsed * 0.2;
        if (object.userData.operationalCore) object.rotation.y = elapsed * 0.3;
        if (object.userData.knowledgeCore) object.rotation.y = -elapsed * 0.22;
        if (object.userData.warningBeacon) ((object as THREE.Mesh).material as THREE.MeshBasicMaterial).opacity = 0.45 + Math.sin(elapsed * 4.5) * 0.35;
        if (object.userData.meetingRing) object.rotation.z = elapsed * 0.35;
      });
      warehouseInterior?.root.traverse((object) => {
        if (object.userData.warehouseCeilingLight && object instanceof THREE.Mesh) {
          ((object.material as THREE.MeshBasicMaterial).opacity = 0.44 + Math.sin(elapsed * 1.8) * 0.12);
        }
        if (object.userData.hotspotRing) {
          object.rotation.z = elapsed * 0.55 + Number(object.userData.phase ?? 0);
          object.scale.setScalar(1 + Math.sin(elapsed * 2.8 + Number(object.userData.phase ?? 0)) * 0.08);
        }
        if (object.userData.hotspotBeam && object instanceof THREE.Mesh) {
          (object.material as THREE.MeshBasicMaterial).opacity = 0.28 + Math.sin(elapsed * 3.2) * 0.16;
        }
      });
      if (meetingInterior) {
        meetingInterior.root.traverse((object) => {
          if (object.userData.meetingCeilingRing) object.rotation.z = elapsed * 0.08;
          if (object.userData.meetingInteriorRing) object.rotation.z = elapsed * 0.32;
          if (object.userData.meetingEvidenceCore) {
            object.rotation.y = elapsed * 0.28;
            object.position.y = 2.05 + Math.sin(elapsed * 1.6) * 0.08;
          }
          if (object.userData.meetingConflict) {
            object.rotation.y = -elapsed * 0.36;
            object.scale.setScalar(1 + Math.sin(elapsed * 2.4) * 0.08);
          }
          if (object.userData.meetingConflictOrbit) object.rotation.z = elapsed * 0.4;
        });
        for (const decisionMaterial of meetingInterior.decisionMaterials) {
          const targetIntensity = meetingRef.current === "decision_ready" ? 0.82 : meetingRef.current === "in_session" ? 0.3 : 0.12;
          decisionMaterial.emissiveIntensity += (targetIntensity - decisionMaterial.emissiveIntensity) * 0.08;
          decisionMaterial.emissive.setHex(meetingRef.current === "decision_ready" ? 0xf2c66d : 0x6d6441);
        }
      }
      if (warehouseInterior) {
        for (const [index, item] of warehouseInterior.automationParts.entries()) {
          item.position.x = Math.sin(elapsed * 0.38 + index) * 2.7;
        }
      }
      composer.render();
      if (firstFrame) { host.dataset.renderState = "ready"; firstFrame = false; }
      frame = window.requestAnimationFrame(animate);
    };
    animate();
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      controls.removeEventListener("start", onControlsStart);
      controls.dispose();
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerleave", onPointerLeave);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("dblclick", onDoubleClick);
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.LineSegments) {
          object.geometry?.dispose();
          for (const item of Array.isArray(object.material) ? object.material : [object.material]) item.dispose();
        } else if (object instanceof THREE.Sprite) {
          const spriteMaterial = object.material as THREE.SpriteMaterial;
          spriteMaterial.map?.dispose();
          spriteMaterial.dispose();
        }
      });
      composer.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [sceneProjection.key, sceneProjection.version]);

  return (
    <div
      className="enterprise-twin-scene"
      data-camera-mode={cameraInteractionMode}
      data-detail-scene={detailSceneKey ?? "campus"}
      data-focus={focus}
      data-selected-key={selectedKey}
      ref={hostRef}
    />
  );
}
