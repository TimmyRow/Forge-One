import RAPIER from "@dimforge/rapier3d-compat";
import * as THREE from "three";

export interface BoxColliderSpec { position: [number, number, number]; half: [number, number, number] }

const ROOM_COLLIDERS: BoxColliderSpec[] = [
  { position: [0, -0.1, 0], half: [4.5, 0.1, 4] },
  { position: [0, 1.5, -4], half: [4.5, 1.5, 0.1] },
  { position: [-4.5, 1.5, 0], half: [0.1, 1.5, 4] },
  { position: [4.5, 1.5, 0], half: [0.1, 1.5, 4] },
  { position: [0, 0.45, -2.3], half: [1.15, 0.45, 1.1] },
  { position: [-1.65, 0.4, -2.75], half: [0.42, 0.4, 0.42] },
  { position: [1.65, 0.4, -2.75], half: [0.42, 0.4, 0.42] },
  { position: [3.55, 1.15, -2.65], half: [0.75, 1.15, 0.75] },
  { position: [-3.35, 0.4, 1.65], half: [1.0, 0.4, 0.55] },
  { position: [-2.6, 1.5, 3.95], half: [1.9, 1.5, 0.1] },
  { position: [2.6, 1.5, 3.95], half: [1.9, 1.5, 0.1] },
];

const FRONT_WALL_COLLIDERS: BoxColliderSpec[] = [
  { position: [-2.6, 1.5, 3.95], half: [1.9, 1.5, 0.1] },
  { position: [2.6, 1.5, 3.95], half: [1.9, 1.5, 0.1] },
];

export class BedroomPhysics {
  private constructor(
    readonly world: RAPIER.World,
    private readonly body: RAPIER.RigidBody,
    private readonly collider: RAPIER.Collider,
    private readonly controller: RAPIER.KinematicCharacterController,
    private readonly doorBody: RAPIER.RigidBody,
    private doorCollider: RAPIER.Collider | null,
  ) {}

  static async create(authoredColliders: BoxColliderSpec[] = []): Promise<BedroomPhysics> {
    await RAPIER.init();
    const world = new RAPIER.World({ x: 0, y: -9.81, z: 0 });
    const colliders = authoredColliders.length > 0
      ? [...authoredColliders, ...FRONT_WALL_COLLIDERS]
      : ROOM_COLLIDERS;
    for (const spec of colliders) {
      const body = world.createRigidBody(RAPIER.RigidBodyDesc.fixed().setTranslation(...spec.position));
      world.createCollider(RAPIER.ColliderDesc.cuboid(...spec.half), body);
    }
    const body = world.createRigidBody(RAPIER.RigidBodyDesc.kinematicPositionBased().setTranslation(0, 1.0, 2.8));
    const collider = world.createCollider(RAPIER.ColliderDesc.capsule(0.58, 0.32), body);
    const doorBody = world.createRigidBody(RAPIER.RigidBodyDesc.fixed().setTranslation(0, 1.175, 3.9));
    const doorCollider = world.createCollider(RAPIER.ColliderDesc.cuboid(0.65, 1.175, 0.12), doorBody);
    const controller = world.createCharacterController(0.04);
    controller.enableAutostep(0.35, 0.2, true);
    controller.enableSnapToGround(0.22);
    controller.setApplyImpulsesToDynamicBodies(true);
    return new BedroomPhysics(world, body, collider, controller, doorBody, doorCollider);
  }

  update(dt: number, direction: THREE.Vector3, sprint: boolean): THREE.Vector3 {
    const speed = sprint ? 3.9 : 2.35;
    const movement = { x: direction.x * speed * dt, y: -0.7 * dt, z: direction.z * speed * dt };
    this.controller.computeColliderMovement(this.collider, movement);
    const corrected = this.controller.computedMovement();
    const position = this.body.translation();
    this.body.setNextKinematicTranslation({ x: position.x + corrected.x, y: position.y + corrected.y, z: position.z + corrected.z });
    this.world.step();
    const next = this.body.translation();
    return new THREE.Vector3(next.x, next.y + 0.62, next.z);
  }

  reset(): void {
    this.body.setTranslation({ x: 0, y: 1, z: 2.8 }, true);
    if (!this.doorCollider) {
      this.doorCollider = this.world.createCollider(RAPIER.ColliderDesc.cuboid(0.65, 1.175, 0.12), this.doorBody);
    }
  }

  unlockDoor(): void {
    if (!this.doorCollider) return;
    this.world.removeCollider(this.doorCollider, true);
    this.doorCollider = null;
  }
}
