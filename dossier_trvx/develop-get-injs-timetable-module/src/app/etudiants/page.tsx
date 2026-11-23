import Link from "next/link";

import { Badge, PageHeader, Section, StatCard } from "@/components/get-injs/ui";
import { getEtudiants, getReferentiels } from "@/lib/get-injs/queries";
import { ensureSeeded } from "@/lib/get-injs/seed";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function lire(params: Record<string, string | string[] | undefined>, cle: string) {
  const valeur = params[cle];
  return Array.isArray(valeur) ? valeur[0] : valeur;
}

export default async function EtudiantsPage({ searchParams }: { searchParams: SearchParams }) {
  await ensureSeeded();
  const params = await searchParams;
  const recherche = lire(params, "q") ?? "";
  const formationCode = lire(params, "formation") ?? "";
  const niveau = lire(params, "niveau") ?? "";
  const page = Number(lire(params, "page") ?? "1") || 1;

  const [referentiels, resultat] = await Promise.all([
    getReferentiels(),
    getEtudiants({ recherche, formationCode, niveau, page, taille: 25 }),
  ]);

  const totalPages = Math.max(1, Math.ceil(resultat.total / resultat.taille));
  const construireLien = (nouvellePage: number) => {
    const query = new URLSearchParams();
    if (recherche) query.set("q", recherche);
    if (formationCode) query.set("formation", formationCode);
    if (niveau) query.set("niveau", niveau);
    query.set("page", String(nouvellePage));
    return `/etudiants?${query.toString()}`;
  };

  const hommes = resultat.lignes.filter((e) => e.sexe === "M").length;
  const importes = resultat.lignes.filter((e) => e.source === "import").length;

  return (
    <div>
      <PageHeader
        eyebrow="Populations LMD"
        title="Étudiants inscrits"
        description="Population issue du processus d'inscription de backend-injs2026 ou d'un fichier externe importé. Chaque étudiant est rattaché à un parcours complet : filière, formation, niveau, groupe, vague et semestres."
        actions={
          <>
            <Link href="/import" className="btn-ghost">
              Importer un fichier
            </Link>
            <Link href="/emplois-du-temps" className="btn-primary">
              Emplois du temps
            </Link>
          </>
        }
      />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Étudiants filtrés" value={resultat.total.toLocaleString("fr-FR")} accent />
        <StatCard label="Page" value={`${resultat.page} / ${totalPages}`} hint={`${resultat.taille} par page`} />
        <StatCard label="Femmes / hommes" value={`${resultat.lignes.length - hommes} / ${hommes}`} hint="Sur la page affichée" />
        <StatCard label="Origine import" value={importes} hint="Sur la page affichée" />
      </div>

      <form method="get" className="card mb-5 grid gap-3 p-4 md:grid-cols-4">
        <div className="md:col-span-2">
          <label className="label" htmlFor="q">
            Recherche (matricule, nom, prénom)
          </label>
          <input id="q" name="q" defaultValue={recherche} className="field mt-1" placeholder="Ex. INJS-2026-00001 ou Kouassi" />
        </div>
        <div>
          <label className="label" htmlFor="formation">
            Formation
          </label>
          <select id="formation" name="formation" defaultValue={formationCode} className="field mt-1">
            <option value="">Toutes</option>
            {referentiels.formations.map((f) => (
              <option key={f.id} value={f.code}>
                {f.code} — {f.nom}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="niveau">
            Niveau
          </label>
          <div className="flex gap-2">
            <select id="niveau" name="niveau" defaultValue={niveau} className="field mt-1">
              <option value="">Tous</option>
              {referentiels.niveaux.map(({ niveau: n }) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <button type="submit" className="btn-primary mt-1 h-[38px]">
              Filtrer
            </button>
          </div>
        </div>
      </form>

      <Section
        title="Liste des étudiants"
        subtitle="Rattachement académique complet, prêt pour la génération et les présences"
        actions={
          <div className="flex items-center gap-2">
            <Badge tone="neutral">Source : base + imports</Badge>
            <Badge tone="green">{resultat.total.toLocaleString("fr-FR")} étudiant(s)</Badge>
          </div>
        }
      >
        <table className="table-injs">
          <thead>
            <tr>
              <th>Matricule</th>
              <th>Nom et prénoms</th>
              <th>Sexe</th>
              <th>Formation</th>
              <th>Niveau</th>
              <th>Groupe</th>
              <th>Vague</th>
              <th>Statut</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {resultat.lignes.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-8 text-center text-sm text-slate-500">
                  Aucun étudiant ne correspond aux critères.
                </td>
              </tr>
            ) : (
              resultat.lignes.map((etudiant) => (
                <tr key={etudiant.id}>
                  <td className="whitespace-nowrap font-mono text-[0.72rem] text-[color:var(--inj-green)]">
                    {etudiant.matricule}
                  </td>
                  <td>
                    <span className="font-semibold">{etudiant.nom}</span> {etudiant.prenom}
                  </td>
                  <td>{etudiant.sexe}</td>
                  <td>
                    <span className="font-semibold">{etudiant.formation ?? "—"}</span>
                    <span className="block max-w-[240px] truncate text-[0.68rem] text-slate-500">
                      {etudiant.formationNom ?? "Parcours non renseigné"}
                    </span>
                  </td>
                  <td>{etudiant.niveau ?? "—"}</td>
                  <td>{etudiant.groupe ?? "—"}</td>
                  <td className="text-[0.7rem] text-slate-600">{etudiant.vague ?? "—"}</td>
                  <td>
                    <Badge tone={etudiant.statut === "inscrit" ? "green" : "neutral"}>{etudiant.statut}</Badge>
                  </td>
                  <td>
                    <Badge tone={etudiant.source === "import" ? "orange" : "blue"}>{etudiant.source}</Badge>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Section>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">
          {(resultat.page - 1) * resultat.taille + 1} –{" "}
          {Math.min(resultat.page * resultat.taille, resultat.total)} sur {resultat.total.toLocaleString("fr-FR")}
        </p>
        <div className="flex items-center gap-2">
          <Link
            href={construireLien(Math.max(1, resultat.page - 1))}
            className={`btn-ghost ${resultat.page <= 1 ? "pointer-events-none opacity-40" : ""}`}
          >
            ← Précédent
          </Link>
          <span className="text-xs font-semibold text-slate-600">
            Page {resultat.page} / {totalPages}
          </span>
          <Link
            href={construireLien(Math.min(totalPages, resultat.page + 1))}
            className={`btn-ghost ${resultat.page >= totalPages ? "pointer-events-none opacity-40" : ""}`}
          >
            Suivant →
          </Link>
        </div>
      </div>
    </div>
  );
}
