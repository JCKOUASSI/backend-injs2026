"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Option = { id: number; code: string; nom: string; niveau?: string; effectif?: number };

type Resultat = {
  edtCode: string;
  classes: number;
  semestres: number[];
  stats: {
    seances: number;
    cm: number;
    td: number;
    tp: number;
    groupes: number;
    modules: number;
    sallesMobilisees: number;
    enseignantsMobilises: number;
    placesEtudiantes: number;
    nonPlacees: number;
    conflits: number;
    tauxCouverture: number;
    tauxOccupationSalles: number;
    dureeMs: number;
  };
  alertes: string[];
  nonPlacees: {
    semestre: number;
    moduleCode: string;
    groupeCode: string;
    typeSeance: string;
    raison: string;
  }[];
};

export function GenerationForm({
  annees,
  filieres,
  formations,
  niveaux,
  groupes,
  anneeDefaut,
}: {
  annees: { code: string; label: string }[];
  filieres: Option[];
  formations: Option[];
  niveaux: string[];
  groupes: Option[];
  anneeDefaut: string;
}) {
  const router = useRouter();
  const [anneeCode, setAnneeCode] = useState(anneeDefaut);
  const [filiereCode, setFiliereCode] = useState("");
  const [formationId, setFormationId] = useState("");
  const [niveau, setNiveau] = useState("");
  const [groupeId, setGroupeId] = useState("");
  const [semestre, setSemestre] = useState("");
  const [inclureSamedi, setInclureSamedi] = useState(true);
  const [eviterPauseMidi, setEviterPauseMidi] = useState(true);
  const [maxSeances, setMaxSeances] = useState("30");
  const [publier, setPublier] = useState(false);
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [resultat, setResultat] = useState<Resultat | null>(null);

  const groupesFiltres = groupes.filter((g) => {
    if (!formationId) return Boolean(g.niveau);
    return true;
  });

  async function soumettre(evenement: React.FormEvent) {
    evenement.preventDefault();
    setEnCours(true);
    setErreur(null);
    setResultat(null);
    try {
      const reponse = await fetch("/api/generation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          anneeCode,
          filiereCode: filiereCode || undefined,
          formationId: formationId ? Number(formationId) : undefined,
          niveau: niveau || undefined,
          groupeId: groupeId ? Number(groupeId) : undefined,
          semestre: semestre ? Number(semestre) : undefined,
          inclureSamedi,
          eviterPauseMidi,
          maxSeancesParGroupe: Number(maxSeances),
          publier,
        }),
      });
      const donnees = (await reponse.json()) as
        | { ok: true; resultat: Resultat }
        | { ok: false; erreur: string };
      if (!donnees.ok) {
        setErreur(donnees.erreur);
      } else {
        setResultat(donnees.resultat);
        router.refresh();
      }
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Erreur réseau pendant la génération.");
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
      <form onSubmit={soumettre} className="card p-5">
        <div className="mb-4">
          <h2 className="font-display text-xl font-semibold text-[color:var(--inj-green)]">
            Paramètres de génération
          </h2>
          <p className="text-xs text-slate-500">
            Le moteur remplace les séances existantes du périmètre sélectionné puis persiste la nouvelle
            grille (versionnée, horodatée et traçable).
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="label" htmlFor="gen-annee">
              Année académique *
            </label>
            <select id="gen-annee" className="field mt-1" value={anneeCode} onChange={(e) => setAnneeCode(e.target.value)}>
              {annees.map((a) => (
                <option key={a.code} value={a.code}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="gen-filiere">
              Filière (mention)
            </label>
            <select id="gen-filiere" className="field mt-1" value={filiereCode} onChange={(e) => setFiliereCode(e.target.value)}>
              <option value="">Toutes les filières</option>
              {filieres.map((f) => (
                <option key={f.code} value={f.code}>
                  {f.code} — {f.nom}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="gen-formation">
              Formation / parcours
            </label>
            <select id="gen-formation" className="field mt-1" value={formationId} onChange={(e) => setFormationId(e.target.value)}>
              <option value="">Toutes les formations</option>
              {formations.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.code} — {f.nom}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="gen-niveau">
              Niveau
            </label>
            <select id="gen-niveau" className="field mt-1" value={niveau} onChange={(e) => setNiveau(e.target.value)}>
              <option value="">Tous les niveaux</option>
              {niveaux.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="gen-groupe">
              Groupe (optionnel)
            </label>
            <select id="gen-groupe" className="field mt-1" value={groupeId} onChange={(e) => setGroupeId(e.target.value)}>
              <option value="">Tous les groupes du périmètre</option>
              {groupesFiltres.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.code} {g.effectif ? `(${g.effectif} ét.)` : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="gen-semestre">
              Semestre
            </label>
            <select id="gen-semestre" className="field mt-1" value={semestre} onChange={(e) => setSemestre(e.target.value)}>
              <option value="">Toute l&apos;année (2 semestres par niveau)</option>
              {Array.from({ length: 10 }, (_, i) => i + 1).map((s) => (
                <option key={s} value={s}>
                  Semestre {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        <fieldset className="mt-5 rounded-lg border border-[color:var(--inj-line)] bg-[#fbf8f0] p-3">
          <legend className="label px-1">Contraintes et options</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={inclureSamedi} onChange={(e) => setInclureSamedi(e.target.checked)} />
              Inclure le samedi (créneaux du matin)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={eviterPauseMidi} onChange={(e) => setEviterPauseMidi(e.target.checked)} />
              Éviter la pause méridienne (12h–14h)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={publier} onChange={(e) => setPublier(e.target.checked)} />
              Publier directement l&apos;emploi du temps
            </label>
            <label className="flex items-center gap-2 text-sm">
              Séances max / groupe / semaine
              <input
                type="number"
                min={10}
                max={36}
                value={maxSeances}
                onChange={(e) => setMaxSeances(e.target.value)}
                className="field w-20"
              />
            </label>
          </div>
        </fieldset>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button type="submit" className="btn-primary" disabled={enCours}>
            {enCours ? "Génération en cours…" : "Lancer la génération"}
          </button>
          <span className="text-xs text-slate-500">
            Déterministe · CM mutualisés · TD/TP par groupe · contrôle des conflits
          </span>
        </div>

        {enCours ? (
          <div className="mt-4 rounded-lg border border-[#c9dced] bg-[#eef5fa] px-3 py-2 text-sm text-[#245b80]">
            Le moteur affecte les salles, enseignants et créneaux. Cela peut prendre quelques secondes
            pour plusieurs milliers de séances.
          </div>
        ) : null}
        {erreur ? (
          <div className="mt-4 rounded-lg border border-[#f3c6bf] bg-[#fbe9e6] px-3 py-2 text-sm text-[#9d2f22]">
            {erreur}
          </div>
        ) : null}
      </form>

      <div className="space-y-4">
        <div className="card p-5">
          <h3 className="font-display text-lg font-semibold text-[color:var(--inj-green)]">
            Comment le moteur décide
          </h3>
          <ol className="mt-3 space-y-2 text-sm text-slate-600">
            <li>
              <strong className="text-[color:var(--inj-green)]">1.</strong> Lecture des groupes inscrits,
              de leur niveau, vague et effectif réel.
            </li>
            <li>
              <strong className="text-[color:var(--inj-green)]">2.</strong> CM mutualisés par promotion,
              découpés si l&apos;effectif dépasse la plus grande salle.
            </li>
            <li>
              <strong className="text-[color:var(--inj-green)]">3.</strong> TD et TP par groupe, avec
              meilleur ajustement de capacité.
            </li>
            <li>
              <strong className="text-[color:var(--inj-green)]">4.</strong> Vérification croisée salle /
              enseignant / groupe, puis persistance.
            </li>
            <li>
              <strong className="text-[color:var(--inj-green)]">5.</strong> Rapport de couverture,
              conflits et séances non placées.
            </li>
          </ol>
        </div>
        <div className="card border-[#f2d3b5] bg-[#fdf5ea] p-5">
          <h3 className="font-display text-lg font-semibold text-[#9b4d11]">Bon à savoir</h3>
          <ul className="mt-2 space-y-1.5 text-sm text-[#7c4a21]">
            <li>• Un semestre = une grille ; les semestres impairs et pairs ne se chevauchent pas.</li>
            <li>• 32 créneaux hebdomadaires (5 jours × 6 créneaux + samedi matin).</li>
            <li>• Les quotas par groupe évitent les semaines surchargées.</li>
            <li>• Relancer la génération remplace proprement l&apos;ancienne version du périmètre.</li>
          </ul>
        </div>
      </div>

      {resultat ? (
        <div className="xl:col-span-2">
          <div className="card border-[#c5e0d1] p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="label text-[#1c5c45]">Génération terminée</p>
                <h3 className="font-display text-xl font-semibold text-[color:var(--inj-green)]">
                  {resultat.stats.seances.toLocaleString("fr-FR")} séances planifiées
                </h3>
                <p className="text-xs text-slate-500">
                  {resultat.edtCode} · semestres {resultat.semestres.join(", ")} · {resultat.classes} couples
                  formation/semestre
                </p>
              </div>
              <a href="/emplois-du-temps" className="btn-primary">
                Voir la grille
              </a>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
              {[
                ["Séances", resultat.stats.seances],
                ["CM", resultat.stats.cm],
                ["TD", resultat.stats.td],
                ["TP", resultat.stats.tp],
                ["Conflits", resultat.stats.conflits],
                ["Non placées", resultat.stats.nonPlacees],
                ["Couverture", `${resultat.stats.tauxCouverture} %`],
                ["Durée", `${(resultat.stats.dureeMs / 1000).toFixed(1)} s`],
              ].map(([label, valeur]) => (
                <div key={label} className="rounded-lg bg-[#f6f2e8] px-3 py-2">
                  <p className="text-[0.62rem] font-bold uppercase tracking-wide text-slate-500">{label}</p>
                  <p className="text-lg font-semibold text-[color:var(--inj-green)]">{valeur}</p>
                </div>
              ))}
            </div>
            {resultat.alertes.length > 0 ? (
              <ul className="mt-4 space-y-1 rounded-lg border border-[#f2d3b5] bg-[#fdf5ea] p-3 text-sm text-[#7c4a21]">
                {resultat.alertes.map((alerte) => (
                  <li key={alerte}>• {alerte}</li>
                ))}
              </ul>
            ) : null}
            {resultat.nonPlacees.length > 0 ? (
              <details className="mt-3 text-sm">
                <summary className="cursor-pointer font-semibold text-[color:var(--inj-green)]">
                  Séances non placées ({resultat.nonPlacees.length})
                </summary>
                <ul className="mt-2 space-y-1 text-xs text-slate-600">
                  {resultat.nonPlacees.slice(0, 15).map((n, i) => (
                    <li key={`${n.moduleCode}-${n.groupeCode}-${i}`}>
                      S{n.semestre} · {n.moduleCode} · {n.groupeCode} · {n.typeSeance} — {n.raison}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
