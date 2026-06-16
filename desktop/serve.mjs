import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const root = process.cwd();
const port = 1420;
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
};

const server = http.createServer(async (request, response) => {
  const pathname = new URL(request.url, `http://localhost:${port}`).pathname;
  const filePath = resolveFilePath(pathname);
  if (!filePath) {
    response.writeHead(403);
    response.end("Forbidden");
    return;
  }
  try {
    const resolvedPath = await existingPath(filePath);
    const data = await readFile(resolvedPath);
    response.writeHead(200, { "Content-Type": types[extname(resolvedPath)] || "application/octet-stream" });
    response.end(data);
  } catch {
    response.writeHead(404);
    response.end("Not found");
  }
});

async function existingPath(filePath) {
  try {
    await readFile(filePath);
    return filePath;
  } catch (error) {
    if (!extname(filePath)) {
      const jsPath = `${filePath}.js`;
      await readFile(jsPath);
      return jsPath;
    }
    throw error;
  }
}

function resolveFilePath(pathname) {
  if (pathname.startsWith("/@tauri-apps/api/")) {
    const modulePath = pathname.replace("/@tauri-apps/api/", "");
    const filePath = normalize(join(root, "node_modules", "@tauri-apps", "api", modulePath));
    const packageRoot = normalize(join(root, "node_modules", "@tauri-apps", "api"));
    return filePath.startsWith(packageRoot) ? filePath : null;
  }

  const relativePath = pathname === "/" ? "index.html" : pathname.slice(1);
  const filePath = normalize(join(root, relativePath));
  return filePath.startsWith(root) ? filePath : null;
}

server.listen(port, "127.0.0.1", () => {
  console.log(`Desktop dev server running at http://localhost:${port}`);
});
