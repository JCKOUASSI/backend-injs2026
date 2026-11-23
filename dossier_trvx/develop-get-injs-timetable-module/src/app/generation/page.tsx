import Link from "next/link";

import { GenerationForm } from "@/components/get-injs/GenerationForm";
import { Badge, PageHeader, Section } from "@/components/get-injs/ui";
import { getAnneeActive, getHistorique, getReferentiels } from "@/lib/get-injs/queries";
import { ensureSeeded } from "@/lib/get-injs/seed";
import { referentiel } from "../../../get-injs-app/data/referentiel";

export const dynamic = "force-dynamic";

type Stats = {
  seances?: number;
  conflits?: number;
  nonPlacees?: number;
  tauxCouverture?: number;
  dureeMs?: number;
};

export default async function GenerationPage() {
  await ensureSeeded();
  const [referentiels, annee, historique] = await Promise.all([
    getReferentiels(),
    getAnneeActive(),
    getHistorique(),
  ]);
  const anneeDefaut = annee?.code ?? referentiel.activeYear;

  return (
    <div>
      <PageHeader
        eyebrow="Moteur LMD"
        title="Générer les emplois du temps"
        description="Un seul passage pour toute l'année académique ou pour un périmètre ciblé (filière, formation, niveau, groupe, semestre). Le moteur garantit l'absence de double réservation de salle, d'enseignant et de groupe."
        actions={
          <>
            <Link href="/emplois-du-temps" className="btn-ghost">
              Consulter les grilles
            </Link>
            <Link href="/referentiels" className="btn-ghost">
              Vérifier les référentiels
            </Link>
          </>
        }
      />

      <GenerationForm
        annees={referentiels.annees.map((a) => ({ code: a.code, label: a.label }))}
        filieres={referentiels.filieres.map((f) => ({ id: f.id, code: f.code, nom: f.nom }))}
        formations={referentiels.formations.map((f) => ({ id: f.id, code: f.code, nom: f.nom }))}
        niveaux={referentiels.niveaux.map((n) => n.niveau)}
        groupes={referentiels.groupes.map((g) => ({
          id: g.id,
          code: g.code,
          nom: g.label,
          niveau: g.niveau,
          effectif: g.effectif,
        }))}
        anneeDefaut={anneeDefaut}
      />

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        <Section title="Historique des générations" subtitle="Traçabilité complète : périmètre, volumes, conflits, durée">
          {historique.runs.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500">Aucune génération enregistrée.</p>
          ) : (
            <table className="table-injs">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Périmètre</th>
                  <th>Semestres</th>
                  <th>Séances</th>
                  <th>Couverture</th>
                  <th>Conflits</th>
                  <th>Durée</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {historique.runs.map((run) => {
                  const stats = run.stats as Stats;
                  const scope = run.scope as {
                    filiereCode?: string | null;
                    formationId?: number | null;
                    niveau?: string | null;
                    semestres?: number[];
                  };
                  return (
                    <tr key={run.id}>
                      <td className="whitespace-nowrap text-slate-600">
                        {new Date(run.demarreLe).toLocaleString("fr-FR", {
                          day: "2-digit",
                          month: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td>
                        <span className="font-semibold text-[color:var(--inj-green)]">
                          {scope.filiereCode ?? "Toutes filières"}
                        </span>
                        <span className="block text-[0.7rem] text-slate-500">
                          {scope.niveau ?? "Tous niveaux"}
                          {scope.formationId ? ` · formation #${scope.formationId}` : ""}
                        </span>
                      </td>
                      <td className="whitespace-nowrap text-slate-600">
                        S{(scope.semestres ?? []).join(", S")}
                      </td>
                      <td className="font-semibold">{stats.seances ?? 0}</td>
                      <td>{stats.tauxCouverture ?? 0} %</td>
                      <td>
                        {(stats.conflits ?? 0) > 0 ? (
                          <Badge tone="red">{stats.conflits}</Badge>
                        ) : (
                          <Badge tone="green">0</Badge>
                        )}
                      </td>
                      <td className="whitespace-nowrap text-slate-500">
                        {((stats.dureeMs ?? run.dureeMs) / 1000).toFixed(1)} s
                      </td>
                      <td>
                        <Badge tone="blue">{run.statut}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Section>

        <Section title="Emplois du temps versionnés" subtitle="Chaque passage crée une version horodatée">
          {historique.edts.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500">Aucune version d&apos;EDT.</p>
          ) : (
            <ul className="divide-y divide-[#eee8db]">
              {historique.edts.map((edt) => (
                <li key={edt.id} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-[color:var(--inj-green)]">{edt.code}</p>
                      <p className="text-[0.7rem] text-slate-500">
                        {new Date(edt.genereLe).toLocaleString("fr-FR")}
                      </p>
                    </div>
                    <Badge tone={edt.statut === "publie" ? "green" : "neutral"}>{edt.statut}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-600">{edt.libelle}</p>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <div className="card mt-6 border-[#f2d3b5] bg-[#fdf5ea] p-5">
        <h3 className="font-display text-lg font-semibold text-[#9b4d11]">
          Règles métier appliquées par le moteur
        </h3>
        <div className="mt-2 grid gap-2 text-sm text-[#7c4a21] md:grid-cols-2">
          <p>• Un enseignant ne peut pas être affecté à deux séances au même créneau.</p>
          <p>• Une salle ne peut accueillir qu&apos;une séance par créneau et par semestre.</p>
          <p>• Un groupe ne peut pas suivre deux cours simultanément.</p>
          <p>• Le CM est mutualisé au niveau de la promotion puis découpé selon la capacité des amphis.</p>
          <p>• Le meilleur ajustement de capacité est utilisé pour les TD et TP.</p>
          <p>• Les quotas par groupe limitent la charge hebdomadaire à 30 séances par défaut.</p>
        </div>
      </div>
    </div>
  );
}
