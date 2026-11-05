"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

type ResultatImport = {
  jobId: number;
  fichier: string;
  anneeCode: string;
  lignes: number;
  importes: number;
  nouveaux: number;
  ignores: number;
  erreurs: string[];
  colonnesDetectees: Record<string, string>;
  colonnesIgnorees: string[];
  referentielsCrees: { filieres: number; formations: number; groupes: number; vagues: number };
  dureeMs: number;
  generation?: {
    stats: { seances: number; conflits: number; nonPlacees: number; tauxCouverture: number };
    alertes: string[];
    classes: number;
  };
};

export function ImportForm({
  annees,
  anneeDefaut,
}: {
  annees: { code: string; label: string }[];
  anneeDefaut: string;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [fichier, setFichier] = useState<File | null>(null);
  const [anneeCode, setAnneeCode] = useState(anneeDefaut);
  const [autoCreer, setAutoCreer] = useState(true);
  const [generer, setGenerer] = useState(true);
  const [semestre, setSemestre] = useState("");
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [resultat, setResultat] = useState<ResultatImport | null>(null);

  async function soumettre(evenement: React.FormEvent) {
    evenement.preventDefault();
    if (!fichier) {
      setErreur("Sélectionnez un fichier CSV ou XLSX.");
      return;
    }
    setEnCours(true);
    setErreur(null);
    setResultat(null);
    const donnees = new FormData();
    donnees.append("fichier", fichier);
    donnees.append("anneeCode", anneeCode);
    donnees.append("autoCreer", String(autoCreer));
    donnees.append("generer", String(generer));
    if (semestre) donnees.append("semestre", semestre);
    try {
      const reponse = await fetch("/api/import", { method: "POST", body: donnees });
      const json = (await reponse.json()) as
        | { ok: true; resultat: ResultatImport }
        | { ok: false; erreur: string };
      if (!json.ok) {
        setErreur(json.erreur);
      } else {
        setResultat(json.resultat);
        router.refresh();
      }
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Erreur réseau pendant l'import.");
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div className="space-y-5">
      <form onSubmit={soumettre} className="card p-5">
        <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
          <div>
            <label
              htmlFor="fichier-etudiants"
              className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-[color:var(--inj-line)] bg-[#fbf8f0] px-4 py-8 text-center transition hover:border-[color:var(--inj-green-soft)]"
            >
              <span className="grid h-11 w-11 place-items-center rounded-full bg-[color:var(--inj-green)] text-white">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-5 w-5">
                  <path d="M12 16V4m0 0L7 9m5-5 5 5M4 16v3h16v-3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <span className="text-sm font-semibold text-[color:var(--inj-green)]">
                {fichier ? fichier.name : "Déposer ou sélectionner le fichier des inscrits"}
              </span>
              <span className="text-xs text-slate-500">
                CSV, XLSX ou XLS · 20 000 lignes max · 15 Mo max
              </span>
              {fichier ? (
                <span className="text-xs text-slate-500">
                  {(fichier.size / 1024).toFixed(0)} Ko sélectionnés
                </span>
              ) : null}
            </label>
            <input
              ref={inputRef}
              id="fichier-etudiants"
              type="file"
              accept=".csv,.xlsx,.xls,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="sr-only"
              onChange={(e) => setFichier(e.target.files?.[0] ?? null)}
            />
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => inputRef.current?.click()}
              >
                Parcourir
              </button>
              <a href="/api/import" className="btn-ghost" download>
                Télécharger le modèle CSV
              </a>
            </div>
          </div>

          <div className="space-y-3">
            <div>
              <label className="label" htmlFor="import-annee">
                Année académique cible
              </label>
              <select id="import-annee" className="field mt-1" value={anneeCode} onChange={(e) => setAnneeCode(e.target.value)}>
                {annees.map((a) => (
                  <option key={a.code} value={a.code}>
                    {a.label}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-start gap-2 rounded-lg border border-[color:var(--inj-line)] bg-[#fbf8f0] p-2.5 text-sm">
              <input type="checkbox" className="mt-0.5" checked={autoCreer} onChange={(e) => setAutoCreer(e.target.checked)} />
              <span>
                <strong className="text-[color:var(--inj-green)]">Reconstruire le parcours</strong>
                <span className="block text-xs text-slate-500">
                  Crée filière, formation, vague, groupe et maquette par défaut si absents.
                </span>
              </span>
            </label>
            <label className="flex items-start gap-2 rounded-lg border border-[color:var(--inj-line)] bg-[#fbf8f0] p-2.5 text-sm">
              <input type="checkbox" className="mt-0.5" checked={generer} onChange={(e) => setGenerer(e.target.checked)} />
              <span>
                <strong className="text-[color:var(--inj-green)]">Générer les EDT après import</strong>
                <span className="block text-xs text-slate-500">
                  Un emploi du temps par parcours, groupe et semestre détecté.
                </span>
              </span>
            </label>
            <div>
              <label className="label" htmlFor="import-semestre">
                Semestre à générer (optionnel)
              </label>
              <select id="import-semestre" className="field mt-1" value={semestre} onChange={(e) => setSemestre(e.target.value)}>
                <option value="">Toute l&apos;année</option>
                {Array.from({ length: 10 }, (_, i) => i + 1).map((s) => (
                  <option key={s} value={s}>
                    Semestre {s}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button type="submit" className="btn-primary" disabled={enCours}>
            {enCours ? "Import et génération en cours…" : "Importer les inscrits"}
          </button>
          <span className="text-xs text-slate-500">
            Idempotent : un matricule déjà présent n&apos;est jamais dupliqué.
          </span>
        </div>

        {enCours ? (
          <div className="mt-3 rounded-lg border border-[#c9dced] bg-[#eef5fa] px-3 py-2 text-sm text-[#245b80]">
            Lecture du fichier, normalisation des colonnes, reconstruction des parcours puis génération
            des emplois du temps. Ne fermez pas la page.
          </div>
        ) : null}
        {erreur ? (
          <div className="mt-3 rounded-lg border border-[#f3c6bf] bg-[#fbe9e6] px-3 py-2 text-sm text-[#9d2f22]">
            {erreur}
          </div>
        ) : null}
      </form>

      {resultat ? (
        <div className="card border-[#c5e0d1] p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="label text-[#1c5c45]">Import terminé</p>
              <h3 className="font-display text-xl font-semibold text-[color:var(--inj-green)]">
                {resultat.importes.toLocaleString("fr-FR")} étudiants traités
              </h3>
              <p className="text-xs text-slate-500">
                {resultat.fichier} · {resultat.anneeCode} · {(resultat.dureeMs / 1000).toFixed(1)} s
              </p>
            </div>
            <div className="flex gap-2">
              <a href="/etudiants" className="btn-ghost">
                Voir les étudiants
              </a>
              <a href="/emplois-du-temps" className="btn-primary">
                Voir les emplois du temps
              </a>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
            {[
              ["Lignes lues", resultat.lignes],
              ["Importés", resultat.importes],
              ["Nouveaux", resultat.nouveaux],
              ["Ignorés", resultat.ignores],
              ["Formations créées", resultat.referentielsCrees.formations],
              ["Groupes créés", resultat.referentielsCrees.groupes],
              ["Vagues créées", resultat.referentielsCrees.vagues],
            ].map(([label, valeur]) => (
              <div key={label} className="rounded-lg bg-[#f6f2e8] px-3 py-2">
                <p className="text-[0.62rem] font-bold uppercase tracking-wide text-slate-500">{label}</p>
                <p className="text-lg font-semibold text-[color:var(--inj-green)]">{valeur}</p>
              </div>
            ))}
          </div>

          {resultat.generation ? (
            <div className="mt-4 rounded-lg border border-[#c9dced] bg-[#eef5fa] p-3 text-sm text-[#245b80]">
              <strong>Génération automatique :</strong> {resultat.generation.stats.seances} séances ·{" "}
              {resultat.generation.stats.conflits} conflit(s) ·{" "}
              {resultat.generation.stats.nonPlacees} non placée(s) · couverture{" "}
              {resultat.generation.stats.tauxCouverture} %.
            </div>
          ) : null}

          <details className="mt-3 text-xs">
            <summary className="cursor-pointer font-semibold text-[color:var(--inj-green)]">
              Colonnes détectées et inutilisées
            </summary>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <div>
                <p className="font-semibold text-slate-600">Colonnes reconnues</p>
                <ul className="mt-1 space-y-0.5">
                  {Object.entries(resultat.colonnesDetectees).map(([champ, entete]) => (
                    <li key={champ}>
                      <span className="font-mono text-[color:var(--inj-green)]">{entete}</span> → {champ}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="font-semibold text-slate-600">Colonnes non utilisées</p>
                <p className="mt-1">{resultat.colonnesIgnorees.join(", ") || "Aucune"}</p>
              </div>
            </div>
          </details>

          {resultat.erreurs.length > 0 ? (
            <details className="mt-3 text-xs" open>
              <summary className="cursor-pointer font-semibold text-[#9d2f22]">
                Alertes ({resultat.erreurs.length})
              </summary>
              <ul className="mt-2 space-y-0.5 text-slate-600">
                {resultat.erreurs.slice(0, 25).map((e, i) => (
                  <li key={`${e}-${i}`}>• {e}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
