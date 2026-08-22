/**
 * Room One visual language.
 *
 * Keep this file free of Three.js imports so the renderer, DOM HUD, and loading
 * screen can share the same values without increasing the initial bundle.
 */

export const palette = {
  night: {
    void: "#080D15",
    deep: "#0D1522",
    room: "#151E2B",
    lifted: "#202B39",
    moon: "#9DC7E8",
  },
  warm: {
    candle: "#FFD6A0",
    honey: "#E6A45B",
    terracotta: "#C96D52",
    parchment: "#F4E1B5",
    walnut: "#6E4430",
  },
  neutral: {
    chalk: "#FFF8EB",
    linen: "#D8D0C2",
    mist: "#AEB8C4",
    slate: "#566474",
    ink: "#101721",
  },
  signal: {
    interact: "#63D5FF",
    objective: "#FFD166",
    collected: "#8EE6A8",
    warning: "#FF8B73",
    focus: "#D6A8FF",
  },
} as const;

export const materials = {
  paintedWall: {
    baseColor: "#7A8794",
    roughness: 0.94,
    metalness: 0,
  },
  ceiling: {
    baseColor: "#B7B5AE",
    roughness: 0.98,
    metalness: 0,
  },
  darkWood: {
    baseColor: "#4E3026",
    roughness: 0.68,
    metalness: 0,
  },
  honeyWood: {
    baseColor: "#95623B",
    roughness: 0.62,
    metalness: 0,
  },
  bedding: {
    baseColor: "#5D7180",
    roughness: 0.96,
    metalness: 0,
  },
  linenAccent: {
    baseColor: "#D1BCA1",
    roughness: 1,
    metalness: 0,
  },
  rug: {
    baseColor: "#7E4C43",
    roughness: 1,
    metalness: 0,
  },
  paintedMetal: {
    baseColor: "#39434D",
    roughness: 0.48,
    metalness: 0.58,
  },
  glass: {
    baseColor: "#BCD7E5",
    roughness: 0.12,
    metalness: 0,
    opacity: 0.24,
    transmission: 0.88,
  },
  lampShade: {
    baseColor: "#E8C998",
    roughness: 0.78,
    metalness: 0,
    emissive: "#FFB45E",
    emissiveIntensity: 0.32,
  },
  collectible: {
    baseColor: "#F7D58A",
    roughness: 0.35,
    metalness: 0.12,
    emissive: palette.signal.objective,
    emissiveIntensity: 0.72,
  },
} as const;

export const lighting = {
  renderer: {
    toneMapping: "ACESFilmicToneMapping",
    exposure: 1.12,
    outputColorSpace: "SRGBColorSpace",
    shadowMap: "PCFSoftShadowMap",
  },
  hemisphere: {
    skyColor: "#7798B9",
    groundColor: "#33251F",
    intensity: 0.62,
  },
  moonKey: {
    color: "#A9D4F5",
    intensity: 1.7,
    position: [-3.5, 5.8, -2.5] as const,
    castsShadow: true,
  },
  bedsidePractical: {
    color: "#FFB867",
    intensityCandela: 32,
    distance: 5.2,
    decay: 2,
    castsShadow: true,
  },
  doorwayFill: {
    color: "#F5D8AC",
    intensity: 5.5,
    distance: 4.5,
    decay: 2,
  },
  fog: {
    color: palette.night.deep,
    density: 0.018,
  },
} as const;

export const interactionStyle = {
  available: {
    color: palette.signal.interact,
    emissiveIntensity: 0.52,
    outlineWidthPx: 2,
    icon: "◇",
    motion: "single 900ms breathe, then still",
  },
  objective: {
    color: palette.signal.objective,
    emissiveIntensity: 0.72,
    outlineWidthPx: 3,
    icon: "✦",
    motion: "slow 1.8s halo pulse",
  },
  collected: {
    color: palette.signal.collected,
    emissiveIntensity: 0.2,
    outlineWidthPx: 0,
    icon: "✓",
    motion: "120ms scale-up, 160ms dissolve",
  },
  blocked: {
    color: palette.signal.warning,
    emissiveIntensity: 0.18,
    outlineWidthPx: 2,
    icon: "×",
    motion: "two short lateral nudges",
  },
} as const;

/** Values can be installed on document.documentElement by the HUD entry point. */
export const uiCssVariables = {
  "--room-bg": palette.night.deep,
  "--room-panel": "rgba(13, 21, 34, 0.82)",
  "--room-panel-strong": "rgba(8, 13, 21, 0.94)",
  "--room-panel-border": "rgba(174, 184, 196, 0.25)",
  "--room-text": palette.neutral.chalk,
  "--room-text-muted": "#BCC5CE",
  "--room-accent": palette.signal.interact,
  "--room-objective": palette.signal.objective,
  "--room-success": palette.signal.collected,
  "--room-danger": palette.signal.warning,
  "--room-focus": palette.signal.focus,
  "--room-shadow": "0 10px 36px rgba(0, 0, 0, 0.38)",
  "--room-blur": "blur(10px)",
  "--room-radius": "10px",
  "--room-font-display": '"Trebuchet MS", "Avenir Next", sans-serif',
  "--room-font-body": 'Inter, "Segoe UI", sans-serif',
  "--room-motion-fast": "140ms",
  "--room-motion-calm": "260ms",
} as const satisfies Readonly<Record<string, string>>;

export type ThemeCssVariable = keyof typeof uiCssVariables;

export function installVisualTheme(root: HTMLElement = document.documentElement): void {
  for (const [name, value] of Object.entries(uiCssVariables)) {
    root.style.setProperty(name, value);
  }
}

export const accessibility = {
  minimumTextContrast: "4.5:1",
  minimumLargeTextContrast: "3:1",
  minimumTargetSizePx: 44,
  promptTreatment:
    "Every state pairs color with an icon, label, outline pattern, and short sound; never use hue alone.",
  focusTreatment:
    "2px solid var(--room-focus) with a 3px dark separation ring; visible for keyboard/gamepad focus.",
  reducedMotion:
    "Disable pulses, bobbing, camera sway, and blur transitions under prefers-reduced-motion; retain static outlines and icons.",
} as const;

