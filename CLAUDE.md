# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Business context

Agentiva is an Argentine AI-automation platform targeting SMBs.
Four product lines: (1) customer service & conversational AI (WhatsApp-first),
(2) administrative & fiscal tasks (AFIP/ARCA invoicing), (3) marketing & sales,
(4) HR & talent management.

Language: Argentine Spanish (rioplatense). Dollar amounts → U$S (never USD or bare $).
Copy style: punchy headlines, ≤2-sentence elaboration, no bullet lists on homepage,
left-aligned eyebrows, ≤3 article cards in the Recursos section.

# Deployment

Commit and push to `main` → Vercel auto-deploys to agentiva.com.ar in ~30 s.
Always verify changes on **agentiva.com.ar**, not localhost.
GitHub repo: `M477iA/Agentiva.website` (private).
Local dev fallback: `python -m http.server 8080` → `http://localhost:8080`.

# Active integrations

- **EmailJS**: wired but inactive — 3 constants need filling in the last `<script>` block:
  `EMAILJS_PUBLIC_KEY`, `EMAILJS_SERVICE_ID`, `EMAILJS_TEMPLATE_ID`.
  Requires `no-reply@agentiva.com.ar` mailbox on Zoho Mail first.
- **ElevenLabs voice agent**: ID `agent_0101kqe5t2hxf2gtf5y60pe4jtm7` ("Agentiva receptionist").
  Shadow-DOM patches via MutationObserver (branding hidden, UI in Spanish).
  Client tools: scroll-to-section, teal-pulse highlight, booking CTA.

# Architecture

Static HTML + React. Single page: `index.html`. Tweaks panel: `tweaks-panel.jsx`. No build tooling.

- `index.html` — all CSS (~950 lines inline in `<style>`), all vanilla JS (sections at bottom of `<body>`), and full HTML markup. No external stylesheet.
- `tweaks-panel.jsx` — React 18 component library for a floating live design-tweaks panel. Loaded via `<script type="text/babel">` and transpiled at runtime by Babel Standalone from CDN.
- CDN deps (unpkg): React 18.3.1 + ReactDOM dev builds, Babel Standalone 7.29.0. Intentionally dev builds to support runtime JSX.
- All four themes, typography scale, and layout toggles are controlled via body-class changes and CSS custom property overrides driven by the tweaks panel (`useTweaks()` hook → `React.useEffect` → `document.body.classList` / `style.setProperty`).

# CSS / Theming

Design tokens live on `:root` — `--bg`, `--bone`, `--teal`, `--graphite`, `--slate`, `--mist`, `--hairline`, `--accent`, `--display-font`, `--body-font`, `--mono-font`.

Theme classes on `<body>`: `theme-bright`, `theme-midnight`, `theme-paper`, default dark.

Toggle classes on `<body>`: `no-video`, `no-grade`, `no-noise`, `no-corners`, `no-schematic`, `glow-on`, `solid-bg`, `layout-center`, `layout-right`.

# EDITMODE blocks

Tweak defaults in `index.html` are wrapped in `/*EDITMODE-BEGIN*/ … /*EDITMODE-END*/` comments. The tweaks host (parent iframe) rewrites this block to persist changes. Never remove these comment markers.

# Asset paths

- Nav/footer logo: `assets/images/logos/Agentiva Logo esteso.png` (horizontal wordmark)
- Favicon: `assets/images/logos/agentiva-logo.png` — the "A" icon ONLY, never the wordmark
- Partner logos: `assets/images/partners/` (12 files, all greyscale in carousel)
- Client logos: `assets/images/clients/` (6 files — Campaso, D&A Tango, Fare, Mayorista Omega, Pacifican Group, Senor Tango)
- Hero background video: `assets/hero-bg.mp4`

# Non-obvious design rules

- Hero h1 stays **black** on `theme-bright` — never override to white
- Card deck = `position: absolute` stack + Z-rotation fan — NOT flex column
- Active card = `#0A0A0A` bg, white text; teal accents (`var(--teal)`) stay teal
- Partner carousel: `grayscale(100%) brightness(0.4)`, no labels, seamless `-50%` loop
- Broken decorative elements → remove rather than reposition
- All hero ticks use `■` (teal), all hero metadata text uses cream `rgba(245,242,236,0.65–0.80)`
- Client logos: real brand colors, height 52px, no filter
- Mobile (≤720px): card deck collapses to single active card (absolute positioning disabled); hamburger nav replaces inline links
- HLS video (Integraciones section): hls.js `<script>` must load BEFORE the main script block; requires `hls.on(Hls.Events.MANIFEST_PARSED, () => video.play())` — Chrome won't autoplay HLS otherwise
