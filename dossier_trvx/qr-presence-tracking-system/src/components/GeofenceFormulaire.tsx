"use client";

/**
 * Configuration du geofence — explicite, configurable, auditée.
 * Aucune coordonnée n'est codée en dur dans le moteur de badgeage.
 */
import { useState } from "react";

import { apiFetch, type ReponseErreurClient } from "@/lib/client";

export interface SiteConfig {
  id: number;
  code: string;
  nom: string;
  actif: boolean;
  geofenceLatitude: number | null;
  geofenceLongitude: number | null;
  geofenceRayonM: number | null;
  precisionMaxM: number;
  noteConfiguration: string | null;
}

export default function GeofenceFormulaire({ site }: { site: SiteConfig }) {
  const [latitude, setLatitude] = useState(String(site.geofenceLatitude ?? ""));
  const [longitude, setLongitude] = useState(String(site.geofenceLongitude ?? ""));
  const [rayon, setRayon] = useState(String(site.geofenceRayonM ?? 200));
  const [precision, setPrecision] = useState(String(site.precisionMaxM ?? 50));
  const [actif, setActif] = useState(site.actif);
  const [note, setNote] = useState(site.noteConfiguration ?? "");
  const [etat, setEtat] = useState<string | null>(null);
  const [erreur, setErreur] = useState<ReponseErreurClient | null>(null);
  const [enCours, setEnCours] = useState(false);

  const enregistrer = async () => {
    setEnCours(true);
    setErreur(null);
    setEtat(null);
    try {
      await apiFetch("/api/config/geofence", {
        method: "PUT",
        body: JSON.stringify({
          site_id: site.id,
          geofence_latitude: latitude === "" ? null : Number(latitude),
          geofence_longitude: longitude === "" ? null : Number(longitude),
          geofence_rayon_m: rayon === "" ? null : Number(rayon),
          precision_max_m: Number(precision),
          actif,
          note_configuration: note,
        }),
      });
      setEtat(
        "Configuration enregistrée et journalisée (ancienne / nouvelle valeur dans le journal d'audit).",
      );
    } catch (e) {
      const err = e as { payload?: ReponseErreurClient };
      setErreur(
        err.payload ?? {
          ok: false,
          code: "RESEAU",
          message: "Enregistrement impossible.",
          explication: "Le serveur n'a pas traité la demande.",
          action_recommandee: "Réessayer.",
        },
      );
    } finally {
      setEnCours(false);
    }
  };

  return (
    <div className="panneau p-8">
      <div className="caps text-encre-pale">{site.code}</div>
      <h3 className="mt-1 font-display text-[25px] font-bold">{site.nom}</h3>

      <div className="mt-6 grid gap-5 md:grid-cols-2">
        <div>
          <label className="caps mb-1.5 block text-encre-pale" htmlFor="lat">
            Latitude du centre
          </label>
          <input
            id="lat"
            className="champ font-mono tab"
            value={latitude}
            onChange={(e) => setLatitude(e.target.value)}
            placeholder="ex. 5.360000"
          />
        </div>
        <div>
          <label className="caps mb-1.5 block text-encre-pale" htmlFor="lng">
            Longitude du centre
          </label>
          <input
            id="lng"
            className="champ font-mono tab"
            value={longitude}
            onChange={(e) => setLongitude(e.target.value)}
            placeholder="ex. -4.008200"
          />
        </div>
        <div>
          <label className="caps mb-1.5 block text-encre-pale" htmlFor="rayon">
            Rayon autorisé (mètres)
          </label>
          <input
            id="rayon"
            className="champ font-mono tab"
            value={rayon}
            onChange={(e) => setRayon(e.target.value.replace(/\D/g, ""))}
          />
          <p className="mt-1 text-[11px] text-encre-pale">
            Valeur par défaut du référentiel : 200 m (MOBILE_GEOFENCE_DEFAULT_RADIUS_M).
          </p>
        </div>
        <div>
          <label className="caps mb-1.5 block text-encre-pale" htmlFor="precision">
            Précision GPS maximale tolérée (mètres)
          </label>
          <input
            id="precision"
            className="champ font-mono tab"
            value={precision}
            onChange={(e) => setPrecision(e.target.value.replace(/\D/g, ""))}
          />
          <p className="mt-1 text-[11px] text-encre-pale">
            Au-delà : POSITION_IMPRECISE. Trois fois ce seuil : POSITION_INEXPLOITABLE.
          </p>
        </div>
        <div className="md:col-span-2">
          <label className="caps mb-1.5 block text-encre-pale" htmlFor="note">
            Note de configuration
          </label>
          <textarea
            id="note"
            className="champ h-[80px] resize-none"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-5">
        <label className="flex items-center gap-2.5">
          <input
            type="checkbox"
            checked={actif}
            onChange={(e) => setActif(e.target.checked)}
            className="h-4 w-4 accent-[#1f5c3d]"
          />
          <span className="caps">Site actif · contrôle de périmètre appliqué</span>
        </label>
        <button type="button" className="bouton" onClick={() => void enregistrer()} disabled={enCours}>
          Enregistrer la configuration
        </button>
      </div>

      {etat ? (
        <div className="mt-5 border-2 border-vert bg-vert/8 p-4 text-[13px] text-vert">{etat}</div>
      ) : null}
      {erreur ? (
        <div className="mt-5 border-2 border-vermillon bg-vermillon/8 p-4">
          <div className="caps text-vermillon">{erreur.code}</div>
          <p className="mt-1.5 text-[13.5px] font-medium">{erreur.message}</p>
          <p className="mt-1 text-[13px] text-encre-pale">{erreur.explication}</p>
        </div>
      ) : null}
    </div>
  );
}
