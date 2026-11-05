import Link from "next/link";

import { ImportForm } from "@/components/get-injs/ImportForm";
import { Badge, PageHeader, Section } from "@/components/get-injs/ui";
import { getAnneeActive, getHistorique, getReferentiels } from "@/lib/get-injs/queries";
import { ensureSeeded } from "@/lib/get-injs/seed";
import { referentiel } from "../../../get-injs-app/data/referentiel";

export const dynamic = "force-dynamic";

export default async function ImportPage() {
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
        eyebrow="Situation 2 · fichier externe"
        title="Importer les étudiants inscrits"
        description="Recevez un fichier d'inscrits produit hors application (scolarité, rectorat, partenaire) et générez malgré tout tous les emplois du temps de l'année : le module reconstruit filière, formation, vague, groupe et maquette lorsque le parcours LMD n'existe pas encore."
        actions={
          <>
            <a href="/api/import" className="btn-ghost" download>
              Modèle CSV
            </a>
            <Link href="/generation" className="btn-primary">
              Moteur de génération
            </Link>
          </>
        }
      />

      <ImportForm
        annees={referentiels.annees.map((a) => ({ code: a.code, label: a.label }))}
        anneeDefaut={anneeDefaut}
      />

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.25fr_1fr]">
        <Section title="Colonnes acceptées" subtitle="Détection automatique par alias, insensible aux accents et à la casse">
          <div className="grid gap-3 p-4 text-sm sm:grid-cols-2">
            {[
              ["Matricule", "matricule, code_etudiant, numéro…"],
              ["Identité", "nom, prénom(s), sexe, date_naissance"],
              ["Contact", "email, téléphone"],
              ["Parcours", "filière/mention, formation/parcours"],
              ["Classement", "niveau (L1…M2), groupe, vague/promotion"],
              ["Scolarité", "semestre, statut, année académique"],
            ].map(([titre, exemples]) => (
              <div key={titre} className="rounded-lg border border-[color:var(--inj-line)] bg-[#fbf8f0] p-3">
                <p className="text-sm font-semibold text-[color:var(--inj-green)]">{titre}</p>
                <p className="mt-1 font-mono text-[0.7rem] text-slate-600">{exemples}</p>
              </div>
            ))}
            <p className="sm:col-span-2 text-xs text-slate-500">
              Les colonnes inconnues sont tracées mais ignorées. Un matricule absent est généré
              automatiquement (préfixe <code className="font-mono">IMP-</code>) afin de ne jamais perdre une
              ligne.
            </p>
          </div>
        </Section>

        <Section title="Scénarios couverts" subtitle="Avec ou sans parcours académique préalable">
          <div className="space-y-3 p-4 text-sm">
            <div className="rounded-lg border border-[#c5e0d1] bg-[#eef7f1] p-3">
              <p className="font-semibold text-[#1c5c45]">Situation 1 — inscrits dans l&apos;application</p>
              <p className="mt-1 text-xs text-[#2c6b52]">
                Les inscriptions proviennent du processus LMD de backend-injs2026 : groupes, vagues et
                semestres sont déjà cohérents. Il suffit de lancer la génération.
              </p>
            </div>
            <div className="rounded-lg border border-[#f2d3b5] bg-[#fdf5e6] p-3">
              <p className="font-semibold text-[#9b4d11]">Situation 2 — fichier externe sans parcours</p>
              <p className="mt-1 text-xs text-[#7c4a21]">
                Le module crée les référentiels manquants, génère une maquette LMD par défaut (8 modules /
                semestre), inscrit chaque étudiant sur les deux semestres de son niveau, puis génère les
                emplois du temps. Capacité testée : 3 500 à 14 000 étudiants.
              </p>
            </div>
            <div className="rounded-lg border border-[#c9dced] bg-[#eef5fa] p-3">
              <p className="font-semibold text-[#245b80]">Idempotence et sécurité</p>
              <p className="mt-1 text-xs text-[#2c5f80]">
                Réimporter le même fichier ne duplique ni étudiant ni inscription. Le matricule est la clé
                d&apos;unicité ; l&apos;inscription est unique par étudiant, année et semestre.
              </p>
            </div>
          </div>
        </Section>
      </div>

      <div className="mt-6">
        <Section
          title="Journal des imports"
          subtitle="Chaque fichier est horodaté avec ses volumes, erreurs et référentiels créés"
          actions={<Badge tone="neutral">{historique.imports.length} import(s)</Badge>}
        >
          {historique.imports.length === 0 ? (
            <p className="px-4 py-8 text-sm text-slate-500">
              Aucun import externe pour le moment. Déposez un CSV ou un XLSX pour démarrer.
            </p>
          ) : (
            <table className="table-injs">
              <thead>
                <tr>
                  <th>Fichier</th>
                  <th>Date</th>
                  <th>Lignes</th>
                  <th>Importés</th>
                  <th>Ignorés</th>
                  <th>Formations</th>
                  <th>Groupes</th>
                  <th>Vagues</th>
                  <th>Alertes</th>
                  <th>Durée</th>
                </tr>
              </thead>
              <tbody>
                {historique.imports.map((imp) => {
                  const refs = imp.referentielsCrees as Record<string, number>;
                  return (
                    <tr key={imp.id}>
                      <td className="max-w-[240px] truncate font-medium">{imp.fichier}</td>
                      <td className="whitespace-nowrap text-slate-500">
                        {new Date(imp.createdAt).toLocaleString("fr-FR", {
                          day: "2-digit",
                          month: "2-digit",
                          year: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td>{imp.lignes}</td>
                      <td className="font-semibold text-[#1c5c45]">{imp.importes}</td>
                      <td>{imp.ignores}</td>
                      <td>{refs.formations ?? 0}</td>
                      <td>{refs.groupes ?? 0}</td>
                      <td>{refs.vagues ?? 0}</td>
                      <td>
                        {imp.erreurs.length > 0 ? (
                          <Badge tone="orange">{imp.erreurs.length}</Badge>
                        ) : (
                          <Badge tone="green">0</Badge>
                        )}
                      </td>
                      <td className="text-slate-500">{(imp.dureeMs / 1000).toFixed(1)} s</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Section>
      </div>
    </div>
  );
}
