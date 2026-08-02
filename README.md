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

## Windows release

Install the compiler and packaging dependencies once:

```powershell
compiler\.venv\Scripts\python.exe -m pip install -r compiler\requirements.txt
compiler\.venv\Scripts\python.exe -m pip install -r compiler\requirements-build.txt
```

Build the Windows installers and portable ZIP:

```powershell
npm run desktop:build
```

Release artifacts are written to `src-tauri\target\release`:

- `bundle\nsis\ky.handwriter_<version>_x64-setup.exe`
- `bundle\msi\ky.handwriter_<version>_x64_en-US.msi`
- `ky.handwriter_<version>_x64-portable.zip`

The installer and portable ZIP include the frozen font compiler. End users do not need Python or the development virtual environment. Keep the full contents of the portable ZIP together; `ky.handwriter.exe` expects its `compiler` subfolder.
