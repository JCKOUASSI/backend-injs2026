import GeofenceFormulaire from "@/components/GeofenceFormulaire";
import { Cartouche, Legende, Puce } from "@/components/ui";
import { chargerSites } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function PageConfiguration() {
  const sites = await chargerSites();
  const site = sites.find((s) => s.actif) ?? sites[0];

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-12">
      <Cartouche
        surtitre="Paramètres du contrôle géographique"
        titre="Configuration du périmètre"
        action={<Puce texte="Aucune coordonnée codée en dur" ton="conforme" />}
      />

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div>{site ? <GeofenceFormulaire site={site} /> : null}</div>

        <div className="space-y-8">
          <figure className="panneau overflow-hidden">
            <img
              src="/images/campus.jpg"
              alt="Vue aérienne du campus INJS Abidjan"
              className="h-[280px] w-full object-cover"
              style={{ objectPosition: "50% 55%" }}
            />
            <figcaption className="border-t border-filet px-5 py-3 text-[12px] text-encre-pale">
              Le périmètre est défini autour du site de la séance (salle → site), jamais autour de
              la position déclarée par le terminal.
            </figcaption>
          </figure>

          <div className="panneau p-6">
            <div className="caps text-encre-pale">Règles appliquées</div>
            <ul className="mt-4 space-y-3 text-[13.5px] leading-relaxed">
              <li>
                <strong>Site non configuré</strong> — aucun contrôle de périmètre n&apos;est
                appliqué, conformément au comportement historique du référentiel.
              </li>
              <li>
                <strong>Précision</strong> — la mesure est qualifiée : POSITION_ACCEPTABLE,
                POSITION_IMPRECISE, POSITION_INEXPLOITABLE, POSITION_ABSENTE.
              </li>
              <li>
                <strong>Distance</strong> — calculée par le serveur (haversine), comparée au rayon
                du site : DANS_PERIMETRE ou HORS_PERIMETRE.
              </li>
              <li>
                <strong>Heartbeat</strong> — une sortie temporaire du périmètre produit une
                anomalie HEARTBEAT_HORS_GEOFENCE sans annuler la présence validée.
              </li>
              <li>
                <strong>Collecte limitée</strong> — aucune géolocalisation hors activité : les
                mesures ne sont collectées qu&apos;à l&apos;entrée, pendant la séance et à la
                sortie.
              </li>
            </ul>
          </div>

          <div className="panneau p-6">
            <div className="caps text-encre-pale">Sites déclarés</div>
            <ul className="mt-3">
              {sites.map((s, i) => (
                <li
                  key={s.id}
                  className={`ligne-registre flex flex-wrap items-center gap-3 py-2.5 ${
                    (i + 1) % 5 === 0 ? "ligne-registre-epaisse" : ""
                  }`}
                >
                  <span className="font-mono text-[12px]">{s.code}</span>
                  <span className="flex-1 text-[13px]">{s.nom}</span>
                  <span className="tab font-mono text-[11px] text-encre-pale">
                    {s.geofenceLatitude ?? "—"} / {s.geofenceLongitude ?? "—"} ·{" "}
                    {s.geofenceRayonM ?? "—"} m
                  </span>
                  <Puce texte={s.actif ? "ACTIF" : "INACTIF"} ton={s.actif ? "conforme" : "neutre"} />
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <Legende>
        Les coordonnées chargées ici sont des coordonnées de démonstration : elles doivent être
        remplacées par la configuration officielle du site INJS. Le moteur de badgeage ne contient
        aucune valeur géographique en dur.
      </Legende>
    </div>
  );
}
