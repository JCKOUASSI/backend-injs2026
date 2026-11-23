import Link from "next/link";

import { PrintButton } from "@/components/get-injs/PrintButton";
import { Badge, EmptyState, PageHeader, Section } from "@/components/get-injs/ui";
import {
  getAnneeActive,
  getEmploiDuTemps,
  getReferentiels,
  getResumeEmploiDuTemps,
  type SeanceDetaillee,
} from "@/lib/get-injs/queries";
import { ensureSeeded } from "@/lib/get-injs/seed";
import { semestresDuNiveau } from "../../../get-injs-app/lib/engine";
import { referentiel } from "../../../get-injs-app/data/referentiel";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function lire(params: Record<string, string | string[] | undefined>, cle: string) {
  const valeur = params[cle];
  return Array.isArray(valeur) ? valeur[0] : valeur;
}

const TYPE_TONES: Record<string, string> = {
  CM: "border-[#c9dced] bg-[#eaf2f9] text-[#245b80]",
  TD: "border-[#c5e0d1] bg-[#e8f3ec] text-[#1c5c45]",
  TP: "border-[#f2d3b5] bg-[#fbeddd] text-[#9b4d11]",
};

export default async function EmploisDuTempsPage({ searchParams }: { searchParams: SearchParams }) {
  await ensureSeeded();
  const params = await searchParams;
  const referentiels = await getReferentiels();
  const anneeActive = await getAnneeActive();
  const anneeCode = lire(params, "anneeCode") ?? anneeActive?.code ?? referentiel.activeYear;

  const groupeIdParam = Number(lire(params, "groupeId"));
  const formationIdParam = Number(lire(params, "formationId"));
  const niveauParam = lire(params, "niveau");
  const semestreParam = Number(lire(params, "semestre"));
  const typeParam = lire(params, "typeSeance");
  const filiereParam = lire(params, "filiereCode");

  const groupeChoisi =
    referentiels.groupes.find((g) => g.id === groupeIdParam) ??
    (!formationIdParam && !niveauParam
      ? referentiels.groupes.find((g) => g.niveau === "L1") ?? referentiels.groupes[0]
      : undefined);

  const semestre =
    semestreParam ||
    (groupeChoisi ? semestresDuNiveau(groupeChoisi.niveau)[0] : undefined);

  const filtres = {
    anneeCode,
    filiereCode: filiereParam,
    formationId: formationIdParam || undefined,
    niveau: niveauParam || undefined,
    groupeId: groupeChoisi?.id,
    semestre,
    typeSeance: typeParam,
    limit: 500,
  };

  const [lignes, resume] = await Promise.all([
    getEmploiDuTemps(filtres),
    getResumeEmploiDuTemps(filtres),
  ]);

  const groupeInfo = groupeChoisi
    ? referentiels.groupes.find((g) => g.id === groupeChoisi.id)
    : undefined;
  const formationInfo = referentiels.formations.find(
    (f) => f.id === (groupeInfo?.formationId ?? formationIdParam),
  );

  const query = new URLSearchParams();
  query.set("anneeCode", anneeCode);
  if (groupeChoisi) query.set("groupeId", String(groupeChoisi.id));
  if (formationIdParam) query.set("formationId", String(formationIdParam));
  if (niveauParam) query.set("niveau", niveauParam);
  if (semestre) query.set("semestre", String(semestre));
  if (filiereParam) query.set("filiereCode", filiereParam);
  if (typeParam) query.set("typeSeance", typeParam);

  const titrePerimetre = groupeChoisi
    ? `${groupeChoisi.code} · ${groupeChoisi.label}`
    : formationIdParam
      ? `${formationInfo?.code ?? "Formation"} · vue formation`
      : niveauParam
        ? `Niveau ${niveauParam} · tous groupes`
        : "Toutes les séances";

  return (
    <div>
      <PageHeader
        eyebrow="Exploitation"
        title="Emplois du temps"
        description="Grille hebdomadaire par filière, formation, vague, groupe et semestre. Les cours magistraux sont mutualisés à l'échelle de la promotion ; les TD et TP sont propres à chaque groupe."
        actions={
          <>
            <Link href={`/api/emplois-du-temps/export?${query.toString()}`} className="btn-primary">
              Exporter CSV
            </Link>
            <PrintButton label="Imprimer la grille" />
          </>
        }
      />

      <form method="get" className="card mb-5 grid gap-3 p-4 md:grid-cols-3 xl:grid-cols-6">
        <div>
          <label className="label" htmlFor="anneeCode">
            Année académique
          </label>
          <select id="anneeCode" name="anneeCode" defaultValue={anneeCode} className="field mt-1">
            {referentiels.annees.map((a) => (
              <option key={a.id} value={a.code}>
                {a.code}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="filiereCode">
            Filière
          </label>
          <select id="filiereCode" name="filiereCode" defaultValue={filiereParam ?? ""} className="field mt-1">
            <option value="">Toutes</option>
            {referentiels.filieres.map((f) => (
              <option key={f.id} value={f.code}>
                {f.code}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="formationId">
            Formation
          </label>
          <select id="formationId" name="formationId" defaultValue={formationIdParam || ""} className="field mt-1">
            <option value="">Toutes</option>
            {referentiels.formations.map((f) => (
              <option key={f.id} value={f.id}>
                {f.code} — {f.nom}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="niveau">
            Niveau
          </label>
          <select id="niveau" name="niveau" defaultValue={niveauParam ?? ""} className="field mt-1">
            <option value="">Tous</option>
            {referentiels.niveaux.map(({ niveau }) => (
              <option key={niveau} value={niveau}>
                {niveau}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="groupeId">
            Groupe
          </label>
          <select id="groupeId" name="groupeId" defaultValue={groupeChoisi?.id ?? ""} className="field mt-1">
            <option value="">Toute la promotion</option>
            {referentiels.groupes.map((g) => (
              <option key={g.id} value={g.id}>
                {g.code} ({g.effectif} ét.)
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="label" htmlFor="semestre">
              Semestre
            </label>
            <select id="semestre" name="semestre" defaultValue={semestre ?? ""} className="field mt-1">
              <option value="">Tous</option>
              {Array.from({ length: 10 }, (_, i) => i + 1).map((s) => (
                <option key={s} value={s}>
                  Semestre {s}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className="btn-primary h-[38px]">
            Afficher
          </button>
        </div>
        <div className="md:col-span-3 xl:col-span-6 flex flex-wrap items-center gap-2 border-t border-[color:var(--inj-line)] pt-2">
          <span className="label">Équivalences de parcours</span>
          {referentiels.groupes
            .filter((g) => g.niveau === (groupeChoisi?.niveau ?? "L1"))
            .slice(0, 10)
            .map((g) => (
              <Link
                key={g.id}
                href={`/emplois-du-temps?anneeCode=${anneeCode}&groupeId=${g.id}`}
                className={`rounded-full border px-2.5 py-1 text-[0.7rem] font-semibold ${
                  g.id === groupeChoisi?.id
                    ? "border-[color:var(--inj-green)] bg-[color:var(--inj-green)] text-white"
                    : "border-[color:var(--inj-line)] bg-white text-[color:var(--inj-green)]"
                }`}
              >
                {g.code}
              </Link>
            ))}
          <Link href={`/emplois-du-temps?anneeCode=${anneeCode}`} className="ml-auto text-xs font-semibold text-[color:var(--inj-green-soft)] underline">
            Réinitialiser les filtres
          </Link>
        </div>
      </form>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Badge tone="green">{titrePerimetre}</Badge>
        {semestre ? <Badge tone="blue">Semestre {semestre}</Badge> : <Badge>Tous semestres</Badge>}
        <Badge tone="orange">{resume.seances} séance(s)</Badge>
        <span className="text-xs text-slate-500">
          {resume.cm} CM · {resume.td} TD · {resume.tp} TP · {resume.places.toLocaleString("fr-FR")} places
          étudiantes couvertes
        </span>
      </div>

      {lignes.length === 0 ? (
        <EmptyState
          title="Aucune séance sur ce périmètre"
          description="Lancez une génération pour cette année académique, ce niveau ou ce groupe. Les séances apparaîtront immédiatement dans la grille."
          action={
            <Link href="/generation" className="btn-primary">
              Générer les emplois du temps
            </Link>
          }
        />
      ) : (
        <>
          <div className="card mb-6 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--inj-line)] px-4 py-3">
              <div>
                <h2 className="font-display text-lg font-semibold text-[color:var(--inj-green)]">
                  Grille hebdomadaire {semestre ? `— Semestre ${semestre}` : ""}
                </h2>
                <p className="text-xs text-slate-500">
                  {groupeChoisi
                    ? `${groupeChoisi.effectif} étudiants · ${formationInfo?.nom ?? ""}`
                    : "Vue consolidée : plusieurs groupes peuvent apparaître sur un créneau."}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge tone="blue">CM — cours magistral</Badge>
                <Badge tone="green">TD — travaux dirigés</Badge>
                <Badge tone="orange">TP — travaux pratiques</Badge>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] border-collapse text-xs">
                <thead>
                  <tr>
                    <th className="w-[92px] bg-[#f2eee4] px-2 py-2 text-left text-[0.65rem] uppercase tracking-wide text-[#48574f]">
                      Créneau
                    </th>
                    {referentiel.jours.map((jour) => (
                      <th
                        key={jour.code}
                        className="bg-[#f2eee4] px-2 py-2 text-left text-[0.65rem] uppercase tracking-wide text-[#48574f]"
                      >
                        {jour.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {referentiel.slots.map((slot) => (
                    <tr key={slot.code}>
                      <th className="border-t border-[#eee8db] bg-[#faf7ef] px-2 py-2 text-left align-top">
                        <span className="block text-[0.7rem] font-bold text-[color:var(--inj-green)]">{slot.code}</span>
                        <span className="block text-[0.65rem] font-normal text-slate-500">{slot.label}</span>
                      </th>
                      {referentiel.jours.map((jour) => {
                        const cellules = lignes.filter(
                          (l) => l.jour === jour.code && l.slotCode === slot.code,
                        );
                        return (
                          <td
                            key={jour.code}
                            className="h-[74px] border-t border-l border-[#eee8db] px-1.5 py-1.5 align-top"
                          >
                            {cellules.length === 0 ? (
                              <span className="block h-full rounded-md bg-[#fbf9f3]" />
                            ) : (
                              <div className="space-y-1">
                                {cellules.slice(0, 3).map((seance) => (
                                  <SeanceCard key={seance.id} seance={seance} />
                                ))}
                                {cellules.length > 3 ? (
                                  <p className="text-[0.6rem] font-semibold text-slate-500">
                                    +{cellules.length - 3} autre(s)
                                  </p>
                                ) : null}
                              </div>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <Section
            title="Détail des séances"
            subtitle="Vue tabulaire exploitable pour la scolarité et les enseignants"
            actions={<Badge tone="neutral">{lignes.length} lignes affichées · 500 max</Badge>}
          >
            <table className="table-injs">
              <thead>
                <tr>
                  <th>Semestre</th>
                  <th>Jour</th>
                  <th>Horaire</th>
                  <th>Type</th>
                  <th>Module</th>
                  <th>Groupe</th>
                  <th>Salle</th>
                  <th>Enseignant</th>
                  <th>Effectif</th>
                </tr>
              </thead>
              <tbody>
                {lignes.map((l) => (
                  <tr key={`detail-${l.id}`}>
                    <td className="font-semibold">S{l.semestre}</td>
                    <td>{referentiel.jours.find((j) => j.code === l.jour)?.label ?? l.jour}</td>
                    <td className="whitespace-nowrap">{l.heureDebut} – {l.heureFin}</td>
                    <td>
                      <span className={`rounded border px-1.5 py-0.5 text-[0.65rem] font-bold ${TYPE_TONES[l.typeSeance] ?? ""}`}>
                        {l.typeSeance}
                      </span>
                    </td>
                    <td>
                      <span className="font-medium">{l.moduleCode}</span>
                      <span className="block max-w-[320px] truncate text-[0.7rem] text-slate-500">{l.module}</span>
                    </td>
                    <td>{l.groupeCode ?? "Promotion"}</td>
                    <td>
                      {l.salle}
                      <span className="block text-[0.65rem] text-slate-500">{l.salleType} · {l.capacite} pl.</span>
                    </td>
                    <td>{l.ennseignant ?? <span className="text-[#9b4d11]">À affecter</span>}</td>
                    <td>{l.effectif}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </>
      )}
    </div>
  );
}

function SeanceCard({ seance }: { seance: SeanceDetaillee }) {
  return (
    <div className={`rounded border px-1.5 py-1 ${TYPE_TONES[seance.typeSeance] ?? "border-[#e0d8c7] bg-white"}`}>
      <div className="flex items-center justify-between gap-1">
        <span className="text-[0.6rem] font-bold uppercase">{seance.typeSeance}</span>
        <span className="text-[0.55rem] font-semibold opacity-80">{seance.salle}</span>
      </div>
      <p className="text-[0.65rem] leading-tight font-semibold">{seance.moduleCode}</p>
      <p className="truncate text-[0.6rem] leading-tight opacity-90">{seance.module}</p>
      <p className="truncate text-[0.55rem] opacity-80">
        {seance.groupeCode ?? "Promotion"} · {seance.ennseignant ?? "À affecter"}
      </p>
    </div>
  );
}
