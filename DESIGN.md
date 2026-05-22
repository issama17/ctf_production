---
name: CTF_LAB
colors:
  background: "#03060b"
  surface: "#0b101a"
  border: "#162235"
  primary: "#00e676"
  primary-dim: "#00c853"
  secondary: "#00b0ff"
  accent: "#ff66b2"
  accent-dim: "#ff3399"
  danger: "#ff3366"
  warning: "#ffc400"
  text: "#d0dbe8"
  text-dim: "#6b829e"
typography:
  sans: "Rajdhani, sans-serif"
  mono: "JetBrains Mono, monospace"
  brand: "Orbitron, monospace"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
---

# CTF_LAB Design System

This file serves as the official design system specification for the **CTF_LAB** platform. It provides design tokens and visual guidelines for AI agents and design engines (like Google Stitch) to ensure visual coherence, high-tech aesthetics, and modern styling across the platform.

## Visual Identity & Vibe
*   **Vibe:** Sci-Fi / Cyberpunk, high-fidelity security operations center (SOC), dark mode premium, glowing cyber accents.
*   **Atmosphere:** Deep navy/black workspace with sharp neon borders, clean monospaced indicators, subtle shadows, and retro scanline overlays.

## Colors & Tokens
The application relies on a dark palette with vibrant neon accent states:
*   **Background (`{colors.background}`):** `#03060b` - Main window canvas.
*   **Surface (`{colors.surface}`):** `#0b101a` - Challenge cards, forms, modals.
*   **Border (`{colors.border}`):** `#162235` - Accent and inactive dividers.
*   **Primary Green (`{colors.primary}`):** `#00e676` - Active indicators, success alerts, CTF score counts.
*   **Secondary Cyan (`{colors.secondary}`):** `#00b0ff` - Active links, call-to-actions, primary highlights.
*   **Accent Pink (`{colors.accent}`):** `#ff66b2` - Specialized action highlights, targets, and CTF badges.

## Typography
*   **Brand Headers:** `{typography.brand}` (`Orbitron`) is used exclusively for the main platform name and main scoreboard dashboard headers.
*   **General UI:** `{typography.sans}` (`Rajdhani`) is used for titles, cards, labels, and primary navigations.
*   **Code & Metadata:** `{typography.mono}` (`JetBrains Mono`) is used for code outputs, parameters, inputs, and score counts.

## Component Specifications

### 1. Challenge Cards (`.ctf-card`)
*   **Style:** Background `{colors.surface}` (opaque `0.7` with backdrop blur), border `1px solid {colors.border}`, rounded corners (`8px`).
*   **Hover State:** Transformed with slight 3D perspective rotation (`translateY(-2px) rotateY(3deg) rotateX(1deg)`), border glows with `{colors.secondary}`, drops shadow `0 0 15px rgba(0, 230, 118, 0.2)`.
*   **Solved State:** Background repeating linear gradient overlay at 45deg with `{colors.primary}` opacity `0.03`.

### 2. Buttons
*   **Outline Action (`.btn-ctf`):** Transparent base, border `1px solid {colors.secondary}`, text `{colors.secondary}`. Hover gets a cyan glow and background opacity transition.
*   **Solid Action (`.btn-ctf-full`):** Solid `{colors.primary}` background, dark text `#000`. Hover gets a green-dim glow and scanline animation effect.

### 3. Inputs (`.ctf-input`)
*   **Style:** Dark background `#03060b`, border `1px solid {colors.border}`, monospaced font.
*   **Focus State:** Border changes to `{colors.secondary}` with a soft cyan shadow ring (`box-shadow: 0 0 0 2px rgba(0,176,255,.15)`).

## Animations & Transitions
*   **Interactive Glow:** Glowing elements (`.glow`) pulse using `glowPulse` keyframes, scaling text shadows between `{colors.primary}` opacity variations.
*   **Scroll Reveal:** CTF Cards use an `IntersectionObserver` that toggles `.card-visible` (staggered transition delay of `80ms` per index) to slide up cards.
*   **Matrix Scanline:** A subtle repeating scanline overlay runs vertically on the body element using a CSS gradient overlay.

## Do's and Don'ts
*   **DO:** Always use HSL/Hex variables defined above. Keep background dark and backgrounds of overlays translucent to preserve the radial glow.
*   **DON'T:** Do not use default bootstrap primary blues or basic reds. Do not use opaque light backgrounds for card components.
