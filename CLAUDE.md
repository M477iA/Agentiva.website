# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Business context

Agentiva builds WhatsApp (and adjacent Facebook/Instagram Messenger)
customer-service chatbots for Argentinian SMBs. Narrow specialist positioning
(since 2026-08-17) — not a broad automation platform. Flagship proof point:
Mayorista Omega, live WhatsApp bot, 160+ clients served, U$S 225/mo.
Voice agents and a live chat widget are roadmap items, not part of the
current pitch — don't reintroduce them as headline services.

Language: Argentine Spanish (rioplatense). Dollar amounts → U$S (never USD or bare $).
Copy style: punchy headlines, ≤2-sentence elaboration, no bullet lists on homepage,
left-aligned eyebrows, ≤3 article cards in the Recursos section.

# Deployment

Commit and push to `main` → Vercel auto-deploys to agentiva.com.ar in ~30 s.
Always verify changes on **agentiva.com.ar**, not localhost.
GitHub repo: `M477iA/Agentiva.website` (private).
Local dev fallback: `python -m http.server 8080` → `http://localhost:8080`.

# Active integrations

- **EmailJS**: removed entirely in commit `44e3906` (2026-05-11) when auth moved to Supabase — it was a welcome-email-on-registration trigger, not a general contact form. No contact form currently exists; the site relies on the WhatsApp CTA + Google Calendar booking link instead (deliberate, not a gap).
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
- Partner logos: `assets/images/partners/` (12 files on disk; carousel narrowed 2026-08-17 to 4 relevant ones — Claude, WhatsApp, Telegram, Google — unused files left in place, harmless)
- Client logos: `assets/images/clients/` (7 files — Campaso, D&A Tango, Fare, Mayorista Omega, Pacifican Group, Senor Tango, Bronson Pizza — trust bar reframed 2026-08-17 as generic "empresas que confiaron en nosotros," not per-client service claims; only Mayorista Omega is an actual WhatsApp bot case study)
- Hero background video: `assets/hero-bg.mp4`
- Brand mark lockup (added 2026-08-21): `assets/images/logos/logo-mark-green.png` (light backgrounds — portal login screen) and `logo-mark-white.png` (dark chrome nav) — used by `portal/index.html`'s new nav/login design as a mark+wordtext lockup, distinct from the `Agentiva Logo esteso.png` wordmark above. Not yet used on the main `index.html`.

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
