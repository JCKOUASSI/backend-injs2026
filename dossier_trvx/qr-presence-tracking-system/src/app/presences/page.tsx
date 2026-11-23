import Link from "next/link";

import Emargement from "@/components/Emargement";
import { Cartouche, Legende, Puce, heure, tonStatut, tonVerdict } from "@/components/ui";
import {
  chargerActeurs,
  chargerPresences,
  chargerSeances,
} from "@/lib/queries";
import { MOTIFS_MANUELS } from "@/lib/domain";

export const dynamic = "force-dynamic";

const TYPES = ["", "ETUDIANT", "ENSEIGNANT", "ENCADRANT"];
const MODES = ["", "QR_AUTOMATIQUE", "MANUEL"];

export default async function PagePresences({
  searchParams,
}: {
  searchParams: Promise<{ type?: string; mode?: string; nom?: string; groupe?: string }>;
}) {
  const params = await searchParams;
  const [presences, seances, acteurs] = await Promise.all([
    chargerPresences({
      typeParticipant: params.type || undefined,
      mode: params.mode || undefined,
      nom: params.nom || undefined,
      groupe: params.groupe || undefined,
    }),
    chargerSeances(),
    chargerActeurs(),
  ]);

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-12">
      <Cartouche
        surtitre="Historique · Étudiants, enseignants, encadrants"
        titre="Registre des présences"
        action={
          <form className="flex flex-wrap items-center gap-3">
            <input
              name="nom"
              defaultValue={params.nom ?? ""}
              placeholder="Nom du participant"
              className="champ w-[190px]"
            />
            <input
              name="groupe"
              defaultValue={params.groupe ?? ""}
              placeholder="Groupe (ex. L2-SGN-A)"
              className="champ w-[160px]"
            />
            <select name="type" defaultValue={params.type ?? ""} className="champ">
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {t || "Tous les types"}
                </option>
              ))}
            </select>
            <select name="mode" defaultValue={params.mode ?? ""} className="champ">
              {MODES.map((m) => (
                <option key={m} value={m}>
                  {m || "Tous les modes"}
                </option>
              ))}
            </select>
            <button type="submit" className="bouton bouton-secondaire">
              Filtrer
            </button>
          </form>
        }
      />

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1120px] border-collapse text-[13.5px]">
          <thead>
            <tr className="border-b-2 border-encre text-left">
              <th className="caps py-2 pr-3 text-encre-pale">Participant</th>
              <th className="caps py-2 pr-3 text-encre-pale">Type</th>
              <th className="caps py-2 pr-3 text-encre-pale">Séance</th>
              <th className="caps py-2 pr-3 text-encre-pale">Date</th>
              <th className="caps py-2 pr-3 text-encre-pale">Entrée</th>
              <th className="caps py-2 pr-3 text-encre-pale">Sortie</th>
              <th className="caps py-2 pr-3 text-right text-encre-pale">Durée</th>
              <th className="caps py-2 pr-3 text-encre-pale">Mode</th>
              <th className="caps py-2 pr-3 text-encre-pale">Position</th>
              <th className="caps py-2 pr-3 text-encre-pale">Assiduité</th>
              <th className="caps py-2 pr-3 text-encre-pale">Anomalies</th>
            </tr>
          </thead>
          <tbody>
            {presences.map((p, i) => (
              <tr
                key={p.id}
                className={`ligne-registre ligne-animee align-baseline hover:bg-neutre/35 ${
                  (i + 1) % 5 === 0 ? "ligne-registre-epaisse" : ""
                }`}
                style={{ animationDelay: `${Math.min(i, 20) * 16}ms` }}
              >
                <td className="py-2.5 pr-3">
                  <span className="font-medium">{p.nom}</span>
                  <div className="caps mt-0.5 text-encre-pale">{p.matricule}</div>
                </td>
                <td className="py-2.5 pr-3">
                  <Puce texte={p.typeParticipant} ton="neutre" />
                </td>
                <td className="py-2.5 pr-3">
                  <Link
                    href={`/seances/${p.seanceId}`}
                    className="hover:text-vert"
                  >
                    {p.seance}
                  </Link>
                  <div className="caps mt-0.5 text-encre-pale">{p.groupe}</div>
                </td>
                <td className="tab py-2.5 pr-3 whitespace-nowrap">{p.dateSeance}</td>
                <td className="tab py-2.5 pr-3 font-mono text-[12px]">{heure(p.timestampEntree)}</td>
                <td className="tab py-2.5 pr-3 font-mono text-[12px]">
                  {heure(p.timestampSortie)}
                  <div className="caps mt-0.5 text-encre-pale">
                    {p.heartbeats} heartbeat{p.heartbeats > 1 ? "s" : ""}
                  </div>
                </td>
                <td className="tab py-2.5 pr-3 text-right">
                  {p.dureeMinutes ? `${p.dureeMinutes} min` : "—"}
                </td>
                <td className="py-2.5 pr-3">
                  <Puce texte={p.mode} ton={p.mode === "MANUEL" ? "alerte" : "conforme"} />
                  {p.motifManuel ? (
                    <div className="mt-0.5 max-w-[20ch] text-[11px] text-encre-pale">
                      {p.motifManuel}
                      {p.auteurManuelNom ? ` · ${p.auteurManuelNom}` : ""}
                    </div>
                  ) : null}
                </td>
                <td className="py-2.5 pr-3">
                  <Puce texte={p.verdictGeofence ?? "—"} ton={tonVerdict(p.verdictGeofence)} />
                  <div className="tab mt-0.5 font-mono text-[11px] text-encre-pale">
                    {p.accuracyM !== null ? `±${p.accuracyM.toFixed(0)} m` : "—"}
                  </div>
                </td>
                <td className="py-2.5 pr-3">
                  <Puce texte={p.statutAssiduite ?? p.statut} ton={tonStatut(p.statutAssiduite ?? p.statut)} />
                </td>
                <td className="py-2.5 pr-3">
                  <div className="flex flex-wrap gap-1">
                    {(p.anomalies ?? []).map((a) => (
                      <Puce key={a} texte={a} ton="alerte" />
                    ))}
                    {!(p.anomalies ?? []).length ? <span className="text-encre-pale">—</span> : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {presences.length === 0 ? (
        <p className="py-16 text-center text-encre-pale">
          Aucune présence ne correspond à ces critères.
        </p>
      ) : null}

      <Legende>
        Les coordonnées GPS brutes ne sont jamais affichées publiquement : seul le verdict de
        conformité, la distance au site et la précision annoncée sont restitués. La collecte est
        limitée au badge d&apos;entrée, aux heartbeats pendant la séance et à la sortie.
      </Legende>

      <section className="mt-14">
        <Cartouche
          surtitre="Exceptions"
          titre="Émargement manuel et corrections"
          action={<span className="caps text-encre-pale">RBAC · motif · audit</span>}
        />
        <Emargement
          seances={seances.map((s) => ({
            id: s.id,
            libelle: `${s.dateSeance} ${s.heureDebut} · ${s.ecueCode} · ${s.groupe}`,
          }))}
          acteurs={acteurs.map((a) => ({
            id: a.id,
            nom: `${a.prenom} ${a.nom}`,
            role: a.role,
          }))}
          motifs={MOTIFS_MANUELS.map((m) => ({
            code: m.code,
            libelle: m.libelle,
            exigeCommentaire: m.exigeCommentaire,
          }))}
        />
      </section>
    </div>
  );
}
