/** Pièces d'interface du registre : pastilles, cartouches, chiffres. */

const COULEURS: Record<string, string> = {
  conforme: "border-vert text-vert bg-vert/8",
  alerte: "border-vermillon text-vermillon bg-vermillon/8",
  neutre: "border-filet text-encre-pale bg-neutre/40",
  encours: "border-vert-clair text-vert-clair bg-vert-clair/8",
};

export function Puce({
  texte,
  ton = "neutre",
}: {
  texte: string;
  ton?: keyof typeof COULEURS | string;
}) {
  return (
    <span
      className={`caps inline-flex items-center whitespace-nowrap rounded-[2px] border px-2 py-[3px] ${
        COULEURS[ton] ?? COULEURS.neutre
      }`}
    >
      {texte}
    </span>
  );
}

export function tonVerdict(verdict: string | null | undefined): string {
  switch (verdict) {
    case "DANS_PERIMETRE":
      return "conforme";
    case "HORS_PERIMETRE":
    case "POSITION_INEXPLOITABLE":
      return "alerte";
    case "POSITION_IMPRECISE":
    case "POSITION_ABSENTE":
    case "SITE_NON_LOCALISE":
      return "neutre";
    default:
      return "neutre";
  }
}

export function tonStatut(statut: string | null | undefined): string {
  switch (statut) {
    case "TERMINE":
    case "PRESENT":
      return "conforme";
    case "EN_COURS":
    case "SORTIE_AUTO":
      return "encours";
    case "ABSENT_NON_BADGE":
    case "ABSENT":
    case "HORS_LIGNE_SUSPECT":
    case "FORCE_DFRC":
      return "alerte";
    case "RETARD":
      return "alerte";
    default:
      return "neutre";
  }
}

export function Cartouche({
  titre,
  surtitre,
  action,
}: {
  titre: string;
  surtitre?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b-2 border-encre pb-2">
      <div>
        {surtitre ? <div className="caps mb-1 text-encre-pale">{surtitre}</div> : null}
        <h2 className="font-display text-[25px] leading-tight font-bold text-encre">
          {titre}
        </h2>
      </div>
      {action}
    </div>
  );
}

export function Chiffre({
  valeur,
  libelle,
  legende,
  ton = "encre",
}: {
  valeur: string | number;
  libelle: string;
  legende?: string;
  ton?: "encre" | "vert" | "vermillon";
}) {
  const couleur =
    ton === "vert" ? "text-vert" : ton === "vermillon" ? "text-vermillon" : "text-encre";
  return (
    <div className="border-l-2 border-filet pl-4">
      <div className={`font-display tab text-[39px] leading-none font-black ${couleur}`}>
        {valeur}
      </div>
      <div className="caps mt-2 text-encre">{libelle}</div>
      {legende ? <div className="mt-1 text-[13px] text-encre-pale">{legende}</div> : null}
    </div>
  );
}

export function Barre({ valeur, max, ton = "vert" }: { valeur: number; max: number; ton?: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((valeur / max) * 100)) : 0;
  return (
    <div className="h-2 w-full border border-filet bg-papier">
      <div
        className={`h-full ${ton === "vermillon" ? "bg-vermillon" : "bg-vert"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function Legende({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-2 max-w-[70ch] text-[13px] leading-relaxed text-encre-pale">{children}</p>
  );
}

export function formatDateFr(dateIso: string): string {
  const d = new Date(`${dateIso}T00:00:00`);
  return d.toLocaleDateString("fr-FR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

export function heure(iso: Date | string | null | undefined): string {
  if (!iso) return "—";
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}
