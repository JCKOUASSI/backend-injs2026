"use client";

/**
 * Émargement manuel et correction — exceptions tracées.
 * Motif obligatoire ; commentaire obligatoire pour le motif AUTRE.
 */
import { useState } from "react";

import { apiFetch, type ReponseErreurClient } from "@/lib/client";

export interface SeanceRef {
  id: number;
  libelle: string;
}
export interface ActeurRef {
  id: number;
  nom: string;
  role: string;
}
export interface MotifRef {
  code: string;
  libelle: string;
  exigeCommentaire: boolean;
}

export default function Emargement({
  seances,
  acteurs,
  motifs,
}: {
  seances: SeanceRef[];
  acteurs: ActeurRef[];
  motifs: MotifRef[];
}) {
  const [onglet, setOnglet] = useState<"manuel" | "correction">("manuel");
  const [seanceId, setSeanceId] = useState<number>(seances[0]?.id ?? 0);
  const [utilisateurId, setUtilisateurId] = useState<number>(
    acteurs.find((a) => a.role === "ETUDIANT")?.id ?? acteurs[0]?.id ?? 0,
  );
  const [motif, setMotif] = useState<string>(motifs[0]?.code ?? "QR_NON_LISIBLE");
  const [commentaire, setCommentaire] = useState("");
  const [pointageId, setPointageId] = useState<string>("");
  const [assiduite, setAssiduite] = useState<string>("PRESENT");
  const [motifCorrection, setMotifCorrection] = useState("");
  const [etat, setEtat] = useState<string | null>(null);
  const [erreur, setErreur] = useState<ReponseErreurClient | null>(null);
  const [enCours, setEnCours] = useState(false);

  const motifActif = motifs.find((m) => m.code === motif);

  const soumettre = async () => {
    setEnCours(true);
    setErreur(null);
    setEtat(null);
    try {
      if (onglet === "manuel") {
        const res = await apiFetch<{ pointage: { id: number; mode: string } }>(
          "/api/presences/manual",
          {
            method: "POST",
            body: JSON.stringify({
              seance_id: seanceId,
              utilisateur_id: utilisateurId,
              motif,
              commentaire: commentaire || null,
            }),
          },
        );
        setEtat(
          `Émargement manuel enregistré — pointage #${res.pointage.id}, mode MANUEL, auteur et motif journalisés.`,
        );
      } else {
        const res = await apiFetch<{ pointage: { id: number } }>(
          `/api/presences/${Number(pointageId)}/correct`,
          {
            method: "POST",
            body: JSON.stringify({
              statut_assiduite: assiduite,
              commentaire: commentaire || undefined,
              motif: motifCorrection,
            }),
          },
        );
        setEtat(
          `Correction enregistrée sur le pointage #${res.pointage.id} — ancienne et nouvelle valeurs conservées dans le journal d'audit.`,
        );
      }
    } catch (e) {
      const err = e as { payload?: ReponseErreurClient };
      setErreur(
        err.payload ?? {
          ok: false,
          code: "RESEAU",
          message: "Requête refusée.",
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
      <div className="flex flex-wrap items-center gap-2 border-b-2 border-encre pb-3">
        {(["manuel", "correction"] as const).map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => setOnglet(o)}
            className={`caps border-b-2 px-3 pb-2 ${
              onglet === o ? "border-vert text-vert" : "border-transparent text-encre-pale"
            }`}
          >
            {o === "manuel" ? "Émargement manuel" : "Correction de présence"}
          </button>
        ))}
        <span className="caps ml-auto text-encre-pale">
          Opération exceptionnelle · auditée systématiquement
        </span>
      </div>

      <div className="mt-6 grid gap-5 md:grid-cols-2">
        {onglet === "manuel" ? (
          <>
            <div>
              <label className="caps mb-1.5 block text-encre-pale" htmlFor="seance-manuel">
                Séance
              </label>
              <select
                id="seance-manuel"
                className="champ"
                value={seanceId}
                onChange={(e) => setSeanceId(Number(e.target.value))}
              >
                {seances.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.libelle}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="caps mb-1.5 block text-encre-pale" htmlFor="participant">
                Participant
              </label>
              <select
                id="participant"
                className="champ"
                value={utilisateurId}
                onChange={(e) => setUtilisateurId(Number(e.target.value))}
              >
                {acteurs.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nom} ({a.role})
                  </option>
                ))}
              </select>
            </div>
          </>
        ) : (
          <>
            <div>
              <label className="caps mb-1.5 block text-encre-pale" htmlFor="pointage-id">
                Pointage à corriger (identifiant)
              </label>
              <input
                id="pointage-id-id"
                className="champ font-mono"
                value={pointageId}
                onChange={(e) => setPointageId(e.target.value.replace(/\D/g, ""))}
                placeholder="ex. 12"
              />
            </div>
            <div>
              <label className="caps mb-1.5 block text-encre-pale" htmlFor="assiduite">
                Nouveau statut d&apos;assiduité
              </label>
              <select
                id="assiduite"
                className="champ"
                value={assiduite}
                onChange={(e) => setAssiduite(e.target.value)}
              >
                {["PRESENT", "ABSENT", "RETARD", "ABSENCE_JUSTIFIEE", "EXCUSE", "NON_RENSEIGNE"].map(
                  (s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ),
                )}
              </select>
            </div>
          </>
        )}

        <div>
          <label className="caps mb-1.5 block text-encre-pale" htmlFor="motif">
            Motif {onglet === "manuel" ? "(obligatoire)" : "de correction (obligatoire)"}
          </label>
          {onglet === "manuel" ? (
            <select
              id="motif"
              className="champ"
              value={motif}
              onChange={(e) => setMotif(e.target.value)}
            >
              {motifs.map((m) => (
                <option key={m.code} value={m.code}>
                  {m.libelle}
                </option>
              ))}
            </select>
          ) : (
            <input
              id="motif"
              className="champ"
              value={motifCorrection}
              onChange={(e) => setMotifCorrection(e.target.value)}
              placeholder="Motif de la correction"
            />
          )}
        </div>

        <div>
          <label className="caps mb-1.5 block text-encre-pale" htmlFor="commentaire">
            Commentaire{" "}
            {motifActif?.exigeCommentaire && onglet === "manuel" ? "(obligatoire)" : "(facultatif)"}
          </label>
          <textarea
            id="commentaire"
            className="champ h-[80px] resize-none"
            value={commentaire}
            onChange={(e) => setCommentaire(e.target.value)}
          />
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <button type="button" className="bouton" onClick={() => void soumettre()} disabled={enCours}>
          {onglet === "manuel" ? "Enregistrer l'émargement" : "Enregistrer la correction"}
        </button>
        <p className="max-w-[52ch] text-[12px] text-encre-pale">
          L&apos;opérateur, la date et l&apos;heure, le participant, la séance, le motif et le
          commentaire sont enregistrés. Une correction ne remplace jamais la valeur d&apos;origine :
          elle est ajoutée au journal.
        </p>
      </div>

      {erreur ? (
        <div className="mt-5 border-2 border-vermillon bg-vermillon/8 p-4">
          <div className="caps text-vermillon">{erreur.code}</div>
          <p className="mt-1.5 font-medium">{erreur.message}</p>
          <p className="mt-1 text-[13px] text-encre-pale">{erreur.explication}</p>
          <p className="mt-2 text-[12.5px]">
            <span className="caps text-vermillon">Action recommandée · </span>
            {erreur.action_recommandee}
          </p>
        </div>
      ) : null}

      {etat ? (
        <div className="mt-5 border-2 border-vert bg-vert/8 p-4">
          <div className="caps text-vert">Opération enregistrée</div>
          <p className="mt-1.5 text-[13.5px]">{etat}</p>
        </div>
      ) : null}
    </div>
  );
}
