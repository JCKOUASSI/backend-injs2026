import Link from "next/link";

import { ensureSeeded } from "@/lib/get-injs/seed";
import { getDashboard } from "@/lib/get-injs/queries";
import { Badge, ProgressBar, Section, StatCard } from "@/components/get-injs/ui";

export const dynamic = "force-dynamic";

type StatsEdt = {
  seances?: number;
  cm?: number;
  td?: number;
  tp?: number;
  nonPlacees?: number;
  conflits?: number;
  tauxCouverture?: number;
  tauxOccupationSalles?: number;
  enseignantsMobilises?: number;
  sallesMobilisees?: number;
  placesEtudiantes?: number;
};

const JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"];

export default async function DashboardPage() {
  await ensureSeeded();
  const data = await getDashboard();
  const dernier = data.edt[0];
  const stats = (dernier?.stats ?? {}) as StatsEdt;
  const dernierRun = data.runs[0];
  const maxFiliere = Math.max(1, ...data.parFiliere.map((f) => f.effectif));

  return (
    <div className="space-y-6">
      <section className="card relative overflow-hidden border-0 bg-[color:var(--inj-green)] p-6 text-[#f4efe2] lg:p-9">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-25"
          style={{
            backgroundImage:
              "radial-gradient(circle at 85% 15%, rgba(226,118,44,0.55), transparent 42%), radial-gradient(circle at 15% 90%, rgba(255,255,255,0.22), transparent 45%)",
          }}
        />
        <div className="relative grid gap-8 lg:grid-cols-[1.35fr_1fr]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="orange">INJS Marcory · Côte d&apos;Ivoire</Badge>
              <Badge tone="green">LMD · Licence → Master</Badge>
              <Badge tone="neutral">Année 2026-2027</Badge>
            </div>
            <h1 className="font-display mt-4 max-w-2xl text-3xl leading-tight font-semibold text-white md:text-[2.6rem]">
              Tous les emplois du temps de l&apos;INJS, générés sans conflit.
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[#d3e2d6]">
              GET INJS APP orchestre les filières, formations, promotions (vagues), groupes, semestres,
              salles et enseignants. Il génère une grille hebdomadaire par parcours académique, à partir
              des inscriptions de la base ou d&apos;un fichier externe de 3 500 à 14 000 étudiants.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/generation" className="btn-accent">
                Générer un emploi du temps
              </Link>
              <Link
                href="/import"
                className="inline-flex items-center gap-2 rounded-lg border border-white/25 bg-white/10 px-4 py-2.5 text-sm font-semibold text-white hover:bg-white/15"
              >
                Importer un fichier d&apos;inscrits
              </Link>
              <Link
                href="/emplois-du-temps"
                className="inline-flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-semibold text-[#cfe1d4] hover:text-white"
              >
                Consulter les grilles →
              </Link>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 self-center">
            <MiniKpi label="Étudiants inscrits" value={data.compteurs.etudiants.toLocaleString("fr-FR")} />
            <MiniKpi label="Groupes" value={data.compteurs.groupes} />
            <MiniKpi label="Séances générées" value={data.compteurs.seances.toLocaleString("fr-FR")} />
            <MiniKpi
              label="Couverture moteur"
              value={`${stats.tauxCouverture ?? 0} %`}
              hint={`${stats.conflits ?? 0} conflit(s)`}
            />
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <StatCard label="Étudiants" value={data.compteurs.etudiants.toLocaleString("fr-FR")} hint="Inscriptions LMD" accent />
        <StatCard label="Inscriptions" value={data.compteurs.inscriptions.toLocaleString("fr-FR")} hint="Semestres actifs" />
        <StatCard label="Groupes" value={data.compteurs.groupes} hint={`${data.parNiveau.length} niveaux`} />
        <StatCard label="Salles" value={data.compteurs.salles} hint="Amphis, labos, plateaux" />
        <StatCard label="Enseignants" value={data.compteurs.enseignants} hint={`${stats.enseignantsMobilises ?? 0} mobilisés`} />
        <StatCard label="Modules" value={data.compteurs.modules} hint="Maquettes LMD" />
        <StatCard label="Séances" value={data.compteurs.seances.toLocaleString("fr-FR")} hint={`${stats.nonPlacees ?? 0} non placées`} />
      </section>

      <div className="grid gap-5 xl:grid-cols-[1.2fr_1fr]">
        <Section
          title="Charge par semestre"
          subtitle="Séances planifiées, ventilation CM / TD / TP"
          actions={<Badge tone="green">{data.parSemestre.reduce((t, s) => t + s.seances, 0)} séances</Badge>}
        >
          {data.parSemestre.length === 0 ? (
            <p className="px-4 py-8 text-sm text-slate-500">
              Aucune séance pour l&apos;instant. Lancez une génération depuis le module{" "}
              <Link className="font-semibold text-[color:var(--inj-green)] underline" href="/generation">
                Génération
              </Link>
              .
            </p>
          ) : (
            <div className="space-y-3 p-4">
              {data.parSemestre.map((s) => {
                const max = Math.max(...data.parSemestre.map((x) => x.seances), 1);
                return (
                  <div key={s.semestre} className="grid grid-cols-[64px_1fr_120px] items-center gap-3">
                    <span className="text-sm font-semibold text-[color:var(--inj-green)]">S{s.semestre}</span>
                    <ProgressBar value={(s.seances / max) * 100} />
                    <span className="text-right text-xs text-slate-500">
                      {s.seances} · <span className="text-[#245b80]">{s.cm} CM</span> /{" "}
                      <span className="text-[#1c5c45]">{s.td} TD</span> /{" "}
                      <span className="text-[#9b4d11]">{s.tp} TP</span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </Section>

        <Section title="Population par filière" subtitle="Étudiants rattachés au parcours">
          <div className="space-y-4 p-4">
            {data.parFiliere.length === 0 ? (
              <p className="text-sm text-slate-500">Aucun étudiant importé ou inscrit.</p>
            ) : (
              data.parFiliere.map((f) => (
                <div key={f.filiere}>
                  <div className="mb-1 flex items-baseline justify-between gap-3">
                    <span className="text-sm font-semibold text-[color:var(--inj-green)]">{f.filiere}</span>
                    <span className="text-xs text-slate-500">
                      {f.effectif.toLocaleString("fr-FR")} étudiants
                    </span>
                  </div>
                  <ProgressBar value={(f.effectif / maxFiliere) * 100} tone="orange" />
                  <p className="mt-1 text-[0.7rem] text-slate-500">{f.nom}</p>
                </div>
              ))
            )}
            <div className="grid grid-cols-5 gap-2 border-t border-[color:var(--inj-line)] pt-3">
              {data.parNiveau.map((n) => (
                <div key={n.niveau} className="rounded-lg bg-[#f4efe4] px-2 py-2 text-center">
                  <p className="text-[0.65rem] font-bold tracking-wide text-[#6b7a71]">{n.niveau}</p>
                  <p className="text-sm font-semibold text-[color:var(--inj-green)]">{n.effectif}</p>
                  <p className="text-[0.6rem] text-slate-500">{n.groupes} gr.</p>
                </div>
              ))}
            </div>
          </div>
        </Section>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <Section
          title="Dernières générations"
          subtitle={dernier ? `Dernier EDT : ${dernier.code}` : "Aucun emploi du temps enregistré"}
          actions={
            <Link href="/generation" className="btn-ghost">
              Ouvrir le moteur
            </Link>
          }
        >
          {data.runs.length === 0 ? (
            <p className="px-4 py-8 text-sm text-slate-500">
              Le moteur n&apos;a pas encore tourné. Générez vos premiers emplois du temps.
            </p>
          ) : (
            <table className="table-injs">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Périmètre</th>
                  <th>Séances</th>
                  <th>Conflits</th>
                  <th>Couverture</th>
                  <th>Durée</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((run) => {
                  const s = run.stats as StatsEdt;
                  const scope = run.scope as { filiereCode?: string | null; niveau?: string | null; semestres?: number[] };
                  return (
                    <tr key={run.id}>
                      <td className="whitespace-nowrap text-slate-600">
                        {new Date(run.demarreLe).toLocaleString("fr-FR", {
                          day: "2-digit",
                          month: "2-digit",
                          year: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td>
                        <span className="font-semibold text-[color:var(--inj-green)]">
                          {scope.filiereCode ?? "Toutes filières"}
                        </span>
                        <span className="block text-[0.7rem] text-slate-500">
                          {scope.niveau ?? "Tous niveaux"} · S{(scope.semestres ?? []).join(", S")}
                        </span>
                      </td>
                      <td className="font-semibold">{s.seances ?? 0}</td>
                      <td>
                        {(s.conflits ?? 0) > 0 ? (
                          <Badge tone="red">{s.conflits} conflit(s)</Badge>
                        ) : (
                          <Badge tone="green">0 conflit</Badge>
                        )}
                      </td>
                      <td>{s.tauxCouverture ?? 0} %</td>
                      <td className="whitespace-nowrap text-slate-500">
                        {(run.dureeMs / 1000).toFixed(1)} s
                      </td>
                      <td>
                        <Badge tone="blue">Terminé</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Section>

        <Section title="Les 5 étapes du processus" subtitle="De l'inscription à la publication">
          <ol className="divide-y divide-[#eee8db]">
            {[
              { t: "Référentiels INJS", d: "Filières, formations, maquettes, salles, enseignants", href: "/referentiels" },
              { t: "Inscriptions / import", d: "Base applicative ou fichier externe de 3 500 à 14 000 étudiants", href: "/import" },
              { t: "Parcours LMD", d: "Groupe + vague + semestre rattachés automatiquement", href: "/etudiants" },
              { t: "Génération", d: "Moteur déterministe sans conflit salle / enseignant / groupe", href: "/generation" },
              { t: "Consultation & export", d: "Grille hebdomadaire, impression et export CSV", href: "/emplois-du-temps" },
            ].map((etape, i) => (
              <li key={etape.t}>
                <Link href={etape.href} className="flex items-start gap-3 px-4 py-3 hover:bg-[#fbf8f0]">
                  <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[color:var(--inj-green)] text-xs font-bold text-white">
                    {i + 1}
                  </span>
                  <span>
                    <span className="block text-sm font-semibold text-[color:var(--inj-green)]">{etape.t}</span>
                    <span className="block text-xs text-slate-500">{etape.d}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </Section>
      </div>

      <Section
        title="Journal des imports"
        subtitle="Traçabilité des fichiers externes et création de référentiels"
        actions={
          <Link href="/import" className="btn-ghost">
            Importer
          </Link>
        }
      >
        {data.imports.length === 0 ? (
          <p className="px-4 py-8 text-sm text-slate-500">
            Aucun import externe. Le module accepte CSV et XLSX avec reconstruction du parcours
            académique.
          </p>
        ) : (
          <table className="table-injs">
            <thead>
              <tr>
                <th>Fichier</th>
                <th>Reçu le</th>
                <th>Lignes</th>
                <th>Importés</th>
                <th>Ignorés</th>
                <th>Référentiels créés</th>
                <th>Durée</th>
              </tr>
            </thead>
            <tbody>
              {data.imports.map((imp) => {
                const refs = imp.referentielsCrees as Record<string, number>;
                return (
                  <tr key={imp.id}>
                    <td className="max-w-[220px] truncate font-medium">{imp.fichier}</td>
                    <td className="whitespace-nowrap text-slate-500">
                      {new Date(imp.createdAt).toLocaleDateString("fr-FR")}
                    </td>
                    <td>{imp.lignes}</td>
                    <td className="font-semibold text-[#1c5c45]">{imp.importes}</td>
                    <td>{imp.ignores}</td>
                    <td className="text-xs text-slate-600">
                      {refs.formations ?? 0} form. · {refs.groupes ?? 0} gr. · {refs.vagues ?? 0} vagues
                    </td>
                    <td className="text-slate-500">{(imp.dureeMs / 1000).toFixed(1)} s</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Section>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { href: "/emplois-du-temps", t: "Grille hebdomadaire", d: "Vue 6 jours × 5 créneaux par groupe", n: `${JOURS.length} jours` },
          { href: "/generation", t: "Moteur LMD", d: "CM mutualisés, TD/TP par groupe", n: "0 conflit" },
          { href: "/import", t: "Import externe", d: "CSV / XLSX avec alias de colonnes", n: "20 000 lignes" },
          { href: "/conception", t: "Conception", d: "Processus, commandes et API", n: "Document" },
        ].map((c) => (
          <Link key={c.href} href={c.href} className="card-flat group p-4 transition hover:border-[color:var(--inj-green-soft)]">
            <p className="text-[0.68rem] font-bold uppercase tracking-[0.1em] text-[color:var(--inj-orange)]">{c.n}</p>
            <p className="font-display mt-1 text-base font-semibold text-[color:var(--inj-green)]">{c.t}</p>
            <p className="mt-1 text-xs text-slate-500">{c.d}</p>
            <p className="mt-3 text-xs font-semibold text-[color:var(--inj-green-soft)] group-hover:underline">Accéder →</p>
          </Link>
        ))}
      </div>
    </div>
  );
}

function MiniKpi({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-xl border border-white/15 bg-white/8 px-3 py-2.5">
      <p className="text-[0.62rem] uppercase tracking-[0.1em] text-[#a9c3b3]">{label}</p>
      <p className="font-display text-xl font-semibold text-white">{value}</p>
      {hint ? <p className="text-[0.62rem] text-[#a9c3b3]">{hint}</p> : null}
    </div>
  );
}
