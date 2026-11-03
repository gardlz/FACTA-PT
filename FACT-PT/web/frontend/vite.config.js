import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The bundle goes where FastAPI serves it from: `index.html` at `/`, hashed files under
// `/assets`. In development the API is proxied to a uvicorn running beside Vite, with the page's
// own `Host`: the API refuses a POST whose `Origin` names another host (`acesso.verificar_origem`).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: fileURLToPath(new URL("../app/static", import.meta.url)),
    emptyOutDir: true,
    assetsDir: "assets",
  },
  server: {
    proxy: {
      "/api": { target: process.env.FACTA_API || "http://127.0.0.1:8000" },
    },
  },
});
