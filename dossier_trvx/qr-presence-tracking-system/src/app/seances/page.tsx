import Link from "next/link";

import { chargerSeances } from "@/lib/queries";
import { Cartouche, Legende, Puce, tonStatut } from "@/components/ui";

export const dynamic = "force-dynamic";

const FILTRES = [
  { valeur: "", libelle: "Toutes" },
  { valeur: "PUBLIEE", libelle: "Publiées" },
  { valeur: "TERMINEE", libelle: "Terminées" },
  { valeur: "ANNULEE", libelle: "Annulées" },
  { valeur: "SIMULATION", libelle: "Simulation" },
];

export default async function PageSeances({
  searchParams,
}: {
  searchParams: Promise<{ statut?: string; date?: string }>;
}) {
  const params = await searchParams;
  const lignes = await chargerSeances({
    statut: params.statut || undefined,
    date: params.date || undefined,
  });

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-12">
      <Cartouche
        surtitre="Emplois du temps · Séances pédagogiques"
        titre="Registre des séances"
        action={
          <form className="flex flex-wrap items-center gap-3">
            <input
              type="date"
              name="date"
              defaultValue={params.date ?? ""}
              className="champ font-mono text-[13px]"
            />
            <select name="statut" defaultValue={params.statut ?? ""} className="champ">
              {FILTRES.map((f) => (
                <option key={f.valeur} value={f.valeur}>
                  {f.libelle}
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
        <table className="w-full min-w-[1040px] border-collapse text-[14px]">
          <thead>
            <tr className="border-b-2 border-encre text-left align-bottom">
              <th className="caps py-2 pr-3 text-encre-pale">Identifiant</th>
              <th className="caps py-2 pr-3 text-encre-pale">Date</th>
              <th className="caps py-2 pr-3 text-encre-pale">Horaire</th>
              <th className="caps py-2 pr-3 text-encre-pale">ECUE → UE</th>
              <th className="caps py-2 pr-3 text-encre-pale">Parcours / niveau</th>
              <th className="caps py-2 pr-3 text-encre-pale">Groupe</th>
              <th className="caps py-2 pr-3 text-encre-pale">Enseignant</th>
              <th className="caps py-2 pr-3 text-encre-pale">Salle</th>
              <th className="caps py-2 pr-3 text-right text-encre-pale">Attendus</th>
              <th className="caps py-2 pr-3 text-right text-encre-pale">Présents</th>
              <th className="caps py-2 pr-3 text-right text-encre-pale">Manuels</th>
              <th className="caps py-2 pr-3 text-right text-encre-pale">Anom.</th>
              <th className="caps py-2 pr-3 text-encre-pale">Statut</th>
            </tr>
          </thead>
          <tbody>
            {lignes.map((s, i) => (
              <tr
                key={s.id}
                className={`ligne-registre ligne-animee align-baseline hover:bg-neutre/35 ${
                  (i + 1) % 5 === 0 ? "ligne-registre-epaisse" : ""
                }`}
                style={{ animationDelay: `${Math.min(i, 20) * 18}ms` }}
              >
                <td className="py-2.5 pr-3 font-mono text-[11px] text-encre-pale">
                  {s.identifiantPermanent}
                </td>
                <td className="tab py-2.5 pr-3 whitespace-nowrap">{s.dateSeance}</td>
                <td className="tab py-2.5 pr-3 font-mono text-[13px] whitespace-nowrap">
                  {s.heureDebut}–{s.heureFin}
                </td>
                <td className="py-2.5 pr-3">
                  <Link href={`/seances/${s.id}`} className="font-medium text-encre hover:text-vert">
                    {s.ecueCode} · {s.ecueIntitule}
                  </Link>
                  <div className="caps mt-1 text-encre-pale">
                    {s.ueCode} · {s.typeSeance} · {s.maquette}
                  </div>
                </td>
                <td className="py-2.5 pr-3 text-[13px]">
                  {s.parcours} · {s.niveau} {s.semestre}
                  <div className="caps mt-1 text-encre-pale">{s.formation}</div>
                </td>
                <td className="py-2.5 pr-3 font-mono text-[13px]">{s.groupe}</td>
                <td className="py-2.5 pr-3">
                  {s.enseignant ?? "—"}
                  {s.encadrant ? (
                    <div className="caps mt-1 text-encre-pale">Enc. {s.encadrant}</div>
                  ) : null}
                </td>
                <td className="py-2.5 pr-3 text-encre-pale">{s.salle ?? "—"}</td>
                <td className="tab py-2.5 pr-3 text-right">{s.attendus}</td>
                <td className="tab py-2.5 pr-3 text-right font-semibold text-vert">
                  {s.presents}
                </td>
                <td className="tab py-2.5 pr-3 text-right">{s.manuels}</td>
                <td className="tab py-2.5 pr-3 text-right">
                  {Number(s.anomalies) > 0 ? (
                    <span className="font-semibold text-vermillon">{s.anomalies}</span>
                  ) : (
                    <span className="text-encre-pale">0</span>
                  )}
                </td>
                <td className="py-2.5 pr-3">
                  <Puce texte={s.statut} ton={tonStatut(s.statut)} />
                  {s.motifAnnulation ? (
                    <div className="mt-1 max-w-[22ch] text-[11px] text-vermillon">
                      {s.motifAnnulation}
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {lignes.length === 0 ? (
        <p className="py-16 text-center text-encre-pale">
          Aucune séance ne correspond à ces critères.
        </p>
      ) : null}

      <Legende>
        L&apos;identifiant permanent (<span className="font-mono text-[12px]">INJS-S-######</span>)
        est stable : une modification d&apos;horaire, de salle ou d&apos;enseignant conserve
        l&apos;identité de la séance. Une annulation suivie d&apos;une reprogrammation crée une
        nouvelle séance reliée à l&apos;annulée (<span className="font-mono text-[12px]">annulee_de_id</span>).
      </Legende>
    </div>
  );
}
