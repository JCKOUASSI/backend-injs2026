import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";
import EnTete, { type ActeurOption } from "@/components/EnTete";
import { chargerActeurs } from "@/lib/queries";

export const metadata: Metadata = {
  title: "GET INJS APP — Présences QR + Géolocalisation",
  description:
    "Gestion des présences par QR code, badgeage manuel, géolocalisation et heartbeat pour les étudiants, enseignants et encadrants de l'INJS Abidjan.",
};

export const dynamic = "force-dynamic";

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const acteurs = await chargerActeurs();
  const options: ActeurOption[] = acteurs.map((a) => ({
    id: a.id,
    matricule: a.matricule,
    nom: `${a.prenom} ${a.nom}`,
    role: a.role,
  }));

  return (
    <html lang="fr">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700;9..144,900&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="grain-papier min-h-screen">
        <EnTete acteurs={options} />
        <main className="relative z-10">{children}</main>
        <footer className="relative z-10 mt-20 border-t-2 border-encre bg-papier-haut">
          <div className="mx-auto flex max-w-[1400px] flex-wrap items-baseline gap-x-8 gap-y-2 px-6 py-8">
            <span className="font-display text-lg font-bold text-vert">GET INJS APP</span>
            <span className="caps text-encre-pale">
              Formation → Parcours → Niveau → Semestre → Groupe → Maquette → UE → ECUE →
              Affectation → Séance → Session QR → Badgeage → Présence
            </span>
            <Link href="/contrat" className="caps ml-auto text-vert underline">
              Contrat d&apos;interopérabilité
            </Link>
          </div>
        </footer>
      </body>
    </html>
  );
}
