import Link from "next/link";

import { Badge, PageHeader, Section, StatCard } from "@/components/get-injs/ui";
import { getReferentielComplet } from "@/lib/get-injs/queries";
import { ensureSeeded } from "@/lib/get-injs/seed";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const ONGLETS = [
  { cle: "formations", label: "Filières & formations" },
  { cle: "modules", label: "Maquettes & modules" },
  { cle: "salles", label: "Bâtiments & salles" },
  { cle: "enseignants", label: "Enseignants" },
  { cle: "groupes", label: "Groupes & vagues" },
];

function lire(params: Record<string, string | string[] | undefined>, cle: string) {
  const valeur = params[cle];
  return Array.isArray(valeur) ? valeur[0] : valeur;
}

export default async function ReferentielsPage({ searchParams }: { searchParams: SearchParams }) {
  await ensureSeeded();
  const params = await searchParams;
  const onglet = lire(params, "onglet") ?? "formations";
  const referentiel = await getReferentielComplet();
  const formationParId = new Map(referentiel.formations.map((f) => [f.id, f]));
  const filiereParId = new Map(referentiel.filieres.map((f) => [f.id, f]));
  const batimentParId = new Map(referentiel.batiments.map((b) => [b.id, b]));
  const formationFiltre = Number(lire(params, "formationId") ?? referentiel.formations[0]?.id ?? 0);
  const modulesFormation = referentiel.modules.filter((m) => m.formationId === formationFiltre);
  const modulesParSemestre = new Map<number, typeof modulesFormation>();
  for (const module of modulesFormation) {
    const liste = modulesParSemestre.get(module.semestre) ?? [];
    liste.push(module);
    modulesParSemestre.set(module.semestre, liste);
  }
  const totalEffectif = referentiel.groupes.reduce((total, g) => total + g.effectif, 0);

  return (
    <div>
      <PageHeader
        eyebrow="Référentiels INJS"
        title="Données de référence 2026-2027"
        description="Filières, formations, maquettes LMD, infrastructures, enseignants, groupes et vagues issues des documents officiels du dossier_trvx. Ces référentiels alimentent directement le moteur de génération."
        actions={
          <>
            <Link href="/generation" className="btn-primary">
              Générer depuis ces référentiels
            </Link>
            <Link href="/conception" className="btn-ghost">
              Voir la conception
            </Link>
          </>
        }
      />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <StatCard label="Filières" value={referentiel.filieres.length} accent />
        <StatCard label="Formations" value={referentiel.formations.length} />
        <StatCard label="Modules" value={referentiel.modules.length} />
        <StatCard label="Groupes" value={referentiel.groupes.length} />
        <StatCard label="Vagues" value={referentiel.vagues.length} />
        <StatCard label="Salles" value={referentiel.salles.length} />
        <StatCard label="Enseignants" value={referentiel.enseignants.length} />
      </div>

      <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
        {ONGLETS.map((o) => (
          <Link
            key={o.cle}
            href={`/referentiels?onglet=${o.cle}`}
            className={`whitespace-nowrap rounded-full border px-3.5 py-1.5 text-xs font-semibold ${
              onglet === o.cle
                ? "border-[color:var(--inj-green)] bg-[color:var(--inj-green)] text-white"
                : "border-[color:var(--inj-line)] bg-[#fffdf8] text-[color:var(--inj-green)]"
            }`}
          >
            {o.label}
          </Link>
        ))}
      </div>

      {onglet === "formations" ? (
        <div className="grid gap-5 xl:grid-cols-[1fr_1.2fr]">
          <Section title="Filières (mentions)" subtitle="Écoles et mentions de l'INJS">
            <table className="table-injs">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Filière</th>
                  <th>École</th>
                </tr>
              </thead>
              <tbody>
                {referentiel.filieres.map((filiere) => (
                  <tr key={filiere.id}>
                    <td className="font-semibold text-[color:var(--inj-green)]">{filiere.code}</td>
                    <td>{filiere.nom}</td>
                    <td>
                      <Badge tone="neutral">{filiere.ecole}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
          <Section title="Formations (parcours)" subtitle="Cycle universitaire LMD, maquette publiée ou paramétrable">
            <table className="table-injs">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Formation</th>
                  <th>Filière</th>
                  <th>Maquette</th>
                  <th>Groupes</th>
                </tr>
              </thead>
              <tbody>
                {referentiel.formations.map((formation) => (
                  <tr key={formation.id}>
                    <td className="font-semibold text-[color:var(--inj-green)]">{formation.code}</td>
                    <td>{formation.nom}</td>
                    <td>{filiereParId.get(formation.filiereId)?.code ?? "—"}</td>
                    <td>
                      <Badge tone={formation.maquette.includes("publiee") ? "green" : "orange"}>
                        {formation.maquette.includes("publiee") ? "publiée" : "paramétrable"}
                      </Badge>
                    </td>
                    <td>{referentiel.groupes.filter((g) => g.formationId === formation.id).length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>
      ) : null}

      {onglet === "modules" ? (
        <div className="space-y-4">
          <form method="get" className="card flex flex-wrap items-end gap-3 p-4">
            <input type="hidden" name="onglet" value="modules" />
            <div>
              <label className="label" htmlFor="formationId">
                Formation
              </label>
              <select id="formationId" name="formationId" defaultValue={String(formationFiltre)} className="field mt-1 min-w-[260px]">
                {referentiel.formations.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.code} — {f.nom}
                  </option>
                ))}
              </select>
            </div>
            <button className="btn-primary" type="submit">
              Afficher la maquette
            </button>
            <Badge tone="neutral">{modulesFormation.length} modules</Badge>
            <Badge tone="green">
              {modulesFormation.reduce((t, m) => t + m.heuresCm + m.heuresTd + m.heuresTp, 0)} h de contact
            </Badge>
          </form>

          {[...modulesParSemestre.entries()]
            .sort((a, b) => a[0] - b[0])
            .map(([semestre, modules]) => (
              <Section
                key={semestre}
                title={`Semestre ${semestre}`}
                subtitle={`${modules.length} modules · ${modules.reduce((t, m) => t + m.ects, 0)} crédits ECTS`}
              >
                <table className="table-injs">
                  <thead>
                    <tr>
                      <th>Code</th>
                      <th>Titre du module</th>
                      <th>Nature</th>
                      <th>ECTS</th>
                      <th>CM</th>
                      <th>TD</th>
                      <th>TP</th>
                      <th>Salle CM</th>
                      <th>Salle TD</th>
                      <th>Salle TP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {modules.map((module) => (
                      <tr key={module.id}>
                        <td className="font-semibold text-[color:var(--inj-green)]">{module.code}</td>
                        <td>{module.titre}</td>
                        <td>
                          <Badge
                            tone={module.nature === "pratique" ? "orange" : module.nature === "mixte" ? "blue" : "neutral"}
                          >
                            {module.nature}
                          </Badge>
                        </td>
                        <td>{module.ects}</td>
                        <td>{module.heuresCm} h</td>
                        <td>{module.heuresTd} h</td>
                        <td>{module.heuresTp} h</td>
                        <td className="font-mono text-[0.68rem]">{module.roomNeedCm}</td>
                        <td className="font-mono text-[0.68rem]">{module.roomNeedTd}</td>
                        <td className="font-mono text-[0.68rem]">{module.roomNeedTp}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>
            ))}
        </div>
      ) : null}

      {onglet === "salles" ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {referentiel.batiments.map((b) => (
              <div key={b.id} className="card-flat p-3">
                <p className="text-xs font-bold text-[color:var(--inj-green)]">{b.code}</p>
                <p className="text-[0.7rem] text-slate-600">{b.nom}</p>
                <p className="mt-1 text-[0.65rem] text-slate-500">
                  {referentiel.salles.filter((s) => s.batimentId === b.id).length} salle(s)
                </p>
              </div>
            ))}
          </div>
          <Section title="Salles et espaces de formation" subtitle="Capacités validées, type et équipements">
            <table className="table-injs">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Nom</th>
                  <th>Type</th>
                  <th>Capacité</th>
                  <th>Bâtiment</th>
                  <th>Équipements</th>
                  <th>Planifiable</th>
                </tr>
              </thead>
              <tbody>
                {referentiel.salles.map((salle) => (
                  <tr key={salle.id}>
                    <td className="font-mono text-[0.7rem] font-semibold text-[color:var(--inj-green)]">{salle.code}</td>
                    <td className="max-w-[280px] truncate">{salle.nom}</td>
                    <td>
                      <Badge tone={salle.type === "amphi" ? "blue" : salle.type === "gym" || salle.type === "terrain" ? "orange" : "neutral"}>
                        {salle.type}
                      </Badge>
                    </td>
                    <td className="font-semibold">{salle.capacite}</td>
                    <td>{batimentParId.get(salle.batimentId ?? 0)?.code ?? "—"}</td>
                    <td className="max-w-[260px] truncate text-[0.7rem] text-slate-500">{salle.equipements || "—"}</td>
                    <td>{salle.schedulable ? <Badge tone="green">oui</Badge> : <Badge tone="red">non</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>
      ) : null}

      {onglet === "enseignants" ? (
        <Section title="Corps enseignant" subtitle="Grades, spécialités et charges hebdomadaires maximales">
          <table className="table-injs">
            <thead>
              <tr>
                <th>Matricule</th>
                <th>Nom et prénoms</th>
                <th>Grade</th>
                <th>Spécialité / formation</th>
                <th>Email</th>
                <th>Charge max.</th>
              </tr>
            </thead>
            <tbody>
              {referentiel.enseignants.map((enseignant) => (
                <tr key={enseignant.id}>
                  <td className="font-mono text-[0.7rem] text-[color:var(--inj-green)]">{enseignant.matricule}</td>
                  <td>
                    <span className="font-semibold">{enseignant.nom}</span> {enseignant.prenom}
                  </td>
                  <td>{enseignant.grade}</td>
                  <td>
                    <Badge tone="blue">{enseignant.specialite}</Badge>
                  </td>
                  <td className="text-[0.7rem] text-slate-500">{enseignant.email}</td>
                  <td>{enseignant.maxHeures} h</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      {onglet === "groupes" ? (
        <div className="grid gap-5 xl:grid-cols-[1.3fr_1fr]">
          <Section
            title="Groupes pédagogiques"
            subtitle={`${referentiel.groupes.length} groupes · ${totalEffectif.toLocaleString("fr-FR")} étudiants rattachés`}
          >
            <table className="table-injs">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Libellé</th>
                  <th>Formation</th>
                  <th>Niveau</th>
                  <th>Effectif</th>
                  <th>Vague</th>
                </tr>
              </thead>
              <tbody>
                {referentiel.groupes.map((groupe) => (
                  <tr key={groupe.id}>
                    <td className="font-semibold text-[color:var(--inj-green)]">{groupe.code}</td>
                    <td className="max-w-[260px] truncate">{groupe.label}</td>
                    <td>{formationParId.get(groupe.formationId)?.code ?? "—"}</td>
                    <td>{groupe.niveau}</td>
                    <td className="font-semibold">{groupe.effectif}</td>
                    <td className="text-[0.7rem] text-slate-600">
                      {referentiel.vagues.find((v) => v.id === groupe.vagueId)?.code ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
          <Section title="Vagues / promotions" subtitle="Sessions de recrutement et effectifs réels">
            <table className="table-injs">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Libellé</th>
                  <th>Niveau</th>
                  <th>Effectif prévu</th>
                  <th>Effectif réel</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {referentiel.vagues.map((vague) => (
                  <tr key={vague.id}>
                    <td className="font-semibold text-[color:var(--inj-green)]">{vague.code}</td>
                    <td className="max-w-[220px] truncate">{vague.label}</td>
                    <td>{vague.niveau}</td>
                    <td>{vague.effectifPrevu}</td>
                    <td className="font-semibold">{vague.effectifReel}</td>
                    <td>
                      <Badge tone="green">{vague.statut}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>
      ) : null}
    </div>
  );
}
