import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { Sidebar } from "@/components/get-injs/Sidebar";
import { referentiel } from "../../get-injs-app/data/referentiel";

export const metadata: Metadata = {
  title: "GET INJS APP — Emplois du temps LMD",
  description:
    "Module de génération des emplois du temps de l'INJS d'Abidjan : filières, formations, groupes, vagues et semestres LMD.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <body className="min-h-screen text-[color:var(--inj-ink)] antialiased">
        <Sidebar annee={referentiel.activeYear} />
        <div className="lg:pl-[264px]">
          <main className="mx-auto w-full max-w-[1500px] px-4 py-6 lg:px-8 lg:py-8">{children}</main>
          <footer className="mx-auto w-full max-w-[1500px] px-4 pb-8 text-xs text-slate-500 lg:px-8">
            GET INJS APP · module intégré à backend-injs2026 · Institut National de la Jeunesse et des
            Sports d&apos;Abidjan (Marcory) · Moteur LMD déterministe.
          </footer>
        </div>
      </body>
    </html>
  );
}
