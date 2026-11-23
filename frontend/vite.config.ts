import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Build into the directory FastAPI serves, so operators only need Python at run time.
// Fonts (Pretendard) are bundled from node_modules into app/static — no CDN, no runtime network request.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // "@/..." resolves from the project root (shadcn/ui convention).
  resolve: { alias: { "@": "/src" } },
  build: { outDir: "../app/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
