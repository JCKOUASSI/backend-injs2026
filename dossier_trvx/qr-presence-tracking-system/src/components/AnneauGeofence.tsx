"use client";

/**
 * Anneau de périmètre — visualisation du contrôle geofence serveur.
 * Chaque point est une mesure reçue (badge entrée ou heartbeat), placée selon
 * sa distance calculée par le serveur. Le client ne décide jamais du verdict.
 */
import { useState } from "react";

export interface PointMesure {
  id: number;
  nom: string;
  distanceM: number | null;
  verdict: string | null;
  horodatage: string;
}

const TON: Record<string, string> = {
  DANS_PERIMETRE: "#2f7d52",
  HORS_PERIMETRE: "#c2410c",
  POSITION_IMPRECISE: "#b4762a",
  POSITION_INEXPLOITABLE: "#c2410c",
  POSITION_ABSENTE: "#5c544a",
  SITE_NON_LOCALISE: "#5c544a",
};

export default function AnneauGeofence({
  rayonM,
  points,
  site,
}: {
  rayonM: number;
  points: PointMesure[];
  site: string;
}) {
  const [survol, setSurvol] = useState<PointMesure | null>(null);
  const centre = 150;
  const rayonPx = 112;

  return (
    <div className="panneau p-6">
      <div className="caps mb-1 text-encre-pale">Contrôle de périmètre</div>
      <h3 className="font-display text-[20px] font-bold">{site}</h3>

      <div className="mt-4 flex flex-wrap items-start gap-6">
        <svg viewBox="0 0 300 300" className="h-[260px] w-[260px] shrink-0" role="img"
          aria-label={`Périmètre autorisé de ${rayonM} mètres autour du site`}>
          <circle cx={centre} cy={centre} r={rayonPx} fill="#2f7d52" fillOpacity="0.08"
            stroke="#1f5c3d" strokeWidth="1.5" strokeDasharray="4 4" />
          <circle cx={centre} cy={centre} r={rayonPx * 0.62} fill="none" stroke="#cfc5b2" strokeWidth="1" />
          <circle cx={centre} cy={centre} r={rayonPx * 0.31} fill="none" stroke="#cfc5b2" strokeWidth="1" />
          <line x1={centre} y1={centre - rayonPx - 12} x2={centre} y2={centre + rayonPx + 12}
            stroke="#cfc5b2" strokeWidth="0.75" />
          <line x1={centre - rayonPx - 12} y1={centre} x2={centre + rayonPx + 12} y2={centre}
            stroke="#cfc5b2" strokeWidth="0.75" />
          <rect x={centre - 9} y={centre - 9} width="18" height="18" fill="#17140f" />
          <text x={centre} y={centre + 34} textAnchor="middle" fontSize="9"
            letterSpacing="1.6" fill="#5c544a">
            {rayonM} M
          </text>

          {points.map((p, i) => {
            const ratio = p.distanceM === null ? 0 : Math.min(1.35, p.distanceM / rayonM);
            const angle = (i * 137.5 * Math.PI) / 180;
            const x = centre + Math.cos(angle) * rayonPx * ratio;
            const y = centre + Math.sin(angle) * rayonPx * ratio;
            const couleur = TON[p.verdict ?? "POSITION_ABSENTE"] ?? "#5c544a";
            return (
              <g key={p.id} onMouseEnter={() => setSurvol(p)} onMouseLeave={() => setSurvol(null)}>
                <circle cx={x} cy={y} r={survol?.id === p.id ? 8 : 5.5} fill={couleur}
                  fillOpacity="0.85" stroke="#faf7f0" strokeWidth="1.25" />
              </g>
            );
          })}
        </svg>

        <div className="min-w-[190px] flex-1">
          <div className="caps text-encre-pale">Mesures reçues</div>
          <p className="mt-2 text-[13px] leading-relaxed text-encre-pale">
            Distance calculée serveur (haversine) entre la position déclarée et le centre du site.
            Rayon autorisé <strong className="text-encre">{rayonM} m</strong>.
          </p>

          <div className="mt-4 space-y-2">
            {survol ? (
              <div className="border border-filet bg-papier px-3 py-2">
                <div className="text-[13px] font-medium">{survol.nom}</div>
                <div className="tab mt-1 font-mono text-[11px] text-encre-pale">
                  {survol.distanceM === null ? "distance inconnue" : `${survol.distanceM.toFixed(1)} m`}
                  {" · "}
                  {survol.verdict ?? "—"}
                </div>
              </div>
            ) : (
              <div className="border border-dashed border-filet px-3 py-4 text-[12px] text-encre-pale">
                Survolez un point pour lire la mesure.
              </div>
            )}

            <ul className="space-y-1.5 pt-2">
              {Object.entries(TON).map(([verdict, couleur]) => (
                <li key={verdict} className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: couleur }} />
                  <span className="caps text-encre-pale">{verdict.replace(/_/g, " ")}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
