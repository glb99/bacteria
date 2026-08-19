import { defineConfig } from "vite";

// The build lands inside the Python package rather than beside this directory,
// because that is where `bacteria.app.views` looks for it and package data is
// the only location that resolves the same in development and in production.
// See `backend/app/src/bacteria/app/views.py` for why it cannot be a setting.
const CONSOLE_DIR = "../backend/app/src/bacteria/app/console";

export default defineConfig({
  build: {
    outDir: CONSOLE_DIR,
    // The directory is gitignored and holds nothing but output, so clearing it
    // is safe -- and without this a renamed asset from a previous build stays
    // behind and ships forever.
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    // `npm run dev` talks to a real API on the usual port. Same-origin in
    // production is what makes `SameSite=Strict` the CSRF answer (ADR 0005);
    // this proxy is what keeps development same-origin too, rather than
    // introducing a CORS configuration that production does not have.
    proxy: {
      "/auth": "http://127.0.0.1:8000",
      "/chat": "http://127.0.0.1:8000",
      "/ingestion": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
