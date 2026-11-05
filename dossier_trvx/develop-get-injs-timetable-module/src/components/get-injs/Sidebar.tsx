"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LIENS = [
  { href: "/", label: "Tableau de bord", icone: "grid", description: "Pilotage du module" },
  { href: "/emplois-du-temps", label: "Emplois du temps", icone: "calendar", description: "Grille hebdomadaire" },
  { href: "/generation", label: "Génération", icone: "wand", description: "Moteur LMD" },
  { href: "/import", label: "Import étudiants", icone: "upload", description: "Fichier externe" },
  { href: "/etudiants", label: "Étudiants inscrits", icone: "users", description: "Populations" },
  { href: "/referentiels", label: "Référentiels", icone: "layers", description: "INJS 2026" },
  { href: "/conception", label: "Conception", icone: "book", description: "Documentation" },
];

function Icone({ nom }: { nom: string }) {
  const paths: Record<string, string> = {
    grid: "M4 4h6v6H4V4Zm10 0h6v6h-6V4ZM4 14h6v6H4v-6Zm10 0h6v6h-6v-6Z",
    calendar: "M4 6h16v14H4V6Zm0 4h16M8 3v4m8-4v4M8 13h3v3H8v-3Z",
    wand: "m4 20 10-10m0 0 2-6 2 2 2-2 2 2-2 2 2 2-6 2m-2 0-2-2M4 8l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2Z",
    upload: "M12 16V4m0 0L7 9m5-5 5 5M4 16v3h16v-3",
    users: "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM2 20c0-3 2.7-5 6-5s6 2 6 5m2-5c3 0 6 1.6 6 5",
    layers: "m12 3 9 5-9 5-9-5 9-5Zm9 9-9 5-9-5m18 4-9 5-9-5",
    book: "M4 5c3-1 5-1 8 1v14c-3-2-5-2-8-1V5Zm16 0c-3-1-5-1-8 1v14c3-2 5-2 8-1V5Z",
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-4 w-4">
      <path d={paths[nom] ?? paths.grid} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Sidebar({ annee }: { annee: string }) {
  const pathname = usePathname();
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[264px] flex-col bg-[color:var(--inj-green)] px-4 py-5 text-[#eaf3ec] lg:flex">
        <Brand />
        <nav className="mt-7 flex flex-1 flex-col gap-1">
          {LIENS.map((lien) => {
            const actif = pathname === lien.href;
            return (
              <Link
                key={lien.href}
                href={lien.href}
                className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 transition ${
                  actif
                    ? "bg-white/12 text-white shadow-[inset_3px_0_0_0_var(--inj-orange)]"
                    : "text-[#c6d9cd] hover:bg-white/8 hover:text-white"
                }`}
              >
                <span className={actif ? "text-[color:var(--inj-orange)]" : "text-[#9db9a8]"}>
                  <Icone nom={lien.icone} />
                </span>
                <span>
                  <span className="block text-sm font-semibold">{lien.label}</span>
                  <span className="block text-[0.68rem] text-[#9db9a8]">{lien.description}</span>
                </span>
              </Link>
            );
          })}
        </nav>
        <div className="mt-4 rounded-xl border border-white/15 bg-white/5 p-3">
          <p className="text-[0.65rem] uppercase tracking-[0.14em] text-[#a9c3b3]">Année active</p>
          <p className="font-display text-lg font-semibold text-white">{annee}</p>
          <div className="mt-2 flex items-center gap-2 text-[0.68rem] text-[#c6d9cd]">
            <span className="h-2 w-2 rounded-full bg-[#7fd1a4]" />
            Moteur LMD opérationnel
          </div>
        </div>
        <p className="mt-4 text-[0.65rem] leading-relaxed text-[#8aa899]">
          INJS Marcory · Abidjan
          <br />
          Module GET INJS APP v1.0
        </p>
      </aside>

      <div className="sticky top-0 z-30 border-b border-white/10 bg-[color:var(--inj-green)] px-4 py-3 text-white lg:hidden">
        <div className="flex items-center justify-between gap-3">
          <Brand compact />
          <span className="rounded-full bg-white/12 px-2.5 py-1 text-[0.7rem] font-semibold">{annee}</span>
        </div>
        <nav className="mt-3 flex gap-1 overflow-x-auto pb-1">
          {LIENS.map((lien) => {
            const actif = pathname === lien.href;
            return (
              <Link
                key={lien.href}
                href={lien.href}
                className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-semibold ${
                  actif ? "bg-[color:var(--inj-orange)] text-[#24160b]" : "bg-white/10 text-[#d7e6db]"
                }`}
              >
                {lien.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-3">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[color:var(--inj-orange)] font-display text-sm font-bold text-[#20150a]">
        GET
      </span>
      <span>
        <span className="font-display block text-lg leading-tight font-semibold text-white">
          INJS APP
        </span>
        {!compact ? (
          <span className="block text-[0.68rem] uppercase tracking-[0.12em] text-[#a9c3b3]">
            Emplois du temps LMD
          </span>
        ) : null}
      </span>
    </Link>
  );
}
