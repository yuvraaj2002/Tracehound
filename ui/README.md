# Tracehound UI

React and TypeScript landing page built with Vite.

```sh
npm ci
npm run dev
```

Run `npm run lint` and `npm run build` before publishing changes.
Use Node.js 22, matching the UI CI workflow.

See [DESIGN.md](DESIGN.md) for the finalized visual system and agent sequence.
Switzer and the Cabinet Grotesk wordmark load from Fontshare with system-font
fallbacks. Lenis eases wheel/anchor scrolling while respecting reduced motion.

Commit source files, public assets, and package-lock.json. Dependencies,
build output, caches, and local environment files are excluded by .gitignore.
