import * as THREE from "three";
import { DRACOLoader } from "three/examples/jsm/loaders/DRACOLoader.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { lighting, materials, palette } from "../content/visualTheme";

export type InteractableKind = "key" | "photo" | "journal" | "door";
export interface Interactable { kind: InteractableKind; object: THREE.Object3D; label: string; collected: boolean }
export interface ColliderBox { position: [number, number, number]; half: [number, number, number] }

interface GeneratedCollectible {
  url: string;
  name: string;
  position: [number, number, number];
  targetSize: number;
  markerHeight: number;
  rotationY?: number;
}

interface GeneratedReplacement {
  url: string;
  replaces: string;
  name: string;
  position: [number, number, number];
  rotationY?: number;
  scale: [number, number, number];
  replacePrefix?: string;
  replacePrefixes?: string[];
}

const BASE_URL = import.meta.env.BASE_URL;

const GENERATED_REPLACEMENTS: GeneratedReplacement[] = [
  {
    url: `${BASE_URL}assets/models/generated/bed_semantic.glb`, replaces: "Furniture_Bed", name: "ForgeGenerated_Bed",
    position: [0, 0.7, -2.3], scale: [1.5, 1.05, 1.2],
  },
  {
    url: `${BASE_URL}assets/models/generated/nightstand_semantic.glb`, replaces: "Furniture_Nightstand_Left", name: "ForgeGenerated_Nightstand_Left",
    position: [-1.65, 0.4, -2.75], scale: [0.52, 0.42, 0.58],
  },
  {
    url: `${BASE_URL}assets/models/generated/nightstand_semantic.glb`, replaces: "Furniture_Nightstand_Right", name: "ForgeGenerated_Nightstand_Right",
    position: [1.65, 0.4, -2.75], scale: [0.52, 0.42, 0.58],
  },
  {
    url: `${BASE_URL}assets/models/generated/wardrobe_semantic.glb`, replaces: "Furniture_Wardrobe", name: "ForgeGenerated_Wardrobe",
    position: [3.35, 1.09, -2.62], scale: [0.9, 1.15, 1.1],
  },
  {
    url: `${BASE_URL}assets/models/generated/desk_semantic.glb`, replaces: "Furniture_Desk", name: "ForgeGenerated_Desk",
    position: [-3.35, 0.43, 1.65], scale: [1.0, 0.6, 0.85],
  },
  {
    url: `${BASE_URL}assets/models/generated/chair_semantic.glb`, replaces: "Furniture_Chair", name: "ForgeGenerated_Chair",
    position: [-3.35, 0.5, 2.45], rotationY: Math.PI, scale: [0.55, 0.5, 0.55],
  },
  {
    url: `${BASE_URL}assets/models/generated/rug_semantic.glb`, replaces: "Rug_Main", replacePrefix: "Rug_", name: "ForgeGenerated_Rug",
    position: [0, 0.015, 0.65], scale: [1.65, 0.15, 1.45],
  },
  {
    url: `${BASE_URL}assets/models/generated/lamp_semantic.glb`, replaces: "Prop_BedsideLamp", name: "ForgeGenerated_Lamp",
    position: [1.65, 1.15, -2.75], scale: [0.35, 0.35, 0.35],
  },
  {
    url: `${BASE_URL}assets/models/generated/window_semantic.glb`, replaces: "Window_Glass",
    replacePrefixes: ["Window_", "Curtain_"], name: "ForgeGenerated_Window",
    position: [-2.25, 1.19, -3.88], scale: [1, 1, 1],
  },
];

const GENERATED_COLLECTIBLES: Record<"key" | "photo" | "journal", GeneratedCollectible> = {
  key: {
    url: `${BASE_URL}assets/models/generated/key_semantic.glb`, name: "ForgeGenerated_Key",
    position: [-1.65, 0.82, -2.75], targetSize: 0.38, markerHeight: 0.34, rotationY: -0.45,
  },
  photo: {
    url: `${BASE_URL}assets/models/generated/frame_semantic.glb`, name: "ForgeGenerated_PhotoFrame",
    position: [-3.52, 0.84, 1.62], targetSize: 0.36, markerHeight: 0.42, rotationY: 0.12,
  },
  journal: {
    url: `${BASE_URL}assets/models/generated/journal_semantic.glb`, name: "ForgeGenerated_Journal",
    position: [-3.02, 0.87, 1.62], targetSize: 0.5, markerHeight: 0.32, rotationY: 0.22,
  },
};

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
  const windowFill = new THREE.PointLight("#8eaeeb", 2.4, 4.8, 2);
  windowFill.position.set(-2.2, 2.15, -2.7);
  scene.add(windowFill);

  let roomRoot: THREE.Object3D;
  const collisionBoxes: ColliderBox[] = [];
  let key = collectibleKey();
  let photo = collectiblePhoto();
  let journal = collectibleJournal();
  let door: THREE.Object3D = box("ExitDoor", [1.25, 2.35, 0.15], [0, 1.175, 3.92], material("woodDark"));
  (door as THREE.Mesh).geometry.translate(0.625, 0, 0);
  door.position.x = -0.625;
  try {
    const draco = new DRACOLoader();
    draco.setDecoderPath(`${BASE_URL}draco/`);
    const loader = new GLTFLoader();
    loader.setDRACOLoader(draco);
    const gltf = await loader.loadAsync(`${BASE_URL}assets/models/bedroom/cozy_bedroom.glb`);
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
    await Promise.all(GENERATED_REPLACEMENTS.map(async (spec) => {
      try {
        const replacement = (await loader.loadAsync(spec.url)).scene;
        replacement.name = spec.name;
        replacement.position.set(...spec.position);
        replacement.scale.set(...spec.scale);
        replacement.rotation.y = spec.rotationY ?? 0;
        replacement.traverse((object) => {
          if (!(object instanceof THREE.Mesh)) return;
          object.castShadow = true;
          object.receiveShadow = true;
        });
        scene.add(replacement);
        const original = roomRoot.getObjectByName(spec.replaces);
        if (original) original.visible = false;
        if (spec.replacePrefix) {
          roomRoot.traverse((object) => {
            if (object.name.startsWith(spec.replacePrefix!)) object.visible = false;
          });
        }
        if (spec.replacePrefixes) {
          roomRoot.traverse((object) => {
            if (spec.replacePrefixes!.some((prefix) => object.name.startsWith(prefix))) object.visible = false;
          });
        }
      } catch (error) {
        console.warn(`Forge-generated replacement ${spec.name} could not load; keeping the authored fallback.`, error);
      }
    }));

    const loadGeneratedCollectible = async (spec: GeneratedCollectible): Promise<THREE.Group> => {
      const generated = (await loader.loadAsync(spec.url)).scene;
      generated.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        object.castShadow = true;
        object.receiveShadow = true;
      });
      generated.updateMatrixWorld(true);
      const sourceBounds = new THREE.Box3().setFromObject(generated);
      const sourceSize = sourceBounds.getSize(new THREE.Vector3());
      const longestSide = Math.max(sourceSize.x, sourceSize.y, sourceSize.z);
      if (!Number.isFinite(longestSide) || longestSide <= 0) throw new Error(`${spec.name} has invalid bounds.`);
      generated.scale.setScalar(spec.targetSize / longestSide);
      generated.updateMatrixWorld(true);
      const scaledBounds = new THREE.Box3().setFromObject(generated);
      const scaledCenter = scaledBounds.getCenter(new THREE.Vector3());
      generated.position.add(new THREE.Vector3(-scaledCenter.x, -scaledBounds.min.y, -scaledCenter.z));

      const group = new THREE.Group();
      group.name = spec.name;
      group.position.set(...spec.position);
      group.rotation.y = spec.rotationY ?? 0;
      const collectibleMarker = marker();
      collectibleMarker.position.y = spec.markerHeight;
      group.add(generated, collectibleMarker);
      return group;
    };

    const generatedCollectibles = await Promise.allSettled([
      loadGeneratedCollectible(GENERATED_COLLECTIBLES.key),
      loadGeneratedCollectible(GENERATED_COLLECTIBLES.photo),
      loadGeneratedCollectible(GENERATED_COLLECTIBLES.journal),
    ]);
    if (generatedCollectibles[0].status === "fulfilled") key = generatedCollectibles[0].value;
    if (generatedCollectibles[1].status === "fulfilled") photo = generatedCollectibles[1].value;
    if (generatedCollectibles[2].status === "fulfilled") journal = generatedCollectibles[2].value;
    generatedCollectibles.forEach((result) => {
      if (result.status === "rejected") {
        console.warn("A Forge-generated collectible could not load; keeping its authored fallback.", result.reason);
      }
    });

    try {
      const generatedDoor = (await loader.loadAsync(`${BASE_URL}assets/models/generated/door_semantic.glb`)).scene;
      generatedDoor.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        object.castShadow = true;
        object.receiveShadow = true;
      });
      generatedDoor.updateMatrixWorld(true);
      const sourceBounds = new THREE.Box3().setFromObject(generatedDoor);
      const sourceSize = sourceBounds.getSize(new THREE.Vector3());
      if (!Number.isFinite(sourceSize.y) || sourceSize.y <= 0) throw new Error("Generated door has invalid bounds.");
      generatedDoor.scale.setScalar(2.35 / sourceSize.y);
      generatedDoor.updateMatrixWorld(true);
      const scaledBounds = new THREE.Box3().setFromObject(generatedDoor);
      const scaledCenter = scaledBounds.getCenter(new THREE.Vector3());
      // The accepted asset's handle is on local X-min, so local X-max is the true hinge edge.
      generatedDoor.position.add(new THREE.Vector3(-scaledBounds.max.x, -scaledBounds.min.y, -scaledCenter.z));
      const hinge = new THREE.Group();
      hinge.name = "ForgeGenerated_ExitDoor_Hinge";
      hinge.position.set(0.625, 0, 3.92);
      hinge.add(generatedDoor);
      door = hinge;
    } catch (error) {
      console.warn("Forge-generated door could not load; keeping the authored fallback.", error);
    }
    draco.dispose();
    const ceiling = box("RuntimeCeiling", [9.1, 0.1, 8], [0, 3.22, 0], material("wall"));
    ceiling.castShadow = false;
    scene.add(ceiling);
  } catch {
    roomRoot = buildProceduralFallback(scene);
  }

  scene.add(key, photo, journal, door);
  const interactables: Interactable[] = [
    { kind: "key", object: key, label: "Take the brass key", collected: false },
    { kind: "photo", object: photo, label: "Remember the photograph", collected: false },
    { kind: "journal", object: journal, label: "Read the small journal", collected: false },
    { kind: "door", object: door, label: "Try the bedroom door", collected: false },
  ];
  return { scene, camera, renderer, interactables, door, roomRoot, collisionBoxes };
}
