import Link from "next/link";

import AnneauGeofence from "@/components/AnneauGeofence";
import QrPlanche from "@/components/QrPlanche";
import {
  Cartouche,
  Chiffre,
  Legende,
  Puce,
  heure,
  tonStatut,
  tonVerdict,
} from "@/components/ui";
import { chargerSeanceDetail, chargerSites } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function PageSeance({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const detail = await chargerSeanceDetail(Number(id));
  const sites = await chargerSites();

  if (!detail) {
    return (
      <div className="mx-auto max-w-[1400px] px-6 py-24 text-center">
        <p className="font-display text-[25px]">Séance introuvable</p>
        <Link href="/seances" className="caps mt-4 inline-block text-vert underline">
          Retour au registre des séances
        </Link>
      </div>
    );
  }

  const site = sites.find((s) => s.id === detail.siteId) ?? sites[0];
  const rayonM = site?.geofenceRayonM ?? 200;
  const sessionOuverte = detail.sessionQr?.statut === "OUVERTE";
  const sessionAutorisee = detail.statut === "PUBLIEE";

  const points = detail.pointages.map((p) => ({
    id: p.id,
    nom: p.nom,
    distanceM: p.distanceM,
    verdict: p.verdictGeofence,
    horodatage: p.timestampEntree.toISOString(),
  }));

  const chaineLmd = [
    { libelle: "Formation", valeur: `${detail.formation} ${detail.formationNom}` },
    { libelle: "Parcours", valeur: `${detail.parcours} ${detail.parcoursNom}` },
    { libelle: "Niveau", valeur: detail.niveau },
    { libelle: "Semestre", valeur: detail.semestre },
    { libelle: "Groupe", valeur: detail.groupe },
    { libelle: "Maquette", valeur: detail.maquette },
    { libelle: "UE", valeur: `${detail.ueCode} ${detail.ueIntitule}` },
    { libelle: "ECUE", valeur: `${detail.ecueCode} ${detail.ecueIntitule}` },
    {
      libelle: "Affectation",
      valeur: detail.enseignant ?? "Non affectée",
    },
    { libelle: "Séance", valeur: detail.identifiantPermanent },
    {
      libelle: "Session QR",
      valeur: detail.sessionQr ? `rotation ${detail.sessionQr.rotation}` : "Aucune",
    },
    { libelle: "Présence", valeur: `${detail.metriques.presents} enregistrées` },
  ];

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-10">
      {/* Fiche */}
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <Link href="/seances" className="caps text-encre-pale hover:text-vert">
            ← Registre des séances
          </Link>
          <h1 className="mt-3 max-w-[24ch] font-display text-[39px] leading-[1.05] font-black">
            {detail.ecueCode} — {detail.ecueIntitule}
          </h1>
          <p className="mt-3 text-[15px] text-encre-pale">
            {detail.ueCode} · {detail.ueIntitule} · {detail.typeSeance} · {detail.groupeNom}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Puce texte={detail.statut} ton={tonStatut(detail.statut)} />
          <Puce texte={`validation ${detail.statutValidation}`} ton="neutre" />
          <Puce texte={`publication ${detail.statutPublication}`} ton="neutre" />
          <Puce texte={`version ${detail.version}`} ton="neutre" />
          {detail.annuleeDeId ? (
            <Puce texte={`reprogrammée depuis #${detail.annuleeDeId}`} ton="alerte" />
          ) : null}
        </div>
      </div>

      {/* Chaîne LMD gravée */}
      <div className="mt-8 overflow-x-auto border-y-2 border-encre py-4">
        <ol className="flex min-w-max items-stretch">
          {chaineLmd.map((etape, i) => (
            <li
              key={etape.libelle}
              className={`px-4 py-1 ${i > 0 ? "border-l border-filet" : ""}`}
            >
              <div className="caps text-encre-pale">{etape.libelle}</div>
              <div className="mt-1 text-[13px] font-medium whitespace-nowrap">{etape.valeur}</div>
            </li>
          ))}
        </ol>
      </div>

      {/* Session QR */}
      <section className="mt-10">
        <Cartouche
          surtitre="Badgeage automatique"
          titre="Session QR de la séance"
          action={
            <div className="caps text-encre-pale">
              {detail.dateSeance} · {detail.heureDebut}–{detail.heureFin} · {detail.salle ?? "salle non renseignée"}
            </div>
          }
        />
        <QrPlanche
          seanceId={detail.id}
          seanceLibelle={`${detail.ecueCode} · ${detail.groupe}`}
          sessionInitiale={
            detail.sessionQr
              ? {
                  id: detail.sessionQr.id,
                  jeton: detail.sessionQr.jeton,
                  expireLe: detail.sessionQr.expireLe.toISOString(),
                  rotation: detail.sessionQr.rotation,
                  statut: detail.sessionQr.statut,
                }
              : null
          }
          peutEmettre
          sessionAutorisee={sessionAutorisee}
        />
        <Legende>
          Session {sessionOuverte ? "ouverte" : "clôturée"} · jeton signé · expiration
          temporaire · toute rotation invalide les jetons précédents. Une séance en simulation ou
          non publiée ne peut jamais ouvrir de session officielle.
        </Legende>
      </section>

      {/* Métriques */}
      <section className="mt-12">
        <Cartouche surtitre="Tableau de bord de séance" titre="Contrôle d'assiduité" />
        <div className="grid grid-cols-2 gap-8 md:grid-cols-4">
          <Chiffre valeur={detail.metriques.attendus} libelle="Attendus" legende="Inscriptions validées en vigueur" />
          <Chiffre valeur={detail.metriques.presents} libelle="Présents" ton="vert" />
          <Chiffre valeur={detail.metriques.absents} libelle="Absents" ton="vermillon" />
          <Chiffre valeur={detail.metriques.retards} libelle="Retards" legende="Entrée au-delà de 15 min" />
          <Chiffre valeur={detail.metriques.sortiesAnticipees} libelle="Sorties anticipées" />
          <Chiffre valeur={detail.metriques.manuels} libelle="Émargements manuels" legende="Motivés et audités" />
          <Chiffre valeur={detail.metriques.anomaliesGps} libelle="Anomalies GPS" ton="vermillon" />
          <Chiffre valeur={detail.metriques.anomaliesQr} libelle="Anomalies QR" ton="vermillon" />
        </div>
      </section>

      {/* Registre + anneau */}
      <section className="mt-12 grid gap-10 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div>
          <Cartouche surtitre="Registre de badgeage" titre="Présences enregistrées" />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] border-collapse text-[13.5px]">
              <thead>
                <tr className="border-b-2 border-encre text-left">
                  <th className="caps py-2 pr-3 text-encre-pale">Participant</th>
                  <th className="caps py-2 pr-3 text-encre-pale">Type</th>
                  <th className="caps py-2 pr-3 text-encre-pale">Entrée</th>
                  <th className="caps py-2 pr-3 text-encre-pale">Sortie</th>
                  <th className="caps py-2 pr-3 text-right text-encre-pale">Durée</th>
                  <th className="caps py-2 pr-3 text-encre-pale">Mode</th>
                  <th className="caps py-2 pr-3 text-encre-pale">Position</th>
                  <th className="caps py-2 pr-3 text-right text-encre-pale">HB</th>
                  <th className="caps py-2 pr-3 text-encre-pale">Assiduité</th>
                  <th className="caps py-2 pr-3 text-encre-pale">Anomalies</th>
                </tr>
              </thead>
              <tbody>
                {detail.pointages.map((p, i) => (
                  <tr
                    key={p.id}
                    className={`ligne-registre ligne-animee align-baseline ${
                      (i + 1) % 5 === 0 ? "ligne-registre-epaisse" : ""
                    }`}
                    style={{ animationDelay: `${i * 20}ms` }}
                  >
                    <td className="py-2.5 pr-3">
                      <span className="font-medium">{p.nom}</span>
                      <div className="caps mt-1 text-encre-pale">{p.matricule}</div>
                    </td>
                    <td className="py-2.5 pr-3">
                      <Puce texte={p.typeParticipant} ton="neutre" />
                    </td>
                    <td className="tab py-2.5 pr-3 font-mono text-[12px]">
                      {heure(p.timestampEntree)}
                    </td>
                    <td className="tab py-2.5 pr-3 font-mono text-[12px]">
                      {heure(p.timestampSortie)}
                      {p.sourceSortie === "SORTIE_AUTOMATIQUE_FIN_SEANCE" ? (
                        <div className="caps mt-0.5 text-encre-pale">auto</div>
                      ) : null}
                    </td>
                    <td className="tab py-2.5 pr-3 text-right">
                      {p.dureeMinutes ? `${p.dureeMinutes} min` : "—"}
                    </td>
                    <td className="py-2.5 pr-3">
                      <Puce
                        texte={p.mode}
                        ton={p.mode === "MANUEL" ? "alerte" : "conforme"}
                      />
                      {p.motifManuel ? (
                        <div className="mt-1 max-w-[18ch] text-[11px] text-encre-pale">
                          {p.motifManuel}
                          {p.auteurManuelNom ? ` · ${p.auteurManuelNom}` : ""}
                        </div>
                      ) : null}
                    </td>
                    <td className="py-2.5 pr-3">
                      <Puce
                        texte={p.verdictGeofence ?? "—"}
                        ton={tonVerdict(p.verdictGeofence)}
                      />
                      <div className="tab mt-1 font-mono text-[11px] text-encre-pale">
                        {p.distanceM === null ? "—" : `${p.distanceM.toFixed(0)} m`}
                        {p.accuracyM !== null ? ` · ±${p.accuracyM.toFixed(0)} m` : ""}
                      </div>
                    </td>
                    <td className="tab py-2.5 pr-3 text-right">{p.heartbeats}</td>
                    <td className="py-2.5 pr-3">
                      <Puce
                        texte={p.statutAssiduite ?? p.statut}
                        ton={tonStatut(p.statutAssiduite ?? p.statut)}
                      />
                    </td>
                    <td className="py-2.5 pr-3">
                      <div className="flex flex-wrap gap-1">
                        {(p.anomalies ?? []).map((a) => (
                          <Puce key={a} texte={a} ton="alerte" />
                        ))}
                        {!(p.anomalies ?? []).length ? (
                          <span className="text-encre-pale">—</span>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {detail.pointages.length === 0 ? (
            <p className="py-12 text-center text-encre-pale">
              Aucun pointage pour cette séance pour l&apos;instant.
            </p>
          ) : null}
        </div>

        <div className="space-y-10">
          <AnneauGeofence
            rayonM={rayonM}
            points={points}
            site={site?.nom ?? "Site non configuré"}
          />

          <div>
            <Cartouche surtitre="Liste officielle" titre="Théoriquement attendus" />
            <ul>
              {detail.attendusListe.map((a, i) => (
                <li
                  key={`${a.matricule}-${a.utilisateurId}`}
                  className={`ligne-registre flex items-center gap-3 py-2 ${
                    (i + 1) % 5 === 0 ? "ligne-registre-epaisse" : ""
                  }`}
                >
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${
                      a.dejaBadge ? "bg-vert" : "bg-filet"
                    }`}
                  />
                  <span className="min-w-0 flex-1 truncate text-[13.5px]">{a.nom}</span>
                  <span className="caps text-encre-pale">{a.role}</span>
                  <span className="tab font-mono text-[11px] text-encre-pale">{a.groupe}</span>
                </li>
              ))}
            </ul>
            <Legende>
              Liste calculée à la date de la séance depuis les inscriptions validées — jamais
              figée dans la séance. L&apos;instantané conservé reste celui du pointage.
            </Legende>
          </div>
        </div>
      </section>
    </div>
  );
}
