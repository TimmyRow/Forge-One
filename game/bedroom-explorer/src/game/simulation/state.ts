export type GamePhase = "menu" | "playing" | "paused" | "complete";
export type CollectibleId = "key" | "photo" | "journal";

export interface GameState {
  phase: GamePhase;
  collected: Set<CollectibleId>;
  doorUnlocked: boolean;
  elapsedSeconds: number;
}

const SAVE_KEY = "forge-room-one-save-v1";

export function createGameState(): GameState {
  return { phase: "menu", collected: new Set(), doorUnlocked: false, elapsedSeconds: 0 };
}

export function collectItem(state: GameState, id: CollectibleId): boolean {
  if (state.collected.has(id)) return false;
  state.collected.add(id);
  state.doorUnlocked = state.collected.size === 3;
  saveGame(state);
  return true;
}

export function resetGame(state: GameState): void {
  state.phase = "menu";
  state.collected.clear();
  state.doorUnlocked = false;
  state.elapsedSeconds = 0;
  localStorage.removeItem(SAVE_KEY);
}

export function saveGame(state: GameState): void {
  localStorage.setItem(SAVE_KEY, JSON.stringify({
    collected: [...state.collected],
    doorUnlocked: state.doorUnlocked,
    elapsedSeconds: state.elapsedSeconds,
  }));
}

export function loadGame(state: GameState): boolean {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) return false;
    const saved = JSON.parse(raw) as { collected?: CollectibleId[]; doorUnlocked?: boolean; elapsedSeconds?: number };
    state.collected = new Set((saved.collected ?? []).filter((id): id is CollectibleId => ["key", "photo", "journal"].includes(id)));
    state.doorUnlocked = state.collected.size === 3 || Boolean(saved.doorUnlocked);
    state.elapsedSeconds = Number.isFinite(saved.elapsedSeconds) ? Number(saved.elapsedSeconds) : 0;
    return state.collected.size > 0;
  } catch {
    return false;
  }
}

export function objectiveText(state: GameState): string {
  if (state.phase === "complete") return "You found the memory and left Room One.";
  if (state.doorUnlocked) return "The brass key hums. Open the bedroom door.";
  const remaining = 3 - state.collected.size;
  return `Find ${remaining} memory fragment${remaining === 1 ? "" : "s"}.`;
}
