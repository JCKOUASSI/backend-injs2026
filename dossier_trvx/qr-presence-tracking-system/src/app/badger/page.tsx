import PosteBadgeage, { type SeanceOption } from "@/components/PosteBadgeage";
import { Cartouche, Legende } from "@/components/ui";
import { chargerSeances, chargerSites } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function PageBadgeage() {
  const seances = await chargerSeances();
  const sites = await chargerSites();
  const site = sites.find((s) => s.actif) ?? sites[0];

  const options: SeanceOption[] = seances.map((s) => ({
    id: s.id,
    libelle: `${s.ecueCode} — ${s.ecueIntitule}`,
    horaire: `${s.dateSeance} ${s.heureDebut}–${s.heureFin}`,
    groupe: s.groupe,
    statut: s.statut,
    jeton: null,
  }));

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-12">
      <Cartouche
        surtitre="Terminal de badgeage · Flutter PWA / navigateur"
        titre="Poste de badgeage"
        action={
          <div className="caps text-encre-pale">
            Étudiants · Enseignants · Encadrants
          </div>
        }
      />
      <Legende>
        Le scanner du client ne fait que collecter : jeton QR, latitude, longitude, précision,
        horodatage. Toute décision — validité du jeton, appartenance à la séance, respect du
        périmètre — revient au serveur.
      </Legende>

      <div className="mt-8">
        <PosteBadgeage
          seances={options}
          site={{
            nom: site?.nom ?? "Site non configuré",
            latitude: site?.geofenceLatitude ?? null,
            longitude: site?.geofenceLongitude ?? null,
            rayon: site?.geofenceRayonM ?? 200,
          }}
        />
      </div>
    </div>
  );
}
