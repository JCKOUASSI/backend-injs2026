import { readFile } from "node:fs/promises";
import path from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const telecharger = url.searchParams.get("download") === "1";
  try {
    const fichier = path.join(process.cwd(), "get-injs-app", "Conception-GET-INJS.txt");
    const contenu = await readFile(fichier, "utf8");
    return new Response(contenu, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": `${telecharger ? "attachment" : "inline"}; filename="Conception-GET-INJS.txt"`,
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return new Response(
      "Conception-GET-INJS.txt est introuvable. Consultez get-injs-app/Conception-GET-INJS.txt.",
      { status: 404, headers: { "Content-Type": "text/plain; charset=utf-8" } },
    );
  }
}
