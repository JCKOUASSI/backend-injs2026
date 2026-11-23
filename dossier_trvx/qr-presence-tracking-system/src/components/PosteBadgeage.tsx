"use client";

/**
 * Poste de badgeage — parcours réel : scan → vérification serveur → présence
 * validée ou refusée → heartbeat → sortie. L'état n'est jamais déclaré
 * « validé » avant la confirmation du serveur.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch, type ReponseErreurClient } from "@/lib/client";
import { Puce } from "@/components/ui";

export interface SeanceOption {
  id: number;
  libelle: string;
  horaire: string;
  groupe: string;
  statut: string;
  jeton: string | null;
}

const ETATS = [
  "PRET_A_BADGER",
  "SCAN_EN_COURS",
  "VERIFICATION",
  "PRESENCE_VALIDEE",
  "PRESENCE_REFUSEE",
  "HEARTBEAT_ACTIF",
  "SEANCE_TERMINEE",
  "EN_ATTENTE_SYNCHRONISATION",
] as const;

type Etat = (typeof ETATS)[number];

interface Resultat {
  titre: string;
  lignes: { libelle: string; valeur: string }[];
}

export default function PosteBadgeage({
  seances,
  site,
}: {
  seances: SeanceOption[];
  site: { nom: string; latitude: number | null; longitude: number | null; rayon: number };
}) {
  const [seanceId, setSeanceId] = useState<number>(seances[0]?.id ?? 0);
  const [jeton, setJeton] = useState<string>(seances[0]?.jeton ?? "");
  const [etat, setEtat] = useState<Etat>("PRET_A_BADGER");
  const [erreur, setErreur] = useState<ReponseErreurClient | null>(null);
  const [resultat, setResultat] = useState<Resultat | null>(null);
  const [pointageId, setPointageId] = useState<number | null>(null);
  const [position, setPosition] = useState<{ lat: number; lng: number; acc: number } | null>(null);
  const [gpsEtat, setGpsEtat] = useState<string>("En attente de la mesure");
  const [reseauOk, setReseauOk] = useState(true);
  const [journal, setJournal] = useState<string[]>([]);
  const minuteur = useRef<ReturnType<typeof setInterval> | null>(null);

  const seance = seances.find((s) => s.id === seanceId) ?? seances[0];

  const noter = useCallback((ligne: string) => {
    setJournal((j) => [`${new Date().toLocaleTimeString("fr-FR")} · ${ligne}`, ...j].slice(0, 8));
  }, []);

  const mesurer = useCallback(async () => {
    setGpsEtat("Acquisition GPS…");
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGpsEtat("Géolocalisation indisponible sur ce terminal");
      return null;
    }
    return new Promise<{ lat: number; lng: number; acc: number } | null>((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const mesure = {
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            acc: pos.coords.accuracy ?? 999,
          };
          setPosition(mesure);
          setGpsEtat(
            `Position acquise · ±${mesure.acc.toFixed(0)} m (précision annoncée par le terminal)`,
          );
          resolve(mesure);
        },
        () => {
          setGpsEtat("Position refusée ou indisponible — utilisez la mesure de secours");
          resolve(null);
        },
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 },
      );
    });
  }, []);

  // Heartbeat : tant que la présence est ouverte, le terminal envoie position,
  // horodatage et précision. Une sortie du périmètre génère une anomalie, elle
  // ne supprime pas la présence.
  useEffect(() => {
    if (etat !== "HEARTBEAT_ACTIF" || pointageId === null) return;
    minuteur.current = setInterval(async () => {
      const mesure = position ?? (await mesurer());
      try {
        const res = await apiFetch<{ heartbeat: { verdict: string; distanceM: number | null } }>(
          "/api/scan/secure/heartbeat",
          {
            method: "POST",
            body: JSON.stringify({
              jeton,
              pointage_id: pointageId,
              latitude: mesure?.lat ?? null,
              longitude: mesure?.lng ?? null,
              accuracy: mesure?.acc ?? null,
            }),
          },
        );
        setReseauOk(true);
        noter(
          `heartbeat · ${res.heartbeat.verdict}${
            res.heartbeat.distanceM !== null ? ` · ${res.heartbeat.distanceM.toFixed(0)} m` : ""
          }`,
        );
      } catch (e) {
        setReseauOk(false);
        const err = e as ReponseErreurClient;
        noter(`heartbeat refusé · ${err.code ?? "RESEAU"}`);
      }
    }, 15000);
    return () => {
      if (minuteur.current) clearInterval(minuteur.current);
    };
  }, [etat, pointageId, jeton, position, mesurer, noter]);

  const chargerJeton = useCallback(async () => {
    setEtat("VERIFICATION");
    try {
      const res = await apiFetch<{ sessionQr: { jeton: string } | null }>(
        `/api/seances/${seanceId}`,
      );
      if (res.sessionQr?.jeton) {
        setJeton(res.sessionQr.jeton);
        noter("jeton de session récupéré depuis la séance");
        setEtat("PRET_A_BADGER");
      } else {
        setErreur({
          ok: false,
          code: "SEANCE_INACTIVE",
          message: "Aucune session QR ouverte.",
          explication:
            "La séance ne dispose pas de session de badgeage active. L'enseignant doit émettre le QR.",
          action_recommandee: "Émettre le QR depuis la fiche de séance.",
        });
        setEtat("PRESENCE_REFUSEE");
      }
    } catch (e) {
      const err = e as { payload?: ReponseErreurClient };
      setErreur(err.payload ?? null);
      setEtat("PRESENCE_REFUSEE");
    }
  }, [seanceId, noter]);

  const badger = useCallback(
    async (action: "scan" | "sortie") => {
      setErreur(null);
      setResultat(null);
      setEtat(action === "scan" ? "SCAN_EN_COURS" : "VERIFICATION");
      const mesure = position ?? (await mesurer());

      if (action === "scan" && !mesure) {
        // Pas de position : le serveur refuserait GPS_INDISPONIBLE. On laisse le
        // serveur trancher — il est l'autorité — mais on prévient l'utilisateur.
        noter("aucune mesure GPS disponible avant l'envoi");
      }

      setEtat("VERIFICATION");
      try {
        if (action === "scan") {
          const res = await apiFetch<{
            pointage: { id: number; statut: string; timestampEntree: string };
            seance: { libelle: string; dateSeance: string; heureDebut: string; heureFin: string; salle: string | null };
            evaluation: { verdict: string; distanceM: number | null; rayonM: number | null; precision: string };
          }>("/api/scan/secure", {
            method: "POST",
            body: JSON.stringify({
              jeton,
              latitude: mesure?.lat ?? null,
              longitude: mesure?.lng ?? null,
              accuracy: mesure?.acc ?? null,
              device_id: "PWA-NAVIGATEUR",
              timestamp_client: new Date().toISOString(),
            }),
          });
          setPointageId(res.pointage.id);
          setEtat("PRESENCE_VALIDEE");
          noter(`entrée validée · pointage #${res.pointage.id}`);
          window.setTimeout(() => setEtat("HEARTBEAT_ACTIF"), 1200);
          setResultat({
            titre: "Présence enregistrée",
            lignes: [
              { libelle: "Séance", valeur: res.seance.libelle },
              {
                libelle: "Heure",
                valeur: `${res.seance.dateSeance} · ${res.seance.heureDebut}–${res.seance.heureFin}`,
              },
              { libelle: "Mode", valeur: "QR automatique" },
              {
                libelle: "Localisation",
                valeur: `${res.evaluation.verdict}${
                  res.evaluation.distanceM !== null
                    ? ` · ${res.evaluation.distanceM.toFixed(0)} m du site`
                    : ""
                }`,
              },
              {
                libelle: "Précision",
                valeur: `${res.evaluation.precision}${
                  mesure ? ` · ±${mesure.acc.toFixed(0)} m` : ""
                }`,
              },
            ],
          });
        } else {
          if (pointageId === null) {
            setErreur({
              ok: false,
              code: "SORTIE_SANS_ENTREE",
              message: "Sortie sans entrée.",
              explication: "Aucun pointage ouvert pour ce terminal.",
              action_recommandee: "Procéder d'abord à l'entrée.",
            });
            setEtat("PRESENCE_REFUSEE");
            return;
          }
          const res = await apiFetch<{
            pointage: { id: number; dureeMinutes: number; timestampSortie: string };
          }>("/api/scan/secure/exit", {
            method: "POST",
            body: JSON.stringify({
              pointage_id: pointageId,
              source: "BADGE_SORTIE",
              latitude: mesure?.lat ?? null,
              longitude: mesure?.lng ?? null,
              accuracy: mesure?.acc ?? null,
            }),
          });
          setEtat("SEANCE_TERMINEE");
          noter(`sortie validée · durée ${res.pointage.dureeMinutes} min`);
          setResultat({
            titre: "Sortie enregistrée",
            lignes: [
              { libelle: "Pointage", valeur: `#${res.pointage.id}` },
              { libelle: "Durée de présence", valeur: `${res.pointage.dureeMinutes} minutes` },
              { libelle: "Source de sortie", valeur: "Badge sortie" },
            ],
          });
        }
      } catch (e) {
        const err = e as { payload?: ReponseErreurClient; status?: number };
        setErreur(
          err.payload ?? {
            ok: false,
            code: "RESEAU",
            message: "Serveur injoignable.",
            explication:
              "La requête n'a pas abouti. Aucune présence n'est validée avant confirmation serveur.",
            action_recommandee: "Réessayer une fois le réseau rétabli.",
          },
        );
        if (!err.payload) setEtat("EN_ATTENTE_SYNCHRONISATION");
        else setEtat("PRESENCE_REFUSEE");
        noter(`refus · ${err.payload?.code ?? "RESEAU"}`);
      }
    },
    [jeton, pointageId, position, mesurer, noter],
  );

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      {/* Colonne de commande */}
      <div className="panneau p-8">
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              etat === "PRESENCE_REFUSEE" ? "bg-vermillon" : "bg-vert-clair pouls"
            }`}
          />
          <span className="caps text-encre-pale">État du badgeage</span>
          <Puce
            texte={etat.replace(/_/g, " ")}
            ton={etat === "PRESENCE_REFUSEE" || etat === "EN_ATTENTE_SYNCHRONISATION" ? "alerte" : "conforme"}
          />
          {!reseauOk ? <Puce texte="EN ATTENTE SYNCHRONISATION" ton="alerte" /> : null}
        </div>

        <div className="mt-6 space-y-5">
          <div>
            <label className="caps mb-1.5 block text-encre-pale" htmlFor="seance">
              Séance
            </label>
            <select
              id="seance"
              className="champ"
              value={seanceId}
              onChange={(e) => {
                const id = Number(e.target.value);
                setSeanceId(id);
                const s = seances.find((x) => x.id === id);
                setJeton(s?.jeton ?? "");
                setEtat("PRET_A_BADGER");
                setResultat(null);
                setErreur(null);
                setPointageId(null);
              }}
            >
              {seances.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.horaire} · {s.libelle} · {s.groupe} ({s.statut})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="caps mb-1.5 block text-encre-pale" htmlFor="jeton">
              Jeton de session QR
            </label>
            <textarea
              id="jeton"
              className="champ h-[76px] resize-none font-mono text-[11px]"
              value={jeton}
              onChange={(e) => setJeton(e.target.value)}
              placeholder="INJS1.<seance>.<session>.<nonce>.<expiration>.<signature>"
            />
            <button
              type="button"
              className="caps mt-2 text-vert underline"
              onClick={() => void chargerJeton()}
            >
              Récupérer le jeton de la séance
            </button>
          </div>

          <div className="border border-filet bg-papier px-4 py-3">
            <div className="caps text-encre-pale">Mesure GPS du terminal</div>
            <p className="mt-1.5 text-[13px] text-encre-pale">{gpsEtat}</p>
            {position ? (
              <p className="tab mt-1 font-mono text-[11px] text-encre">
                {position.lat.toFixed(6)}, {position.lng.toFixed(6)} · ±{position.acc.toFixed(0)} m
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="bouton bouton-secondaire" onClick={() => void mesurer()}>
                Mesurer la position
              </button>
              <button
                type="button"
                className="bouton bouton-secondaire"
                onClick={() => {
                  const mesure = {
                    lat: site.latitude ?? 5.36,
                    lng: site.longitude ?? -4.0082,
                    acc: 12,
                  };
                  setPosition(mesure);
                  setGpsEtat("Mesure de démonstration injectée (dans le périmètre)");
                }}
              >
                Mesure de démo (dans le périmètre)
              </button>
              <button
                type="button"
                className="bouton bouton-danger"
                onClick={() => {
                  const mesure = {
                    lat: (site.latitude ?? 5.36) + 0.01,
                    lng: (site.longitude ?? -4.0082) + 0.01,
                    acc: 12,
                  };
                  setPosition(mesure);
                  setGpsEtat("Mesure de démonstration injectée (hors périmètre)");
                }}
              >
                Mesure de démo (hors périmètre)
              </button>
            </div>
            <p className="mt-2 text-[11px] text-encre-pale">
              Le client transmet uniquement latitude, longitude et précision. Le verdict
              d&apos;appartenance au périmètre ({site.nom}, rayon {site.rayon} m) est calculé par
              le serveur.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              className="bouton"
              onClick={() => void badger("scan")}
              disabled={etat === "VERIFICATION" || !jeton}
            >
              Scanner le QR · entrée
            </button>
            <button
              type="button"
              className="bouton bouton-secondaire"
              onClick={() => void badger("sortie")}
              disabled={pointageId === null}
            >
              Badger la sortie
            </button>
          </div>
        </div>

        {erreur ? (
          <div className="mt-6 border-2 border-vermillon bg-vermillon/8 p-5">
            <div className="caps text-vermillon">{erreur.code}</div>
            <p className="mt-2 font-display text-[20px] font-bold">{erreur.message}</p>
            <p className="mt-2 max-w-[60ch] text-[13.5px] leading-relaxed text-encre-pale">
              {erreur.explication}
            </p>
            <p className="mt-3 border-t border-vermillon/30 pt-3 text-[13px]">
              <span className="caps text-vermillon">Action recommandée · </span>
              {erreur.action_recommandee}
            </p>
          </div>
        ) : null}

        {resultat ? (
          <div className="mt-6 border-2 border-vert bg-vert/8 p-5">
            <div className="caps text-vert">Confirmé par le serveur</div>
            <p className="mt-2 font-display text-[20px] font-bold">{resultat.titre}</p>
            <dl className="mt-3 space-y-1.5">
              {resultat.lignes.map((l) => (
                <div key={l.libelle} className="flex flex-wrap gap-x-3 border-b border-filet pb-1.5">
                  <dt className="caps w-[150px] text-encre-pale">{l.libelle}</dt>
                  <dd className="flex-1 text-[13.5px]">{l.valeur}</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}
      </div>

      {/* Colonne de lecture */}
      <div className="space-y-8">
        <div className="panneau p-6">
          <div className="caps text-encre-pale">Parcours de contrôle</div>
          <ol className="mt-4 space-y-2.5">
            {[
              "Utilisateur authentifié",
              "Scan du QR de la séance",
              "Validation du jeton (signature, expiration, anti-rejeu)",
              "Validation de la séance (publiée, non terminée, non annulée)",
              "Validation du participant (inscription / affectation / mission)",
              "Obtention de la position GPS du terminal",
              "Validation du geofence par le serveur",
              "Badgeage d'entrée",
              "Heartbeat pendant la séance",
              "Badgeage de sortie",
              "Clôture de la présence",
            ].map((etape, i) => (
              <li key={etape} className="flex items-start gap-3">
                <span className="tab mt-0.5 w-6 shrink-0 font-mono text-[11px] text-encre-pale">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-[13.5px] leading-snug">{etape}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="panneau p-6">
          <div className="caps text-encre-pale">Journal du terminal</div>
          <ul className="mt-3 space-y-1">
            {journal.length === 0 ? (
              <li className="text-[13px] text-encre-pale">Aucun événement pour l&apos;instant.</li>
            ) : (
              journal.map((l, i) => (
                <li key={`${l}-${i}`} className="tab font-mono text-[11px] text-encre-pale">
                  {l}
                </li>
              ))
            )}
          </ul>
        </div>

        <div className="panneau p-6">
          <div className="caps text-encre-pale">Hors ligne</div>
          <p className="mt-2 text-[13px] leading-relaxed text-encre-pale">
            Si le réseau est momentanément indisponible, le badgeage passe en{" "}
            <strong className="text-encre">EN ATTENTE SYNCHRONISATION</strong>. La mention
            « présence validée » n&apos;apparaît jamais avant la confirmation serveur ; après
            synchronisation, le pointage devient <strong className="text-encre">VALIDÉE</strong> ou{" "}
            <strong className="text-encre">REFUSÉE</strong>.
          </p>
        </div>
      </div>
    </div>
  );
}
