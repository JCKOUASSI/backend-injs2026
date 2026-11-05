import { Cartouche, Legende, Puce } from "@/components/ui";
import { chargerAudit } from "@/lib/queries";

export const dynamic = "force-dynamic";

function Valeur({ titre, contenu }: { titre: string; contenu: unknown }) {
  if (contenu === null || contenu === undefined) return null;
  return (
    <div>
      <div className="caps text-encre-pale">{titre}</div>
      <pre className="mt-1 overflow-x-auto border border-filet bg-papier px-3 py-2 font-mono text-[11px] leading-relaxed">
        {JSON.stringify(contenu, null, 2)}
      </pre>
    </div>
  );
}

export default async function PageAudit() {
  const journal = await chargerAudit(200);

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-12">
      <Cartouche
        surtitre="Traçabilité non destructive"
        titre="Journal d'audit"
        action={<span className="caps text-encre-pale">{journal.length} événements</span>}
      />
      <Legende>
        Toute présence manuelle, toute correction, toute clôture de séance et toute modification
        de configuration géographique y sont inscrites avec leur auteur, leur date et leur motif.
        Une correction conserve l&apos;ancienne valeur à côté de la nouvelle : rien n&apos;est
        écrasé silencieusement.
      </Legende>

      <div className="mt-8 space-y-0">
        {journal.map((e, i) => (
          <article
            key={e.id}
            className={`ligne-registre ligne-animee grid gap-6 py-5 md:grid-cols-[220px_minmax(0,1fr)] ${
              (i + 1) % 5 === 0 ? "ligne-registre-epaisse" : ""
            }`}
            style={{ animationDelay: `${Math.min(i, 20) * 18}ms` }}
          >
            <div>
              <div className="tab font-mono text-[11px] text-encre-pale">
                {e.horodatage.toLocaleString("fr-FR")}
              </div>
              <div className="mt-1.5 text-[13px] font-medium">{e.auteurNom}</div>
              <div className="caps mt-1 text-encre-pale">
                {e.entite}
                {e.entiteId ? ` #${e.entiteId}` : ""}
              </div>
            </div>

            <div>
              <div className="flex flex-wrap items-center gap-3">
                <Puce
                  texte={e.action}
                  ton={
                    e.action.includes("CORRECTION") || e.action.includes("MANUEL")
                      ? "alerte"
                      : "conforme"
                  }
                />
                {e.motif ? <span className="text-[12.5px] text-encre-pale">motif : {e.motif}</span> : null}
              </div>

              <div className="mt-3 grid gap-5 lg:grid-cols-2">
                <Valeur titre="Ancienne valeur" contenu={e.ancienneValeur} />
                <Valeur titre="Nouvelle valeur" contenu={e.nouvelleValeur} />
              </div>
            </div>
          </article>
        ))}
        {journal.length === 0 ? (
          <p className="py-16 text-center text-encre-pale">Aucun événement d&apos;audit.</p>
        ) : null}
      </div>
    </div>
  );
}
