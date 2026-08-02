# ky.handwriter

ky.handwriter is a local-first desktop application for turning handwritten character images into OpenType fonts. It uses Svelte, TypeScript, Vite, Tauri, and a local Python font compiler.

## Development

```powershell
npm install
npm run check
npm run tauri dev
```

The first milestone supports a local project folder and prepares an uppercase A–Z glyph set. Font tracing and compilation are the next implementation slice.

The compiler protocol can be checked without installing dependencies:

```powershell
'{"command":"health-check"}' | python -m handfont_compiler
```

Run this command from the `compiler` directory.

No accounts, remote APIs, analytics, or project uploads are used.
