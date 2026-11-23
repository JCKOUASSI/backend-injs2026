"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

export interface ActeurOption {
  id: number;
  matricule: string;
  nom: string;
  role: string;
}

const LIENS = [
  { href: "/", libelle: "Tableau de bord" },
  { href: "/seances", libelle: "Séances" },
  { href: "/badger", libelle: "Badgeage" },
  { href: "/presences", libelle: "Présences" },
  { href: "/audit", libelle: "Audit" },
  { href: "/config", libelle: "Configuration" },
  { href: "/contrat", libelle: "Contrat API" },
];

export function acteurCourantId(): number {
  if (typeof window === "undefined") return 1;
  const brut = window.localStorage.getItem("injs-acteur");
  const id = Number(brut ?? 1);
  return Number.isFinite(id) ? id : 1;
}

export default function EnTete({ acteurs }: { acteurs: ActeurOption[] }) {
  const chemin = usePathname();
  const [acteurId, setActeurId] = useState<number>(1);

  useEffect(() => {
    setActeurId(acteurCourantId());
  }, []);

  const changer = (id: number) => {
    setActeurId(id);
    window.localStorage.setItem("injs-acteur", String(id));
  };

  const actif = acteurs.find((a) => a.id === acteurId) ?? acteurs[0];

  return (
    <header className="relative z-20 border-b-2 border-encre bg-papier-haut/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-8 gap-y-3 px-6 py-4">
        <Link href="/" className="flex items-baseline gap-3">
          <span className="font-display text-[26px] font-black leading-none tracking-tight text-vert">
            GET INJS
          </span>
          <span className="caps text-encre-pale">Présences QR · Géolocalisation</span>
        </Link>

        <nav className="flex flex-wrap items-center gap-x-5 gap-y-2">
          {LIENS.map((l) => {
            const actifLien = l.href === "/" ? chemin === "/" : chemin.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`caps border-b-2 pb-1 transition-colors ${
                  actifLien
                    ? "border-vert text-vert"
                    : "border-transparent text-encre-pale hover:text-encre"
                }`}
              >
                {l.libelle}
              </Link>
            );
          })}
        </nav>

        <label className="ml-auto flex items-center gap-3">
          <span className="caps text-encre-pale">Agir en tant que</span>
          <select
            className="champ max-w-[280px] font-mono text-[13px]"
            value={acteurId}
            onChange={(e) => changer(Number(e.target.value))}
          >
            {acteurs.map((a) => (
              <option key={a.id} value={a.id}>
                {a.matricule} · {a.nom} ({a.role})
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="border-t border-filet bg-neutre/50">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-1 px-6 py-1.5">
          <span className="caps text-encre-pale">Actif</span>
          <span className="font-mono text-[12px] text-encre">
            {actif ? `${actif.matricule} — ${actif.nom}` : "—"}
          </span>
          <span className="caps text-vert">{actif?.role}</span>
          <span className="caps ml-auto text-encre-pale">
            Jeu de démonstration — aucune donnée métier INJS réelle
          </span>
        </div>
      </div>
    </header>
  );
}
