import { Cartouche, Legende, Puce } from "@/components/ui";
import { ERREURS, ETATS_BADGEAGE, MOTIFS_MANUELS, STATUTS_ASSIDUITE, STATUTS_POINTAGE } from "@/lib/domain";

export const dynamic = "force-dynamic";

const ENDPOINTS: {
  methode: string;
  url: string;
  objet: string;
  detail?: string;
}[] = [
  { methode: "POST", url: "/api/scan/secure/", objet: "Badgeage automatique par QR (entrée)", detail: "jeton · latitude · longitude · accuracy · device_id" },
  { methode: "POST", url: "/api/scan/secure/heartbeat/", objet: "Signal périodique pendant la séance", detail: "jeton · pointage_id · position" },
  { methode: "POST", url: "/api/scan/secure/exit/", objet: "Badgeage de sortie", detail: "pointage_id · source · position" },
  { methode: "POST", url: "/api/presences/manual/", objet: "Émargement manuel", detail: "RBAC · motif obligatoire · commentaire si AUTRE" },
  { methode: "POST", url: "/api/presences/{id}/correct/", objet: "Correction non destructive", detail: "ancienne / nouvelle valeur journalisées" },
  { methode: "GET", url: "/api/presences/", objet: "Historique filtrable", detail: "type_participant · seance_id · groupe · ecue · mode · nom" },
  { methode: "GET", url: "/api/presences/{id}/", objet: "Détail d'un pointage", detail: "sans coordonnées GPS brutes" },
  { methode: "GET", url: "/api/presences/session/{id}/", objet: "Présences d'une séance" },
  { methode: "GET", url: "/api/presences/actor/{id}/", objet: "Historique d'un participant (étudiant, enseignant, encadrant)" },
  { methode: "POST", url: "/api/seances/{id}/qr/", objet: "Émission / rotation de la session QR", detail: "duree_secondes · anti-rejeu" },
  { methode: "POST", url: "/api/seances/{id}/autoclore/", objet: "Clôture de séance", detail: "QR fermés · sorties automatiques" },
  { methode: "GET", url: "/api/seances/{id}/", objet: "Fiche séance + métriques de tableau de bord" },
  { methode: "GET · PUT", url: "/api/config/geofence/", objet: "Configuration du périmètre", detail: "site · latitude · longitude · rayon · actif" },
  { methode: "GET", url: "/api/audit/", objet: "Journal d'audit" },
  { methode: "GET", url: "/api/contract/", objet: "Ce contrat, au format JSON" },
];

export default function PageContrat() {
  return (
    <div className="mx-auto max-w-[1400px] px-6 py-12">
      <Cartouche
        surtitre="Interopérabilité · Flutter PWA, GET INJS APP, contrôle académique"
        titre="Contrat d'intégration"
        action={<Puce texte="Version 1.0" ton="conforme" />}
      />
      <Legende>
        Le module Présences consomme les séances publiées par GET INJS APP sans reconstruire les
        référentiels LMD : chaque pointage porte l&apos;identifiant permanent de la séance
        (<span className="font-mono text-[12px]">INJS-S-######</span>), stable dans le temps. Le
        client ne transmet qu&apos;une mesure ; le serveur décide.
      </Legende>

      <section className="mt-10">
        <h2 className="font-display text-[25px] font-bold">Points d&apos;entrée</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[860px] border-collapse text-[13.5px]">
            <thead>
              <tr className="border-b-2 border-encre text-left">
                <th className="caps py-2 pr-3 text-encre-pale">Méthode</th>
                <th className="caps py-2 pr-3 text-encre-pale">URL</th>
                <th className="caps py-2 pr-3 text-encre-pale">Objet</th>
                <th className="caps py-2 pr-3 text-encre-pale">Détail</th>
              </tr>
            </thead>
            <tbody>
              {ENDPOINTS.map((e, i) => (
                <tr
                  key={e.url}
                  className={`ligne-registre align-baseline ${(i + 1) % 5 === 0 ? "ligne-registre-epaisse" : ""}`}
                >
                  <td className="py-2.5 pr-3 font-mono text-[12px] whitespace-nowrap">{e.methode}</td>
                  <td className="py-2.5 pr-3 font-mono text-[12px]">{e.url}</td>
                  <td className="py-2.5 pr-3">{e.objet}</td>
                  <td className="py-2.5 pr-3 text-encre-pale">{e.detail ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-14">
        <h2 className="font-display text-[25px] font-bold">Codes d&apos;erreur métier</h2>
        <Legende>
          Chaque refus renvoie <span className="font-mono text-[12px]">code</span>,{" "}
          <span className="font-mono text-[12px]">message</span>,{" "}
          <span className="font-mono text-[12px]">explication</span> et{" "}
          <span className="font-mono text-[12px]">action_recommandee</span> — pour que le terminal
          puisse expliquer le refus sans deviner la règle.
        </Legende>
        <div className="mt-5 grid gap-x-10 gap-y-6 md:grid-cols-2">
          {Object.values(ERREURS).map((e) => (
            <article key={e.code} className="border-l-2 border-vermillon pl-4">
              <div className="caps text-vermillon">{e.code}</div>
              <p className="mt-1.5 font-medium">{e.message}</p>
              <p className="mt-1.5 text-[13px] leading-relaxed text-encre-pale">{e.explication}</p>
              <p className="mt-2 text-[12.5px]">
                <span className="caps text-encre">Action · </span>
                {e.action_recommandee}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="mt-14 grid gap-10 md:grid-cols-3">
        <div>
          <h3 className="font-display text-[20px] font-bold">Statuts de pointage</h3>
          <ul className="mt-3 space-y-1.5">
            {STATUTS_POINTAGE.map((s) => (
              <li key={s} className="ligne-registre py-1.5 font-mono text-[12px]">
                {s}
              </li>
            ))}
          </ul>
          <Legende>Processus de badgeage.</Legende>
        </div>
        <div>
          <h3 className="font-display text-[20px] font-bold">Statuts d&apos;assiduité</h3>
          <ul className="mt-3 space-y-1.5">
            {STATUTS_ASSIDUITE.map((s) => (
              <li key={s} className="ligne-registre py-1.5 font-mono text-[12px]">
                {s}
              </li>
            ))}
          </ul>
          <Legende>Résultat pédagogique, distinct du processus.</Legende>
        </div>
        <div>
          <h3 className="font-display text-[20px] font-bold">Motifs d&apos;émargement manuel</h3>
          <ul className="mt-3 space-y-1.5">
            {MOTIFS_MANUELS.map((m) => (
              <li key={m.code} className="ligne-registre py-1.5">
                <span className="font-mono text-[12px]">{m.code}</span>
                <div className="text-[12px] text-encre-pale">{m.libelle}</div>
              </li>
            ))}
          </ul>
          <Legende>AUTRE exige un commentaire.</Legende>
        </div>
      </section>

      <section className="mt-14">
        <h2 className="font-display text-[25px] font-bold">États du poste de badgeage</h2>
        <div className="mt-4 flex flex-wrap gap-2">
          {ETATS_BADGEAGE.map((e) => (
            <Puce key={e} texte={e.replace(/_/g, " ")} ton="neutre" />
          ))}
        </div>
      </section>
    </div>
  );
}
