"use client";

/**
 * Planche de session QR — le jeton temporaire signé, sa rotation et son
 * décompte. Le QR est l'entrée du badgeage automatique ; la validation reste
 * intégralement serveur.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/client";
import { Puce } from "@/components/ui";

interface SessionInitiale {
  id: number;
  jeton: string;
  expireLe: string;
  rotation: number;
  statut: string;
}

export default function QrPlanche({
  seanceId,
  seanceLibelle,
  sessionInitiale,
  peutEmettre,
  sessionAutorisee,
}: {
  seanceId: number;
  seanceLibelle: string;
  sessionInitiale: SessionInitiale | null;
  peutEmettre: boolean;
  sessionAutorisee: boolean;
}) {
  const [session, setSession] = useState<SessionInitiale | null>(sessionInitiale);
  const [image, setImage] = useState<string | null>(null);
  const [secondes, setSecondes] = useState(0);
  const [etat, setEtat] = useState<string>("PRET_A_BADGER");
  const [message, setMessage] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const minuteur = useRef<ReturnType<typeof setInterval> | null>(null);

  const dessiner = useCallback(async (jeton: string) => {
    try {
      const mod = (await import("qrcode")) as unknown as {
        toDataURL?: (t: string, o: unknown) => Promise<string>;
        default?: { toDataURL: (t: string, o: unknown) => Promise<string> };
      };
      const versDataUrl = mod.toDataURL ?? mod.default?.toDataURL;
      if (!versDataUrl) throw new Error("qrcode indisponible");
      const url = await versDataUrl(jeton, {
        margin: 1,
        width: 360,
        color: { dark: "#123524", light: "#faf7f0" },
      });
      setImage(url);
    } catch {
      setImage(null);
    }
  }, []);

  useEffect(() => {
    if (session?.jeton) void dessiner(session.jeton);
  }, [session?.jeton, dessiner]);

  useEffect(() => {
    const tick = () => {
      if (!session) return;
      const reste = Math.round(
        (new Date(session.expireLe).getTime() - Date.now()) / 1000,
      );
      setSecondes(Math.max(0, reste));
      if (reste <= 0) setEtat("QR_EXPIRE");
    };
    tick();
    minuteur.current = setInterval(tick, 1000);
    return () => {
      if (minuteur.current) clearInterval(minuteur.current);
    };
  }, [session]);

  const ouvrir = useCallback(
    async (dureeSecondes = 300) => {
      setEnCours(true);
      setEtat("VERIFICATION");
      setMessage(null);
      try {
        const res = await apiFetch<{ session: SessionInitiale }>(
          `/api/seances/${seanceId}/qr`,
          {
            method: "POST",
            body: JSON.stringify({ duree_secondes: dureeSecondes }),
          },
        );
        setSession(res.session);
        setEtat("PRET_A_BADGER");
      } catch (e) {
        const err = e as { payload?: { code?: string; message?: string; explication?: string } };
        setEtat("PRESENCE_REFUSEE");
        setMessage(
          `${err.payload?.code ?? "ERREUR"} — ${err.payload?.message ?? "émission impossible"}. ${
            err.payload?.explication ?? ""
          }`,
        );
      } finally {
        setEnCours(false);
      }
    },
    [seanceId],
  );

  const clore = useCallback(async () => {
    setEnCours(true);
    try {
      await apiFetch(`/api/seances/${seanceId}/autoclore`, {
        method: "POST",
        body: JSON.stringify({ motif: "Clôture manuelle depuis la planche QR" }),
      });
      setEtat("SEANCE_TERMINEE");
      setMessage("Séance clôturée : QR fermés, heartbeats stoppés, sorties automatiques.");
    } catch (e) {
      const err = e as { payload?: { code?: string; message?: string } };
      setMessage(`${err.payload?.code ?? "ERREUR"} — ${err.payload?.message ?? ""}`);
    } finally {
      setEnCours(false);
    }
  }, [seanceId]);

  const pourcentage = session ? Math.min(100, (secondes / 300) * 100) : 0;

  return (
    <div className="border-2 border-vert-fonce bg-vert-fonce text-papier-haut">
      <div className="flex flex-wrap items-start gap-8 px-8 py-8">
        {/* Carton de registre tamponné */}
        <div className="relative">
          <div className="border border-papier-haut/25 bg-papier-haut p-5">
            {image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={image}
                alt={`QR code de la session de badgeage — ${seanceLibelle}`}
                className="h-[248px] w-[248px]"
              />
            ) : (
              <div className="flex h-[248px] w-[248px] items-center justify-center overflow-hidden bg-papier p-3 font-mono text-[10px] break-all text-vert-fonce">
                {session?.jeton ?? "Session absente"}
              </div>
            )}
            <div className="caps mt-3 flex items-center justify-between text-vert-fonce">
              <span>Session QR · rotation {session?.rotation ?? 0}</span>
              <span className="tab font-mono">{session ? `T−${secondes}s` : "—"}</span>
            </div>
            <div className="mt-2 h-[3px] w-full bg-neutre">
              <div
                className="h-full bg-vert transition-[width] duration-500"
                style={{ width: `${pourcentage}%` }}
              />
            </div>
          </div>
          <div className="tampon caps absolute -right-5 -bottom-4 bg-papier-haut px-3 py-1.5">
            Jeton signé · anti-rejeu
          </div>
        </div>

        {/* État + conduite à tenir */}
        <div className="min-w-[300px] flex-1">
          <div className="caps text-papier-haut/60">Poste de badgeage</div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Puce
              texte={etat.replace(/_/g, " ")}
              ton={etat === "PRESENCE_REFUSEE" || etat === "QR_EXPIRE" ? "alerte" : "conforme"}
            />
            {sessionAutorisee ? (
              <Puce texte="Session ouverte" ton="conforme" />
            ) : (
              <Puce texte="Séance non badgeable" ton="alerte" />
            )}
          </div>

          <p className="mt-4 max-w-[52ch] text-[15px] leading-relaxed text-papier-haut/85">
            Le QR ne contient aucun identifiant d&apos;étudiant : il porte un jeton temporaire
            signé, rattaché à <strong>{seanceLibelle}</strong>, valable {Math.round(300 / 60)}{" "}
            minutes. Chaque rotation expire les jetons précédents — un QR photographié et rejoué
            est refusé.
          </p>

          {message ? (
            <div className="mt-4 border border-vermillon/60 bg-vermillon/15 px-4 py-3 text-[13px]">
              {message}
            </div>
          ) : null}

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              className="bouton bg-papier-haut text-vert-fonce hover:bg-white"
              onClick={() => void ouvrir(300)}
              disabled={enCours || !peutEmettre}
            >
              {session ? "Rafraîchir le QR" : "Émettre le QR"}
            </button>
            <button
              type="button"
              className="bouton bouton-secondaire border-papier-haut/50 text-papier-haut hover:bg-papier-haut/10"
              onClick={() => void ouvrir(60)}
              disabled={enCours || !peutEmettre}
            >
              Rotation 60 s
            </button>
            <button
              type="button"
              className="bouton bouton-danger border-papier-haut/50 text-papier-haut hover:bg-papier-haut/10"
              onClick={() => void clore()}
              disabled={enCours}
            >
              Clôturer la séance
            </button>
          </div>

          {!peutEmettre ? (
            <p className="mt-3 text-[12px] text-papier-haut/60">
              L&apos;acteur sélectionné ne dispose pas de la permission
              <span className="font-mono"> session.qr.emettre</span> (réservée aux enseignants,
              encadrants et administrations).
            </p>
          ) : null}

          <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-1 border-t border-papier-haut/20 pt-4">
            {[
              "PRET_A_BADGER",
              "SCAN_EN_COURS",
              "VERIFICATION",
              "PRESENCE_VALIDEE",
              "PRESENCE_REFUSEE",
              "HEARTBEAT_ACTIF",
              "SEANCE_TERMINEE",
              "EN_ATTENTE_SYNCHRONISATION",
            ].map((e) => (
              <span
                key={e}
                className={`caps py-0.5 ${
                  e === etat ? "text-papier-haut" : "text-papier-haut/40"
                }`}
              >
                {e.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
