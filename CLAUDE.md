# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Agentiva Landing Page

Static HTML + React. Single page: `index.html`. Tweaks panel: `tweaks-panel.jsx`. No build tooling.

## Development

Serve locally with:
```
python -m http.server 8080
```
Open `http://localhost:8080`. No lint or test commands exist.

## Architecture

- `index.html` — all CSS (~950 lines inline in `<style>`), all vanilla JS (sections at bottom of `<body>`), and full HTML markup. No external stylesheet.
- `tweaks-panel.jsx` — React 18 component library for a floating live design-tweaks panel. Loaded via `<script type="text/babel">` and transpiled at runtime by Babel Standalone from CDN.
- CDN deps (unpkg): React 18.3.1 + ReactDOM dev builds, Babel Standalone 7.29.0. Intentionally dev builds to support runtime JSX.
- All four themes, typography scale, and layout toggles are controlled via body-class changes and CSS custom property overrides driven by the tweaks panel (`useTweaks()` hook → `React.useEffect` → `document.body.classList` / `style.setProperty`).

## CSS / Theming

Design tokens live on `:root` — `--bg`, `--bone`, `--teal`, `--graphite`, `--slate`, `--mist`, `--hairline`, `--accent`, `--display-font`, `--body-font`, `--mono-font`.

Theme classes on `<body>`: `theme-bright`, `theme-midnight`, `theme-paper`, default dark.

Toggle classes on `<body>`: `no-video`, `no-grade`, `no-noise`, `no-corners`, `no-schematic`, `glow-on`, `solid-bg`, `layout-center`, `layout-right`.

## EDITMODE blocks

Tweak defaults in `index.html` are wrapped in `/*EDITMODE-BEGIN*/ … /*EDITMODE-END*/` comments. The tweaks host (parent iframe) rewrites this block to persist changes. Never remove these comment markers.

## Asset paths

- Nav/footer logo: `assets/images/logos/Agentiva Logo esteso.png` (horizontal wordmark)
- Favicon: `assets/images/logos/agentiva-logo.png` — the "A" icon ONLY, never the wordmark
- Partner logos: `assets/images/partners/` (12 files, all greyscale in carousel)
- Client logos: `assets/images/clients/` (6 files — Campaso, D&A Tango, Fare, Mayorista Omega, Pacifican Group, Senor Tango)
- Hero background video: `assets/hero-bg.mp4`

## Non-obvious design rules

- Hero h1 stays **black** on `theme-bright` — never override to white
- Card deck = `position: absolute` stack + Z-rotation fan — NOT flex column
- Active card = `#0A0A0A` bg, white text; teal accents (`var(--teal)`) stay teal
- Partner carousel: `grayscale(100%) brightness(0.4)`, no labels, seamless `-50%` loop
- Broken decorative elements → remove rather than reposition
- All hero ticks use `■` (teal), all hero metadata text uses cream `rgba(245,242,236,0.65–0.80)`
