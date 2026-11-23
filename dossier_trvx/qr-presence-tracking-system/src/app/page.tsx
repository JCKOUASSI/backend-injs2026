import Link from "next/link";

import {
  chargerTableauDeBord,
} from "@/lib/queries";
import {
  Barre,
  Cartouche,
  Chiffre,
  formatDateFr,
  Legende,
  Puce,
  heure,
  tonStatut,
  tonVerdict,
} from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function TableauDeBord() {
  const bord = await chargerTableauDeBord();
  const aujourdhui = new Date().toISOString().slice(0, 10);

  return (
    <div>
      {/* Bandeau — la salle de cours, avant le badgeage */}
      <section className="relative overflow-hidden border-b-2 border-encre">
        <img
          src="/images/amphie.jpg"
          alt="Amphithéâtre de l'INJS au petit matin"
          className="absolute inset-0 h-full w-full object-cover"
          style={{ objectPosition: "50% 58%" }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-vert-fonce/95 via-vert-fonce/85 to-vert-fonce/35" />
        <div className="relative mx-auto max-w-[1400px] px-6 py-16">
          <div className="caps text-papier-haut/70">
            Registre national des présences · Année académique 2025-2026
          </div>
          <h1 className="mt-4 max-w-[18ch] font-display text-[49px] leading-[0.98] font-black text-papier-haut">
            Présences QR code et géolocalisation
          </h1>
          <p className="mt-5 max-w-[62ch] text-[17px] leading-relaxed text-papier-haut/85">
            Étudiants, enseignants et encadrants. Session QR temporaire signée,
            badgeage manuel motivé, heartbeat continu et contrôle de périmètre
            calculé côté serveur — le tout rattaché à la séance LMD publiée.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-x-10 gap-y-4">
            <div>
              <div className="font-display tab text-[39px] leading-none font-black text-papier-haut">
                {bord.kpis.tauxPresence} %
              </div>
              <div className="caps mt-2 text-papier-haut/70">Taux de présence du jour</div>
            </div>
            <div>
              <div className="font-display tab text-[39px] leading-none font-black text-papier-haut">
                {bord.kpis.presentsJour}/{bord.kpis.attendusJour}
              </div>
              <div className="caps mt-2 text-papier-haut/70">Présents / attendus</div>
            </div>
            <div>
              <div className="font-display tab text-[39px] leading-none font-black text-papier-haut">
                {bord.kpis.sessionsQrOuvertes}
              </div>
              <div className="caps mt-2 text-papier-haut/70">Sessions QR ouvertes</div>
            </div>
            <Link href="/badger" className="bouton ml-2 bg-papier-haut text-vert-fonce hover:bg-white">
              Ouvrir le poste de badgeage
            </Link>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-[1400px] px-6 py-12">
        {/* Compteurs */}
        <div className="grid grid-cols-2 gap-8 md:grid-cols-4">
          <Chiffre
            valeur={bord.kpis.seancesJour}
            libelle="Séances programmées aujourd'hui"
            legende="Séances publiées, statut PUBLIEE"
          />
          <Chiffre
            valeur={bord.kpis.heartbeatsJour}
            libelle="Signaux heartbeat reçus"
            legende="Position, horodatage, précision"
            ton="vert"
          />
          <Chiffre
            valeur={bord.kpis.manuels}
            libelle="Émargements manuels"
            legende="Toujours motivés et audités"
          />
          <Chiffre
            valeur={bord.kpis.anomalies}
            libelle="Anomalies à contrôler"
            legende="GPS, QR, sorties non badgées"
            ton="vermillon"
          />
        </div>

        {/* Registre du jour + colonne de contrôle */}
        <div className="mt-14 grid gap-12 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
          <section>
            <Cartouche
              surtitre={formatDateFr(aujourdhui)}
              titre="Séances du jour"
              action={
                <Link href="/seances" className="caps text-vert underline">
                  Registre complet des séances
                </Link>
              }
            />
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-[14px]">
                <thead>
                  <tr className="border-b-2 border-encre text-left">
                    <th className="caps py-2 pr-3 text-encre-pale">Horaire</th>
                    <th className="caps py-2 pr-3 text-encre-pale">ECUE / UE</th>
                    <th className="caps py-2 pr-3 text-encre-pale">Groupe</th>
                    <th className="caps py-2 pr-3 text-encre-pale">Enseignant</th>
                    <th className="caps py-2 pr-3 text-encre-pale">Salle</th>
                    <th className="caps py-2 pr-3 text-right text-encre-pale">Attendus</th>
                    <th className="caps py-2 pr-3 text-right text-encre-pale">Présents</th>
                    <th className="caps py-2 pr-3 text-encre-pale">Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {bord.seancesJour.map((s, i) => (
                    <tr
                      key={s.id}
                      className={`ligne-registre ligne-animee align-baseline ${
                        (i + 1) % 5 === 0 ? "ligne-registre-epaisse" : ""
                      }`}
                      style={{ animationDelay: `${i * 26}ms` }}
                    >
                      <td className="tab py-2.5 pr-3 font-mono text-[13px]">
                        {s.heureDebut} — {s.heureFin}
                      </td>
                      <td className="py-2.5 pr-3">
                        <Link href={`/seances/${s.id}`} className="font-medium text-encre hover:text-vert">
                          {s.ecueCode} · {s.ecueIntitule}
                        </Link>
                        <div className="caps mt-1 text-encre-pale">
                          {s.ueCode} · {s.niveau} {s.semestre} · {s.typeSeance}
                        </div>
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-[13px]">{s.groupe}</td>
                      <td className="py-2.5 pr-3">{s.enseignant ?? "—"}</td>
                      <td className="py-2.5 pr-3 text-encre-pale">{s.salle ?? "—"}</td>
                      <td className="tab py-2.5 pr-3 text-right">{s.attendus}</td>
                      <td className="tab py-2.5 pr-3 text-right">
                        <span className="font-semibold text-vert">{s.presents}</span>
                        <span className="text-encre-pale">/{s.attendus}</span>
                      </td>
                      <td className="py-2.5 pr-3">
                        <Puce texte={s.statut} ton={tonStatut(s.statut)} />
                      </td>
                    </tr>
                  ))}
                  {bord.seancesJour.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-10 text-center text-encre-pale">
                        Aucune séance programmée pour cette date.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            <Legende>
              Une présence est toujours rattachée à une séance publiée
              (<span className="font-mono text-[12px]">edts.AffectationCreneau</span>) : jamais à
              un module hors référentiel LMD, jamais à un simple créneau reconstitué.
            </Legende>
          </section>

          <aside>
            <Cartouche surtitre="Contrôle" titre="Anomalies détectées" />
            <ul className="space-y-0">
              {bord.anomalies.map((a, i) => (
                <li
                  key={a.id}
                  className="ligne-registre ligne-animee flex items-start gap-3 py-3"
                  style={{ animationDelay: `${i * 24}ms` }}
                >
                  <span
                    className={`mt-1 inline-block h-2 w-2 shrink-0 rounded-full ${
                      tonVerdict(a.verdict) === "alerte" ? "bg-vermillon" : "bg-vert-clair"
                    }`}
                  />
                  <div className="min-w-0">
                    <div className="truncate text-[14px] font-medium">{a.nom}</div>
                    <div className="caps mt-1 text-encre-pale">
                      {a.seance} · {a.typeParticipant}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {(a.anomalies ?? []).map((tag) => (
                        <Puce key={tag} texte={tag} ton="alerte" />
                      ))}
                      {!a.anomalies?.length ? (
                        <Puce texte={a.verdict ?? "SANS_BADGE"} ton={tonVerdict(a.verdict)} />
                      ) : null}
                    </div>
                  </div>
                  <span className="tab ml-auto shrink-0 font-mono text-[11px] text-encre-pale">
                    {heure(a.horodatage)}
                  </span>
                </li>
              ))}
              {bord.anomalies.length === 0 ? (
                <li className="py-8 text-center text-encre-pale">Aucune anomalie enregistrée.</li>
              ) : null}
            </ul>

            <div className="mt-10">
              <Cartouche surtitre="Répartition" titre="Par type de participant" />
              <div className="space-y-5">
                {bord.parRole.map((r) => (
                  <div key={r.role}>
                    <div className="mb-1.5 flex items-baseline justify-between">
                      <span className="caps">{r.role}</span>
                      <span className="tab font-mono text-[12px] text-encre-pale">
                        {r.presents}/{r.total} badgés
                      </span>
                    </div>
                    <Barre valeur={r.presents} max={r.total} />
                  </div>
                ))}
                {bord.parRole.length === 0 ? (
                  <p className="text-encre-pale">Aucun pointage enregistré.</p>
                ) : null}
              </div>
              <Legende>
                Les trois populations sont distinguées : l&apos;étudiant est contrôlé par son
                inscription et son groupe, l&apos;enseignant par son affectation pédagogique,
                l&apos;encadrant par sa mission d&apos;activité. Aucun rapprochement par nom.
              </Legende>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
