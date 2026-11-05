import { Badge, PageHeader, Section } from "@/components/get-injs/ui";

export const dynamic = "force-dynamic";

const ENDPOINTS = [
  ["GET", "/api/health", "Sonde de santé de l'application (PostgreSQL)"],
  ["POST", "/api/seed", "Initialise le référentiel INJS et la cohorte (idempotent)"],
  ["POST", "/api/generation", "Génère et persiste les emplois du temps du périmètre"],
  ["GET", "/api/generation", "Historique JSON des 20 dernières générations"],
  ["POST", "/api/import", "Importe un fichier CSV/XLSX et génère éventuellement les EDT"],
  ["GET", "/api/import", "Télécharge le modèle CSV d'import"],
  ["GET", "/api/emplois-du-temps/export", "Export CSV filtrable des séances"],
  ["GET", "/api/artifacts/conception", "Sert Conception-GET-INJS.txt (inline ou download=1)"],
];

const TABLES = [
  ["gi_academic_years", "Années académiques et année active"],
  ["gi_filieres / gi_formations", "Mentions (STAPS, STASE) et parcours LMD"],
  ["gi_modules", "Maquettes LMD : semestre, ECTS, volumes CM/TD/TP, besoins de salle"],
  ["gi_module_enseignants", "Affectations enseignant ↔ module ↔ type de séance"],
  ["gi_vagues / gi_groupes", "Promotions et groupes pédagogiques par niveau"],
  ["gi_salles / gi_batiments", "Infrastructures et capacités"],
  ["gi_enseignants", "Grades, spécialités, charges maximales"],
  ["gi_etudiants", "Identité et parcours courant (base ou import)"],
  ["gi_inscriptions", "Inscription par étudiant, année et semestre (unique)"],
  ["gi_emplois_du_temps", "Versions d'emplois du temps, statut et statistiques"],
  ["gi_seances", "Séances planifiées (salle, enseignant, groupe, créneau)"],
  ["gi_generation_runs", "Traçabilité du moteur : périmètre, durées, alertes"],
  ["gi_import_jobs", "Journal des imports : volumes, erreurs, référentiels créés"],
  ["gi_app_meta", "Marqueurs d'initialisation"],
];

export default function ConceptionPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Documentation technique"
        title="Conception du module GET INJS APP"
        description="Architecture, modèle de données, algorithme de génération, API et procédures d'exploitation. Le document complet est téléchargeable au format texte et versionnable avec le code."
        actions={
          <>
            <a href="/api/artifacts/conception?download=1" className="btn-primary" download>
              Télécharger Conception-GET-INJS.txt
            </a>
            <a href="/api/artifacts/conception" className="btn-ghost" target="_blank" rel="noreferrer">
              Consulter en ligne
            </a>
          </>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[1.1fr_1fr]">
        <Section title="Architecture en couches" subtitle="Intégration au backend-injs2026">
          <div className="space-y-2 p-4 text-sm">
            {[
              ["Interface", "Next.js App Router · React 19 · Tailwind CSS 4", "Tableau de bord, grilles, formulaires, référentiels"],
              ["API", "Route Handlers Node.js", "Génération, import, export, seed, documentation"],
              ["Services", "Orchestration Drizzle", "seed · generation-service · import-service · queries"],
              ["Domaine (get-injs-app/lib)", "TypeScript pur, sans framework", "engine.ts · import-parser.ts · types.ts"],
              ["Données", "PostgreSQL 16 + Drizzle ORM", "14 tables préfixées gi_"],
            ].map(([couche, techno, role]) => (
              <div key={couche} className="grid gap-1 rounded-lg border border-[color:var(--inj-line)] bg-[#fbf8f0] p-3 md:grid-cols-[140px_1fr]">
                <p className="text-sm font-bold text-[color:var(--inj-green)]">{couche}</p>
                <div>
                  <p className="text-xs font-semibold text-slate-700">{techno}</p>
                  <p className="text-xs text-slate-500">{role}</p>
                </div>
              </div>
            ))}
            <p className="text-xs text-slate-500">
              Le dossier <code className="font-mono">get-injs-app/</code> contient le domaine, les données de
              référence et la documentation. Les routes et pages restent sous <code className="font-mono">src/app</code>{" "}
              conformément au framework, et consomment le domaine via des services.
            </p>
          </div>
        </Section>

        <Section title="Algorithme de génération" subtitle="Déterministe, sous contraintes multiples">
          <ol className="space-y-2 p-4 text-sm text-slate-600">
            <li><strong className="text-[color:var(--inj-green)]">1.</strong> Chargement du périmètre : groupes inscrits, niveaux, vagues, effectifs réels, maquettes du semestre.</li>
            <li><strong className="text-[color:var(--inj-green)]">2.</strong> Cours magistraux mutualisés par formation + semestre, découpés en lots selon la plus grande salle compatible.</li>
            <li><strong className="text-[color:var(--inj-green)]">3.</strong> TD puis TP par groupe, avec choix de salle par meilleur ajustement de capacité et préférence de type (amphi, TD, labo, gymnase, plateau).</li>
            <li><strong className="text-[color:var(--inj-green)]">4.</strong> Vérification simultanée des occupations : salle, enseignant, groupe, plus quota hebdomadaire et équilibrage par jour.</li>
            <li><strong className="text-[color:var(--inj-green)]">5.</strong> Contrôle croisé indépendant (<code className="font-mono">verifierConflits</code>), statistiques et journalisation.</li>
          </ol>
        </Section>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Section title="API du module" subtitle="Contrats d'échange utilisés par l'interface">
          <table className="table-injs">
            <thead>
              <tr>
                <th>Méthode</th>
                <th>Route</th>
                <th>Rôle</th>
              </tr>
            </thead>
            <tbody>
              {ENDPOINTS.map(([methode, route, role]) => (
                <tr key={`${methode}-${route}`}>
                  <td><Badge tone={methode === "GET" ? "blue" : "green"}>{methode}</Badge></td>
                  <td className="font-mono text-[0.7rem] text-[color:var(--inj-green)]">{route}</td>
                  <td>{role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Modèle de données" subtitle="Tables et responsabilités">
          <table className="table-injs">
            <thead>
              <tr>
                <th>Table</th>
                <th>Contenu</th>
              </tr>
            </thead>
            <tbody>
              {TABLES.map(([table, contenu]) => (
                <tr key={table}>
                  <td className="font-mono text-[0.7rem] text-[color:var(--inj-green)]">{table}</td>
                  <td>{contenu}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.1fr_1fr]">
        <Section title="Commandes d'implémentation" subtitle="Séquence exécutable de bout en bout">
          <pre className="overflow-x-auto p-4 text-[0.72rem] leading-relaxed text-slate-700">{`# 1. Dépendances
npm install
npm install xlsx

# 2. Base de données locale
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/app_db"

# 3. Schéma Drizzle (14 tables gi_*)
npx drizzle-kit push

# 4. Build et démarrage
npm run build
npm run start -- -p 3000

# 5. Initialisation du référentiel INJS + cohorte
curl -X POST http://localhost:3000/api/seed

# 6. Génération complète de l'année
curl -X POST http://localhost:3000/api/generation \\
  -H "Content-Type: application/json" \\
  -d '{"anneeCode":"2026-2027","inclureSamedi":true}'

# 7. Import d'un fichier externe (scénario 2)
curl -X POST http://localhost:3000/api/import \\
  -F "fichier=@inscrits-injs-2026.csv" \\
  -F "anneeCode=2026-2027" \\
  -F "autoCreer=true" \\
  -F "generer=true"

# 8. Export CSV des séances
curl -L "http://localhost:3000/api/emplois-du-temps/export?anneeCode=2026-2027&semestre=1" -o edt-s1.csv

# 9. Validation finale
npx next typegen
npm exec tsc -- --noEmit
npm run build`}</pre>
        </Section>

        <Section title="Exigences couvertes" subtitle="Traçabilité de la mission">
          <ul className="space-y-2 p-4 text-sm text-slate-600">
            {[
              ["Module complet", "Tableau de bord, référentiels, import, étudiants, génération, grilles, export, historique."],
              ["Génération par parcours", "Filière, formation, niveau, groupe, vague, semestre, année académique."],
              ["Volume 3 500 étudiants", "Cohorte initiale de 3 474 places (100 groupes) portée à 14 000 via import."],
              ["Fichier externe", "CSV/XLSX, alias de colonnes, reconstruction des référentiels et maquettes."],
              ["Sans parcours préalable", "Création automatique filière/formation/vague/groupe/modules."],
              ["Documentation", "Conception-GET-INJS.txt téléchargeable et module isolé dans get-injs-app/."],
              ["Backend vert", "Aucune table existante modifiée, préfixe gi_, healthcheck respecté."],
            ].map(([titre, detail]) => (
              <li key={titre} className="flex gap-2">
                <span className="mt-0.5 text-[#1c5c45]">✔</span>
                <span>
                  <strong className="text-[color:var(--inj-green)]">{titre}</strong> — {detail}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </div>
  );
}
