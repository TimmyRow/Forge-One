import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { lighting, materials, palette } from "../content/visualTheme";

export type InteractableKind = "key" | "photo" | "journal" | "door";
export interface Interactable { kind: InteractableKind; object: THREE.Object3D; label: string; collected: boolean }
export interface ColliderBox { position: [number, number, number]; half: [number, number, number] }

type MaterialAlias = "wall" | "wood" | "woodDark" | "fabricLight" | "fabricBlue" | "rug" | "collectible";

function material(name: MaterialAlias): THREE.MeshStandardMaterial {
  const actual = {
    wall: "paintedWall", wood: "honeyWood", woodDark: "darkWood", fabricLight: "linenAccent",
    fabricBlue: "bedding", rug: "rug", collectible: "collectible",
  }[name] as keyof typeof materials;
  const spec = materials[actual];
  return new THREE.MeshStandardMaterial({
    color: spec.baseColor, roughness: spec.roughness, metalness: spec.metalness,
    emissive: "emissive" in spec ? spec.emissive : "#000000",
    emissiveIntensity: "emissiveIntensity" in spec ? spec.emissiveIntensity : 0,
  });
}

function box(name: string, size: [number, number, number], position: [number, number, number], mat: THREE.Material): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), mat);
  mesh.name = name;
  mesh.position.set(...position);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

function marker(): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.OctahedronGeometry(0.065, 0), material("collectible"));
  mesh.position.y = 0.3;
  return mesh;
}

function collectibleKey(): THREE.Group {
  const group = new THREE.Group(); group.name = "Collectible_Key";
  const gold = material("collectible");
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.085, 0.018, 8, 20), gold); ring.position.x = -0.09;
  const shaft = box("KeyShaft", [0.22, 0.035, 0.035], [0.08, 0, 0], gold);
  const tooth = box("KeyTooth", [0.045, 0.075, 0.035], [0.17, -0.025, 0], gold);
  group.add(ring, shaft, tooth, marker()); group.position.set(-1.65, 0.92, -2.75);
  return group;
}

function collectiblePhoto(): THREE.Group {
  const group = new THREE.Group(); group.name = "Collectible_Photo";
  const frame = material("woodDark");
  group.add(box("PhotoTop", [0.38, 0.045, 0.045], [0, 0.22, 0], frame));
  group.add(box("PhotoBottom", [0.38, 0.045, 0.045], [0, -0.22, 0], frame));
  group.add(box("PhotoLeft", [0.045, 0.4, 0.045], [-0.17, 0, 0], frame));
  group.add(box("PhotoRight", [0.045, 0.4, 0.045], [0.17, 0, 0], frame));
  group.add(box("PhotoPrint", [0.29, 0.33, 0.025], [0, 0, 0], material("fabricBlue")), marker());
  group.position.set(-3.3, 1.1, 1.58); return group;
}

function collectibleJournal(): THREE.Group {
  const group = new THREE.Group(); group.name = "Collectible_Journal";
  group.add(box("JournalCover", [0.4, 0.075, 0.5], [0, 0, 0], material("woodDark")));
  group.add(box("JournalPages", [0.35, 0.055, 0.46], [0.015, 0.045, 0], material("fabricLight")), marker());
  group.position.set(3.52, 1.2, -2.0); return group;
}

function buildProceduralFallback(scene: THREE.Scene): THREE.Group {
  const room = new THREE.Group();
  room.name = "BedroomFallback";
  const floor = box("Floor", [9, 0.18, 8], [0, -0.09, 0], material("wood"));
  const back = box("BackWall", [9, 3, 0.18], [0, 1.5, -4], material("wall"));
  const left = box("LeftWall", [0.18, 3, 8], [-4.5, 1.5, 0], material("wall"));
  const right = box("RightWall", [0.18, 3, 8], [4.5, 1.5, 0], material("wall"));
  const ceiling = box("Ceiling", [9, 0.1, 8], [0, 3.2, 0], material("wall"));
  ceiling.castShadow = false;
  room.add(floor, back, left, right, ceiling);

  const bed = new THREE.Group(); bed.name = "Bed";
  bed.add(box("BedFrame", [2.4, 0.34, 2.3], [0, 0.3, -2.35], material("wood")));
  bed.add(box("Mattress", [2.25, 0.28, 2.08], [0, 0.6, -2.3], material("fabricLight")));
  bed.add(box("Blanket", [2.1, 0.12, 1.35], [0, 0.79, -2.05], material("fabricBlue")));
  bed.add(box("Headboard", [2.5, 1.15, 0.16], [0, 1.05, -3.45], material("wood")));
  for (const x of [-0.58, 0.58]) bed.add(box("Pillow", [0.95, 0.18, 0.52], [x, 0.84, -3.05], material("fabricLight")));
  room.add(bed);

  for (const x of [-1.65, 1.65]) {
    room.add(box("Nightstand", [0.78, 0.8, 0.72], [x, 0.4, -2.75], material("wood")));
  }
  room.add(box("Wardrobe", [1.45, 2.3, 1.25], [3.55, 1.15, -2.65], material("woodDark")));
  room.add(box("Desk", [2, 0.12, 1.05], [-3.35, 0.83, 1.65], material("wood")));
  for (const x of [-4.15, -2.55]) room.add(box("DeskLeg", [0.12, 0.82, 0.12], [x, 0.41, 1.65], material("woodDark")));
  room.add(box("Rug", [3.3, 0.025, 2.2], [0, 0.015, 0.65], material("rug")));
  scene.add(room);
  return room;
}

export async function createBedroomScene(canvas: HTMLCanvasElement): Promise<{
  scene: THREE.Scene; camera: THREE.PerspectiveCamera; renderer: THREE.WebGLRenderer;
  interactables: Interactable[]; door: THREE.Object3D; roomRoot: THREE.Object3D; collisionBoxes: ColliderBox[];
}> {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(palette.night.deep);
  scene.fog = new THREE.FogExp2(lighting.fog.color, lighting.fog.density);
  const camera = new THREE.PerspectiveCamera(67, innerWidth / innerHeight, 0.05, 80);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.8));
  renderer.setSize(innerWidth, innerHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = lighting.renderer.exposure;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  scene.add(new THREE.HemisphereLight(lighting.hemisphere.skyColor, lighting.hemisphere.groundColor, lighting.hemisphere.intensity));
  const moon = new THREE.DirectionalLight(lighting.moonKey.color, 1.15);
  moon.position.set(...lighting.moonKey.position); moon.castShadow = true; moon.shadow.mapSize.set(2048, 2048);
  moon.shadow.normalBias = 0.035; moon.shadow.bias = -0.0002;
  moon.shadow.camera.left = -6; moon.shadow.camera.right = 6; moon.shadow.camera.top = 6; moon.shadow.camera.bottom = -6;
  scene.add(moon);
  const lamp = new THREE.PointLight(lighting.bedsidePractical.color, 11, lighting.bedsidePractical.distance, lighting.bedsidePractical.decay);
  lamp.position.set(1.65, 1.45, -2.5); lamp.castShadow = true;
  lamp.shadow.normalBias = 0.025; lamp.shadow.bias = -0.0002; lamp.shadow.mapSize.set(1024, 1024);
  scene.add(lamp);

  let roomRoot: THREE.Object3D;
  const collisionBoxes: ColliderBox[] = [];
  try {
    const gltf = await new GLTFLoader().loadAsync("/assets/models/bedroom/cozy_bedroom.glb");
    roomRoot = gltf.scene;
    roomRoot.name = "BedroomAsset";
    roomRoot.updateMatrixWorld(true);
    roomRoot.traverse((object) => {
      if (object.name.startsWith("COLLIDER_")) {
        const bounds = new THREE.Box3().setFromObject(object);
        const center = bounds.getCenter(new THREE.Vector3());
        const half = bounds.getSize(new THREE.Vector3()).multiplyScalar(0.5);
        if (half.x > 0 && half.y > 0 && half.z > 0) {
          collisionBoxes.push({ position: [center.x, center.y, center.z], half: [half.x, half.y, half.z] });
        }
      }
      if (object.name.startsWith("COLLIDER_") || /^PROP_(Key|PhotoFrame|Journal)_Decor/i.test(object.name)) {
        object.visible = false;
      }
      if (!(object instanceof THREE.Mesh)) return;
      object.castShadow = !object.name.startsWith("COLLIDER_");
      object.receiveShadow = true;
    });
    scene.add(roomRoot);
    const ceiling = box("RuntimeCeiling", [9.1, 0.1, 8], [0, 3.22, 0], material("wall"));
    ceiling.castShadow = false;
    scene.add(ceiling);
  } catch {
    roomRoot = buildProceduralFallback(scene);
  }

  const key = collectibleKey();
  const photo = collectiblePhoto();
  const journal = collectibleJournal();
  const door = box("ExitDoor", [1.25, 2.35, 0.15], [0, 1.175, 3.92], material("woodDark"));
  door.geometry.translate(0.625, 0, 0); door.position.x = -0.625;
  scene.add(key, photo, journal, door);
  const interactables: Interactable[] = [
    { kind: "key", object: key, label: "Take the brass key", collected: false },
    { kind: "photo", object: photo, label: "Remember the photograph", collected: false },
    { kind: "journal", object: journal, label: "Read the small journal", collected: false },
    { kind: "door", object: door, label: "Try the bedroom door", collected: false },
  ];
  return { scene, camera, renderer, interactables, door, roomRoot, collisionBoxes };
}
