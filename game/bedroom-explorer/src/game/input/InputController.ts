export class InputController {
  private readonly keys = new Set<string>();
  private lookX = 0;
  private lookY = 0;
  private interactQueued = false;
  private jumpQueued = false;
  private touchLook: { x: number; y: number; id: number } | null = null;

  constructor(private readonly canvas: HTMLCanvasElement) {
    window.addEventListener("keydown", (event) => {
      this.keys.add(event.code);
      if (event.code === "KeyE") this.interactQueued = true;
      if (event.code === "Space") this.jumpQueued = true;
    });
    window.addEventListener("keyup", (event) => this.keys.delete(event.code));
    window.addEventListener("blur", () => this.keys.clear());
    document.addEventListener("mousemove", (event) => {
      if (document.pointerLockElement !== this.canvas) return;
      this.lookX += event.movementX;
      this.lookY += event.movementY;
    });
    canvas.addEventListener("pointerdown", (event) => {
      if (event.pointerType !== "touch" && document.pointerLockElement === canvas) return;
      this.touchLook = { x: event.clientX, y: event.clientY, id: event.pointerId };
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!this.touchLook || event.pointerId !== this.touchLook.id) return;
      this.lookX += event.clientX - this.touchLook.x;
      this.lookY += event.clientY - this.touchLook.y;
      this.touchLook.x = event.clientX;
      this.touchLook.y = event.clientY;
    });
    const releaseTouchLook = (event: PointerEvent) => { if (this.touchLook?.id === event.pointerId) this.touchLook = null; };
    canvas.addEventListener("pointerup", releaseTouchLook);
    canvas.addEventListener("pointercancel", releaseTouchLook);
    document.querySelectorAll<HTMLElement>("[data-game-key]").forEach((button) => {
      const code = button.dataset.gameKey!;
      button.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        if (code === "KeyE") this.interactQueued = true;
        else this.keys.add(code);
        button.setPointerCapture(event.pointerId);
      });
      const release = () => this.keys.delete(code);
      button.addEventListener("pointerup", release);
      button.addEventListener("pointercancel", release);
    });
  }

  get movement(): { forward: number; right: number; sprint: boolean } {
    return {
      forward: Number(this.keys.has("KeyW") || this.keys.has("ArrowUp")) - Number(this.keys.has("KeyS") || this.keys.has("ArrowDown")),
      right: Number(this.keys.has("KeyD") || this.keys.has("ArrowRight")) - Number(this.keys.has("KeyA") || this.keys.has("ArrowLeft")),
      sprint: this.keys.has("ShiftLeft") || this.keys.has("ShiftRight"),
    };
  }

  consumeLook(): { x: number; y: number } {
    const value = { x: this.lookX, y: this.lookY };
    this.lookX = 0;
    this.lookY = 0;
    return value;
  }

  consumeInteract(): boolean {
    const value = this.interactQueued;
    this.interactQueued = false;
    return value;
  }

  consumeJump(): boolean {
    const value = this.jumpQueued;
    this.jumpQueued = false;
    return value;
  }

  requestPointerLock(): void {
    if (matchMedia("(pointer: coarse)").matches) return;
    void this.canvas.requestPointerLock().catch(() => {
      // Embedded previews may deny pointer lock; drag/touch look and keyboard
      // movement still work, while normal browser tabs receive pointer lock.
    });
  }
}
