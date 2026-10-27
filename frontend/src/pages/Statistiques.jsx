/**
 * Statistiques.jsx — SYGEP-CPFAE
 * Dashboard multi-onglets : Vue d'ensemble · Pédagogique · Administratif · Historique · Secrétariats · Rapports · Alertes
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import FinancePeriodFilter from '../components/FinancePeriodFilter'
import { fmtHeures } from '../components/FinanceStatsGrid'
import {
  appendPeriodToSearchParams,
  loadFinancePeriod,
  saveFinancePeriod,
  isPeriodWhollyFuture,
  currentTrimestreParts,
  financePeriodKey,
} from '../utils/financePeriod'
import { isSecretariatScopedRole, lockedSecretariatId } from '../utils/roles'
import { useStatsMeta } from '../hooks/useStatsMeta'
import { PointJournalierTableauCPFAE, pjPct } from '../components/PointJournalierCPFAE'
import { AuditeursNotoiresPanel, AuditeursNotoiresKpiStrip, filterAuditeursNotoires } from '../components/AuditeursNotoiresPanel'
import RapportsWorkflowPanel from '../components/RapportsWorkflowPanel'

// ── Palettes & constantes ────────────────────────────────────────────────────
const C = ['#2277C1','#1565C0','#F5B100','#7B1FA2','#C62828','#00838F','#0F70AB','#AD1457','#0277BD','#4E342E']

const STATUT_LABELS = {
  TERMINE:'Terminé', EN_COURS:'En cours', FORCE_DFRC:'Forcé DFRC',
  ABSENT_NON_BADGE:'Absent non badgé', HORS_LIGNE_SUSPECT:'Hors ligne suspect',
  SORTIE_AUTO:'Sortie automatique',
}
const VALIDATION_ROLES = ['ADMIN','DIRECTION','CHEF_INJS_ADMIN','INJS_ADMIN']

const RB_VIEWS = [
  { id: 'bilans', label: 'Bilans INJS', icon: 'bi-table' },
  { id: 'workflow', label: 'Rapports périodiques', icon: 'bi-file-earmark-check' },
]

/** Libellés harmonisés des taux pédagogiques (vague 1). */
const TAUX_PEDAGOGIE = {
  assiduite: {
    label: 'Assiduité séance',
    help: 'Places présentes ÷ places attendues sur les séances terminées du périmètre. Utilisé pour le dashboard, les alertes et l\'historique.',
    color: '#2277C1',
    getValue: (ped) => ped?.taux_presence ?? 0,
  },
  couverture: {
    label: 'Couverture étudiants',
    help: 'Étudiants ayant au moins une présence ÷ étudiants inscrits. Aligné sur la logique des bilans INJS.',
    color: '#1565C0',
    getValue: (ped) => ped?.taux_couverture_auditeurs ?? ped?.taux_achevement ?? 0,
  },
  absence: {
    label: 'Absence séance',
    help: 'Places absentes ÷ places attendues sur les séances terminées du périmètre.',
    color: '#C62828',
    getValue: (ped) => ped?.taux_absence ?? 0,
  },
  evenements: {
    label: 'Événements absence / suspect',
    help: 'Pointages « absent non badgé » ou « hors ligne suspect » rapportés aux inscrits (événements, pas absents notoires).',
    color: '#F5B100',
    getValue: (ped) => ped?.taux_abandon ?? 0,
  },
}
const KPI_VH_EXEC = {
  label: 'Avancement VH (sessions clôturées)',
  help: 'Heures réalisées ÷ heures prévues, sur les séances clôturées du périmètre filtré.',
}

const KPI_SESSIONS_COMPT = {
  label: 'Séances comptabilisées',
  help: 'Séances dont la date est atteinte (EDT importé), alignées avec le point journalier et l\'assiduité.',
}

const KPI_SESSIONS_TOTAL = {
  label: 'Séances totales',
  help: 'Séances planifiées dont la date est dans la période sélectionnée (y compris futures sur l\'intervalle).',
}

const KPI_PERIOD_SCOPE_HELP =
  'Filtré selon la période : modules ayant au moins une séance dans l\'intervalle. « Toutes les périodes » = cumul global du périmètre.'

/** Définition métier unifiée (dashboard, bilans, FAC, alertes). */
const AUDITEURS_NOTOIRES = {
  label: 'Absents notoires',
  cardTitle: 'Absents notoires',
  help: 'Inscrit à au moins un module démarré, sans aucune présence enregistrée, ou avec motif notoire renseigné.',
}

/** Onglets accessibles aux comptes secrétariat (point + bilans uniquement). */
const SECRETARIAT_STATS_TABS = new Set(['point_journalier', 'rapports'])

/** Onglets où le filtre période s'applique aux indicateurs clés. */
const VH_PERIOD_TABS = new Set(['overview', 'pedagogy', 'admin', 'history', 'alertes'])

/** Sections API chargées par onglet (évite le calcul de tout le dashboard d'un coup). */
const TAB_SECTIONS = {
  overview: ['kpis', 'pedagogiques', 'admin_operationnel', 'alertes_overview', 'alertes'],
  pedagogy: ['pedagogiques'],
  admin: ['admin_operationnel'],
  history: ['historique', 'pedagogiques', 'admin_operationnel'],
  alertes: ['alertes', 'pedagogiques', 'admin_operationnel'],
  point_journalier: ['admin_operationnel'],
  rapports: ['admin_operationnel'],
}

/** Méta (formations_liste, secretariats_liste, filtre_actif) — chargées via useStatsMeta. */
const ALERTES_OVERVIEW_CODES = ['taux_presence', 'taux_execution_vh', 'saturation_groupe']

const PJ_EXPORT_FORMATS = [
  { fmt: 'xlsx', icon: 'bi-file-earmark-excel', label: 'Excel', col: '#0b4489' },
  { fmt: 'pdf',  icon: 'bi-file-earmark-pdf',   label: 'PDF',   col: '#C62828' },
  { fmt: 'docx', icon: 'bi-file-earmark-word',  label: 'Word',  col: '#1565C0' },
]

const RB_PERIODES = [
  { value: '', label: 'Toutes périodes' },
  { value: 'QUOTIDIEN', label: 'Quotidien' },
  { value: 'HEBDOMADAIRE', label: 'Hebdomadaire' },
  { value: 'MENSUEL', label: 'Mensuel' },
  { value: 'TRIMESTRIEL', label: 'Trimestriel' },
  { value: 'SEMESTRIEL', label: 'Semestriel' },
  { value: 'ANNUEL', label: 'Annuel' },
  { value: 'MI_PARCOURS', label: 'À mi-parcours' },
]

const RB_DIMENSIONS = [
  { id: 'module', label: 'Par Module', icon: 'bi-book' },
  { id: 'matiere', label: 'Par Matière', icon: 'bi-journals' },
  { id: 'categorie', label: 'Par Catégorie', icon: 'bi-tag' },
  { id: 'formation', label: 'Par Formation', icon: 'bi-journal-bookmark' },
]

function rbMatiereOptionValue(m) {
  if (m.ref_module_id) return `r:${m.ref_module_id}`
  return `i:${m.intitule}`
}

function rbParseMatiereKey(key) {
  if (!key) return {}
  if (key.startsWith('r:')) return { ref_module_id: Number(key.slice(2)) }
  if (key.startsWith('i:')) return { matiere_intitule: key.slice(2) }
  return {}
}

// ── Utilitaires graphiques (SVG natif) ───────────────────────────────────────
function Empty({ label = 'Aucune donnée' }) {
  return (
    <div style={{textAlign:'center',padding:'1.5rem',color:'#94a3b8',fontSize:'0.82rem'}}>
      <i className="bi bi-bar-chart" style={{fontSize:'1.8rem',display:'block',marginBottom:'0.4rem'}} />
      {label}
    </div>
  )
}

function Donut({ data, labelKey, valueKey, size = 150 }) {
  if (!data?.length) return <Empty />
  const total = data.reduce((s,d) => s+d[valueKey], 0)
  if (!total) return <Empty />
  const r = size/2 - 18, cx = size/2, cy = size/2
  let a = -Math.PI/2
  const slices = data.map((d,i) => {
    const ang = (d[valueKey]/total)*2*Math.PI
    const x1 = cx+r*Math.cos(a), y1 = cy+r*Math.sin(a)
    a += ang
    return { ...d, x1, y1, x2: cx+r*Math.cos(a), y2: cy+r*Math.sin(a), large: ang>Math.PI?1:0, color: C[i%C.length] }
  })
  return (
    <div style={{display:'flex',alignItems:'center',gap:'1rem',flexWrap:'wrap'}}>
      <svg width={size} height={size} style={{flexShrink:0}}>
        {slices.map((s,i) => (
          <path key={i} d={`M${cx} ${cy} L${s.x1} ${s.y1} A${r} ${r} 0 ${s.large} 1 ${s.x2} ${s.y2}Z`}
            fill={s.color} opacity={0.88} stroke="#fff" strokeWidth={2}/>
        ))}
        <circle cx={cx} cy={cy} r={r*0.55} fill="#fff"/>
        <text x={cx} y={cy+5} textAnchor="middle" fontSize={13} fontWeight={700} fill="#1e293b">{total}</text>
      </svg>
      <ul style={{listStyle:'none',padding:0,margin:0,fontSize:'0.76rem',maxWidth:220}}>
        {slices.map((s,i) => (
          <li key={i} style={{display:'flex',alignItems:'center',gap:'0.35rem',marginBottom:'0.25rem'}}>
            <span style={{width:9,height:9,borderRadius:'50%',background:s.color,flexShrink:0,display:'inline-block'}}/>
            <span style={{color:'#475569',flex:1}}>{s[labelKey]}</span>
            <b style={{color:'#1e293b'}}>{s[valueKey]}</b>
            <span style={{color:'#94a3b8',fontSize:'0.7rem'}}>({Math.round(s[valueKey]/total*100)}%)</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Bars({ data, labelKey, valueKey, color='#2277C1', height=150 }) {
  if (!data?.length) return <Empty />
  const max = Math.max(...data.map(d=>d[valueKey]),1)
  const barW = Math.max(18, Math.min(44, Math.floor(520/data.length)-8))
  const w = data.length*(barW+8)+32
  return (
    <div style={{overflowX:'auto'}}>
      <svg width={Math.max(w,260)} height={height+48} style={{display:'block'}}>
        {data.map((d,i) => {
          const bH = Math.max(4, Math.round((d[valueKey]/max)*height))
          const x = 16+i*(barW+8), y = height-bH+4
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={bH} rx={4} fill={color} opacity={0.85}/>
              <text x={x+barW/2} y={y-3} textAnchor="middle" fontSize={10} fill="#1e293b" fontWeight={600}>{d[valueKey]}</text>
              <text x={x+barW/2} y={height+18} textAnchor="middle" fontSize={9} fill="#64748b">
                {String(d[labelKey]).slice(0,9)}{String(d[labelKey]).length>9?'…':''}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function HBars({ data, labelKey, valueKey }) {
  if (!data?.length) return <Empty />
  const max = Math.max(...data.map(d=>d[valueKey]),1)
  return (
    <div style={{display:'flex',flexDirection:'column',gap:'0.55rem'}}>
      {data.map((d,i) => (
        <div key={i}>
          <div style={{display:'flex',justifyContent:'space-between',fontSize:'0.79rem',marginBottom:'0.18rem'}}>
            <span style={{color:'#334155',fontWeight:500}}>{d[labelKey]}</span>
            <b style={{color:C[i%C.length]}}>{d[valueKey]}</b>
          </div>
          <div style={{background:'#f1f5f9',borderRadius:6,height:9,overflow:'hidden'}}>
            <div style={{width:`${Math.round(d[valueKey]/max*100)}%`,height:'100%',background:C[i%C.length],borderRadius:6,transition:'width 0.5s ease'}}/>
          </div>
        </div>
      ))}
    </div>
  )
}

function formatMoisLabel(cle) {
  if (!cle) return ''
  const [y, m] = String(cle).split('-').map(Number)
  const noms = ['janv.','févr.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.']
  return `${noms[(m || 1) - 1]} ${String(y || '').slice(-2)}`
}

function formatMoisLabelLong(cle) {
  if (!cle) return ''
  const [y, m] = String(cle).split('-').map(Number)
  const noms = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
  return `${noms[(m || 1) - 1]} ${y}`
}

function TrendBadge({ pct }) {
  if (pct == null) return <span style={{fontSize:'0.72rem',color:'#94a3b8'}}>—</span>
  const up = pct >= 0
  return (
    <span style={{
      fontSize:'0.72rem',fontWeight:700,
      color: up ? '#2277C1' : '#C62828',
      background: (up ? '#2277C1' : '#C62828') + '14',
      borderRadius:20,padding:'0.12rem 0.45rem',
    }}>
      {up ? '▲' : '▼'} {Math.abs(pct)}%
    </span>
  )
}

const NIVEAU_ALERTE = {
  ok:              { label: 'Conforme',       bg: '#ecf3fd', border: '#80b7f5', color: '#0b478a', icon: 'bi-check-circle-fill' },
  avertissement:   { label: 'Avertissement',  bg: '#fffceb', border: '#fcdf4d', color: '#b47f09', icon: 'bi-exclamation-triangle-fill' },
  critique:        { label: 'Critique',       bg: '#fff1f2', border: '#fca5a5', color: '#b91c1c', icon: 'bi-exclamation-octagon-fill' },
  inactif:         { label: 'Surveillance off', bg: '#f8fafc', border: '#e2e8f0', color: '#64748b', icon: 'bi-pause-circle' },
  non_configure:   { label: 'Non configuré',  bg: '#f1f5f9', border: '#cbd5e1', color: '#475569', icon: 'bi-gear' },
}

function NiveauBadge({ niveau, pulse = false }) {
  const n = NIVEAU_ALERTE[niveau] || NIVEAU_ALERTE.non_configure
  return (
    <span className={pulse ? 'stats-alerte-pulse' : undefined} style={{
      display:'inline-flex', alignItems:'center', gap:'0.3rem',
      fontSize:'0.72rem', fontWeight:700, padding:'0.2rem 0.55rem', borderRadius:20,
      background:n.bg, border:`1px solid ${n.border}`, color:n.color,
    }}>
      <i className={`bi ${n.icon}`}/>{n.label}
    </span>
  )
}

function SeuilGauge({ valeur, seuilAvert, seuilCrit, inverse, unite, echelleMax, niveau }) {
  const max = echelleMax || Math.max(valeur, seuilCrit * 1.25, seuilAvert * 1.25, 100)
  const pct = Math.min(100, Math.max(0, (valeur / max) * 100))
  const posAvert = Math.min(100, (seuilAvert / max) * 100)
  const posCrit = Math.min(100, (seuilCrit / max) * 100)

  const fillColor = niveau === 'critique' ? '#C62828'
    : niveau === 'avertissement' ? '#F5B100'
    : niveau === 'ok' ? '#2277C1' : '#94a3b8'

  const gradStops = inverse
    ? `#2277C1 0%, #2277C1 ${posAvert}%, #FCDF4D ${posAvert}%, #FCDF4D ${posCrit}%, #FCA5A5 ${posCrit}%, #FCA5A5 100%`
    : `#FCA5A5 0%, #FCA5A5 ${posCrit}%, #FCDF4D ${posCrit}%, #FCDF4D ${posAvert}%, #2277C1 ${posAvert}%, #2277C1 100%`

  return (
    <div style={{marginTop:'0.65rem'}}>
      <div style={{position:'relative', height:12, borderRadius:8, background:`linear-gradient(90deg, ${gradStops})`, opacity:0.45}}/>
      <div style={{position:'relative', height:12, marginTop:-12, borderRadius:8, overflow:'hidden'}}>
        <div className="stats-gauge-fill" style={{
          width:`${pct}%`, height:'100%',
          background: fillColor, borderRadius:8, opacity:0.92,
          boxShadow: niveau === 'critique' ? '0 0 8px rgba(198,40,40,0.45)' : 'none',
        }}/>
      </div>
      <div style={{position:'relative', height:18, marginTop:-15}}>
        <div className="stats-gauge-cursor" style={{
          position:'absolute', left:`calc(${pct}% - 6px)`, top:0,
          width:0, height:0,
          borderLeft:'6px solid transparent', borderRight:'6px solid transparent',
          borderBottom:`10px solid ${fillColor}`,
          filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.2))',
        }}/>
      </div>
      <div style={{display:'flex', justifyContent:'space-between', fontSize:'0.68rem', color:'#94a3b8', marginTop:'0.15rem'}}>
        <span>0{unite}</span>
        <span>⚠ {seuilAvert}{unite}</span>
        <span>🔴 {seuilCrit}{unite}</span>
        <span>{max}{unite}</span>
      </div>
    </div>
  )
}

function IndicateurSurveillanceCard({ ind }) {
  const n = NIVEAU_ALERTE[ind.niveau] || NIVEAU_ALERTE.non_configure
  const pulse = ind.niveau === 'critique'
  return (
    <div className={`stats-ind-card${pulse ? ' stats-ind-critique' : ''}`} style={{
      background:'#fff', borderRadius:12, padding:'1rem',
      border:`1px solid ${n.border}`,
      boxShadow: pulse ? '0 4px 18px rgba(198,40,40,0.12)' : '0 2px 8px rgba(0,0,0,0.06)',
      transition:'transform 0.2s ease, box-shadow 0.2s ease',
    }}>
      <div style={{display:'flex', alignItems:'flex-start', gap:'0.75rem', marginBottom:'0.5rem'}}>
        <div style={{
          width:44, height:44, borderRadius:12, flexShrink:0,
          background:`${ind.couleur}18`, color:ind.couleur,
          display:'flex', alignItems:'center', justifyContent:'center', fontSize:'1.25rem',
        }}>
          <i className={`bi ${ind.icone}`}/>
        </div>
        <div style={{flex:1, minWidth:0}}>
          <div style={{display:'flex', alignItems:'center', gap:'0.4rem', flexWrap:'wrap', marginBottom:'0.2rem'}}>
            <span style={{fontWeight:700, color:'#1e293b', fontSize:'0.88rem'}}>{ind.libelle}</span>
            <NiveauBadge niveau={ind.niveau} pulse={pulse}/>
          </div>
          <p style={{margin:0, fontSize:'0.73rem', color:'#64748b', lineHeight:1.45}}>{ind.aide}</p>
        </div>
      </div>
      <div style={{display:'flex', alignItems:'baseline', gap:'0.35rem', marginBottom:'0.15rem'}}>
        <span style={{fontSize:'2rem', fontWeight:800, color:n.color, lineHeight:1}}>
          {ind.valeur}{ind.unite}
        </span>
        <span style={{fontSize:'0.75rem', color:'#94a3b8'}}>valeur actuelle</span>
      </div>
      {ind.configure && ind.actif ? (
        <SeuilGauge
          valeur={ind.valeur}
          seuilAvert={ind.seuil_avertissement}
          seuilCrit={ind.seuil_critique}
          inverse={ind.inverse}
          unite={ind.unite}
          echelleMax={ind.echelle_max}
          niveau={ind.niveau}
        />
      ) : (
        <div style={{
          marginTop:'0.5rem', padding:'0.55rem 0.65rem', borderRadius:8,
          background:'#f8fafc', fontSize:'0.75rem', color:'#64748b',
        }}>
          {!ind.configure
            ? 'Seuil non configuré — initialisez les seuils INJS pour activer la surveillance.'
            : 'Surveillance désactivée pour cet indicateur.'}
        </div>
      )}
    </div>
  )
}

function AlertesOverviewBandeau({ items }) {
  const actives = (items || []).filter(
    a => ALERTES_OVERVIEW_CODES.includes(a.indicateur)
      && (a.niveau === 'critique' || a.niveau === 'avertissement'),
  )
  if (!actives.length) return null

  return (
    <div style={{ marginBottom: '1rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
      {actives.map((a) => (
        <div
          key={a.indicateur}
          className={a.niveau === 'critique' ? 'stats-alerte-pulse' : undefined}
          style={{
            background: a.niveau === 'critique' ? '#fff3f3' : '#fffceb',
            border: `1px solid ${a.niveau === 'critique' ? '#fca5a5' : '#fcdf4d'}`,
            borderRadius: 8,
            padding: '0.5rem 0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontSize: '0.82rem',
          }}
        >
          <i
            className={`bi ${a.niveau === 'critique' ? 'bi-exclamation-octagon-fill' : 'bi-exclamation-triangle-fill'}`}
            style={{ color: a.niveau === 'critique' ? '#C62828' : '#F5B100', fontSize: '1rem' }}
          />
          <b style={{ color: '#1e293b' }}>{a.libelle}</b>
          <span style={{ color: '#64748b' }}>: {a.valeur}{a.unite}</span>
          <span style={{ color: '#94a3b8', marginLeft: 'auto' }}>
            Seuil {a.niveau === 'critique' ? 'critique' : 'avertissement'} : {a.seuil_critique}{a.unite}
          </span>
        </div>
      ))}
    </div>
  )
}

function buildAlertesSidebarEntries(alertesMeta, alertesList) {
  const syn = alertesMeta?.synthese || {}
  const nbDecl = alertesList?.length ?? 0
  const indicateurs = alertesMeta?.indicateurs || []

  const sections = [
    {
      id: 'synthese', group: 'sections', tag: 'SYN', tagColor: '#2277C1', label: 'Synthèse & guide',
      icon: 'bi-shield-check', sub: `${syn.ok ?? 0} ok · ${syn.avertissement ?? 0} avert. · ${syn.critique ?? 0} crit.`,
    },
    {
      id: 'indicateurs-grid', group: 'sections', tag: 'GRD', tagColor: '#1565C0', label: 'Grille indicateurs',
      icon: 'bi-grid-3x3', sub: `${indicateurs.length} carte${indicateurs.length > 1 ? 's' : ''} de surveillance`,
    },
    {
      id: 'declenchees', group: 'sections', tag: 'ALT', tagColor: nbDecl ? '#C62828' : '#2277C1', label: 'Alertes déclenchées',
      icon: 'bi-bell-fill', sub: nbDecl ? `${nbDecl} alerte${nbDecl > 1 ? 's' : ''} active${nbDecl > 1 ? 's' : ''}` : 'Tout conforme',
    },
    {
      id: 'seuils', group: 'sections', tag: 'CFG', tagColor: '#7B1FA2', label: 'Configuration seuils',
      icon: 'bi-sliders', sub: alertesMeta?.seuils_vides ? 'Seuils à initialiser' : 'Modifier les paliers',
    },
  ]

  const parInd = indicateurs.map(ind => {
    const n = NIVEAU_ALERTE[ind.niveau] || NIVEAU_ALERTE.non_configure
    return {
      id: `ind-${ind.indicateur}`,
      group: 'indicateurs',
      tag: 'IND',
      tagColor: n.color,
      label: ind.libelle,
      icon: ind.icone || 'bi-speedometer2',
      sub: `${ind.valeur}${ind.unite} · ${n.label}`,
      indicateur: ind,
    }
  })

  return [...sections, ...parInd]
}

function AlertesSyntheseWidget({
  alertesMeta, showGuideAlertes, setShowGuideAlertes, formationId, secretariatId,
}) {
  return (
    <div style={{
      background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 50%, #f4f7fb 100%)',
      border: '1px solid #e2e8f0', borderRadius: 12, padding: '1rem 1.15rem', marginBottom: '1rem',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: '#1e293b' }}>
            <i className="bi bi-shield-check me-2" style={{ color: 'var(--navy)' }}/>
            Surveillance des indicateurs
          </h3>
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.78rem', color: '#64748b', maxWidth: 560 }}>
            Les alertes comparent les KPIs en temps réel aux seuils INJS.
            {(formationId || secretariatId)
              ? ' Filtre actif appliqué aux valeurs ci-dessous.'
              : ' Vue globale — utilisez les filtres formation / secrétariat pour affiner.'}
          </p>
        </div>
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setShowGuideAlertes(v => !v)}>
          <i className={`bi ${showGuideAlertes ? 'bi-chevron-up' : 'bi-chevron-down'} me-1`}/>
          {showGuideAlertes ? 'Masquer le guide' : 'Comment lire les alertes ?'}
        </button>
      </div>

      {showGuideAlertes && (
        <div style={{
          marginTop: '0.85rem', display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.5rem',
        }}>
          {[
            { icon: 'bi-check-circle-fill', col: '#2277C1', titre: 'Conforme', texte: 'La valeur respecte les seuils définis.' },
            { icon: 'bi-exclamation-triangle-fill', col: '#F5B100', titre: 'Avertissement', texte: 'Seuil d\'attention atteint — surveiller la tendance.' },
            { icon: 'bi-exclamation-octagon-fill', col: '#C62828', titre: 'Critique', texte: 'Action corrective recommandée rapidement.' },
            { icon: 'bi-sliders', col: '#1565C0', titre: 'Seuils', texte: '⚠ = premier palier · 🔴 = palier critique.' },
          ].map((g, i) => (
            <div key={i} style={{
              background: 'rgba(255,255,255,0.75)', borderRadius: 8, padding: '0.55rem 0.65rem',
              border: '1px solid rgba(255,255,255,0.9)',
            }}>
              <div style={{ fontWeight: 700, fontSize: '0.78rem', color: g.col, marginBottom: '0.15rem' }}>
                <i className={`bi ${g.icon} me-1`}/>{g.titre}
              </div>
              <div style={{ fontSize: '0.72rem', color: '#64748b' }}>{g.texte}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.85rem' }}>
        {[
          { key: 'ok', label: 'Conformes', col: '#2277C1', bg: '#ecf3fd' },
          { key: 'avertissement', label: 'Avertissements', col: '#F5B100', bg: '#fffceb' },
          { key: 'critique', label: 'Critiques', col: '#C62828', bg: '#fff1f2' },
        ].map(p => (
          <div key={p.key} className="stats-synthese-pill" style={{
            flex: '1 1 120px', minWidth: 110, textAlign: 'center', padding: '0.55rem 0.75rem',
            borderRadius: 10, background: p.bg, border: `1px solid ${p.col}33`,
          }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, color: p.col, lineHeight: 1 }}>
              {alertesMeta.synthese?.[p.key] ?? 0}
            </div>
            <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '0.15rem' }}>{p.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function AlertesDeclencheesWidget({ alertes }) {
  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: '1.1rem', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
      <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#1e293b', marginBottom: '0.8rem' }}>
        <i className="bi bi-bell-fill me-1" style={{ color: '#F5B100' }}/>
        Alertes déclenchées
        {alertes?.length > 0 && (
          <span style={{
            marginLeft: '0.4rem', fontSize: '0.72rem', background: '#C62828', color: '#fff',
            borderRadius: 12, padding: '0.1rem 0.45rem', fontWeight: 700,
          }}>{alertes.length}</span>
        )}
      </h4>
      {!alertes?.length ? (
        <div style={{
          textAlign: 'center', padding: '2rem 1rem',
          borderRadius: 10, border: '1px solid #bbd7f7',
          background: 'linear-gradient(180deg, #f0f6fd 0%, #fff 100%)',
        }}>
          <div style={{
            width: 64, height: 64, margin: '0 auto 0.65rem', borderRadius: '50%',
            background: '#2277C118', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <i className="bi bi-check-lg" style={{ fontSize: '2rem', color: '#2277C1' }}/>
          </div>
          <div style={{ fontWeight: 700, color: '#0b478a', fontSize: '0.88rem', marginBottom: '0.25rem' }}>
            Tout est conforme
          </div>
          <div style={{ fontSize: '0.78rem', color: '#64748b' }}>
            Aucune alerte active pour le périmètre sélectionné.
          </div>
        </div>
      ) : alertes.map((a, i) => (
        <div key={i} className={a.niveau === 'critique' ? 'stats-alerte-pulse' : undefined} style={{
          background: a.niveau === 'critique' ? '#fff1f2' : '#fffceb',
          border: `1px solid ${a.niveau === 'critique' ? '#fca5a5' : '#fcdf4d'}`,
          borderRadius: 10, padding: '0.75rem 0.9rem', marginBottom: '0.5rem',
          borderLeft: `4px solid ${a.niveau === 'critique' ? '#C62828' : '#F5B100'}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.35rem' }}>
            <i className={`bi ${a.niveau === 'critique' ? 'bi-exclamation-octagon-fill' : 'bi-exclamation-triangle-fill'}`}
              style={{ color: a.niveau === 'critique' ? '#C62828' : '#F5B100', fontSize: '1.1rem' }}/>
            <b style={{ fontSize: '0.85rem', color: '#1e293b', flex: 1 }}>{a.libelle}</b>
            <NiveauBadge niveau={a.niveau}/>
          </div>
          <div style={{ fontSize: '0.78rem', color: '#64748b', display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
            <span>Valeur : <b style={{ color: '#1e293b', fontSize: '0.95rem' }}>{a.valeur}{a.unite}</b></span>
            <span>Seuil ⚠ : {a.seuil_avertissement}{a.unite}</span>
            <span>Seuil 🔴 : {a.seuil_critique}{a.unite}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function AlertesSeuilsWidget({
  alertesMeta, seuils, seuilsForm, editSeuils, setEditSeuils, setSeuilsForm,
  canValidate, initSeuilsDefaut, initSeuilsLoading, saveSeuils,
}) {
  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: '1.1rem', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.8rem', flexWrap: 'wrap', gap: '0.4rem' }}>
        <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#1e293b', margin: 0 }}>
          <i className="bi bi-sliders me-1" style={{ color: '#1565C0' }}/>
          Configuration des seuils
        </h4>
        <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
          {canValidate && alertesMeta.seuils_vides && (
            <button className="btn btn-sm btn-outline-success" onClick={initSeuilsDefaut} disabled={initSeuilsLoading}>
              <i className="bi bi-magic me-1"/>Init. INJS
            </button>
          )}
          {canValidate && !editSeuils && seuils.length > 0 && (
            <button className="btn btn-sm btn-outline-primary" onClick={() => setEditSeuils(true)}>
              <i className="bi bi-pencil me-1"/>Modifier
            </button>
          )}
        </div>
      </div>

      {seuils.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '1.5rem', color: '#64748b', fontSize: '0.82rem' }}>
          <i className="bi bi-gear-wide-connected" style={{ fontSize: '1.8rem', display: 'block', marginBottom: '0.5rem', color: '#94a3b8' }}/>
          Configurez les seuils pour personnaliser les alertes automatiques.
        </div>
      ) : editSeuils ? (
        <>
          {seuilsForm.map((s, i) => (
            <div key={s.indicateur || s.id} style={{
              borderBottom: '1px solid #f1f5f9', paddingBottom: '0.75rem', marginBottom: '0.75rem',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.35rem' }}>
                <i className={`bi ${s.icone || 'bi-speedometer2'}`} style={{ color: '#1565C0' }}/>
                <p style={{ fontWeight: 600, color: '#334155', fontSize: '0.82rem', margin: 0, flex: 1 }}>{s.libelle}</p>
                <label style={{ fontSize: '0.72rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <input type="checkbox" checked={seuilsForm[i].actif !== false}
                    onChange={e => setSeuilsForm(f => f.map((x, j) => j === i ? { ...x, actif: e.target.checked } : x))}/>
                  Actif
                </label>
              </div>
              {s.aide && <p style={{ fontSize: '0.7rem', color: '#94a3b8', margin: '0 0 0.4rem' }}>{s.aide}</p>}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem' }}>
                <div>
                  <label style={{ fontSize: '0.72rem', color: '#F5B100', fontWeight: 600 }}>⚠ Avertissement</label>
                  <input type="number" className="form-control form-control-sm"
                    value={seuilsForm[i].seuil_avertissement}
                    onChange={e => setSeuilsForm(f => f.map((x, j) => j === i ? { ...x, seuil_avertissement: parseFloat(e.target.value) } : x))}/>
                </div>
                <div>
                  <label style={{ fontSize: '0.72rem', color: '#C62828', fontWeight: 600 }}>🔴 Critique</label>
                  <input type="number" className="form-control form-control-sm"
                    value={seuilsForm[i].seuil_critique}
                    onChange={e => setSeuilsForm(f => f.map((x, j) => j === i ? { ...x, seuil_critique: parseFloat(e.target.value) } : x))}/>
                </div>
              </div>
            </div>
          ))}
          <div style={{ display: 'flex', gap: '0.4rem' }}>
            <button className="btn btn-sm" style={{ background: 'var(--navy)', color: '#fff', border: 'none' }} onClick={saveSeuils}>
              <i className="bi bi-check-lg me-1"/>Enregistrer
            </button>
            <button className="btn btn-sm btn-outline-secondary" onClick={() => { setEditSeuils(false); setSeuilsForm(seuils.map(s => ({ ...s }))) }}>
              Annuler
            </button>
          </div>
        </>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                <th style={{ padding: '0.4rem 0.6rem', color: '#64748b', fontWeight: 600, textAlign: 'left' }}>Indicateur</th>
                <th style={{ padding: '0.4rem 0.6rem', color: '#F5B100', fontWeight: 600, textAlign: 'center' }}>⚠</th>
                <th style={{ padding: '0.4rem 0.6rem', color: '#C62828', fontWeight: 600, textAlign: 'center' }}>🔴</th>
                <th style={{ padding: '0.4rem 0.6rem', color: '#64748b', fontWeight: 600, textAlign: 'center' }}>Actif</th>
              </tr>
            </thead>
            <tbody>
              {seuils.map((s) => {
                const ind = alertesMeta.indicateurs?.find(x => x.indicateur === s.indicateur)
                return (
                  <tr key={s.id || s.indicateur} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '0.45rem 0.6rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <i className={`bi ${s.icone || 'bi-speedometer2'}`} style={{ color: '#64748b' }}/>
                        <span style={{ color: '#334155', fontWeight: 500 }}>{s.libelle}</span>
                        {ind && <NiveauBadge niveau={ind.niveau}/>}
                      </div>
                    </td>
                    <td style={{ textAlign: 'center', padding: '0.45rem 0.6rem', color: '#F5B100', fontWeight: 700 }}>{s.seuil_avertissement}</td>
                    <td style={{ textAlign: 'center', padding: '0.45rem 0.6rem', color: '#C62828', fontWeight: 700 }}>{s.seuil_critique}</td>
                    <td style={{ textAlign: 'center', padding: '0.45rem 0.6rem' }}>
                      {s.actif
                        ? <i className="bi bi-check-circle-fill" style={{ color: '#2277C1' }}/>
                        : <i className="bi bi-dash-circle" style={{ color: '#94a3b8' }}/>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function AlertesEnsemblePanel(props) {
  const { alertesMeta, onSelectWidget, auditeursNotoires, ...rest } = props
  return (
    <div style={{
      background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      overflow: 'hidden', minWidth: 0,
    }}>
      <div style={{
        padding: '0.85rem 1rem', background: 'linear-gradient(135deg, #e8eef6 0%, #f4f7fb 100%)',
        borderBottom: '1px solid #e2e8f0', position: 'sticky', top: 0, zIndex: 2,
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <i className="bi bi-bell me-2" style={{ color: '#F5B100' }}/>
          Alertes — tous les widgets
        </h3>
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>
          Synthèse, cartes de surveillance, alertes actives et configuration des seuils.
        </p>
      </div>
      <div style={{ maxHeight: '62vh', overflowY: 'auto', padding: '1rem' }}>
        <AuditeursNotoiresKpiStrip data={auditeursNotoires}/>
        <div onClick={onSelectWidget ? () => onSelectWidget('synthese') : undefined} role={onSelectWidget ? 'button' : undefined} style={{ cursor: onSelectWidget ? 'pointer' : undefined }}>
          <AlertesSyntheseWidget alertesMeta={alertesMeta} {...rest}/>
        </div>

        {alertesMeta.indicateurs?.length > 0 ? (
          <div
            onClick={onSelectWidget ? () => onSelectWidget('indicateurs-grid') : undefined}
            role={onSelectWidget ? 'button' : undefined}
            style={{ cursor: onSelectWidget ? 'pointer' : undefined, marginBottom: '1rem' }}
          >
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '0.85rem',
            }}>
              {alertesMeta.indicateurs.map(ind => (
                <div
                  key={ind.indicateur}
                  onClick={onSelectWidget ? (e) => { e.stopPropagation(); onSelectWidget(`ind-${ind.indicateur}`) } : undefined}
                  role={onSelectWidget ? 'button' : undefined}
                >
                  <IndicateurSurveillanceCard ind={ind}/>
                </div>
              ))}
            </div>
          </div>
        ) : alertesMeta.seuils_vides ? (
          <div style={{
            textAlign: 'center', padding: '2rem 1rem', marginBottom: '1rem',
            background: '#fff', borderRadius: 12, border: '2px dashed #cbd5e1',
          }}>
            <i className="bi bi-sliders2" style={{ fontSize: '2.5rem', color: '#94a3b8', display: 'block', marginBottom: '0.65rem' }}/>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#334155', marginBottom: '0.35rem' }}>
              Aucun seuil configuré
            </h4>
            <p style={{ fontSize: '0.82rem', color: '#64748b', maxWidth: 420, margin: '0 auto 1rem' }}>
              Initialisez les seuils INJS pour activer la surveillance des 6 indicateurs clés.
            </p>
            {rest.canValidate && (
              <button className="btn btn-sm" style={{ background: 'var(--navy)', color: '#fff', border: 'none' }}
                onClick={rest.initSeuilsDefaut} disabled={rest.initSeuilsLoading}>
                {rest.initSeuilsLoading
                  ? <><span className="spinner-border spinner-border-sm me-1"/>Initialisation…</>
                  : <><i className="bi bi-magic me-1"/>Initialiser les seuils INJS</>}
              </button>
            )}
          </div>
        ) : null}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
          <div onClick={onSelectWidget ? () => onSelectWidget('declenchees') : undefined} role={onSelectWidget ? 'button' : undefined}>
            <AlertesDeclencheesWidget alertes={rest.alertes}/>
          </div>
          <div onClick={onSelectWidget ? () => onSelectWidget('seuils') : undefined} role={onSelectWidget ? 'button' : undefined}>
            <AlertesSeuilsWidget alertesMeta={alertesMeta} {...rest}/>
          </div>
        </div>

        <div style={{ marginTop: '1rem' }}>
          <Card title={AUDITEURS_NOTOIRES.cardTitle} icon="bi-person-x-fill" col="1/-1">
            <AuditeursNotoiresPanel data={auditeursNotoires} maxHeight={280} compact/>
          </Card>
        </div>
      </div>
    </div>
  )
}

function AlertesWidgetDetailPanel({ entry, onGoSeuils, auditeursNotoires, ...props }) {
  const { alertesMeta, alertes, seuils, ...rest } = props

  if (entry.id === 'synthese') {
    return (
      <div style={{ background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)', padding: '1rem', minWidth: 0 }}>
        <AlertesSyntheseWidget alertesMeta={alertesMeta} {...rest}/>
      </div>
    )
  }

  if (entry.id === 'indicateurs-grid') {
    return (
      <div style={{ background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)', padding: '1rem', minWidth: 0 }}>
        <h3 style={{ margin: '0 0 1rem', fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <i className="bi bi-grid-3x3 me-2" style={{ color: '#1565C0' }}/>
          Grille des indicateurs
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '0.85rem' }}>
          {alertesMeta.indicateurs?.map(ind => (
            <IndicateurSurveillanceCard key={ind.indicateur} ind={ind}/>
          ))}
        </div>
      </div>
    )
  }

  if (entry.id === 'declenchees') {
    return (
      <div style={{ background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)', padding: '1rem', minWidth: 0 }}>
        <AuditeursNotoiresKpiStrip data={auditeursNotoires}/>
        <AlertesDeclencheesWidget alertes={alertes}/>
      </div>
    )
  }

  if (entry.id === 'seuils') {
    return <AlertesSeuilsWidget alertesMeta={alertesMeta} seuils={seuils} {...rest}/>
  }

  if (entry.id?.startsWith('ind-') && entry.indicateur) {
    const ind = entry.indicateur
    const seuilRow = seuils?.find(s => s.indicateur === ind.indicateur)
    return (
      <div style={{ background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)', padding: '1rem', minWidth: 0 }}>
        <IndicateurSurveillanceCard ind={ind}/>
        {seuilRow && (
          <div style={{ marginTop: '1rem', padding: '0.75rem', background: '#f8fafc', borderRadius: 8, fontSize: '0.8rem' }}>
            <b style={{ color: '#334155' }}>Seuils configurés :</b>{' '}
            ⚠ {seuilRow.seuil_avertissement}{ind.unite} · 🔴 {seuilRow.seuil_critique}{ind.unite}
            {onGoSeuils && (
              <button type="button" className="btn btn-sm btn-link" style={{ fontSize: '0.78rem' }} onClick={onGoSeuils}>
                Modifier tous les seuils
              </button>
            )}
          </div>
        )}
      </div>
    )
  }

  return <Empty label="Widget non disponible"/>
}

function AlertesStyles() {
  return (
    <style>{`
      @keyframes statsPulse {
        0%, 100% { box-shadow: 0 0 0 0 rgba(198,40,40,0.35); }
        50% { box-shadow: 0 0 0 6px rgba(198,40,40,0); }
      }
      @keyframes statsGaugeGrow {
        from { width: 0; }
      }
      @keyframes statsFadeUp {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
      }
      .stats-alerte-pulse { animation: statsPulse 2s ease-in-out infinite; }
      .stats-gauge-fill { animation: statsGaugeGrow 0.8s ease-out; }
      .stats-ind-card { animation: statsFadeUp 0.45s ease-out both; }
      .stats-ind-critique { animation: statsFadeUp 0.45s ease-out both, statsPulse 2.5s ease-in-out infinite; }
      .stats-ind-card:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.08); }
      .stats-synthese-pill { transition: transform 0.15s ease; }
      .stats-synthese-pill:hover { transform: scale(1.04); }
    `}</style>
  )
}

/** Graphique mensuel 12 mois avec grille, axe Y et libellés français */
function MonthTrendChart({ data, valueKey = 'total', color = '#2277C1', height = 160, unit = '' }) {
  if (!data?.length) return <Empty />
  const max = Math.max(...data.map(d => d[valueKey] || 0), 1)
  const barW = 28
  const gap = 10
  const padL = 36
  const w = padL + data.length * (barW + gap) + 16
  const gridSteps = 4

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width={Math.max(w, 360)} height={height + 44} style={{ display: 'block' }}>
        {[...Array(gridSteps + 1)].map((_, i) => {
          const y = 8 + (i / gridSteps) * (height - 16)
          const val = Math.round(max - (i / gridSteps) * max)
          return (
            <g key={i}>
              <line x1={padL - 4} y1={y} x2={w - 8} y2={y} stroke="#e2e8f0" strokeWidth={1} />
              <text x={padL - 8} y={y + 3} textAnchor="end" fontSize={8} fill="#94a3b8">{val}</text>
            </g>
          )
        })}
        {data.map((d, i) => {
          const v = d[valueKey] || 0
          const bH = v > 0 ? Math.max(6, Math.round((v / max) * (height - 20))) : 0
          const x = padL + i * (barW + gap)
          const y = height - bH
          const hasData = v > 0
          return (
            <g key={i}>
              <rect
                x={x} y={y} width={barW} height={bH || 2} rx={4}
                fill={hasData ? color : '#e2e8f0'}
                opacity={hasData ? 0.88 : 0.5}
              />
              {hasData && (
                <text x={x + barW / 2} y={y - 4} textAnchor="middle" fontSize={9} fill="#1e293b" fontWeight={600}>
                  {v}{unit}
                </text>
              )}
              <text x={x + barW / 2} y={height + 16} textAnchor="middle" fontSize={8} fill="#64748b">
                {formatMoisLabel(d.mois)}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/** Barres empilées présents / absents par mois */
function StackedPresenceChart({ data, height = 160 }) {
  if (!data?.length) return <Empty label="Aucun pointage sur la période" />
  const max = Math.max(...data.map(d => (d.presents || 0) + (d.absents || 0)), 1)
  const barW = 28
  const gap = 10
  const padL = 36
  const w = padL + data.length * (barW + gap) + 16

  return (
    <div>
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '0.5rem', fontSize: '0.75rem' }}>
        <span><span style={{ display: 'inline-block', width: 10, height: 10, background: '#2277C1', borderRadius: 2, marginRight: 4 }} />Présents</span>
        <span><span style={{ display: 'inline-block', width: 10, height: 10, background: '#C62828', borderRadius: 2, marginRight: 4 }} />Absents</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <svg width={Math.max(w, 360)} height={height + 44} style={{ display: 'block' }}>
          {data.map((d, i) => {
            const pres = d.presents || 0
            const abs = d.absents || 0
            const total = pres + abs
            const presH = total ? Math.round((pres / max) * (height - 20)) : 0
            const absH = total ? Math.round((abs / max) * (height - 20)) : 0
            const x = padL + i * (barW + gap)
            const baseY = height
            return (
              <g key={i}>
                {total === 0 ? (
                  <rect x={x} y={baseY - 2} width={barW} height={2} rx={2} fill="#e2e8f0" />
                ) : (
                  <>
                    {absH > 0 && (
                      <rect x={x} y={baseY - absH - presH} width={barW} height={absH} rx={absH && !presH ? 4 : 0} fill="#C62828" opacity={0.85} />
                    )}
                    {presH > 0 && (
                      <rect x={x} y={baseY - presH} width={barW} height={presH} rx={4} fill="#2277C1" opacity={0.88} />
                    )}
                    <text x={x + barW / 2} y={baseY - presH - absH - 4} textAnchor="middle" fontSize={8} fill="#64748b">{total}</text>
                  </>
                )}
                <text x={x + barW / 2} y={height + 16} textAnchor="middle" fontSize={8} fill="#64748b">
                  {formatMoisLabel(d.mois)}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

function TauxBar({ value, small }) {
  const col = value>=70 ? '#2277C1' : value>=40 ? '#F5B100' : '#C62828'
  return (
    <div style={{display:'flex',alignItems:'center',gap:'0.4rem'}}>
      <div style={{flex:1,background:'#f1f5f9',borderRadius:4,height:small?6:9,overflow:'hidden',minWidth:50}}>
        <div style={{width:`${value}%`,height:'100%',background:col,borderRadius:4}}/>
      </div>
      <b style={{fontSize:'0.8rem',color:col,minWidth:38}}>{value}%</b>
    </div>
  )
}

// ── KPI Card ──────────────────────────────────────────────────────────────────
function Kpi({ icon, label, value, color, sub, help }) {
  return (
    <div style={{background:'#fff',borderRadius:12,padding:'1.1rem 1.3rem',display:'flex',alignItems:'center',gap:'0.9rem',boxShadow:'0 1px 4px rgba(0,0,0,0.07)',borderLeft:`4px solid ${color}`}}>
      <div style={{width:42,height:42,borderRadius:'50%',background:color+'1a',display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0}}>
        <i className={`bi ${icon}`} style={{fontSize:'1.2rem',color}}/>
      </div>
      <div>
        <div style={{fontSize:'1.55rem',fontWeight:800,color:'#1e293b',lineHeight:1}}>{value??'—'}</div>
        <div style={{fontSize:'0.77rem',color:'#64748b',marginTop:'0.15rem',display:'flex',alignItems:'center',gap:'0.25rem'}}>
          {label}
          {help && (
            <i className="bi bi-info-circle" title={help} style={{fontSize:'0.72rem',color:'#94a3b8',cursor:'help'}}/>
          )}
        </div>
        {sub && <div style={{fontSize:'0.72rem',color:'#94a3b8'}}>{sub}</div>}
      </div>
    </div>
  )
}

function PedagogieTauxPrincipaux({ ped, auditeursNotoires }) {
  const a = TAUX_PEDAGOGIE.assiduite
  const c = TAUX_PEDAGOGIE.couverture
  const an = auditeursNotoires || ped?.auditeurs_notoires
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
      <Kpi icon="bi-person-check" label={a.label} value={`${a.getValue(ped)}%`} color={a.color} help={a.help}/>
      <Kpi icon="bi-people" label={c.label} value={`${c.getValue(ped)}%`} color={c.color} help={c.help}/>
      {an != null && (
        <Kpi
          icon="bi-person-x-fill"
          label="Absents notoires"
          value={an.total ?? 0}
          color="#C62828"
          sub={`${Number(an.pct || 0).toFixed(1).replace('.', ',')}% des inscrits`}
          help="Inscrit à au moins un module démarré, sans présence enregistrée ou avec motif notoire."
        />
      )}
    </div>
  )
}

function PedagogieTauxGrille({ ped, withBars = false, grid = false }) {
  const items = [
    TAUX_PEDAGOGIE.assiduite,
    TAUX_PEDAGOGIE.absence,
    TAUX_PEDAGOGIE.evenements,
    TAUX_PEDAGOGIE.couverture,
  ]
  return (
    <div style={{
      display: grid ? 'grid' : 'flex',
      gridTemplateColumns: grid ? 'repeat(2, minmax(0, 1fr))' : undefined,
      gap: grid ? '0.75rem' : '1.25rem',
      flexWrap: grid ? undefined : 'wrap',
      justifyContent: grid ? 'stretch' : 'center',
      padding: withBars || grid ? '0.5rem 0' : 0,
    }}>
      {items.map((t) => (
        <div key={t.label} style={{ textAlign: 'center', minWidth: withBars ? 100 : 80 }} title={t.help}>
          <div style={{ fontSize: withBars ? '2rem' : '1.6rem', fontWeight: 800, color: t.color }}>{t.getValue(ped)}%</div>
          <div style={{ fontSize: withBars ? '0.78rem' : '0.72rem', color: '#64748b', fontWeight: withBars ? 600 : 400, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.2rem' }}>
            {t.label}
            <i className="bi bi-info-circle" style={{ fontSize: '0.68rem', color: '#94a3b8', cursor: 'help' }}/>
          </div>
          {withBars && (
            <div style={{ marginTop: '0.35rem' }}><TauxBar value={t.getValue(ped)} small/></div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Chart Card ────────────────────────────────────────────────────────────────
function Card({ title, icon, children, col }) {
  return (
    <div style={{background:'#fff',borderRadius:12,padding:'1.1rem 1.3rem',boxShadow:'0 1px 4px rgba(0,0,0,0.07)',gridColumn:col}}>
      <h4 style={{fontSize:'0.85rem',fontWeight:700,color:'#1e293b',marginBottom:'0.85rem',display:'flex',alignItems:'center',gap:'0.35rem'}}>
        <i className={`bi ${icon}`} style={{color:'var(--navy)'}}/>
        {title}
      </h4>
      {children}
    </div>
  )
}

// ── Composant principal ────────────────────────────────────────────────────────
export default function Statistiques() {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const isSecretariatScoped = isSecretariatScopedRole(user?.role)
  const isEncadrantScoped = user?.role === 'ENCADRANT'
  const secretariatFilterLocked = isSecretariatScoped
  const userLockedSecretariatId = lockedSecretariatId(user)
  const [onglet, setOnglet] = useState(() => (
    isSecretariatScopedRole(user?.role) ? 'point_journalier' : 'overview'
  ))
  const [data, setData] = useState(null)
  const [loadingInitial, setLoadingInitial] = useState(true)
  const [loadingTab, setLoadingTab] = useState(false)
  const [error, setError] = useState(null)
  const [formationId, setFormationId] = useState('')
  const [secretariatId, setSecretariatId] = useState('')
  const effectiveSecretariatId = userLockedSecretariatId || secretariatId
  const [lastRefresh, setLastRefresh] = useState(null)
  const [vhPeriod, setVhPeriod] = useState(() => loadFinancePeriod())
  const [appliedVhPeriod, setAppliedVhPeriod] = useState(() => loadFinancePeriod())
  const appliedPeriodKey = financePeriodKey(appliedVhPeriod)

  const { data: statsMeta } = useStatsMeta({
    formationId: formationId || undefined,
    secretariatId: effectiveSecretariatId || undefined,
    period: appliedVhPeriod,
  })

  useEffect(() => {
    if (!statsMeta) return
    setData(prev => ({
      ...(prev || {}),
      formations_liste: statsMeta.formations_liste,
      secretariats_liste: statsMeta.secretariats_liste,
      filtre_actif: statsMeta.filtre_actif,
    }))
  }, [statsMeta])

  // Secrétariats — onglet dédié
  const [secStats, setSecStats] = useState(null)
  const [loadingSecStats, setLoadingSecStats] = useState(false)
  const [secSelection, setSecSelection] = useState(null)
  const [secDetail, setSecDetail] = useState(null)
  const [loadingSecDetail, setLoadingSecDetail] = useState(false)

  // Historique — navigation par mois
  const [histSelection, setHistSelection] = useState(null)

  // Pédagogique — navigation par périmètre
  const [pedSelection, setPedSelection] = useState(null)

  // Vue d'ensemble — navigation par section
  const [overviewSelection, setOverviewSelection] = useState(null)

  // Alertes — navigation par widget / indicateur
  const [alertesSelection, setAlertesSelection] = useState(null)

  // Seuils alertes
  const [seuils, setSeuils] = useState([])
  const [editSeuils, setEditSeuils] = useState(false)
  const [seuilsForm, setSeuilsForm] = useState([])
  const [alertesMeta, setAlertesMeta] = useState({ indicateurs: [], synthese: {}, seuils_vides: true })
  const [initSeuilsLoading, setInitSeuilsLoading] = useState(false)
  const [showGuideAlertes, setShowGuideAlertes] = useState(true)

  // Point journalier
  const [pjData, setPjData] = useState(null)
  const [pjAllTableaux, setPjAllTableaux] = useState([])
  const [pjDetail, setPjDetail] = useState(null)
  const [loadingPj, setLoadingPj] = useState(false)
  const [loadingPjDetail, setLoadingPjDetail] = useState(false)
  const [pjAnnee, setPjAnnee] = useState(new Date().getFullYear())
  const [pjMois, setPjMois] = useState('')
  const [pjError, setPjError] = useState(null)
  const [pjCategorie, setPjCategorie] = useState('')
  const [pjFormationId, setPjFormationId] = useState('')
  const [pjSelection, setPjSelection] = useState(null)
  const [exportingPj, setExportingPj] = useState(null)

  // Bilans & Rapports — filtres (entête type Point Journalier)
  const [rbAnnee, setRbAnnee] = useState(new Date().getFullYear())
  const [rbMois, setRbMois] = useState('')
  const [rbCategorie, setRbCategorie] = useState('')
  const [rbModuleId, setRbModuleId] = useState('')
  const [rbMatiereKey, setRbMatiereKey] = useState('')
  const [rbFormationId, setRbFormationId] = useState('')
  const [rbPeriode, setRbPeriode] = useState('')
  const [rbCalendrier, setRbCalendrier] = useState('')
  const [rbDimension, setRbDimension] = useState('module')
  const [rbData, setRbData] = useState(null)
  const [rbAllTableaux, setRbAllTableaux] = useState([])
  const [rbJustificatifsText, setRbJustificatifsText] = useState('')
  const [rbSelection, setRbSelection] = useState(null)
  const [rbDetail, setRbDetail] = useState(null)
  const [loadingRb, setLoadingRb] = useState(false)
  const [loadingRbDetail, setLoadingRbDetail] = useState(false)
  const [exportingRb, setExportingRb] = useState(null)
  const [exportingFac, setExportingFac] = useState(null)
  const [facExportMeta, setFacExportMeta] = useState({ justificatifs: {}, difficultes: {} })

  // Bilan FAC — sous-onglet dans Rapports & Bilans
  const [facFormationId, setFacFormationId] = useState('')
  const [facAnnee, setFacAnnee] = useState(new Date().getFullYear())
  const [facCategorie, setFacCategorie] = useState('')
  const [facData, setFacData] = useState(null)
  const [loadingFac, setLoadingFac] = useState(false)
  const [facSousOnglet, setFacSousOnglet] = useState('point_global')
  const [showFacPanel, setShowFacPanel] = useState(false)
  const [facPerimetre, setFacPerimetre] = useState({ grades: [], groupes: [] })
  const [facGradesSelected, setFacGradesSelected] = useState([])
  const [facGroupesSelected, setFacGroupesSelected] = useState([])
  const [loadingFacPerimetre, setLoadingFacPerimetre] = useState(false)
  const [rbView, setRbView] = useState(() => searchParams.get('rbView') || 'bilans')

  const canValidate = VALIDATION_ROLES.includes(user?.role)
  const prevLoadCtx = useRef({ onglet, formationId, secretariatId, appliedPeriodKey })
  const hasDataRef = useRef(false)
  const fetchSeqRef = useRef(0)

  useEffect(() => {
    if (userLockedSecretariatId) {
      setSecretariatId(userLockedSecretariatId)
    }
  }, [userLockedSecretariatId])

  useEffect(() => {
    const v = searchParams.get('rbView')
    if (v === 'workflow' || v === 'bilans') setRbView(v)
    if (searchParams.get('tab') === 'rapports' || searchParams.get('rbView') === 'workflow') {
      setOnglet('rapports')
    }
  }, [searchParams])

  const setRbViewAndUrl = (view) => {
    setRbView(view)
    const next = new URLSearchParams(searchParams)
    if (view === 'bilans') next.delete('rbView')
    else next.set('rbView', view)
    setSearchParams(next, { replace: true })
  }

  useEffect(() => {
    if (isSecretariatScoped && !SECRETARIAT_STATS_TABS.has(onglet)) {
      setOnglet('point_journalier')
    }
  }, [isSecretariatScoped, onglet])

  const fetchData = useCallback(async (sections, { silent = false, initial = false } = {}) => {
    const tabSections = sections?.length ? sections : (TAB_SECTIONS[onglet] || TAB_SECTIONS.overview)
    const allSections = tabSections
    const seq = ++fetchSeqRef.current
    if (!silent) {
      if (initial) setLoadingInitial(true)
      else setLoadingTab(true)
    }
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('sections', allSections.join(','))
      if (formationId) params.set('formation_id', formationId)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      appendPeriodToSearchParams(params, appliedVhPeriod)
      const res = await api.get(`/statistiques/?${params}`)
      if (seq !== fetchSeqRef.current) return
      setData(prev => ({ ...(prev || {}), ...res.data }))
      hasDataRef.current = true
      setLastRefresh(new Date())
    } catch(e) {
      if (seq !== fetchSeqRef.current) return
      if (!silent) setError(e.response?.data?.detail || 'Erreur de chargement.')
    } finally {
      if (seq === fetchSeqRef.current) {
        setLoadingInitial(false)
        setLoadingTab(false)
      }
    }
  }, [formationId, effectiveSecretariatId, onglet, appliedVhPeriod])

  const fetchSecStats = useCallback(async () => {
    setLoadingSecStats(true)
    setSecDetail(null)
    try {
      const params = new URLSearchParams()
      if (formationId) params.set('formation_id', formationId)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      appendPeriodToSearchParams(params, appliedVhPeriod)
      const qs = params.toString()
      const res = await api.get(`/statistiques/secretariats/${qs ? `?${qs}` : ''}`)
      setSecStats(res.data)
      setSecSelection(prev => {
        if (!res.data.secretariats?.length) return null
        if (prev !== null && prev < res.data.secretariats.length) return prev
        return null
      })
    } catch {
      setSecStats(null)
      setSecSelection(null)
    } finally {
      setLoadingSecStats(false)
    }
  }, [formationId, effectiveSecretariatId, appliedVhPeriod])

  const fetchSecDetail = useCallback(async (secId) => {
    if (!secId) {
      setSecDetail(null)
      return
    }
    setLoadingSecDetail(true)
    try {
      const params = new URLSearchParams({
        secretariat_id: String(secId),
        sections: 'kpis,pedagogiques,admin_operationnel,filtre_actif',
      })
      if (formationId) params.set('formation_id', formationId)
      appendPeriodToSearchParams(params, appliedVhPeriod)
      const res = await api.get(`/statistiques/?${params}`)
      setSecDetail(res.data)
    } catch {
      setSecDetail(null)
    } finally {
      setLoadingSecDetail(false)
    }
  }, [formationId, appliedVhPeriod])

  const fetchSeuils = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (formationId) params.set('formation_id', formationId)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      const res = await api.get(`/statistiques/alertes/seuils/?${params}`)
      const payload = Array.isArray(res.data)
        ? { seuils: res.data, indicateurs: [], synthese: {}, seuils_vides: !res.data.length }
        : res.data
      setSeuils(payload.seuils || [])
      setSeuilsForm((payload.seuils || []).map(s => ({ ...s })))
      setAlertesMeta({
        indicateurs: payload.indicateurs || [],
        synthese: payload.synthese || {},
        seuils_vides: payload.seuils_vides ?? !(payload.seuils || []).length,
      })
    } catch {}
    // Le callback ne lit que effectiveSecretariatId (string), pas secretariatId
    // directement : c'est lui qui figure dans les deps (LOT 6, cf. §10.2).
  }, [formationId, effectiveSecretariatId])

  const initSeuilsDefaut = async () => {
    setInitSeuilsLoading(true)
    try {
      const params = new URLSearchParams()
      if (formationId) params.set('formation_id', formationId)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      await api.post(`/statistiques/alertes/seuils/?${params}`)
      await fetchSeuils()
      fetchData()
    } catch (e) {
      alert(e.response?.data?.detail || 'Erreur lors de l\'initialisation des seuils.')
    } finally {
      setInitSeuilsLoading(false)
    }
  }

  const fetchPointJournalier = useCallback(async () => {
    setLoadingPj(true)
    setPjDetail(null)
    setPjAllTableaux([])
    setPjError(null)
    try {
      const params = new URLSearchParams({ annee: String(pjAnnee), tous_tableaux: '1' })
      if (pjMois) params.set('mois', pjMois)
      if (pjCategorie) params.set('categorie', pjCategorie)
      if (pjFormationId) params.set('formation_id', pjFormationId)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      const res = await api.get(`/statistiques/point-journalier/?${params}`)
      setPjData(res.data)
      setPjAllTableaux(res.data.tableaux_complets || [])
      setPjSelection(prev => {
        if (!res.data.tableaux?.length) return null
        if (prev !== null && prev < res.data.tableaux.length) return prev
        return null
      })
    } catch (e) {
      setPjData(null)
      setPjAllTableaux([])
      setPjSelection(null)
      setPjDetail(null)
      setPjError(e.response?.data?.detail || e.message || 'Erreur de chargement.')
    } finally {
      setLoadingPj(false)
    }
    // Le callback ne lit que effectiveSecretariatId (string), pas secretariatId
    // directement : c'est lui qui figure dans les deps (LOT 6, cf. §10.2).
  }, [pjAnnee, pjMois, pjCategorie, pjFormationId, effectiveSecretariatId])

  const fetchPjDetail = useCallback(async (tb) => {
    if (!tb) {
      setPjDetail(null)
      return
    }
    setLoadingPjDetail(true)
    try {
      const params = new URLSearchParams({
        annee: String(pjAnnee),
        detail: '1',
        jour: tb.date,
        formation_id: String(tb.formation_id),
        categorie: tb.categorie || '—',
      })
      if (tb.grade) params.set('grade', tb.grade)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      const res = await api.get(`/statistiques/point-journalier/?${params}`)
      setPjDetail(res.data.tableau)
    } catch {
      setPjDetail(null)
    } finally {
      setLoadingPjDetail(false)
    }
    // Le callback ne lit que effectiveSecretariatId (string), pas secretariatId
    // directement : c'est lui qui figure dans les deps (LOT 6, cf. §10.2).
  }, [pjAnnee, effectiveSecretariatId])

  const downloadPointJournalier = async (format) => {
    setExportingPj(format)
    try {
      const params = new URLSearchParams({ export: format, annee: String(pjAnnee) })
      if (pjMois) params.set('mois', pjMois)
      if (pjCategorie) params.set('categorie', pjCategorie)
      if (pjFormationId) params.set('formation_id', pjFormationId)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      if (pjSelection !== null && pjData?.tableaux?.[pjSelection]) {
        const tb = pjData.tableaux[pjSelection]
        params.set('jour', tb.date)
        params.set('formation_id', String(tb.formation_id))
        if (tb.categorie) params.set('categorie', tb.categorie)
        if (tb.grade) params.set('grade', tb.grade)
      }
      const { blob, fileName } = await api.getBlob(`/statistiques/point-journalier-export/?${params}`)
      const ext = format === 'pdf' ? 'pdf' : format === 'docx' ? 'docx' : 'xlsx'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const moisPart = pjMois ? `_M${pjMois}` : '_annuel'
      a.download = fileName || `POINT_JOURNALIER_${pjAnnee}${moisPart}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      const detail = e.response?.data?.detail
      alert(detail || e.message || 'Erreur lors du téléchargement.')
    } finally {
      setExportingPj(null)
    }
  }

  const fetchBilans = useCallback(async () => {
    setLoadingRb(true)
    setRbDetail(null)
    setRbAllTableaux([])
    try {
      const effFormation = rbFormationId || formationId
      const params = new URLSearchParams({
        annee: String(rbAnnee),
        dimension: rbDimension,
        tous_tableaux: '1',
      })
      if (rbMois) params.set('mois', rbMois)
      if (rbCategorie) params.set('categorie', rbCategorie)
      if (rbDimension === 'matiere') {
        const mk = rbParseMatiereKey(rbMatiereKey)
        if (mk.ref_module_id) params.set('ref_module_id', String(mk.ref_module_id))
      } else if (rbModuleId) {
        params.set('module_id', rbModuleId)
      }
      if (effFormation) params.set('formation_id', effFormation)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      if (rbPeriode) params.set('periode', rbPeriode)
      if (rbCalendrier) params.set('calendrier', rbCalendrier)
      const res = await api.get(`/statistiques/bilans/?${params}`)
      setRbData(res.data)
      setRbAllTableaux(res.data.tableaux_complets || [])
      setRbSelection(prev => {
        if (!res.data.bilans?.length) return null
        if (prev !== null && prev < res.data.bilans.length) return prev
        return null
      })
    } catch {
      setRbData(null)
      setRbAllTableaux([])
      setRbSelection(null)
    } finally {
      setLoadingRb(false)
    }
    // Le callback ne lit que effectiveSecretariatId (string), pas secretariatId
    // directement : c'est lui qui figure dans les deps (LOT 6, cf. §10.2).
  }, [rbAnnee, rbMois, rbCategorie, rbModuleId, rbMatiereKey, rbFormationId, rbPeriode, rbCalendrier, rbDimension, formationId, effectiveSecretariatId])

  const fetchFacPerimetre = useCallback(async () => {
    const effFormation = facFormationId || formationId
    if (!effFormation) {
      setFacPerimetre({ grades: [], groupes: [] })
      setFacGradesSelected([])
      setFacGroupesSelected([])
      return
    }
    setLoadingFacPerimetre(true)
    try {
      const params = new URLSearchParams({ formation_id: effFormation })
      if (facCategorie) params.set('categorie', facCategorie)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      const res = await api.get(`/statistiques/bilan-fac/perimetre/?${params}`)
      const grades = res.data?.grades || []
      const groupes = res.data?.groupes || []
      setFacPerimetre({ grades, groupes })
      setFacGradesSelected(grades)
      setFacGroupesSelected(groupes.map(g => g.id))
    } catch {
      setFacPerimetre({ grades: [], groupes: [] })
      setFacGradesSelected([])
      setFacGroupesSelected([])
    } finally {
      setLoadingFacPerimetre(false)
    }
  }, [facFormationId, facCategorie, formationId, effectiveSecretariatId])

  useEffect(() => {
    if (!showFacPanel) return
    fetchFacPerimetre()
  }, [showFacPanel, fetchFacPerimetre])

  const facGroupesVisibles = (facPerimetre.groupes || []).filter(
    g => facGradesSelected.includes(g.grade),
  )

  useEffect(() => {
    const visibleIds = new Set(facGroupesVisibles.map(g => g.id))
    setFacGroupesSelected(prev => prev.filter(id => visibleIds.has(id)))
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [facGradesSelected.join(','), facPerimetre.groupes.length])

  const fetchBilanFac = useCallback(async () => {
    const effFormation = facFormationId || formationId
    if (!effFormation) return
    if (!facGradesSelected.length) return
    setLoadingFac(true)
    try {
      const params = new URLSearchParams({ formation_id: effFormation, annee: String(facAnnee) })
      if (facCategorie) params.set('categorie', facCategorie)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      const allGrades = facPerimetre.grades || []
      const allGroupeIds = facGroupesVisibles.map(g => g.id)
      if (facGradesSelected.length < allGrades.length) {
        params.set('grades', facGradesSelected.join(','))
      }
      if (
        allGroupeIds.length > 0
        && facGroupesSelected.length < allGroupeIds.length
      ) {
        params.set('groupes', facGroupesSelected.join(','))
      }
      const res = await api.get(`/statistiques/bilan-fac/?${params}`)
      setFacData(res.data)
    } catch {
      setFacData(null)
    } finally {
      setLoadingFac(false)
    }
  }, [
    facFormationId, facAnnee, facCategorie, formationId, effectiveSecretariatId,
    facGradesSelected, facGroupesSelected, facPerimetre.grades, facGroupesVisibles,
  ])

  const fetchRbDetail = useCallback(async (bilan) => {
    if (!bilan) {
      setRbDetail(null)
      return
    }
    if (bilan.dimension === 'module' && !bilan.module_id) {
      setRbDetail(null)
      return
    }
    if (bilan.dimension === 'formation' && !bilan.formation_id) {
      setRbDetail(null)
      return
    }
    if (bilan.dimension === 'categorie' && (!bilan.categorie || bilan.categorie === '—')) {
      setRbDetail(null)
      return
    }
    if (bilan.dimension === 'matiere' && !bilan.formation_id) {
      setRbDetail(null)
      return
    }
    if (!['module', 'matiere', 'formation', 'categorie'].includes(bilan.dimension)) {
      setRbDetail(null)
      return
    }
    setLoadingRbDetail(true)
    try {
      const effFormation = rbFormationId || formationId
      const params = new URLSearchParams({
        annee: String(rbAnnee),
        detail: '1',
        dimension: bilan.dimension,
      })
      if (bilan.module_id) params.set('module_id', String(bilan.module_id))
      if (bilan.formation_id) params.set('formation_id', String(bilan.formation_id))
      else if (effFormation) params.set('formation_id', effFormation)
      if (bilan.dimension === 'matiere') {
        if (bilan.ref_module_id) params.set('ref_module_id', String(bilan.ref_module_id))
        if (bilan.matiere_intitule) params.set('matiere_intitule', bilan.matiere_intitule)
      }
      if (rbMois) params.set('mois', rbMois)
      const cat = (bilan.categorie && bilan.categorie !== '—') ? bilan.categorie : rbCategorie
      if (cat) params.set('categorie', cat)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      if (rbPeriode) params.set('periode', rbPeriode)
      if (rbCalendrier) params.set('calendrier', rbCalendrier)
      const res = await api.get(`/statistiques/bilans/?${params}`)
      setRbDetail(res.data.tableau)
    } catch {
      setRbDetail(null)
    } finally {
      setLoadingRbDetail(false)
    }
    // Le callback ne lit que effectiveSecretariatId (string), pas secretariatId
    // directement : c'est lui qui figure dans les deps (LOT 6, cf. §10.2).
  }, [rbAnnee, rbMois, rbCategorie, rbFormationId, rbPeriode, rbCalendrier, formationId, effectiveSecretariatId])

  const downloadBilanExport = async (format) => {
    setExportingRb(format)
    try {
      const effFormation = rbFormationId || formationId
      const params = new URLSearchParams({ export: format, annee: String(rbAnnee), dimension: rbDimension })
      if (rbMois) params.set('mois', rbMois)
      if (rbCategorie) params.set('categorie', rbCategorie)
      if (rbDimension === 'matiere') {
        const mk = rbParseMatiereKey(rbMatiereKey)
        if (mk.ref_module_id) params.set('ref_module_id', String(mk.ref_module_id))
      } else if (rbModuleId) {
        params.set('module_id', rbModuleId)
      }
      if (effFormation) params.set('formation_id', effFormation)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      if (rbPeriode) params.set('periode', rbPeriode)
      if (rbCalendrier) params.set('calendrier', rbCalendrier)
      const bilan = rbSelection !== null && rbData?.bilans?.[rbSelection] ? rbData.bilans[rbSelection] : null
      if (bilan?.module_id) params.set('module_id', String(bilan.module_id))
      if (bilan?.formation_id) params.set('formation_id', String(bilan.formation_id))
      if (bilan?.ref_module_id) params.set('ref_module_id', String(bilan.ref_module_id))
      if (bilan?.matiere_intitule) params.set('matiere_intitule', bilan.matiere_intitule)
      if (bilan?.categorie && bilan.categorie !== '—') params.set('categorie', bilan.categorie)
      if (rbJustificatifsText.trim()) params.set('justificatifs', rbJustificatifsText.trim())
      const { blob, fileName } = await api.getBlob(`/statistiques/bilans-export/?${params}`)
      const ext = format === 'pdf' ? 'pdf' : format === 'docx' ? 'docx' : 'xlsx'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName || `BILANS_${rbAnnee}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      const detail = e.response?.data?.detail
      alert(detail || e.message || 'Erreur lors du téléchargement.')
    } finally {
      setExportingRb(null)
    }
  }

  const downloadBilanFac = async (format) => {
    const effFormation = facFormationId || formationId
    if (!effFormation || !facData) return
    setExportingFac(format)
    try {
      const params = new URLSearchParams({
        export: format,
        formation_id: effFormation,
        annee: String(facAnnee),
      })
      if (facCategorie) params.set('categorie', facCategorie)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      const allGrades = facPerimetre.grades || []
      const allGroupeIds = facGroupesVisibles.map(g => g.id)
      if (facGradesSelected.length < allGrades.length) {
        params.set('grades', facGradesSelected.join(','))
      }
      if (allGroupeIds.length > 0 && facGroupesSelected.length < allGroupeIds.length) {
        params.set('groupes', facGroupesSelected.join(','))
      }
      const { justificatifs, difficultes } = facExportMeta
      if (
        Object.keys(justificatifs || {}).length
        || Object.keys(difficultes || {}).length
      ) {
        params.set('meta', JSON.stringify({ justificatifs, difficultes }))
      }
      const { blob, fileName } = await api.getBlob(`/statistiques/bilan-fac-export/?${params}`)
      const ext = format === 'pdf' ? 'pdf' : format === 'docx' ? 'docx' : 'xlsx'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName || `BILAN_FAC_${facAnnee}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      const detail = e.response?.data?.detail
      alert(detail || e.message || 'Erreur lors du téléchargement.')
    } finally {
      setExportingFac(null)
    }
  }

  const handleApplyVhPeriod = useCallback((periodOverride) => {
    const p = periodOverride ?? vhPeriod
    saveFinancePeriod(p)
    setVhPeriod(p)
    setAppliedVhPeriod({ ...p })
    fetchSeqRef.current += 1
    setData(prev => (prev ? {
      ...prev,
      kpis: undefined,
      periode: undefined,
      pedagogiques: undefined,
      admin_operationnel: undefined,
      alertes: undefined,
      alertes_overview: undefined,
    } : prev))
  }, [vhPeriod])

  const handleRefreshAll = () => {
    fetchData(TAB_SECTIONS[onglet] || TAB_SECTIONS.overview)
    if (onglet === 'point_journalier') fetchPointJournalier()
    if (onglet === 'rapports') fetchBilans()
    if (onglet === 'secretariats') fetchSecStats()
    if (onglet === 'alertes') fetchSeuils()
  }

  useEffect(() => {
    const prev = prevLoadCtx.current
    const ongletChanged = prev.onglet !== onglet
    const filtreChanged = prev.formationId !== formationId
      || prev.secretariatId !== secretariatId
      || prev.appliedPeriodKey !== appliedPeriodKey
    prevLoadCtx.current = { onglet, formationId, secretariatId, appliedPeriodKey }

    if (filtreChanged && hasDataRef.current) {
      fetchSeqRef.current += 1
      setData(d => (d ? {
        ...d,
        kpis: undefined,
        periode: undefined,
        pedagogiques: undefined,
        admin_operationnel: undefined,
        alertes: undefined,
        alertes_overview: undefined,
      } : d))
    }

    const sections = TAB_SECTIONS[onglet] || TAB_SECTIONS.overview
    const isFirst = !hasDataRef.current
    fetchData(sections, {
      initial: isFirst,
      silent: !isFirst && ongletChanged && !filtreChanged,
    })
  }, [formationId, secretariatId, onglet, appliedPeriodKey, fetchData])

  useEffect(() => {
    setHistSelection(null)
    setPedSelection(null)
    setOverviewSelection(null)
    setAlertesSelection(null)
  }, [formationId, secretariatId])

  useEffect(() => {
    if (onglet === 'alertes') fetchSeuils()
    if (onglet === 'secretariats') fetchSecStats()
  }, [onglet, appliedPeriodKey, formationId, secretariatId, fetchSeuils, fetchSecStats])

  useEffect(() => {
    if (onglet !== 'secretariats' || secSelection === null || !secStats?.secretariats?.length) return
    fetchSecDetail(secStats.secretariats[secSelection].secretariat_id)
  }, [onglet, secSelection, secStats, fetchSecDetail])

  useEffect(() => {
    if (onglet !== 'secretariats' || !secretariatId || !secStats?.secretariats?.length) return
    const idx = secStats.secretariats.findIndex(s => String(s.secretariat_id) === String(secretariatId))
    if (idx >= 0) setSecSelection(idx)
  }, [onglet, secretariatId, secStats])

  useEffect(() => {
    if (data?.filtre_actif?.scope_locked && data.filtre_actif.secretariat_id) {
      setSecretariatId(String(data.filtre_actif.secretariat_id))
    }
  }, [data?.filtre_actif?.scope_locked, data?.filtre_actif?.secretariat_id])

  useEffect(() => {
    if (onglet !== 'point_journalier') return
    fetchPointJournalier()
  }, [onglet, pjAnnee, pjMois, pjCategorie, pjFormationId, secretariatId, fetchPointJournalier])

  useEffect(() => {
    setRbJustificatifsText('')
  }, [rbSelection, rbAnnee, rbMois, rbFormationId, rbPeriode, rbCalendrier, rbDimension])

  useEffect(() => {
    if (onglet !== 'rapports') return
    fetchBilans()
  }, [onglet, rbAnnee, rbMois, rbCategorie, rbModuleId, rbMatiereKey, rbFormationId, rbPeriode, rbCalendrier, rbDimension, formationId, secretariatId, fetchBilans])

  useEffect(() => {
    if (onglet !== 'rapports' || rbSelection === null || !rbData?.bilans?.length) return
    const bilan = rbData.bilans[rbSelection]
    const cached = rbAllTableaux.find(t => t.bilan_id === bilan.id)
    if (cached?.tableau) {
      setRbDetail(cached.tableau)
      return
    }
    fetchRbDetail(bilan)
  }, [onglet, rbSelection, rbData, rbAllTableaux, fetchRbDetail])

  useEffect(() => {
    if (onglet !== 'point_journalier' || pjSelection === null || !pjData?.tableaux?.length) return
    const meta = pjData.tableaux[pjSelection]
    const cached = pjAllTableaux.find(t => t.tableau_id === meta.id)
    if (cached?.tableau) {
      setPjDetail(cached.tableau)
      return
    }
    fetchPjDetail(meta)
  }, [onglet, pjSelection, pjData, pjAllTableaux, fetchPjDetail])

  const saveSeuils = async () => {
    try {
      const params = new URLSearchParams()
      if (formationId) params.set('formation_id', formationId)
      if (effectiveSecretariatId) params.set('secretariat_id', effectiveSecretariatId)
      await api.put(`/statistiques/alertes/seuils/?${params}`, seuilsForm)
      setEditSeuils(false)
      await fetchSeuils()
      fetchData()
    } catch(e) {
      alert(e.response?.data?.detail || 'Erreur lors de la sauvegarde.')
    }
  }

  // ── Onglets nav ──────────────────────────────────────────────────────────
  const onglets = [
    {id:'overview',      icon:'bi-speedometer2',       label:'Vue d\'ensemble'},
    {id:'pedagogy',      icon:'bi-mortarboard',         label:'Pédagogique'},
    {id:'admin',         icon:'bi-people',               label:'Administratif'},
    {id:'history',       icon:'bi-graph-up',             label:'Historique'},
    {id:'secretariats',  icon:'bi-building',             label:'Secrétariats'},
    {id:'rapports',      icon:'bi-file-earmark-text',    label:'Rapports & Bilans'},
    {id:'point_journalier', icon:'bi-calendar2-check',   label:'Point Journalier'},
    {id:'alertes',       icon:'bi-bell',                 label:'Alertes'},
  ]
  const visibleOnglets = isSecretariatScoped
    ? onglets.filter(o => SECRETARIAT_STATS_TABS.has(o.id))
    : onglets

  if (loadingInitial && !data) return (
    <div style={{display:'flex',alignItems:'center',justifyContent:'center',minHeight:300,gap:'0.75rem',color:'#64748b'}}>
      <div className="spinner"/><span>Chargement des statistiques…</span>
    </div>
  )
  if (error && !data) return (
    <div style={{background:'#fff3f3',border:'1px solid #fca5a5',borderRadius:10,padding:'1.5rem',color:'#C62828',maxWidth:500}}>
      <i className="bi bi-exclamation-triangle me-2"/>{error}
      <br/><button className="btn btn-sm btn-outline-danger" style={{marginTop:'0.75rem'}} onClick={() => fetchData(TAB_SECTIONS[onglet] || TAB_SECTIONS.overview, { initial: true })}>Réessayer</button>
    </div>
  )

  const { kpis, pedagogiques, admin_operationnel: adm, historique, alertes, alertes_overview, formations_liste, secretariats_liste } = data || {}
  const secretariatScopeLabel = (secretariats_liste || []).find(
    s => String(s.id) === String(effectiveSecretariatId),
  )?.nom || user?.secretariat_nom || 'Mon secrétariat'
  const auditeursNotoires = adm?.auditeurs_notoires
    || pedagogiques?.auditeurs_notoires
    || secDetail?.admin_operationnel?.auditeurs_notoires
    || secStats?.auditeurs_notoires
    || null

  const tabLoading = loadingTab && (
    <div style={{display:'flex',alignItems:'center',gap:'0.4rem',fontSize:'0.78rem',color:'#64748b',marginBottom:'0.65rem'}}>
      <div className="spinner" style={{width:14,height:14}}/>Actualisation…
    </div>
  )

  const TabSpinner = ({ label = 'Chargement…' }) => (
    <div style={{display:'flex',alignItems:'center',gap:'0.5rem',color:'#64748b',padding:'2rem',background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)'}}>
      <div className="spinner"/>{label}
    </div>
  )

  return (
    <div>
      <AlertesStyles />
      {/* ── En-tête ─────────────────────────────────────── */}
      <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',marginBottom:'1.2rem',flexWrap:'wrap',gap:'0.75rem'}}>
        <div>
          <h2 style={{margin:0,fontWeight:800,color:'#1e293b',fontSize:'1.3rem'}}>
            <i className="bi bi-bar-chart-line me-2" style={{color:'var(--navy)'}}/>
            Statistiques & Bilans
          </h2>
          {lastRefresh && (
            <p style={{margin:0,fontSize:'0.73rem',color:'#94a3b8',marginTop:'0.1rem'}}>
              Mis à jour le {lastRefresh.toLocaleString('fr-FR')}
            </p>
          )}
        </div>
        <div style={{display:'flex',gap:'0.5rem',alignItems:'center',flexWrap:'wrap'}}>
          <select
            className="form-select form-select-sm"
            value={formationId}
            onChange={e => { setFormationId(e.target.value) }}
            style={{minWidth:180,maxWidth:240}}
          >
            <option value="">Toutes les formations</option>
            {(formations_liste||[]).map(f => (
              <option key={f.id} value={f.id}>{f.formation}</option>
            ))}
          </select>
          {!secretariatFilterLocked && (
            <select
              className="form-select form-select-sm"
              value={secretariatId}
              onChange={e => { setSecretariatId(e.target.value) }}
              style={{minWidth:170,maxWidth:220}}
              disabled={isEncadrantScoped && (secretariats_liste || []).length <= 1}
            >
              <option value="">Tous les secrétariats</option>
              {(secretariats_liste||[]).map(s => (
                <option key={s.id} value={s.id}>{s.nom}</option>
              ))}
            </select>
          )}
          {secretariatFilterLocked && (secretariats_liste||[]).length > 0 && (
            <span className="badge bg-light text-dark border" style={{fontSize:'0.78rem',padding:'0.45rem 0.65rem'}}>
              <i className="bi bi-building me-1"/>
              {(secretariats_liste||[])[0]?.nom || user?.secretariat_nom || 'Mon secrétariat'}
            </span>
          )}
          {(formationId || (!secretariatFilterLocked && secretariatId)) && (
            <button
              className="btn btn-sm btn-outline-danger"
              onClick={() => {
                setFormationId('')
                if (!secretariatFilterLocked) setSecretariatId('')
              }}
              title="Effacer les filtres"
            >
              <i className="bi bi-x-lg"/>
            </button>
          )}
          <button className="btn btn-sm btn-outline-secondary" onClick={handleRefreshAll} disabled={loadingInitial || loadingTab}>
            <i className="bi bi-arrow-clockwise me-1"/>Actualiser
          </button>
        </div>
      </div>

      {VH_PERIOD_TABS.has(onglet) && (
      <div className="finance-filter-panel" style={{ marginBottom: '1rem' }}>
        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#64748b', marginBottom: '0.5rem', letterSpacing: '0.04em' }}>
          PÉRIODE — INDICATEURS CLÉS
        </div>
        <div className="finance-filter-panel-inner">
          <FinancePeriodFilter
            period={vhPeriod}
            onChange={setVhPeriod}
            onApply={handleApplyVhPeriod}
            applying={loadingInitial || loadingTab || loadingSecStats}
            embedded
            autoApplyOnSelect
          />
        </div>
        {isPeriodWhollyFuture(appliedVhPeriod) && (
          <div style={{
            marginTop: '0.65rem', padding: '0.55rem 0.75rem', borderRadius: 8,
            background: '#fffceb', border: '1px solid #fcdf4d', color: '#92660e', fontSize: '0.82rem',
          }}>
            <i className="bi bi-info-circle me-1"/>
            Cette période n&apos;a pas encore commencé — indicateurs clés et séances comptabilisables à 0
            (volume horaire et présences inclus).
            {(() => {
              const { annee, q } = currentTrimestreParts()
              return (
                <button
                  type="button"
                  className="btn btn-link btn-sm p-0 ms-1 align-baseline"
                  style={{ fontSize: '0.82rem', verticalAlign: 'baseline' }}
                  onClick={() => {
                    const next = {
                      ...appliedVhPeriod,
                      preset: 'trimestre',
                      trimestreAnnee: annee,
                      trimestreQ: q,
                      trimestre: `${annee}-Q${q}`,
                    }
                    setVhPeriod(next)
                    saveFinancePeriod(next)
                    setAppliedVhPeriod({ ...next })
                  }}
                >
                  Voir le trimestre en cours (T{q})
                </button>
              )
            })()}
          </div>
        )}
        {!isPeriodWhollyFuture(appliedVhPeriod)
          && data?.periode?.filtre_actif
          && data?.kpis?.sessions_terminees === 0
          && appliedVhPeriod?.preset !== 'tout' && (
          <div style={{
            marginTop: '0.65rem', padding: '0.55rem 0.75rem', borderRadius: 8,
            background: '#f8fafc', border: '1px solid #e2e8f0', color: '#64748b', fontSize: '0.82rem',
          }}>
            <i className="bi bi-calendar-x me-1"/>
            Aucune séance comptabilisable sur {data.periode.label || 'cette période'}
            {data.periode.periode_label ? ` (${data.periode.periode_label})` : ''}.
          </div>
        )}
        {data?.periode?.label && (
          <div className="finance-period-badge">
            <i className="bi bi-calendar-check"></i>
            <div>
              <strong>{data.periode.label}</strong>
              {data.periode.periode_label && (
                <span className="ms-1">— {data.periode.periode_label}</span>
              )}
            </div>
          </div>
        )}
      </div>
      )}

      {error && data && (
        <div style={{background:'#fff3f3',border:'1px solid #fca5a5',borderRadius:8,padding:'0.65rem 0.85rem',color:'#C62828',fontSize:'0.82rem',marginBottom:'0.75rem'}}>
          <i className="bi bi-exclamation-triangle me-1"/>{error}
        </div>
      )}

      {tabLoading}

      {/* ── Navigation onglets ─────────────────────────── */}
      <div style={{display:'flex',gap:'0.25rem',marginBottom:'1.2rem',borderBottom:'2px solid #e2e8f0',overflowX:'auto',paddingBottom:0}}>
        {visibleOnglets.map(o => (
          <button key={o.id} onClick={() => setOnglet(o.id)} style={{
            background:'none',border:'none',cursor:'pointer',padding:'0.55rem 0.9rem',
            fontSize:'0.82rem',fontWeight:onglet===o.id?700:500,
            color:onglet===o.id?'#001a33':'#64748b',
            borderBottom:onglet===o.id?'2px solid #001a33':'2px solid transparent',
            marginBottom:'-2px',whiteSpace:'nowrap',display:'flex',alignItems:'center',gap:'0.3rem',
          }}>
            <i className={`bi ${o.icon}`}/>{o.label}
          </button>
        ))}
      </div>

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* Onglet 1 — Vue d'ensemble                                            */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {onglet==='overview' && (() => {
        const overviewSections = buildOverviewSections(alertes_overview || alertes)
        const overviewSection = overviewSelection
          ? overviewSections.find(s => s.id === overviewSelection)
          : null
        return (
        <>
          <div style={{display:'flex',flexWrap:'wrap',gap:'0.5rem',alignItems:'center',marginBottom:'0.75rem'}}>
            <span style={{fontSize:'0.78rem',color:'#64748b'}}>
              Tableau de bord synthétique
              {formationId && <> · <b>{(formations_liste||[]).find(f => String(f.id) === formationId)?.formation}</b></>}
              {secretariatId && <> · <b>{(secretariats_liste||[]).find(s => String(s.id) === secretariatId)?.nom}</b></>}
            </span>
            <div style={{marginLeft:'auto'}}>
              <button className="btn btn-sm btn-outline-secondary" onClick={() => fetchData(TAB_SECTIONS.overview)} disabled={loadingTab}>
                <i className="bi bi-arrow-clockwise me-1"/>Actualiser
              </button>
            </div>
          </div>

          {loadingInitial && !data ? <TabSpinner label="Chargement de la vue d'ensemble…"/> : (
          <div style={{display:'grid',gridTemplateColumns:'minmax(200px,260px) 1fr',gap:'1rem',alignItems:'start',marginBottom:'1.2rem'}}>
            <div style={{background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)',overflow:'hidden',maxHeight:'70vh',overflowY:'auto'}}>
              <div style={{padding:'0.65rem 0.85rem',background:'#f8fafc',borderBottom:'1px solid #e2e8f0',fontSize:'0.78rem',color:'#64748b',fontWeight:600}}>
                {overviewSections.length} section{overviewSections.length > 1 ? 's' : ''}
              </div>
              <button
                type="button"
                onClick={()=>setOverviewSelection(null)}
                style={{
                  display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                  padding:'0.55rem 0.85rem', fontSize:'0.78rem', fontWeight:700,
                  background: overviewSelection === null ? '#e0f2fe' : '#fff',
                  borderBottom:'2px solid #e2e8f0', color: overviewSelection === null ? '#0369a1' : '#475569',
                }}
              >
                <i className="bi bi-grid-3x3-gap me-1"/>
                Tous les indicateurs
              </button>
              {overviewSections.map(section => (
                <button
                  key={section.id}
                  type="button"
                  onClick={()=>setOverviewSelection(section.id)}
                  style={{
                    display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                    padding:'0.55rem 0.85rem', fontSize:'0.78rem',
                    background: overviewSelection===section.id ? '#e8eef6' : '#fff',
                    borderBottom:'1px solid #f1f5f9',
                  }}
                >
                  <div style={{fontWeight:700, color:'#1e293b', marginBottom:'0.1rem'}}>
                    <i className={`bi ${section.icon} me-1`} style={{color:section.tagColor}}/>
                    <span style={{
                      background:`${section.tagColor}18`, color:section.tagColor, borderRadius:4,
                      padding:'0.05rem 0.35rem', marginRight:'0.3rem', fontSize:'0.68rem',
                    }}>{section.tag}</span>
                    {section.label}
                  </div>
                  <div style={{color:'#94a3b8', fontSize:'0.72rem'}}>{section.sub}</div>
                </button>
              ))}
            </div>

            {overviewSelection === null ? (
              !kpis ? (
                <TabSpinner label="Mise à jour des indicateurs pour la période sélectionnée…"/>
              ) : (
              <VueEnsemblePanel
                key={appliedPeriodKey}
                kpis={kpis}
                periode={data?.periode}
                loading={loadingTab}
                pedagogiques={pedagogiques}
                adm={adm}
                alertesOverview={alertes_overview || alertes}
                onSelectSection={setOverviewSelection}
                auditeursNotoires={auditeursNotoires}
              />
              )
            ) : overviewSection ? (
              !kpis ? (
                <TabSpinner label="Mise à jour des indicateurs pour la période sélectionnée…"/>
              ) : (
              <div style={{ minWidth: 0 }}>
                <button
                  type="button"
                  className="btn btn-sm btn-outline-secondary mb-2"
                  onClick={()=>setOverviewSelection(null)}
                >
                  <i className="bi bi-grid-3x3-gap me-1"/>Voir tous les indicateurs
                </button>
                <VueOverviewDetailPanel
                  key={appliedPeriodKey}
                  sectionId={overviewSection.id}
                  kpis={kpis}
                  periode={data?.periode}
                  pedagogiques={pedagogiques}
                  adm={adm}
                  alertesOverview={alertes_overview || alertes}
                  onGoAlertes={() => setOnglet('alertes')}
                  onGoPedagogie={() => setOnglet('pedagogy')}
                  onGoAdmin={() => setOnglet('admin')}
                  auditeursNotoires={auditeursNotoires}
                />
              </div>
              )
            ) : (
              <Empty label="Section introuvable"/>
            )}
          </div>
          )}
        </>
        )
      })()}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* Onglet 2 — Pédagogique                                               */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {onglet==='pedagogy' && (() => {
        const pedEntries = buildPedagogieEntries(pedagogiques)
        const pedEntry = pedSelection ? pedEntries.find(e => e.id === pedSelection) : null
        return (
        <>
          <div style={{display:'flex',flexWrap:'wrap',gap:'0.5rem',alignItems:'center',marginBottom:'0.75rem'}}>
            <span style={{fontSize:'0.78rem',color:'#64748b'}}>
              Indicateurs pédagogiques (assiduité séance, couverture étudiants, absences, événements)
              {formationId && <> · <b>{(formations_liste||[]).find(f => String(f.id) === formationId)?.formation}</b></>}
              {secretariatId && <> · <b>{(secretariats_liste||[]).find(s => String(s.id) === secretariatId)?.nom}</b></>}
            </span>
            <div style={{marginLeft:'auto'}}>
              <button className="btn btn-sm btn-outline-secondary" onClick={() => fetchData(TAB_SECTIONS.pedagogy)} disabled={loadingTab}>
                <i className="bi bi-arrow-clockwise me-1"/>Actualiser
              </button>
            </div>
          </div>

          {!pedagogiques ? <TabSpinner label="Chargement des indicateurs pédagogiques…"/> : (
          <div style={{display:'grid',gridTemplateColumns:'minmax(220px,280px) 1fr',gap:'1rem',alignItems:'start',marginBottom:'1.2rem'}}>
            <div style={{background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)',overflow:'hidden',maxHeight:'70vh',overflowY:'auto'}}>
              <div style={{padding:'0.65rem 0.85rem',background:'#f8fafc',borderBottom:'1px solid #e2e8f0',fontSize:'0.78rem',color:'#64748b',fontWeight:600}}>
                {pedEntries.length} périmètre{pedEntries.length > 1 ? 's' : ''}
              </div>
              <button
                type="button"
                onClick={()=>setPedSelection(null)}
                style={{
                  display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                  padding:'0.55rem 0.85rem', fontSize:'0.78rem', fontWeight:700,
                  background: pedSelection === null ? '#e0f2fe' : '#fff',
                  borderBottom:'2px solid #e2e8f0', color: pedSelection === null ? '#0369a1' : '#475569',
                }}
              >
                <i className="bi bi-grid-3x3-gap me-1"/>
                Tous les indicateurs
              </button>
              {pedEntries.length > 0 && (
                <>
                  {['formation', 'grade', 'secretariat'].map(dim => {
                    const group = pedEntries.filter(e => e.type === dim)
                    if (!group.length) return null
                    const dimLabel = dim === 'formation' ? 'Formations' : dim === 'grade' ? 'Grades' : 'Secrétariats'
                    return (
                      <div key={dim}>
                        <div style={{padding:'0.4rem 0.85rem',fontSize:'0.68rem',fontWeight:700,color:'#94a3b8',background:'#fafbfc',borderBottom:'1px solid #f1f5f9'}}>
                          {dimLabel}
                        </div>
                        {group.map(entry => (
                          <button
                            key={entry.id}
                            type="button"
                            onClick={()=>setPedSelection(entry.id)}
                            style={{
                              display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                              padding:'0.55rem 0.85rem', fontSize:'0.78rem',
                              background: pedSelection===entry.id ? '#e8eef6' : '#fff',
                              borderBottom:'1px solid #f1f5f9',
                            }}
                          >
                            <div style={{fontWeight:700, color:'#1e293b', marginBottom:'0.1rem'}}>
                              <span style={{
                                background:`${entry.tagColor}18`, color:entry.tagColor, borderRadius:4,
                                padding:'0.05rem 0.35rem', marginRight:'0.3rem', fontSize:'0.68rem',
                              }}>{entry.tag}</span>
                              <span style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',display:'inline-block',maxWidth:'calc(100% - 2.5rem)',verticalAlign:'bottom'}}>
                                {entry.label}
                              </span>
                            </div>
                            <div style={{color:'#94a3b8', fontSize:'0.72rem'}}>{entry.sub}</div>
                          </button>
                        ))}
                      </div>
                    )
                  })}
                </>
              )}
            </div>

            {pedSelection === null ? (
              <PedagogiqueEnsemblePanel
                pedagogiques={pedagogiques}
                pedEntries={pedEntries}
                onSelect={setPedSelection}
                auditeursNotoires={auditeursNotoires}
              />
            ) : pedEntry ? (
              <div style={{ minWidth: 0 }}>
                <button
                  type="button"
                  className="btn btn-sm btn-outline-secondary mb-2"
                  onClick={()=>setPedSelection(null)}
                >
                  <i className="bi bi-grid-3x3-gap me-1"/>Voir tous les indicateurs
                </button>
                <PedagogiqueDetailPanel
                  entry={pedEntry}
                  pedagogiques={pedagogiques}
                  auditeursNotoires={auditeursNotoires}
                  onGoSecretariat={(id) => {
                    setSecretariatId(String(id))
                    setOnglet('secretariats')
                  }}
                />
              </div>
            ) : (
              <Empty label="Périmètre introuvable"/>
            )}
          </div>
          )}
        </>
        )
      })()}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* Onglet 3 — Administratif & Opérationnel                              */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {onglet==='admin' && (
        !adm ? <TabSpinner label="Chargement des indicateurs administratifs…"/> : (
        <>
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(165px,1fr))',gap:'0.8rem',marginBottom:'1.1rem'}}>
            <Kpi icon="bi-diagram-3"    label="Groupes actifs"       value={adm.nb_groupes}            color="#1565C0"/>
            <Kpi icon="bi-person-badge" label="Encadrants"           value={adm.nb_encadrants}          color="#7B1FA2"/>
            <Kpi icon="bi-x-square"     label="Séances annulées"     value={adm.nb_seances_annulees}    color="#C62828"/>
            <Kpi icon="bi-calendar-check" label={KPI_SESSIONS_COMPT.label} value={adm.nb_seances_terminees} color="#082961"
              help={KPI_SESSIONS_COMPT.help}/>
            <Kpi icon="bi-person-x-fill" label={AUDITEURS_NOTOIRES.label}
              value={auditeursNotoires?.total ?? adm.nb_absences_notoires ?? 0} color="#C62828"
              sub={auditeursNotoires ? `${Number(auditeursNotoires.pct || 0).toFixed(1).replace('.', ',')}% des inscrits` : undefined}
              help={AUDITEURS_NOTOIRES.help}/>
            <Kpi icon="bi-people-fill"  label="Moy. étudiants/groupe" value={adm.moy_auditeurs_groupe}  color="#00838F"/>
            <Kpi icon="bi-percent"      label="% Hommes"             value={`${adm.ratio_hf?.pct_hommes??0}%`} color="#1565C0"/>
            <Kpi icon="bi-percent"      label="% Femmes"             value={`${adm.ratio_hf?.pct_femmes??0}%`} color="#AD1457"/>
          </div>

          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(320px,1fr))',gap:'1rem'}}>
            <Card title="Répartition Hommes / Femmes" icon="bi-gender-ambiguous">
              <Donut data={adm.participants_par_sexe} labelKey="sexe" valueKey="total"/>
            </Card>

            <Card title="Étudiants par catégorie" icon="bi-bar-chart-steps">
              <HBars data={(adm.participants_par_categorie||[]).map(d=>({...d,categorie:d.categorie||'Non rens.'}))}
                labelKey="categorie" valueKey="total"/>
            </Card>

            <Card title="Étudiants par grade" icon="bi-award">
              <Bars data={(adm.participants_par_grade||[]).map(d=>({...d,grade:d.grade||'—'}))}
                labelKey="grade" valueKey="total" color="#7B1FA2"/>
            </Card>

            <Card title="Étudiants par vague" icon="bi-layers">
              <Bars data={(adm.participants_par_vague||[]).map(d=>({...d,vague:d.vague||'—'}))}
                labelKey="vague" valueKey="total" color="#F5B100"/>
            </Card>

            <Card title="Charge des enseignants" icon="bi-person-video3" col="1/-1">
              <HBars data={adm.charge_enseignants} labelKey="nom" valueKey="nb_sessions"/>
            </Card>
          </div>

          <div style={{ marginTop: '1rem' }}>
            <Card title={AUDITEURS_NOTOIRES.cardTitle} icon="bi-person-x-fill" col="1/-1">
              <AuditeursNotoiresPanel data={auditeursNotoires} maxHeight={420}/>
            </Card>
          </div>
        </>
        )
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* Onglet 4 — Historique                                                */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {onglet==='history' && (
        <>
          <div style={{display:'flex',flexWrap:'wrap',gap:'0.5rem',alignItems:'center',marginBottom:'0.75rem'}}>
            <span style={{fontSize:'0.78rem',color:'#64748b'}}>
              Période : <b>12 derniers mois</b>
              {formationId && <> · Formation : <b>{(formations_liste||[]).find(f => String(f.id) === formationId)?.formation}</b></>}
              {secretariatId && <> · Secrétariat : <b>{(secretariats_liste||[]).find(s => String(s.id) === secretariatId)?.nom}</b></>}
            </span>
            <div style={{marginLeft:'auto'}}>
              <button className="btn btn-sm btn-outline-secondary" onClick={() => fetchData(TAB_SECTIONS.history)} disabled={loadingTab}>
                <i className="bi bi-arrow-clockwise me-1"/>Actualiser
              </button>
            </div>
          </div>

          {!historique ? <TabSpinner label="Chargement de l'historique…"/> : !historique.pointages_par_mois?.length ? (
            <div style={{background:'#fff',borderRadius:10,padding:'2rem',textAlign:'center',boxShadow:'0 1px 4px rgba(0,0,0,0.07)'}}>
              <Empty label="Aucune donnée historique pour cette sélection"/>
              <p style={{margin:'0.75rem 0 0',fontSize:'0.78rem',color:'#64748b'}}>
                Vérifiez les filtres formation / secrétariat ou l&apos;activité des séances et pointages.
              </p>
            </div>
          ) : (
            <div style={{display:'grid',gridTemplateColumns:'minmax(200px,260px) 1fr',gap:'1rem',alignItems:'start',marginBottom:'1.2rem'}}>
              <div style={{background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)',overflow:'hidden',maxHeight:'70vh',overflowY:'auto'}}>
                <div style={{padding:'0.65rem 0.85rem',background:'#f8fafc',borderBottom:'1px solid #e2e8f0',fontSize:'0.78rem',color:'#64748b',fontWeight:600}}>
                  {historique.pointages_par_mois.length} mois
                </div>
                <button
                  type="button"
                  onClick={()=>setHistSelection(null)}
                  style={{
                    display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                    padding:'0.55rem 0.85rem', fontSize:'0.78rem', fontWeight:700,
                    background: histSelection === null ? '#e0f2fe' : '#fff',
                    borderBottom:'2px solid #e2e8f0', color: histSelection === null ? '#0369a1' : '#475569',
                  }}
                >
                  <i className="bi bi-grid-3x3-gap me-1"/>
                  Tous les mois (12)
                </button>
                {[...historique.pointages_par_mois].reverse().map((pt) => {
                  const i = historique.pointages_par_mois.findIndex(m => m.mois === pt.mois)
                  const taux = historique.taux_presence_par_mois[i]
                  const hasData = (pt.total || 0) > 0 || (pt.presents || 0) + (pt.absents || 0) > 0
                  return (
                    <button
                      key={pt.mois}
                      type="button"
                      onClick={()=>setHistSelection(i)}
                      style={{
                        display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                        padding:'0.55rem 0.85rem', fontSize:'0.78rem',
                        background: histSelection===i ? '#e8eef6' : '#fff',
                        borderBottom:'1px solid #f1f5f9',
                        opacity: hasData ? 1 : 0.65,
                      }}
                    >
                      <div style={{fontWeight:700, color:'#1e293b', marginBottom:'0.1rem'}}>
                        <i className="bi bi-calendar3 me-1" style={{color:'#1565C0'}}/>
                        {formatMoisLabelLong(pt.mois)}
                      </div>
                      <div style={{color:'#94a3b8', fontSize:'0.72rem'}}>
                        {pt.total} ptg. · {Number(taux?.total || 0).toFixed(1)}% prés.
                        {!hasData ? ' · sans données' : ''}
                      </div>
                    </button>
                  )
                })}
              </div>

              {histSelection === null ? (
                <HistoriqueEnsemblePanel historique={historique} onSelectMois={setHistSelection} auditeursNotoires={auditeursNotoires} />
              ) : (
                <div style={{ minWidth: 0 }}>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-secondary mb-2"
                    onClick={()=>setHistSelection(null)}
                  >
                    <i className="bi bi-grid-3x3-gap me-1"/>Voir tous les mois
                  </button>
                  <HistoriqueMoisPanel historique={historique} monthIndex={histSelection} auditeursNotoires={auditeursNotoires} />
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* Onglet 5 — Secrétariats                                              */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {onglet==='secretariats' && (
        <>
          <div style={{display:'flex',flexWrap:'wrap',gap:'0.5rem',alignItems:'center',marginBottom:'0.75rem'}}>
            <span style={{fontSize:'0.78rem',color:'#64748b'}}>
              {formationId
                ? <>Filtre formation : <b>{(formations_liste||[]).find(f => String(f.id) === formationId)?.formation || formationId}</b></>
                : 'Toutes les formations'}
            </span>
            <div style={{marginLeft:'auto'}}>
              <button className="btn btn-sm btn-outline-secondary" onClick={fetchSecStats} disabled={loadingSecStats}>
                <i className="bi bi-arrow-clockwise me-1"/>Actualiser
              </button>
            </div>
          </div>

          {loadingSecStats ? (
            <div style={{display:'flex',alignItems:'center',gap:'0.5rem',color:'#64748b',padding:'2rem',marginBottom:'1rem'}}>
              <div className="spinner"/>Chargement de tous les secrétariats…
            </div>
          ) : !secStats?.secretariats?.length ? (
            <div style={{marginBottom:'1.2rem'}}>
              <Empty label="Aucun secrétariat trouvé"/>
            </div>
          ) : (
            <div style={{display:'grid',gridTemplateColumns:'minmax(220px,280px) 1fr',gap:'1rem',alignItems:'start',marginBottom:'1.2rem'}}>
              <div style={{background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)',overflow:'hidden',maxHeight:'70vh',overflowY:'auto'}}>
                <div style={{padding:'0.65rem 0.85rem',background:'#f8fafc',borderBottom:'1px solid #e2e8f0',fontSize:'0.78rem',color:'#64748b',fontWeight:600}}>
                  {secStats.total} secrétariat{secStats.total > 1 ? 's' : ''}
                </div>
                <button
                  type="button"
                  onClick={()=>{ setSecSelection(null); setSecDetail(null); setSecretariatId('') }}
                  style={{
                    display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                    padding:'0.55rem 0.85rem', fontSize:'0.78rem', fontWeight:700,
                    background: secSelection === null ? '#e0f2fe' : '#fff',
                    borderBottom:'2px solid #e2e8f0', color: secSelection === null ? '#0369a1' : '#475569',
                  }}
                >
                  <i className="bi bi-grid-3x3-gap me-1"/>
                  Tous les secrétariats ({secStats.total})
                </button>
                {secStats.secretariats.map((s,i)=>(
                  <button
                    key={s.secretariat_id}
                    type="button"
                    onClick={()=>setSecSelection(i)}
                    style={{
                      display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                      padding:'0.55rem 0.85rem', fontSize:'0.78rem',
                      background: secSelection===i ? '#e8eef6' : '#fff',
                      borderBottom:'1px solid #f1f5f9',
                    }}
                  >
                    <div style={{fontWeight:700, color:'#1e293b', marginBottom:'0.1rem'}}>
                      <i className="bi bi-building me-1" style={{color:C[i%C.length]}}/>
                      {s.secretariat}
                    </div>
                    <div style={{color:'#64748b', fontSize:'0.72rem'}}>
                      {s.nb_modules} mod. · {s.nb_inscrits} inscrits · {Number(s.taux_presence).toFixed(1)}% prés.
                      {(s.nb_auditeurs_notoires ?? 0) > 0 && (
                        <> · <span style={{ color: '#C62828' }}>{s.nb_auditeurs_notoires} not.</span></>
                      )}
                    </div>
                  </button>
                ))}
              </div>

              {secSelection === null ? (
                <SecretariatsEnsemblePanel secStats={secStats} onSelectIndividuel={setSecSelection} />
              ) : (
                loadingSecDetail ? (
                  <div style={{display:'flex',alignItems:'center',gap:'0.5rem',color:'#64748b',padding:'2rem',background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)'}}>
                    <div className="spinner"/>Chargement du détail…
                  </div>
                ) : secDetail ? (
                  <div style={{ minWidth: 0 }}>
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-secondary mb-2"
                      onClick={()=>{ setSecSelection(null); setSecDetail(null); setSecretariatId('') }}
                    >
                      <i className="bi bi-grid-3x3-gap me-1"/>Voir tous les secrétariats
                    </button>
                    <SecretariatDetailPanel
                      row={secStats.secretariats[secSelection]}
                      detail={secDetail}
                    />
                  </div>
                ) : (
                  <Empty label="Impossible de charger le détail de ce secrétariat"/>
                )
              )}
            </div>
          )}
        </>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* Onglet 6 — Rapports & Bilans                                         */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {onglet==='rapports' && (
        <>
        {secretariatFilterLocked && (
          <div style={{
            marginBottom: '0.75rem', padding: '0.55rem 0.85rem', borderRadius: 8,
            background: '#e8eef6', border: '1px solid #c5d0e0', color: '#0a2a4d', fontSize: '0.82rem',
          }}>
            <i className="bi bi-building me-1"/>
            Périmètre limité à votre secrétariat : <strong>{secretariatScopeLabel}</strong>
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.35rem', marginBottom: '0.85rem', flexWrap: 'wrap' }}>
          {RB_VIEWS.map(v => (
            <button
              key={v.id}
              type="button"
              onClick={() => setRbViewAndUrl(v.id)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
                padding: '0.45rem 0.85rem', borderRadius: 8, cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600,
                border: rbView === v.id ? '2px solid #001a33' : '1px solid #e2e8f0',
                background: rbView === v.id ? '#e8eef6' : '#fff',
                color: rbView === v.id ? '#001a33' : '#64748b',
              }}
            >
              <i className={`bi ${v.icon}`}/>{v.label}
            </button>
          ))}
        </div>

        {rbView === 'workflow' && (
          <RapportsWorkflowPanel
            user={user}
            formationId={formationId}
            secretariatId={effectiveSecretariatId}
            appliedVhPeriod={appliedVhPeriod}
          />
        )}

        {rbView === 'bilans' && (
        <>
        {/* ── Filtres bilans (même entête que Point Journalier) ─────────── */}
        <div style={{display:'flex',flexWrap:'wrap',gap:'0.5rem',alignItems:'center',marginBottom:'0.75rem'}}>
          <select className="form-select form-select-sm" style={{width:100}}
            value={rbAnnee} onChange={e=>{ setRbAnnee(Number(e.target.value)); setRbSelection(null) }}>
            {[rbAnnee-1, rbAnnee, rbAnnee+1].filter((y,i,a)=>a.indexOf(y)===i).sort().map(y=>(
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
          <select className="form-select form-select-sm" style={{width:130}}
            value={rbMois} onChange={e=>{ setRbMois(e.target.value); setRbSelection(null) }}>
            <option value="">Toute l'année</option>
            {['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'].map((m,i)=>(
              <option key={i+1} value={String(i+1)}>{m}</option>
            ))}
          </select>
          <select className="form-select form-select-sm" style={{width:120}}
            value={rbCategorie} onChange={e=>{ setRbCategorie(e.target.value); setRbSelection(null) }}>
            <option value="">Toutes catég.</option>
            {(rbData?.categories||[]).map(c=>(
              <option key={c} value={c}>Cat. {c}</option>
            ))}
          </select>
          {rbDimension === 'matiere' ? (
            <select className="form-select form-select-sm" style={{minWidth:160,maxWidth:220}}
              value={rbMatiereKey} onChange={e=>{ setRbMatiereKey(e.target.value); setRbSelection(null) }}>
              <option value="">Toutes matières</option>
              {(rbData?.matieres||[])
                .filter(m => !rbFormationId || String(m.formation_id) === rbFormationId)
                .map(m => (
                  <option key={rbMatiereOptionValue(m)} value={rbMatiereOptionValue(m)}>
                    {m.intitule}
                  </option>
                ))}
            </select>
          ) : (
            <select className="form-select form-select-sm" style={{minWidth:160,maxWidth:220}}
              value={rbModuleId} onChange={e=>{ setRbModuleId(e.target.value); setRbSelection(null) }}>
              <option value="">Tous modules</option>
              {(rbData?.modules||[]).map(m=>(
                <option key={m.id} value={m.id}>{m.intitule}</option>
              ))}
            </select>
          )}
          <select className="form-select form-select-sm" style={{minWidth:180,maxWidth:260}}
            value={rbFormationId} onChange={e=>{ setRbFormationId(e.target.value); setRbModuleId(''); setRbMatiereKey(''); setRbSelection(null) }}>
            <option value="">Toutes formations</option>
            {(rbData?.formations||formations_liste||[]).map(f=>(
              <option key={f.id} value={f.id}>{f.formation}</option>
            ))}
          </select>
          <select className="form-select form-select-sm" style={{minWidth:150,maxWidth:180}}
            value={rbPeriode} onChange={e=>{ setRbPeriode(e.target.value); setRbSelection(null) }}>
            {RB_PERIODES.map(p=>(
              <option key={p.value||'all'} value={p.value}>{p.label}</option>
            ))}
          </select>
          <div style={{display:'flex',flexDirection:'column',gap:'0.1rem'}}>
            <span style={{fontSize:'0.65rem',color:'#94a3b8',lineHeight:1}}>Calendrier prév.</span>
            <input
              type="date"
              className="form-control form-control-sm"
              style={{width:155}}
              title="Calendrier prévisionnel"
              value={rbCalendrier}
              onChange={e=>{ setRbCalendrier(e.target.value); setRbSelection(null) }}
            />
          </div>
          <div style={{marginLeft:'auto', display:'flex', gap:'0.4rem', alignItems:'center', flexWrap:'nowrap'}}>
            <button className="btn btn-sm btn-outline-secondary" onClick={fetchBilans} disabled={loadingRb}>
              <i className="bi bi-arrow-clockwise me-1"/>Actualiser
            </button>
            {PJ_EXPORT_FORMATS.map(({ fmt, icon, label, col }) => (
              <button
                key={`rb-${fmt}`}
                className="btn btn-sm"
                disabled={!!exportingRb || loadingRb || !rbData?.bilans?.length}
                style={{ background: col, color: '#fff', border: 'none', minWidth: 88, opacity: (exportingRb || loadingRb) ? 0.65 : 1 }}
                onClick={() => downloadBilanExport(fmt)}
                title={`Exporter les bilans filtrés (${label})`}
              >
                {exportingRb === fmt ? (
                  <span className="spinner-border spinner-border-sm"/>
                ) : (
                  <><i className={`bi ${icon} me-1`}/>{label}</>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Type de bilan : Module · Catégorie · Formation */}
        <div style={{display:'flex',gap:'0.35rem',marginBottom:'0.85rem',flexWrap:'wrap'}}>
          {RB_DIMENSIONS.map(d=>(
            <button
              key={d.id}
              type="button"
              onClick={()=>{
                setRbDimension(d.id)
                setRbModuleId('')
                setRbMatiereKey('')
                setRbSelection(null)
              }}
              style={{
                display:'inline-flex', alignItems:'center', gap:'0.35rem',
                padding:'0.45rem 0.85rem', borderRadius:8, cursor:'pointer', fontSize:'0.82rem', fontWeight:600,
                border: rbDimension===d.id ? '2px solid #001a33' : '1px solid #e2e8f0',
                background: rbDimension===d.id ? '#e8eef6' : '#fff',
                color: rbDimension===d.id ? '#001a33' : '#64748b',
              }}
            >
              <i className={`bi ${d.icon}`}/>{d.label}
            </button>
          ))}
        </div>

        <AuditeursNotoiresKpiStrip data={auditeursNotoires}/>

        {/* Liste bilans + détail */}
        {loadingRb ? (
          <div style={{display:'flex',alignItems:'center',gap:'0.5rem',color:'#64748b',padding:'2rem',marginBottom:'1rem'}}>
            <div className="spinner"/>Chargement des bilans…
          </div>
        ) : !rbData?.bilans?.length ? (
          <div style={{marginBottom:'1.2rem'}}>
            <Empty label="Aucun bilan pour cette sélection"/>
          </div>
        ) : (
          <div style={{display:'grid',gridTemplateColumns:'minmax(220px,280px) 1fr',gap:'1rem',alignItems:'start',marginBottom:'1.2rem'}}>
            <div style={{background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)',overflow:'hidden',maxHeight:'55vh',overflowY:'auto'}}>
              <div style={{padding:'0.65rem 0.85rem',background:'#f8fafc',borderBottom:'1px solid #e2e8f0',fontSize:'0.78rem',color:'#64748b',fontWeight:600}}>
                {rbData.total_bilans} bilan{rbData.total_bilans > 1 ? 's' : ''} · {RB_DIMENSIONS.find(d=>d.id===rbDimension)?.label}
              </div>
              <button
                type="button"
                onClick={()=>{ setRbSelection(null); setRbDetail(null) }}
                style={{
                  display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                  padding:'0.55rem 0.85rem', fontSize:'0.78rem', fontWeight:700,
                  background: rbSelection === null ? '#e0f2fe' : '#fff',
                  borderBottom:'2px solid #e2e8f0', color: rbSelection === null ? '#0369a1' : '#475569',
                }}
              >
                <i className="bi bi-grid-3x3-gap me-1"/>
                Tous les tableaux ({rbAllTableaux.length || rbData.total_bilans})
              </button>
              {rbData.bilans.map((b,i)=>(
                <button
                  key={b.id}
                  type="button"
                  onClick={()=>setRbSelection(i)}
                  style={{
                    display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                    padding:'0.55rem 0.85rem', fontSize:'0.78rem',
                    background: rbSelection===i ? '#e8eef6' : '#fff',
                    borderBottom:'1px solid #f1f5f9',
                  }}
                >
                  <div style={{fontWeight:700, color:'#1e293b', marginBottom:'0.1rem'}}>
                    {b.dimension==='categorie' && (
                      <span style={{background:'#1565C018',color:'#1565C0',borderRadius:4,padding:'0.05rem 0.35rem',marginRight:'0.3rem',fontSize:'0.72rem'}}>
                        CAT {b.categorie}
                      </span>
                    )}
                    {b.dimension==='module' && (
                      <span style={{background:'#7B1FA218',color:'#7B1FA2',borderRadius:4,padding:'0.05rem 0.35rem',marginRight:'0.3rem',fontSize:'0.72rem'}}>
                        MOD
                      </span>
                    )}
                    {b.dimension==='matiere' && (
                      <span style={{background:'#0C3E9518',color:'#0C3E95',borderRadius:4,padding:'0.05rem 0.35rem',marginRight:'0.3rem',fontSize:'0.72rem'}}>
                        MAT
                      </span>
                    )}
                    {b.libelle}
                  </div>
                  <div style={{color:'#64748b', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
                    {b.sous_titre}
                  </div>
                  {b.dimension === 'module' && (b.grade || b.groupe) && (
                    <div style={{color:'#94a3b8', fontSize:'0.7rem', marginTop:'0.05rem'}}>
                      {b.grade ? `Grade ${b.grade}` : ''}{b.grade && b.groupe ? ' · ' : ''}{b.groupe || ''}
                    </div>
                  )}
                  {b.inscrits != null && (
                    <div style={{color:'#94a3b8', fontSize:'0.72rem', marginTop:'0.1rem'}}>
                      {b.inscrits} inscrit{b.inscrits > 1 ? 's' : ''}
                      {b.nb_groupes != null ? ` · ${b.nb_groupes} groupe${b.nb_groupes > 1 ? 's' : ''}` : ''}
                      {b.nb_pointages != null ? ` · ${b.nb_pointages} pointages` : ''}
                    </div>
                  )}
                </button>
              ))}
            </div>
            {rbSelection === null ? (
              loadingRb && !rbAllTableaux.length ? (
                <TabSpinner label="Chargement de tous les tableaux…"/>
              ) : (
              <BilansEnsemblePanel
                items={rbAllTableaux}
                bilans={rbData.bilans}
                filtres={rbData.filtres_actifs}
                dimension={rbDimension}
                onSelectIndividuel={setRbSelection}
              />
              )
            ) : rbData.bilans[rbSelection] && (
              loadingRbDetail ? (
                <div style={{display:'flex',alignItems:'center',gap:'0.5rem',color:'#64748b',padding:'2rem',background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)'}}>
                  <div className="spinner"/>Chargement du tableau…
                </div>
              ) : (
                <div style={{ minWidth: 0 }}>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-secondary mb-2"
                    onClick={()=>{ setRbSelection(null); setRbDetail(null) }}
                  >
                    <i className="bi bi-grid-3x3-gap me-1"/>Voir tous les tableaux
                  </button>
                  <BilanDetailPanel
                    bilan={rbData.bilans[rbSelection]}
                    tableau={rbDetail}
                    filtres={rbData.filtres_actifs}
                    justificatifsText={rbJustificatifsText}
                    onJustificatifsChange={setRbJustificatifsText}
                  />
                </div>
              )
            )}
          </div>
        )}

        {/* ── Bilan FAC ─────────────────────────────────────────────────────── */}
        <div style={{marginTop:'1.5rem'}}>
          <button
            type="button"
            onClick={()=>setShowFacPanel(v=>!v)}
            style={{
              display:'flex', alignItems:'center', gap:'0.5rem', width:'100%',
              background: showFacPanel
                ? 'linear-gradient(135deg,#fffbf0 0%,#fef7e2 100%)'
                : 'linear-gradient(135deg,#f8fafc 0%,#f1f5f9 100%)',
              border: showFacPanel ? '2px solid #EDB131' : '1px solid #e2e8f0',
              borderRadius:10, padding:'0.75rem 1rem', cursor:'pointer',
              boxShadow:'0 1px 4px rgba(0,0,0,0.06)',
            }}
          >
            <span style={{
              background:'#EDB131', color:'#fff', borderRadius:6,
              padding:'0.2rem 0.55rem', fontSize:'0.72rem', fontWeight:800, letterSpacing:1,
            }}>BILAN</span>
            <span style={{fontWeight:700, fontSize:'0.9rem', color:'#1e293b'}}>
              Bilan formation
            </span>
            <span style={{marginLeft:'auto', color:'#94a3b8', fontSize:'0.78rem'}}>
              Point global · VH par groupe · Absents notoires
            </span>
            <i className={`bi bi-chevron-${showFacPanel ? 'up' : 'down'}`} style={{color:'#EDB131', fontSize:'0.85rem'}}/>
          </button>

          {showFacPanel && (
            <div style={{
              background:'#fff', border:'1px solid #fee8aa',
              borderTop:'none', borderRadius:'0 0 10px 10px',
              boxShadow:'0 4px 12px rgba(237,177,49,0.08)', padding:'1rem',
            }}>
              {/* Filtres Bilan FAC */}
              <div style={{display:'flex',flexWrap:'wrap',gap:'0.5rem',alignItems:'flex-end',marginBottom:'1rem'}}>
                <div style={{display:'flex',flexDirection:'column',gap:'0.15rem'}}>
                  <span style={{fontSize:'0.65rem',color:'#94a3b8'}}>Formation</span>
                  <select
                    className="form-select form-select-sm"
                    style={{minWidth:200,maxWidth:300}}
                    value={facFormationId}
                    onChange={e=>{ setFacFormationId(e.target.value); setFacData(null) }}
                  >
                    <option value="">— Sélectionner —</option>
                    {(rbData?.formations || formations_liste || []).map(f=>(
                      <option key={f.id} value={f.id}>{f.formation}</option>
                    ))}
                  </select>
                </div>
                <div style={{display:'flex',flexDirection:'column',gap:'0.15rem'}}>
                  <span style={{fontSize:'0.65rem',color:'#94a3b8'}}>Année</span>
                  <select
                    className="form-select form-select-sm"
                    style={{width:100}}
                    value={facAnnee}
                    onChange={e=>{ setFacAnnee(Number(e.target.value)); setFacData(null) }}
                  >
                    {[facAnnee-1, facAnnee, facAnnee+1].map(y=>(
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                </div>
                <div style={{display:'flex',flexDirection:'column',gap:'0.15rem'}}>
                  <span style={{fontSize:'0.65rem',color:'#94a3b8'}}>Catégorie</span>
                  <select
                    className="form-select form-select-sm"
                    style={{width:110}}
                    value={facCategorie}
                    onChange={e=>{ setFacCategorie(e.target.value); setFacData(null) }}
                  >
                    <option value="">Toutes</option>
                    {['A','B','C','D'].map(c=>(
                      <option key={c} value={c}>Cat. {c}</option>
                    ))}
                  </select>
                </div>
                <button
                  className="btn btn-sm"
                  style={{background:'#EDB131',color:'#fff',border:'none',minWidth:110}}
                  onClick={fetchBilanFac}
                  disabled={loadingFac || (!facFormationId && !formationId) || !facGradesSelected.length}
                >
                  {loadingFac
                    ? <><span className="spinner-border spinner-border-sm me-1"/>Chargement…</>
                    : <><i className="bi bi-file-earmark-bar-graph me-1"/>Générer le bilan</>
                  }
                </button>
              </div>

              {/* Grades & groupes */}
              {(facFormationId || formationId) && (
                <div style={{
                  marginBottom: '1rem', padding: '0.75rem', borderRadius: 8,
                  background: '#fffceb', border: '1px solid #fdec8a',
                }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.55rem',
                  }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#92660e' }}>
                      <i className="bi bi-ui-checks me-1"/>
                      Périmètre — grades et groupes
                    </span>
                    {loadingFacPerimetre && (
                      <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                        <span className="spinner-border spinner-border-sm me-1"/>Chargement…
                      </span>
                    )}
                    {!loadingFacPerimetre && facPerimetre.grades.length > 0 && (
                      <span style={{ display: 'flex', gap: '0.35rem' }}>
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-secondary"
                          style={{ fontSize: '0.68rem', padding: '0.15rem 0.45rem' }}
                          onClick={() => {
                            setFacGradesSelected([...facPerimetre.grades])
                            setFacGroupesSelected(facPerimetre.groupes.map(g => g.id))
                          }}
                        >
                          Tout cocher
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-secondary"
                          style={{ fontSize: '0.68rem', padding: '0.15rem 0.45rem' }}
                          onClick={() => {
                            setFacGradesSelected([])
                            setFacGroupesSelected([])
                            setFacData(null)
                          }}
                        >
                          Tout décocher
                        </button>
                      </span>
                    )}
                  </div>

                  {!loadingFacPerimetre && !facPerimetre.grades.length && (
                    <p style={{ margin: 0, fontSize: '0.78rem', color: '#94a3b8' }}>
                      Aucun grade/groupe pour cette formation et ces filtres.
                    </p>
                  )}

                  {!loadingFacPerimetre && facPerimetre.grades.length > 0 && (
                    <>
                      <div style={{ marginBottom: '0.55rem' }}>
                        <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', marginBottom: '0.3rem' }}>
                          GRADES
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem' }}>
                          {facPerimetre.grades.map(grade => (
                            <label
                              key={grade}
                              style={{
                                display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer',
                                background: facGradesSelected.includes(grade) ? '#fef6c7' : '#f8fafc',
                                border: `1px solid ${facGradesSelected.includes(grade) ? '#f5c10b' : '#e2e8f0'}`,
                                borderRadius: 6, padding: '0.25rem 0.55rem',
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={facGradesSelected.includes(grade)}
                                onChange={e => {
                                  setFacData(null)
                                  setFacGradesSelected(prev => (
                                    e.target.checked
                                      ? [...prev, grade]
                                      : prev.filter(g => g !== grade)
                                  ))
                                }}
                              />
                              {grade}
                            </label>
                          ))}
                        </div>
                      </div>

                      {facGroupesVisibles.length > 0 && (
                        <div>
                          <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', marginBottom: '0.3rem' }}>
                            GROUPES
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', maxHeight: 140, overflowY: 'auto' }}>
                            {facGroupesVisibles.map(g => (
                              <label
                                key={g.id}
                                style={{
                                  display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                                  fontSize: '0.72rem', cursor: 'pointer',
                                  background: facGroupesSelected.includes(g.id) ? '#ecf3fd' : '#f8fafc',
                                  border: `1px solid ${facGroupesSelected.includes(g.id) ? '#80b7f5' : '#e2e8f0'}`,
                                  borderRadius: 6, padding: '0.2rem 0.45rem',
                                }}
                              >
                                <input
                                  type="checkbox"
                                  checked={facGroupesSelected.includes(g.id)}
                                  onChange={e => {
                                    setFacData(null)
                                    setFacGroupesSelected(prev => (
                                      e.target.checked
                                        ? [...prev, g.id]
                                        : prev.filter(id => id !== g.id)
                                    ))
                                  }}
                                />
                                <span style={{ color: '#64748b' }}>{g.grade}</span>
                                <span style={{ fontWeight: 600 }}>{g.groupe}</span>
                              </label>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Contenu Bilan FAC */}
              {!facData && !loadingFac && (
                <div style={{
                  textAlign:'center', padding:'2.5rem 1rem', color:'#94a3b8',
                  fontSize:'0.85rem', borderTop:'1px solid #f1f5f9',
                }}>
                  <i className="bi bi-file-earmark-bar-graph" style={{fontSize:'2.5rem',display:'block',marginBottom:'0.5rem',color:'#EDB13166'}}/>
                  Sélectionnez une formation et cliquez sur &quot;Générer le bilan&quot;
                </div>
              )}

              {facData && (
                <BilanFACPanel
                  data={facData}
                  sousOnglet={facSousOnglet}
                  onChangeSousOnglet={setFacSousOnglet}
                  onMetaChange={setFacExportMeta}
                  onExport={downloadBilanFac}
                  exportingFac={exportingFac}
                />
              )}
            </div>
          )}
        </div>

        </>
        )}

        </>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* Onglet — Point Journalier par catégorie et formation                 */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {onglet==='point_journalier' && (
        <div>
          {secretariatFilterLocked && (
            <div style={{
              marginBottom: '0.75rem', padding: '0.55rem 0.85rem', borderRadius: 8,
              background: '#e8eef6', border: '1px solid #c5d0e0', color: '#0a2a4d', fontSize: '0.82rem',
            }}>
              <i className="bi bi-building me-1"/>
              Périmètre limité à votre secrétariat : <strong>{secretariatScopeLabel}</strong>
            </div>
          )}
          {/* Filtres + Actualiser + exports (même ligne) */}
          <div style={{display:'flex',flexWrap:'wrap',gap:'0.5rem',alignItems:'center',marginBottom:'0.75rem'}}>
            <select className="form-select form-select-sm" style={{width:100}}
              value={pjAnnee} onChange={e=>{ setPjAnnee(Number(e.target.value)); setPjSelection(null) }}>
              {[pjAnnee-1, pjAnnee, pjAnnee+1].filter((y,i,a)=>a.indexOf(y)===i).sort().map(y=>(
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <select className="form-select form-select-sm" style={{width:130}}
              value={pjMois} onChange={e=>{ setPjMois(e.target.value); setPjSelection(null) }}>
              <option value="">Toute l'année</option>
              {['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'].map((m,i)=>(
                <option key={i+1} value={String(i+1)}>{m}</option>
              ))}
            </select>
            <select className="form-select form-select-sm" style={{width:110}}
              value={pjCategorie} onChange={e=>{ setPjCategorie(e.target.value); setPjSelection(null) }}>
              <option value="">Toutes catég.</option>
              {(pjData?.categories||[]).map(c=>(
                <option key={c} value={c}>
                  Cat. {c}
                  {pjData?.categories_avec_donnees && !pjData.categories_avec_donnees.includes(c) ? ' (sans données)' : ''}
                </option>
              ))}
            </select>
            <select className="form-select form-select-sm" style={{minWidth:180,maxWidth:260}}
              value={pjFormationId} onChange={e=>{ setPjFormationId(e.target.value); setPjSelection(null) }}>
              <option value="">Toutes formations</option>
              {(pjData?.formations||formations_liste||[]).map(f=>(
                <option key={f.id} value={f.id}>{f.formation}</option>
              ))}
            </select>
            <div style={{marginLeft:'auto', display:'flex', gap:'0.4rem', alignItems:'center', flexWrap:'nowrap'}}>
              <button className="btn btn-sm btn-outline-secondary" onClick={fetchPointJournalier} disabled={loadingPj}>
                <i className="bi bi-arrow-clockwise me-1"/>Actualiser
              </button>
              {PJ_EXPORT_FORMATS.map(({ fmt, icon, label, col }) => (
                <button
                  key={fmt}
                  className="btn btn-sm"
                  disabled={!!exportingPj || loadingPj || !pjData?.tableaux?.length}
                  style={{ background: col, color: '#fff', border: 'none', minWidth: 88, opacity: (exportingPj || loadingPj) ? 0.65 : 1 }}
                  onClick={() => downloadPointJournalier(fmt)}
                  title={`Exporter la sélection filtrée (${label})`}
                >
                  {exportingPj === fmt ? (
                    <span className="spinner-border spinner-border-sm"/>
                  ) : (
                    <><i className={`bi ${icon} me-1`}/>{label}</>
                  )}
                </button>
              ))}
            </div>
          </div>

          <AuditeursNotoiresKpiStrip data={auditeursNotoires}/>

          {loadingPj ? (
            <div style={{display:'flex',alignItems:'center',gap:'0.5rem',color:'#64748b',padding:'2rem'}}>
              <div className="spinner"/>Chargement de tous les tableaux…
            </div>
          ) : !pjData?.tableaux?.length ? (
            <div style={{ background: '#fff', borderRadius: 10, padding: '2rem', textAlign: 'center', boxShadow: '0 1px 4px rgba(0,0,0,0.07)' }}>
              <Empty label="Aucun point journalier pour cette période"/>
              {pjError && (
                <p style={{ margin: '0.75rem 0 0', fontSize: '0.82rem', color: '#C62828' }}>{pjError}</p>
              )}
              <div style={{ margin: '1rem auto 0', maxWidth: 480, fontSize: '0.78rem', color: '#64748b', textAlign: 'left', background: '#f8fafc', borderRadius: 8, padding: '0.75rem 1rem', border: '1px solid #e2e8f0' }}>
                <p style={{ margin: '0 0 0.5rem', fontWeight: 700, color: '#475569' }}>Filtres actifs</p>
                <ul style={{ margin: 0, paddingLeft: '1.1rem', lineHeight: 1.6 }}>
                  <li>Année : <b>{pjAnnee}</b></li>
                  <li>Mois : <b>{pjMois ? ['','Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'][Number(pjMois)] : 'Toute l\'année'}</b></li>
                  <li>Catégorie : <b>{pjCategorie || 'Toutes'}</b></li>
                  <li>Formation : <b>{pjFormationId ? (pjData?.formations?.find(f => String(f.id) === pjFormationId)?.formation || pjFormationId) : 'Toutes'}</b></li>
                  {secretariatId && <li>Secrétariat : filtre global actif</li>}
                </ul>
                {pjData?.mois_avec_donnees?.length > 0 && (
                  <p style={{ margin: '0.65rem 0 0', fontSize: '0.76rem' }}>
                    Mois avec données en {pjAnnee} :{' '}
                    <b>{pjData.mois_avec_donnees.map(m => ['','Jan','Fév','Mar','Avr','Mai','Juin','Juil','Aoû','Sep','Oct','Nov','Déc'][m]).join(', ')}</b>
                  </p>
                )}
                <p style={{ margin: '0.65rem 0 0', fontSize: '0.76rem' }}>
                  Essayez <b>Toute l&apos;année</b>, une autre catégorie, ou vérifiez que des séances et pointages existent pour la période (import Excel / badgeage).
                </p>
              </div>
            </div>
          ) : (
            <div style={{display:'grid',gridTemplateColumns:'minmax(220px,280px) 1fr',gap:'1rem',alignItems:'start'}}>
              {/* Liste des tableaux */}
              <div style={{background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)',overflow:'hidden',maxHeight:'70vh',overflowY:'auto'}}>
                <div style={{padding:'0.65rem 0.85rem',background:'#f8fafc',borderBottom:'1px solid #e2e8f0',fontSize:'0.78rem',color:'#64748b',fontWeight:600}}>
                  {pjData.total_tableaux} tableau(x) — {pjAnnee}
                </div>
                <button
                  type="button"
                  onClick={()=>{ setPjSelection(null); setPjDetail(null) }}
                  style={{
                    display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                    padding:'0.55rem 0.85rem', fontSize:'0.78rem', fontWeight:700,
                    background: pjSelection === null ? '#e0f2fe' : '#fff',
                    borderBottom:'2px solid #e2e8f0', color: pjSelection === null ? '#0369a1' : '#475569',
                  }}
                >
                  <i className="bi bi-grid-3x3-gap me-1"/>
                  Tous les tableaux ({pjAllTableaux.length || pjData.total_tableaux})
                </button>
                {pjData.tableaux.map((tb,i)=>(
                  <button key={tb.id || `${tb.formation_id}-${tb.categorie}-${tb.date}`}
                    onClick={()=>setPjSelection(i)}
                    style={{
                      display:'block',width:'100%',textAlign:'left',border:'none',cursor:'pointer',
                      padding:'0.55rem 0.85rem',fontSize:'0.78rem',
                      background:pjSelection===i?'#e8eef6':'#fff',
                      borderBottom:'1px solid #f1f5f9',
                    }}>
                    <div style={{fontWeight:700,color:'#1e293b',marginBottom:'0.1rem'}}>
                      <span style={{background:'#2277C118',color:'#2277C1',borderRadius:4,padding:'0.05rem 0.35rem',marginRight:'0.3rem',fontSize:'0.72rem'}}>
                        CAT {tb.categorie}
                      </span>
                      {tb.grade && (
                        <span style={{background:'#EDB13118',color:'#EDB131',borderRadius:4,padding:'0.05rem 0.35rem',marginRight:'0.3rem',fontSize:'0.72rem'}}>
                          {tb.grade}
                        </span>
                      )}
                      {tb.date_fr}
                    </div>
                    <div style={{color:'#64748b',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                      {tb.formation}
                    </div>
                    <div style={{color:'#94a3b8',fontSize:'0.72rem',marginTop:'0.1rem'}}>
                      Prés. jour : {(tb.taux_presence_jour * 100).toFixed(1)}%
                      {' · '}Matin {tb.matin_horaire || tb.matin?.horaire || '—'} / Soir {tb.soir_horaire || tb.soir?.horaire || '—'}
                    </div>
                  </button>
                ))}
              </div>

              {pjSelection === null ? (
                loadingPj && !pjAllTableaux.length ? (
                  <TabSpinner label="Chargement de tous les tableaux…"/>
                ) : (
                <PointJournalierEnsemblePanel
                  items={pjAllTableaux}
                  tableaux={pjData.tableaux}
                  annee={pjAnnee}
                  onSelectIndividuel={setPjSelection}
                />
                )
              ) : (
                loadingPjDetail ? (
                  <div style={{display:'flex',alignItems:'center',gap:'0.5rem',color:'#64748b',padding:'2rem',background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)'}}>
                    <div className="spinner"/>Chargement du tableau…
                  </div>
                ) : pjDetail ? (
                  <div style={{ minWidth: 0 }}>
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-secondary mb-2"
                      onClick={()=>{ setPjSelection(null); setPjDetail(null) }}
                    >
                      <i className="bi bi-grid-3x3-gap me-1"/>Voir tous les tableaux
                    </button>
                    <PointJournalierTableauCPFAE tb={pjDetail} />
                  </div>
                ) : (
                  <div style={{ background: '#fff', borderRadius: 10, padding: '1.5rem', boxShadow: '0 1px 4px rgba(0,0,0,0.07)', color: '#64748b', fontSize: '0.85rem' }}>
                    Impossible de charger le détail de ce tableau. Réessayez ou actualisez la liste.
                  </div>
                )
              )}
            </div>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* Onglet — Alertes & Seuils (surveillance visuelle)                    */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      {onglet==='alertes' && (() => {
        const alertesSidebar = buildAlertesSidebarEntries(alertesMeta, alertes)
        const alertesEntry = alertesSelection ? alertesSidebar.find(e => e.id === alertesSelection) : null
        const alertesProps = {
          alertesMeta, alertes, seuils, seuilsForm, editSeuils, setEditSeuils, setSeuilsForm,
          canValidate, initSeuilsDefaut, initSeuilsLoading, saveSeuils,
          showGuideAlertes, setShowGuideAlertes,
          formationId, secretariatId,
          auditeursNotoires,
        }
        return (
        <div>
          <div style={{display:'flex',flexWrap:'wrap',gap:'0.5rem',alignItems:'center',marginBottom:'0.75rem'}}>
            <span style={{fontSize:'0.78rem',color:'#64748b'}}>
              Surveillance INJS — seuils et alertes
              {formationId && <> · <b>{(formations_liste||[]).find(f => String(f.id) === formationId)?.formation}</b></>}
              {secretariatId && <> · <b>{(secretariats_liste||[]).find(s => String(s.id) === secretariatId)?.nom}</b></>}
            </span>
            <div style={{marginLeft:'auto', display:'flex', gap:'0.35rem'}}>
              <button className="btn btn-sm btn-outline-secondary" onClick={() => { fetchSeuils(); fetchData(TAB_SECTIONS.alertes) }} disabled={loadingTab}>
                <i className="bi bi-arrow-clockwise me-1"/>Actualiser
              </button>
            </div>
          </div>

          <div style={{display:'grid',gridTemplateColumns:'minmax(220px,280px) 1fr',gap:'1rem',alignItems:'start'}}>
            <div style={{background:'#fff',borderRadius:10,boxShadow:'0 1px 4px rgba(0,0,0,0.07)',overflow:'hidden',maxHeight:'70vh',overflowY:'auto'}}>
              <div style={{padding:'0.65rem 0.85rem',background:'#f8fafc',borderBottom:'1px solid #e2e8f0',fontSize:'0.78rem',color:'#64748b',fontWeight:600}}>
                {alertesSidebar.length} vue{alertesSidebar.length > 1 ? 's' : ''}
              </div>
              <button
                type="button"
                onClick={()=>setAlertesSelection(null)}
                style={{
                  display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                  padding:'0.55rem 0.85rem', fontSize:'0.78rem', fontWeight:700,
                  background: alertesSelection === null ? '#e0f2fe' : '#fff',
                  borderBottom:'2px solid #e2e8f0', color: alertesSelection === null ? '#0369a1' : '#475569',
                }}
              >
                <i className="bi bi-grid-3x3-gap me-1"/>
                Tous les widgets
              </button>
              {['sections', 'indicateurs'].map(group => {
                const items = alertesSidebar.filter(e => e.group === group)
                if (!items.length) return null
                const groupLabel = group === 'sections' ? 'Sections' : 'Indicateurs'
                return (
                  <div key={group}>
                    <div style={{padding:'0.4rem 0.85rem',fontSize:'0.68rem',fontWeight:700,color:'#94a3b8',background:'#fafbfc',borderBottom:'1px solid #f1f5f9'}}>
                      {groupLabel}
                    </div>
                    {items.map(entry => (
                      <button
                        key={entry.id}
                        type="button"
                        onClick={()=>setAlertesSelection(entry.id)}
                        style={{
                          display:'block', width:'100%', textAlign:'left', border:'none', cursor:'pointer',
                          padding:'0.55rem 0.85rem', fontSize:'0.78rem',
                          background: alertesSelection===entry.id ? '#e8eef6' : '#fff',
                          borderBottom:'1px solid #f1f5f9',
                        }}
                      >
                        <div style={{fontWeight:700, color:'#1e293b', marginBottom:'0.1rem'}}>
                          <i className={`bi ${entry.icon} me-1`} style={{color:entry.tagColor}}/>
                          <span style={{
                            background:`${entry.tagColor}18`, color:entry.tagColor, borderRadius:4,
                            padding:'0.05rem 0.35rem', marginRight:'0.3rem', fontSize:'0.68rem',
                          }}>{entry.tag}</span>
                          <span style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',display:'inline-block',maxWidth:'calc(100% - 2.8rem)',verticalAlign:'bottom'}}>
                            {entry.label}
                          </span>
                        </div>
                        <div style={{color:'#94a3b8', fontSize:'0.72rem'}}>{entry.sub}</div>
                      </button>
                    ))}
                  </div>
                )
              })}
            </div>

            {alertesSelection === null ? (
              <AlertesEnsemblePanel {...alertesProps} onSelectWidget={setAlertesSelection} />
            ) : alertesEntry ? (
              <div style={{ minWidth: 0 }}>
                <button
                  type="button"
                  className="btn btn-sm btn-outline-secondary mb-2"
                  onClick={()=>setAlertesSelection(null)}
                >
                  <i className="bi bi-grid-3x3-gap me-1"/>Voir tous les widgets
                </button>
                <AlertesWidgetDetailPanel
                  entry={alertesEntry}
                  {...alertesProps}
                  onGoSeuils={() => setAlertesSelection('seuils')}
                />
              </div>
            ) : (
              <Empty label="Widget introuvable"/>
            )}
          </div>
        </div>
        )
      })()}
    </div>
  )
}

// ── Point journalier (format CPFAE — voir PointJournalierCPFAE.jsx) ───────────

function PointJournalierEnsemblePanel({ items, tableaux, annee, onSelectIndividuel }) {
  const selectTableau = (tableauId) => {
    const idx = (tableaux || []).findIndex(tb => tb.id === tableauId)
    if (idx >= 0) onSelectIndividuel(idx)
  }

  if (!items?.length) {
    return (
      <div style={{
        background: '#fff', borderRadius: 10, padding: '2rem', textAlign: 'center',
        boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      }}>
        <Empty label="Aucun tableau à afficher pour cette sélection"/>
      </div>
    )
  }

  return (
    <div style={{
      background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      overflow: 'hidden', minWidth: 0,
    }}>
      <div style={{
        padding: '0.85rem 1rem', background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 100%)',
        borderBottom: '1px solid #e2e8f0', position: 'sticky', top: 0, zIndex: 2,
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <i className="bi bi-grid-3x3-gap me-2" style={{ color: '#EDB131' }}/>
          {items.length} tableau{items.length > 1 ? 'x' : ''} — Point journalier {annee}
        </h3>
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>
          Vue d&apos;ensemble de tous les points journaliers filtrés.
          Utilisez le panneau de gauche pour afficher un seul tableau en plein écran.
        </p>
      </div>
      <div style={{ maxHeight: '62vh', overflowY: 'auto', padding: '1rem' }}>
        {items.map((entry, i) => (
          <div
            key={entry.tableau_id}
            id={`pj-tableau-${entry.tableau_id}`}
            style={{
              marginBottom: i < items.length - 1 ? '1.75rem' : 0,
              paddingBottom: i < items.length - 1 ? '1.75rem' : 0,
              borderBottom: i < items.length - 1 ? '2px dashed #e2e8f0' : 'none',
            }}
          >
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
              gap: '0.5rem', marginBottom: '0.65rem', flexWrap: 'wrap',
            }}>
              <div>
                <div style={{ fontWeight: 800, fontSize: '0.88rem', color: '#1e293b' }}>
                  <span style={{
                    background: '#EDB13118', color: '#EDB131', borderRadius: 4,
                    padding: '0.05rem 0.35rem', marginRight: '0.3rem', fontSize: '0.72rem',
                  }}>CAT {entry.meta?.categorie}</span>
                  {entry.meta?.date_fr} — {entry.meta?.formation}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  Prés. jour : {pjPct(entry.meta?.taux_presence_jour ?? 0)}
                </div>
              </div>
              <button
                type="button"
                className="btn btn-sm btn-outline-warning"
                style={{ fontSize: '0.72rem', flexShrink: 0 }}
                onClick={() => selectTableau(entry.tableau_id)}
              >
                <i className="bi bi-arrows-fullscreen me-1"/>Plein écran
              </button>
            </div>
            <PointJournalierTableauCPFAE tb={entry.tableau} />
          </div>
        ))}
      </div>
    </div>
  )
}

function fmtNbFR(n) {
  return new Intl.NumberFormat('fr-FR').format(n ?? 0)
}

function fmtPctFR(n) {
  return (n ?? 0).toFixed(2).replace('.', ',')
}

function normalizeJustificatifs(value) {
  if (!value) return ''
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.filter(Boolean).map(j => `• ${j}`).join('\n')
  return ''
}

// Exporté pour les tests unitaires de la synchro des justificatifs (§10.7) ;
// le rendu applicatif passe par BilanDetailPanel ci-dessous.
export function BilanPeriodeFormationTable({ data, justificatifsText = '', onJustificatifsChange }) {
  const th = {
    padding: '0.4rem 0.35rem',
    border: '1px solid #000',
    fontWeight: 700,
    fontSize: '0.65rem',
    textAlign: 'center',
    verticalAlign: 'middle',
    lineHeight: 1.2,
    background: '#FCE7B4',
  }
  const thDark = { ...th, background: '#F4CF84' }
  const td = {
    padding: '0.45rem 0.35rem',
    border: '1px solid #000',
    textAlign: 'center',
    verticalAlign: 'middle',
    fontSize: '0.78rem',
    fontWeight: 700,
    background: '#FFFDF5',
  }
  const tdBlue = { ...td, background: '#DDEBF7' }
  const tdTotal = { ...td, background: '#FFE566' }

  const [justifText, setJustifText] = useState(() => (
    justificatifsText || normalizeJustificatifs(data?.justificatifs)
  ))

  useEffect(() => {
    // `data?.justificatifs` est bien une dépendance voulue (écart §10.7 tranché
    // LOT 6) : un justificatif serveur reçu pour une ligne DÉJÀ affichée (mêmes
    // titre/formation/année, ex. rafraîchissement) doit synchroniser le champ.
    // La saisie reste prioritaire : quand le parent porte déjà un texte, le
    // `justificatifsText ||` court-circule la valeur serveur et n'écrase rien.
    setJustifText(justificatifsText || normalizeJustificatifs(data?.justificatifs))
  }, [data?.titre, data?.formation_id, data?.annee, data?.justificatifs, justificatifsText])

  const handleJustifChange = (e) => {
    const next = e.target.value
    setJustifText(next)
    onJustificatifsChange?.(next)
  }

  const Soit = ({ children }) => (
    <div style={{ fontSize: '0.65rem', fontWeight: 600, marginTop: '0.2rem' }}>
      <span style={{ textDecoration: 'underline' }}>Soit</span> {children}
    </div>
  )
  const InscritsCell = ({ t, full = true }) => (
    full ? (
      <>
        <div>{fmtNbFR(t.inscrits_actifs)} / {fmtNbFR(t.inscrits_reference)}</div>
        <Soit>{fmtPctFR(t.pct_inscrits)}%</Soit>
      </>
    ) : (
      <div>{fmtNbFR(t.inscrits_actifs)}</div>
    )
  )
  const AbsentsCell = ({ t, full = true }) => (
    full ? (
      <>
        <div>{fmtNbFR(t.absents_notoires)}</div>
        {t.inscrits_reference > 0 && (
          <Soit>{fmtPctFR(t.pct_absents)}% de l&apos;effectif</Soit>
        )}
      </>
    ) : (
      <div>{String(t.absents_notoires).padStart(2, '0')}</div>
    )
  )

  const firstRowKey = (() => {
    const l = data.lignes[0]
    if (!l) return null
    if (l.multi_grade && l.sous_lignes?.length) return `${l.categorie}-${l.sous_lignes[0].grade}`
    return l.categorie
  })()

  const nbJustifRows = data.lignes.reduce((acc, l) => {
    if (l.multi_grade && l.sous_lignes?.length) return acc + l.sous_lignes.length + 1
    return acc + 1
  }, 0) + 1

  const justificatifsCell = (
    <td rowSpan={nbJustifRows} style={{ ...td, fontWeight: 500, fontSize: '0.72rem', textAlign: 'left', verticalAlign: 'top', minWidth: 160, padding: '0.35rem' }}>
      <textarea
        className="form-control form-control-sm"
        value={justifText}
        onChange={handleJustifChange}
        placeholder={'Saisir les justificatifs…\n• Report de formation\n• Maladie'}
        rows={Math.max(5, nbJustifRows + 1)}
        style={{
          width: '100%',
          minHeight: 120,
          fontSize: '0.72rem',
          lineHeight: 1.45,
          resize: 'vertical',
          border: '1px solid #cbd5e1',
          background: '#fff',
        }}
      />
    </td>
  )

  let justifPlaced = false

  const renderDataRows = () => data.lignes.flatMap((ligne) => {
    const rows = []
    if (ligne.multi_grade && ligne.sous_lignes?.length) {
      ligne.sous_lignes.forEach((sl, idx) => {
        const rowKey = `${ligne.categorie}-${sl.grade}`
        rows.push(
          <tr key={rowKey}>
            {idx === 0 && (
              <td rowSpan={ligne.sous_lignes.length + 1} style={{ ...td, fontSize: '0.9rem' }}>
                {ligne.categorie}
              </td>
            )}
            <td style={td}>{sl.grade}</td>
            <td style={td}>{String(sl.nb_groupes).padStart(2, '0')}</td>
            {idx === 0 && (
              <>
                <td rowSpan={ligne.sous_lignes.length + 1} style={td}>
                  {String(ligne.totaux.nb_encadrants).padStart(2, '0')}
                </td>
                <td rowSpan={ligne.sous_lignes.length + 1} style={td}>
                  {ligne.totaux.effectif_secretariat}
                </td>
              </>
            )}
            <td style={td}><InscritsCell t={sl} full={false} /></td>
            <td style={tdBlue}>{fmtNbFR(sl.auditeurs_listes)}</td>
            <td style={td}><AbsentsCell t={sl} full={false} /></td>
            {rowKey === firstRowKey && !justifPlaced && (justifPlaced = true) && justificatifsCell}
          </tr>,
        )
      })
      rows.push(
        <tr key={`${ligne.categorie}-tot`}>
          <td style={{ ...td, fontStyle: 'italic', color: '#64748b' }}>Σ</td>
          <td style={td}>{String(ligne.totaux.nb_groupes).padStart(2, '0')}</td>
          <td style={td}><InscritsCell t={ligne.totaux} /></td>
          <td style={tdBlue}>{fmtNbFR(ligne.totaux.auditeurs_listes)}</td>
          <td style={td}><AbsentsCell t={ligne.totaux} /></td>
        </tr>,
      )
    } else {
      const t = ligne.totaux
      rows.push(
        <tr key={ligne.categorie}>
          <td colSpan={2} style={td}>{ligne.categorie}</td>
          <td style={td}>{String(t.nb_groupes).padStart(2, '0')}</td>
          <td style={td}>{String(t.nb_encadrants).padStart(2, '0')}</td>
          <td style={td}>{t.effectif_secretariat}</td>
          <td style={td}><InscritsCell t={t} /></td>
          <td style={tdBlue}>{fmtNbFR(t.auditeurs_listes)}</td>
          <td style={td}><AbsentsCell t={t} /></td>
          {ligne.categorie === firstRowKey && !justifPlaced && (justifPlaced = true) && justificatifsCell}
        </tr>,
      )
    }
    return rows
  })

  return (
    <div style={{ overflowX: 'auto' }}>
      <h3 style={{
        textAlign: 'center', fontWeight: 700, fontSize: '0.85rem',
        textDecoration: 'underline', textTransform: 'uppercase',
        margin: '0 0 0.85rem', color: '#1e293b', lineHeight: 1.35,
      }}>
        {data.titre}
      </h3>
      <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
        <thead>
          <tr>
            <th style={th} colSpan={2}>CATEGORIE / GRADE</th>
            <th style={th}>NBRE DE GRPES</th>
            <th style={th}>NBRE D&apos;ENCADRANTS</th>
            <th style={th}>EFFECTIF MEMBRE DE SECRETARIAT</th>
            <th style={thDark}>EFFECTIF DES INSCRITS AU {data.date_inscrits}</th>
            <th style={th}>EFFECTIF DES AUDITEURS SUR LES LISTES DE CLASSES</th>
            <th style={th}>EFFECTIF DES AUDITEURS ABSENTS NOTOIRES</th>
            <th style={th}>JUSTIFICATIFS DES ABSENCES NOTOIRES</th>
          </tr>
        </thead>
        <tbody>
          {renderDataRows()}
          <tr>
            <td colSpan={2} style={tdTotal}>TOTAL</td>
            <td style={tdTotal}>{String(data.total.nb_groupes).padStart(2, '0')}</td>
            <td style={tdTotal}>{String(data.total.nb_encadrants).padStart(2, '0')}</td>
            <td style={tdTotal}>{data.total.effectif_secretariat}</td>
            <td style={tdTotal}><InscritsCell t={data.total} /></td>
            <td style={tdTotal}>{fmtNbFR(data.total.auditeurs_listes)}</td>
            <td style={tdTotal}>{fmtNbFR(data.total.absents_notoires)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

// ── Bilan FAC ─────────────────────────────────────────────────────────────────

const FAC_SOUS_ONGLETS = [
  { id: 'point_global',    label: 'Point global',       icon: 'bi-table' },
  { id: 'vh_par_groupe',   label: 'Volume horaire',     icon: 'bi-clock-history' },
  { id: 'absents',         label: 'Absents notoires',   icon: 'bi-person-x-fill' },
  { id: 'modules',         label: 'État des modules',   icon: 'bi-check2-square' },
]

function fmtVH(n) {
  if (n == null) return '—'
  const v = Number(n)
  return v === Math.round(v) ? String(Math.round(v)) : v.toFixed(2)
}

function fmtTauxPct(n, decimals = 2) {
  if (n == null) return '—'
  return `${Number(n).toFixed(decimals).replace('.', ',')} %`
}

const FAC_TH = {
  padding: '0.4rem 0.35rem',
  border: '1px solid #000',
  fontWeight: 700,
  fontSize: '0.6rem',
  textAlign: 'center',
  verticalAlign: 'middle',
  lineHeight: 1.2,
  background: '#FCEFD6',
  whiteSpace: 'normal',
}
const FAC_TH_DARK = { ...FAC_TH, background: '#F4CF84' }
const FAC_TH_YELLOW = { ...FAC_TH, background: '#EDB131', color: '#fff' }
const FAC_TD = {
  padding: '0.45rem 0.35rem',
  border: '1px solid #000',
  textAlign: 'center',
  verticalAlign: 'middle',
  fontSize: '0.75rem',
  fontWeight: 700,
  background: '#FFFDF5',
}
const FAC_TD_BLUE = { ...FAC_TD, background: '#DDEBF7' }
const FAC_TD_YELLOW = { ...FAC_TD, background: '#FFE566' }
const FAC_TD_BLUE_SOFT = { ...FAC_TD, background: '#DAE7EF' }
const FAC_TD_RED = { ...FAC_TD, background: '#FCEFD6' }
const FAC_TD_TEXT = { ...FAC_TD, textAlign: 'left', fontWeight: 500, fontSize: '0.7rem' }

function BilanFACPointGlobalTable({ data, onMetaChange }) {
  const lignesRaw = data?.lignes || []
  const totaux = data?.totaux || {}

  const [justifByGrade, setJustifByGrade] = useState({})
  const [difficultesByGrade, setDifficultesByGrade] = useState({})

  const updateJustif = (grade, text) => {
    setJustifByGrade(prev => ({ ...prev, [grade]: text }))
  }

  const updateDifficultes = (grade, text) => {
    setDifficultesByGrade(prev => ({ ...prev, [grade]: text }))
  }

  useEffect(() => {
    setJustifByGrade({})
    setDifficultesByGrade({})
  }, [data?.formation_id, data?.annee, data?.date_generation])

  useEffect(() => {
    onMetaChange?.({ justificatifs: justifByGrade, difficultes: difficultesByGrade })
  }, [justifByGrade, difficultesByGrade, onMetaChange])

  // Agréger les lignes par grade (évite les doublons)
  const lignesMap = new Map()
  for (const l of lignesRaw) {
    const grade = l.grade?.trim()
    if (!grade) continue
    if (!lignesMap.has(grade)) {
      lignesMap.set(grade, { ...l, grade })
    } else {
      const existing = lignesMap.get(grade)
      // Sommer les valeurs numériques. L'effectif auditeurs est cumulé à part
      // (ci-dessous) : sa valeur courante sert de poids aux moyennes, donc le
      // sommer ici (via une clé) fausserait les poids en comptant la nouvelle
      // ligne deux fois.
      const sumKeys = ['effectif_secretariat', 'nb_encadrants', 'nb_groupes',
        'absents_notoires', 'groupes_termines', 'vh_total', 'vh_epuise']
      for (const k of sumKeys) {
        existing[k] = (existing[k] || 0) + (l[k] || 0)
      }
      // Moyenne pondérée pour les taux ; n1 = effectif déjà cumulé, n2 =
      // effectif de la ligne fusionnée. Le cumul de l'effectif est posé APRÈS
      // lecture des poids (§10.15, corrigé au LOT 44 : la clé erronée
      // 'effectif_étudiants' laissait l'effectif figé à la première ligne).
      const n1 = existing.effectif_auditeurs || 0
      const n2 = l.effectif_auditeurs || 0
      const total = n1 + n2
      existing.effectif_auditeurs = total
      if (total > 0) {
        const w1 = n1 / total
        const w2 = n2 / total
        existing.taux_participation = (existing.taux_participation || 0) * w1 + (l.taux_participation || 0) * w2
        existing.taux_absents_notoires = (existing.taux_absents_notoires || 0) * w1 + (l.taux_absents_notoires || 0) * w2
        existing.taux_presence_cours = (existing.taux_presence_cours || 0) * w1 + (l.taux_presence_cours || 0) * w2
        existing.taux_absence_cours = (existing.taux_absence_cours || 0) * w1 + (l.taux_absence_cours || 0) * w2
        existing.taux_exec_vh = (existing.taux_exec_vh || 0) * w1 + (l.taux_exec_vh || 0) * w2
      }
      // Fusionner les justificatifs (legacy liste → ignorée, champ libre côté UI)
      existing.justificatifs = existing.justificatifs || ''
    }
  }
  const lignes = Array.from(lignesMap.values()).sort((a, b) => a.grade.localeCompare(b.grade))

  const pctStr = (n) => {
    if (n == null) return '—'
    const v = Number(n)
    if (v <= 1 && v >= 0 && String(n).indexOf('.') > -1) return `${(v * 100).toFixed(2).replace('.', ',')} %`
    return `${v.toFixed(2).replace('.', ',')} %`
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', minWidth: 1400, fontSize: '0.62rem', width: '100%' }}>
        <thead>
          <tr>
            <th style={{ ...FAC_TH, minWidth: 80 }}>CATÉGORIE / GRADE</th>
            <th style={FAC_TH}>EFFECTIF DES MEMBRES DE SECRÉTARIAT</th>
            <th style={FAC_TH}>EFFECTIF DES ENCADREURS</th>
            <th style={FAC_TH}>NOMBRE DE GROUPES</th>
            <th style={{ ...FAC_TH_DARK, minWidth: 60 }}>EFFECTIF TOTAL DES AUDITEURS</th>
            <th style={FAC_TH}>EFFECTIF TOTAL DES AUDITEURS ABSENTS NOTOIRES</th>
            <th style={FAC_TH}>GROUPES AYANT TERMINÉ LA FORMATION</th>
            <th style={{ ...FAC_TH, minWidth: 120 }}>JUSTIFICATIFS DES ABSENCES NOTOIRES</th>
            <th style={FAC_TH}>TAUX DE PARTICIPATION</th>
            <th style={FAC_TH}>TAUX DES AUDITEURS ABSENTS NOTOIRES</th>
            <th style={{ ...FAC_TH_YELLOW, minWidth: 55 }}>TOTAL VOLUME HORAIRE</th>
            <th style={{ ...FAC_TH_YELLOW, minWidth: 55 }}>TOTAL VOLUME HORAIRE ÉPUISÉ</th>
            <th style={{ ...FAC_TH_YELLOW }}>TAUX D&apos;EXÉCUTION DU VOLUME HORAIRE</th>
            <th style={{ ...FAC_TH, background: '#BDD7EE' }}>TAUX DE PRÉSENCE AUX COURS</th>
            <th style={{ ...FAC_TH, background: '#F8E0AD' }}>TAUX D&apos;ABSENCE AUX COURS</th>
            <th style={{ ...FAC_TH, minWidth: 140 }}>DIFFICULTÉS RENCONTRÉES</th>
          </tr>
        </thead>
        <tbody>
          {lignes.map((l, i) => (
            <tr key={l.grade || i}>
              <td style={{ ...FAC_TD, fontWeight: 800, background: '#FCEFD6' }}>
                {l.grade}
              </td>
              <td style={FAC_TD}>{l.effectif_secretariat ?? '—'}</td>
              <td style={FAC_TD}>{l.nb_encadrants ?? '—'}</td>
              <td style={FAC_TD}>{l.nb_groupes ?? '—'}</td>
              <td style={{ ...FAC_TD_BLUE, fontWeight: 800 }}>{l.effectif_auditeurs ?? '—'}</td>
              <td style={FAC_TD}>{l.absents_notoires ?? '—'}</td>
              <td style={FAC_TD_BLUE_SOFT}>{l.groupes_termines ?? '—'}</td>
              <td style={{ ...FAC_TD_TEXT, verticalAlign: 'top', padding: '0.35rem' }}>
                <textarea
                  className="form-control form-control-sm"
                  value={justifByGrade[l.grade] ?? normalizeJustificatifs(l.justificatifs)}
                  onChange={e => updateJustif(l.grade, e.target.value)}
                  placeholder="Justificatifs (saisie libre)…"
                  rows={4}
                  style={{
                    width: '100%',
                    minWidth: 110,
                    fontSize: '0.68rem',
                    lineHeight: 1.45,
                    resize: 'vertical',
                    border: '1px solid #cbd5e1',
                  }}
                />
              </td>
              <td style={FAC_TD_BLUE}>{pctStr(l.taux_participation)}</td>
              <td style={FAC_TD_RED}>{pctStr(l.taux_absents_notoires)}</td>
              <td style={{ ...FAC_TD, background: '#FCEFD6', fontWeight: 800 }}>{fmtVH(l.vh_total)}</td>
              <td style={{ ...FAC_TD, background: '#FCEFD6', fontWeight: 800 }}>{fmtVH(l.vh_epuise)}</td>
              <td style={{ ...FAC_TD, background: '#FCEFD6' }}>{pctStr(l.taux_exec_vh)}</td>
              <td style={{ ...FAC_TD, background: '#BDD7EE' }}>{pctStr(l.taux_presence_cours)}</td>
              <td style={{ ...FAC_TD, background: '#F8E0AD' }}>{pctStr(l.taux_absence_cours)}</td>
              <td style={{ ...FAC_TD_TEXT, verticalAlign: 'top', padding: '0.35rem' }}>
                <textarea
                  className="form-control form-control-sm"
                  value={difficultesByGrade[l.grade] ?? (l.difficultes || '')}
                  onChange={e => updateDifficultes(l.grade, e.target.value)}
                  placeholder="Difficultés rencontrées (saisie libre)…"
                  rows={4}
                  style={{
                    width: '100%',
                    minWidth: 120,
                    fontSize: '0.68rem',
                    lineHeight: 1.45,
                    resize: 'vertical',
                    border: '1px solid #cbd5e1',
                    color: '#C62828',
                  }}
                />
              </td>
            </tr>
          ))}
          {/* Ligne TOTAL */}
          <tr>
            <td style={{ ...FAC_TD_YELLOW, fontWeight: 800, textAlign: 'left' }}>TOTAL</td>
            <td style={FAC_TD_YELLOW}>{totaux.effectif_secretariat ?? '—'}</td>
            <td style={FAC_TD_YELLOW}>{totaux.nb_encadrants ?? '—'}</td>
            <td style={FAC_TD_YELLOW}>{totaux.nb_groupes ?? '—'}</td>
            <td style={{ ...FAC_TD_YELLOW, fontWeight: 800 }}>{totaux.effectif_auditeurs ?? '—'}</td>
            <td style={FAC_TD_YELLOW}>{totaux.absents_notoires ?? '—'}</td>
            <td style={FAC_TD_YELLOW}>{totaux.groupes_termines ?? '—'}</td>
            <td style={FAC_TD_YELLOW}>—</td>
            <td style={FAC_TD_YELLOW}>—</td>
            <td style={FAC_TD_YELLOW}>—</td>
            <td style={{ ...FAC_TD_YELLOW, fontWeight: 800 }}>{fmtVH(totaux.vh_total)}</td>
            <td style={{ ...FAC_TD_YELLOW, fontWeight: 800 }}>{fmtVH(totaux.vh_epuise)}</td>
            <td style={FAC_TD_YELLOW}>{pctStr(totaux.taux_exec_vh)}</td>
            <td style={FAC_TD_YELLOW}>—</td>
            <td style={FAC_TD_YELLOW}>—</td>
            <td style={FAC_TD_YELLOW}>—</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function BilanFACVHParGradeTable({ vhParGrade }) {
  if (!vhParGrade?.length) return <Empty label="Aucune donnée de volume horaire"/>

  const VH_ROWS = [
    { key: 'vh_prevu',      label: 'VOLUME HORAIRE DU CYCLE DE FORMATION', style: FAC_TD },
    { key: 'vh_epuise',     label: 'VOLUME HORAIRE ÉPUISÉ',                style: FAC_TD },
    { key: 'taux_execution',label: "TAUX D'EXÉCUTION (%)",                 style: FAC_TD_BLUE_SOFT },
    { key: 'vh_restant',    label: 'VOLUME HORAIRE RESTANT',               style: FAC_TD },
    { key: 'taux_restant',  label: 'TAUX DU VOLUME HORAIRE RESTANT (%)',   style: FAC_TD_RED },
  ]

  return (
    <div>
      {vhParGrade.map(gradeBlock => {
        // Agréger les groupes identiques (sommer les VH)
        const groupesRaw = gradeBlock.groupes || []
        const groupesMap = new Map()
        for (const g of groupesRaw) {
          const grpName = (g.groupe || '').trim()
          if (!grpName) continue
          if (!groupesMap.has(grpName)) {
            groupesMap.set(grpName, { ...g, groupe: grpName })
          } else {
            const existing = groupesMap.get(grpName)
            existing.vh_prevu = (existing.vh_prevu || 0) + (g.vh_prevu || 0)
            existing.vh_epuise = (existing.vh_epuise || 0) + (g.vh_epuise || 0)
            existing.vh_restant = (existing.vh_restant || 0) + (g.vh_restant || 0)
          }
        }
        const groupes = Array.from(groupesMap.values()).sort((a, b) =>
          a.groupe.localeCompare(b.groupe, undefined, { numeric: true })
        )
        const recap = gradeBlock.recap || {}
        return (
          <div key={gradeBlock.grade} style={{ marginBottom: '2rem' }}>
            <div style={{
              fontWeight: 800, fontSize: '0.82rem', color: '#1e293b',
              marginBottom: '0.5rem', padding: '0.3rem 0.6rem',
              background: '#FCEFD6', borderRadius: 6, display: 'inline-block',
            }}>
              Grade {gradeBlock.grade}
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', minWidth: 300, fontSize: '0.72rem' }}>
                <thead>
                  <tr>
                    <th style={{ ...FAC_TH, minWidth: 220, textAlign: 'left' }}>GROUPES</th>
                    {groupes.map(g => (
                      <th key={g.groupe} style={{ ...FAC_TH, minWidth: 55 }}>{g.groupe}</th>
                    ))}
                    <th style={{ ...FAC_TH_DARK, minWidth: 80 }}>RÉCAPITULATIF</th>
                  </tr>
                </thead>
                <tbody>
                  {VH_ROWS.map(row => (
                    <tr key={row.key}>
                      <td style={{ ...FAC_TD, textAlign: 'left', fontWeight: 600, background: '#FFF6CC' }}>
                        {row.label}
                      </td>
                      {groupes.map(g => {
                        const val = g[row.key]
                        const isRate = row.key.startsWith('taux')
                        return (
                          <td key={g.groupe} style={row.style}>
                            {isRate ? fmtTauxPct(val) : fmtVH(val)}
                          </td>
                        )
                      })}
                      <td style={{ ...FAC_TD_YELLOW, fontWeight: 800 }}>
                        {row.key.startsWith('taux') ? fmtTauxPct(recap[row.key]) : fmtVH(recap[row.key])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}

      {/* Récapitulatif global */}
      {vhParGrade.length > 1 && (
        <div style={{ marginTop: '1rem' }}>
          <div style={{
            fontWeight: 800, fontSize: '0.82rem', color: '#fff',
            background: '#EDB131', borderRadius: 6, padding: '0.3rem 0.6rem',
            display: 'inline-block', marginBottom: '0.5rem',
          }}>
            RÉCAPITULATIF GLOBAL
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', minWidth: 600, fontSize: '0.72rem' }}>
              <thead>
                <tr>
                  <th style={{ ...FAC_TH, textAlign: 'left', minWidth: 100 }}>CATÉGORIE</th>
                  <th style={FAC_TH}>VH CYCLE</th>
                  <th style={FAC_TH}>VH ÉPUISÉ</th>
                  <th style={FAC_TH}>TAUX D&apos;EXÉCUTION</th>
                  <th style={FAC_TH}>VH RESTANT</th>
                  <th style={FAC_TH}>TAUX VH RESTANT</th>
                </tr>
              </thead>
              <tbody>
                {vhParGrade.map(gb => (
                  <tr key={gb.grade}>
                    <td style={{ ...FAC_TD, textAlign: 'left', fontWeight: 700, background: '#FCEFD6' }}>
                      Grade {gb.grade}
                    </td>
                    <td style={FAC_TD}>{fmtVH(gb.recap.vh_prevu)}</td>
                    <td style={FAC_TD}>{fmtVH(gb.recap.vh_epuise)}</td>
                    <td style={FAC_TD_BLUE_SOFT}>{fmtTauxPct(gb.recap.taux_execution)}</td>
                    <td style={FAC_TD}>{fmtVH(gb.recap.vh_restant)}</td>
                    <td style={FAC_TD_RED}>{fmtTauxPct(gb.recap.taux_restant)}</td>
                  </tr>
                ))}
                <tr>
                  <td style={{ ...FAC_TD_YELLOW, fontWeight: 800, textAlign: 'left' }}>TOTAL</td>
                  <td style={{ ...FAC_TD_YELLOW, fontWeight: 800 }}>
                    {fmtVH(vhParGrade.reduce((s, g) => s + (g.recap.vh_prevu || 0), 0))}
                  </td>
                  <td style={{ ...FAC_TD_YELLOW, fontWeight: 800 }}>
                    {fmtVH(vhParGrade.reduce((s, g) => s + (g.recap.vh_epuise || 0), 0))}
                  </td>
                  <td style={FAC_TD_YELLOW}>
                    {(() => {
                      const tot = vhParGrade.reduce((s, g) => s + (g.recap.vh_prevu || 0), 0)
                      const epu = vhParGrade.reduce((s, g) => s + (g.recap.vh_epuise || 0), 0)
                      return tot ? fmtTauxPct(epu / tot * 100) : '—'
                    })()}
                  </td>
                  <td style={FAC_TD_YELLOW}>
                    {fmtVH(vhParGrade.reduce((s, g) => s + (g.recap.vh_restant || 0), 0))}
                  </td>
                  <td style={FAC_TD_YELLOW}>—</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function BilanFACAbsentsNotoiresTable({ absents }) {
  if (!absents?.length) return (
    <div style={{ textAlign: 'center', padding: '2rem', color: '#2277C1', fontSize: '0.85rem' }}>
      <i className="bi bi-check-circle" style={{ fontSize: '2rem', display: 'block', marginBottom: '0.5rem' }}/>
      Aucun absent notoire enregistré.
    </div>
  )

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', minWidth: 900, fontSize: '0.73rem', width: '100%' }}>
        <thead>
          <tr>
            <th style={{ ...FAC_TH, minWidth: 35 }}>N°</th>
            <th style={{ ...FAC_TH, minWidth: 130 }}>N° CONCOURS (MATRICULE)</th>
            <th style={{ ...FAC_TH, minWidth: 100 }}>NOM</th>
            <th style={{ ...FAC_TH, minWidth: 120 }}>PRÉNOMS</th>
            <th style={{ ...FAC_TH, minWidth: 160 }}>LIBELLÉ DU CONCOURS</th>
            <th style={{ ...FAC_TH, minWidth: 100 }}>CONTACTS</th>
            <th style={{ ...FAC_TH, minWidth: 70 }}>GRADE / GROUPE</th>
            <th style={{ ...FAC_TH, minWidth: 160 }}>OBSERVATIONS</th>
          </tr>
        </thead>
        <tbody>
          {absents.map((a, i) => (
            <tr key={a.matricule || i} style={{ background: i % 2 === 0 ? '#FFFDF5' : '#FFF9EC' }}>
              <td style={{ ...FAC_TD, fontWeight: 800 }}>{a.numero}</td>
              <td style={{ ...FAC_TD, fontFamily: 'monospace', fontSize: '0.68rem' }}>{a.matricule}</td>
              <td style={{ ...FAC_TD, textAlign: 'left', fontWeight: 700 }}>{a.nom}</td>
              <td style={{ ...FAC_TD, textAlign: 'left' }}>{a.prenom}</td>
              <td style={{ ...FAC_TD, textAlign: 'left', fontSize: '0.67rem' }}>{a.libelle_concours || '—'}</td>
              <td style={{ ...FAC_TD, fontFamily: 'monospace', fontSize: '0.68rem' }}>{a.contacts || '—'}</td>
              <td style={{ ...FAC_TD, fontWeight: 800 }}>
                {a.grade && a.groupe ? `${a.grade} / ${a.groupe}` : a.grade || a.groupe || '—'}
              </td>
              <td style={{ ...FAC_TD_TEXT, color: a.observations ? '#C62828' : '#94a3b8' }}>
                {a.observations || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '0.5rem', textAlign: 'right' }}>
        {absents.length} absent{absents.length > 1 ? 's' : ''} notoire{absents.length > 1 ? 's' : ''}
      </div>
    </div>
  )
}

function BilanFACModulesTable({ modules }) {
  if (!modules?.length) return <Empty label="Aucun module trouvé"/>

  const grades = [...new Set(modules.map(m => m.grade).filter(Boolean))].sort()

  const STATUT_STYLE = {
    TERMINEE:  { bg: '#DAE7EF', color: '#1063c5', label: 'Terminé' },
    EN_COURS:  { bg: '#DDEBF7', color: '#1565C0', label: 'En cours' },
    PLANIFIEE: { bg: '#FFF6CC', color: '#F5B100', label: 'Planifié' },
    SUSPENDUE: { bg: '#FCEFD6', color: '#C62828', label: 'Suspendu' },
  }

  return (
    <div>
      {grades.map(grade => {
        const mods = modules.filter(m => m.grade === grade)
        return (
          <div key={grade} style={{ marginBottom: '2rem' }}>
            <div style={{
              fontWeight: 800, fontSize: '0.82rem', color: '#1e293b',
              marginBottom: '0.5rem', padding: '0.3rem 0.6rem',
              background: '#FCEFD6', borderRadius: 6, display: 'inline-block',
            }}>
              Grade {grade}
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', minWidth: 400, fontSize: '0.72rem', width: '100%' }}>
                <thead>
                  <tr>
                    <th style={{ ...FAC_TH, textAlign: 'left', minWidth: 200 }}>MODULE</th>
                    <th style={FAC_TH}>GROUPE</th>
                    <th style={FAC_TH}>VH PRÉVU (h)</th>
                    <th style={FAC_TH}>VH RESTANT (h)</th>
                    <th style={FAC_TH}>DATE DÉBUT</th>
                    <th style={FAC_TH}>DATE FIN</th>
                    <th style={FAC_TH}>STATUT</th>
                  </tr>
                </thead>
                <tbody>
                  {mods.map((m, i) => {
                    const st = STATUT_STYLE[m.statut] || STATUT_STYLE.PLANIFIEE
                    return (
                      <tr key={m.id} style={{ background: i % 2 === 0 ? '#FFFDF5' : '#fff' }}>
                        <td style={{ ...FAC_TD, textAlign: 'left', fontWeight: 600, fontSize: '0.7rem' }}>{m.intitule}</td>
                        <td style={FAC_TD}>{m.groupe || '—'}</td>
                        <td style={FAC_TD}>{m.vh_prevu ? fmtVH(m.vh_prevu) : '—'}</td>
                        <td style={FAC_TD}>{m.vh_restant ? fmtVH(m.vh_restant) : '—'}</td>
                        <td style={FAC_TD}>{m.date_debut || '—'}</td>
                        <td style={FAC_TD}>{m.date_fin || '—'}</td>
                        <td style={{ ...FAC_TD, background: st.bg, color: st.color }}>
                          {st.label}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function BilanFACPanel({ data, sousOnglet, onChangeSousOnglet, onMetaChange, onExport, exportingFac }) {
  return (
    <div>
      {/* En-tête */}
      <div style={{
        background: 'linear-gradient(135deg,#FFFBF0 0%,#FEF7E2 100%)',
        borderRadius: 8, padding: '0.85rem 1rem', marginBottom: '1rem',
        border: '1px solid #FEE8AA',
      }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', gap: '0.75rem' }}>
          <div style={{ flex: '1 1 240px' }}>
            <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
              <i className="bi bi-file-earmark-bar-graph me-2" style={{ color: '#EDB131' }}/>
              {data.titre}
            </h3>
            <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.4rem', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                <i className="bi bi-calendar3 me-1"/>{data.annee}
              </span>
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                <i className="bi bi-card-list me-1"/>Grades : {(data.grades || []).join(', ') || '—'}
              </span>
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                <i className="bi bi-person-x me-1"/>Absents notoires : {data.absents_notoires?.length ?? 0}
              </span>
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                <i className="bi bi-printer me-1"/>Généré le {data.date_generation}
              </span>
            </div>
          </div>
          {onExport && (
            <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
              {PJ_EXPORT_FORMATS.map(({ fmt, icon, label, col }) => (
                <button
                  key={`fac-${fmt}`}
                  type="button"
                  className="btn btn-sm"
                  disabled={!!exportingFac}
                  style={{
                    background: col, color: '#fff', border: 'none', minWidth: 88,
                    opacity: exportingFac ? 0.65 : 1,
                  }}
                  onClick={() => onExport(fmt)}
                  title={`Exporter le bilan FAC (${label})`}
                >
                  {exportingFac === fmt ? (
                    <span className="spinner-border spinner-border-sm"/>
                  ) : (
                    <><i className={`bi ${icon} me-1`}/>{label}</>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Sous-onglets */}
      <div style={{ display: 'flex', gap: '0.3rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        {FAC_SOUS_ONGLETS.map(so => (
          <button
            key={so.id}
            type="button"
            onClick={() => onChangeSousOnglet(so.id)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
              padding: '0.4rem 0.8rem', borderRadius: 7, cursor: 'pointer',
              fontSize: '0.79rem', fontWeight: 600,
              border: sousOnglet === so.id ? '2px solid #EDB131' : '1px solid #e2e8f0',
              background: sousOnglet === so.id ? '#FFFBF0' : '#fff',
              color: sousOnglet === so.id ? '#C8891B' : '#64748b',
            }}
          >
            <i className={`bi ${so.icon}`}/>{so.label}
          </button>
        ))}
      </div>

      {/* Contenu selon sous-onglet */}
      <div style={{
        background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        border: '1px solid #f1f5f9', padding: '1rem',
      }}>
        {sousOnglet === 'point_global' && (
          <>
            <h4 style={{
              textAlign: 'center', fontWeight: 700, fontSize: '0.82rem',
              textDecoration: 'underline', textTransform: 'uppercase',
              marginBottom: '1rem', color: '#1e293b',
            }}>
              POINT GLOBAL — {data.formation}
            </h4>
            <BilanFACPointGlobalTable data={data.point_global} onMetaChange={onMetaChange} />
          </>
        )}

        {sousOnglet === 'vh_par_groupe' && (
          <>
            <h4 style={{
              textAlign: 'center', fontWeight: 700, fontSize: '0.82rem',
              textDecoration: 'underline', textTransform: 'uppercase',
              marginBottom: '1rem', color: '#1e293b',
            }}>
              TABLEAU MENSUEL RÉCAPITULANT L&apos;ÉVOLUTION DES HORAIRES DE COURS — {data.formation}
            </h4>
            <BilanFACVHParGradeTable vhParGrade={data.vh_par_grade} />
          </>
        )}

        {sousOnglet === 'absents' && (
          <>
            <h4 style={{
              textAlign: 'center', fontWeight: 700, fontSize: '0.82rem',
              textDecoration: 'underline', textTransform: 'uppercase',
              marginBottom: '1rem', color: '#1e293b',
            }}>
              ÉTAT DES AUDITEURS ABSENTS NOTOIRES — {data.formation}
            </h4>
            <BilanFACAbsentsNotoiresTable absents={data.absents_notoires} />
          </>
        )}

        {sousOnglet === 'modules' && (
          <>
            <h4 style={{
              textAlign: 'center', fontWeight: 700, fontSize: '0.82rem',
              textDecoration: 'underline', textTransform: 'uppercase',
              marginBottom: '1rem', color: '#1e293b',
            }}>
              ÉTAT D&apos;AVANCEMENT DES MODULES — {data.formation}
            </h4>
            <BilanFACModulesTable modules={data.modules_statuts} />
          </>
        )}
      </div>
    </div>
  )
}

const OVERVIEW_SECTION_DEFS = [
  { id: 'alertes', tag: 'ALT', tagColor: '#C62828', label: 'Surveillance', icon: 'bi-bell' },
  { id: 'kpis', tag: 'KPI', tagColor: '#1565C0', label: 'Chiffres clés', icon: 'bi-speedometer2' },
  { id: 'pedagogie', tag: 'PED', tagColor: '#2277C1', label: 'Pédagogique', icon: 'bi-mortarboard' },
  { id: 'operationnel', tag: 'OPE', tagColor: '#7B1FA2', label: 'Opérationnel', icon: 'bi-gear' },
]

function buildOverviewSections(alertesItems) {
  const actives = (alertesItems || []).filter(
    a => ALERTES_OVERVIEW_CODES.includes(a.indicateur)
      && (a.niveau === 'critique' || a.niveau === 'avertissement'),
  )
  const crit = actives.filter(a => a.niveau === 'critique').length
  const avert = actives.filter(a => a.niveau === 'avertissement').length
  const alertesSub = actives.length
    ? `${actives.length} alerte${actives.length > 1 ? 's' : ''} (${crit} crit. · ${avert} avert.)`
    : 'Aucune alerte active'

  return OVERVIEW_SECTION_DEFS.map(def => ({
    ...def,
    sub: def.id === 'alertes' ? alertesSub
      : def.id === 'kpis' ? 'Formations, modules, étudiants, séances…'
      : def.id === 'pedagogie' ? 'Assiduité séance, couverture étudiants, absences'
      : def.id === 'operationnel' ? 'Répartition H/F, charge enseignants, absents notoires'
      : '',
  }))
}

function VueEnsemblePanel({ kpis, periode, loading, pedagogiques, adm, alertesOverview, onSelectSection, auditeursNotoires }) {
  return (
    <div style={{
      background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      overflow: 'hidden', minWidth: 0,
    }}>
      <div style={{
        padding: '0.85rem 1rem', background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 100%)',
        borderBottom: '1px solid #e2e8f0', position: 'sticky', top: 0, zIndex: 2,
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <i className="bi bi-speedometer2 me-2" style={{ color: 'var(--navy)' }}/>
          Vue d&apos;ensemble — synthèse
        </h3>
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>
          Indicateurs clés, surveillance et graphiques opérationnels.
          Choisissez une section à gauche pour le focus détaillé.
        </p>
        {periode?.label && (
          <div className="finance-period-badge" style={{ marginTop: '0.55rem' }}>
            <i className="bi bi-calendar-check"/>
            <div>
              <strong>Données filtrées : {periode.label}</strong>
              {periode.periode_label && (
                <span className="ms-1">— {periode.periode_label}</span>
              )}
            </div>
          </div>
        )}
      </div>
      <div style={{ maxHeight: '62vh', overflowY: 'auto', padding: '1rem', position: 'relative' }}>
        {loading && !kpis && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 3, background: 'rgba(255,255,255,0.85)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
            color: '#64748b', fontSize: '0.85rem',
          }}>
            <div className="spinner"/>Mise à jour des indicateurs…
          </div>
        )}
        <div
          style={{ marginBottom: '1rem', cursor: onSelectSection ? 'pointer' : undefined }}
          onClick={onSelectSection ? () => onSelectSection('alertes') : undefined}
          role={onSelectSection ? 'button' : undefined}
        >
          <AlertesOverviewBandeau items={alertesOverview} />
        </div>

        <div
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(175px,1fr))', gap: '0.85rem', marginBottom: '1.2rem' }}
          onClick={onSelectSection ? () => onSelectSection('kpis') : undefined}
          role={onSelectSection ? 'button' : undefined}
        >
          <Kpi icon="bi-journal-bookmark" label="Formations" value={kpis.formations} color="#1565C0" help={KPI_PERIOD_SCOPE_HELP}/>
          <Kpi icon="bi-book" label="Modules" value={kpis.modules} color="#2277C1" help={KPI_PERIOD_SCOPE_HELP}/>
          <Kpi icon="bi-people" label="Étudiants" value={kpis.participants} color="#F5B100" help={KPI_PERIOD_SCOPE_HELP}/>
          <Kpi icon="bi-person-video3" label="Enseignants" value={kpis.formateurs} color="#7B1FA2" help={KPI_PERIOD_SCOPE_HELP}/>
          <Kpi icon="bi-calendar-event" label={KPI_SESSIONS_TOTAL.label} value={kpis.sessions_total} color="#00838F"
            help={KPI_SESSIONS_TOTAL.help}/>
          <Kpi icon="bi-calendar-check" label={KPI_SESSIONS_COMPT.label} value={kpis.sessions_terminees} color="#082961"
            help={KPI_SESSIONS_COMPT.help}/>
          <Kpi icon="bi-clock-history" label="Vol. horaire prévu" value={`${fmtHeures(kpis.vh_prevu_heures)}h`} color="#0F70AB"/>
          <Kpi icon="bi-check2-all" label={KPI_VH_EXEC.label} value={`${kpis.taux_execution_vh}%`}
            color={kpis.taux_execution_vh >= 70 ? '#2277C1' : kpis.taux_execution_vh >= 40 ? '#F5B100' : '#C62828'}
            help={KPI_VH_EXEC.help}/>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '1rem', alignItems: 'start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div onClick={onSelectSection ? () => onSelectSection('pedagogie') : undefined} role={onSelectSection ? 'button' : undefined} style={{ cursor: onSelectSection ? 'pointer' : undefined }}>
              <Card title="Indicateurs pédagogiques" icon="bi-pie-chart">
                <PedagogieTauxPrincipaux ped={pedagogiques} auditeursNotoires={auditeursNotoires}/>
              </Card>
            </div>
            <div onClick={onSelectSection ? () => onSelectSection('operationnel') : undefined} role={onSelectSection ? 'button' : undefined} style={{ cursor: onSelectSection ? 'pointer' : undefined }}>
              <Card title="Charge des enseignants (top 8)" icon="bi-trophy">
                <HBars data={adm.charge_formateurs} labelKey="nom" valueKey="nb_sessions"/>
              </Card>
            </div>
          </div>

          <div onClick={onSelectSection ? () => onSelectSection('operationnel') : undefined} role={onSelectSection ? 'button' : undefined} style={{ cursor: onSelectSection ? 'pointer' : undefined }}>
            <Card title="Répartition Hommes / Femmes" icon="bi-gender-ambiguous">
              <Donut data={adm.participants_par_sexe} labelKey="sexe" valueKey="total"/>
              <div style={{ marginTop: '1rem', paddingTop: '0.85rem', borderTop: '1px solid #e2e8f0' }}>
                <p style={{ fontSize: '0.72rem', fontWeight: 600, color: '#64748b', marginBottom: '0.65rem', textAlign: 'center' }}>
                  Taux pédagogiques
                </p>
                <PedagogieTauxGrille ped={pedagogiques} grid/>
              </div>
            </Card>
          </div>
        </div>

        <div style={{ marginTop: '1rem' }}>
          <Card title={AUDITEURS_NOTOIRES.cardTitle} icon="bi-person-x-fill" col="1/-1">
            <AuditeursNotoiresPanel data={auditeursNotoires}/>
          </Card>
        </div>
      </div>
    </div>
  )
}

function VueOverviewDetailPanel({
  sectionId, kpis, periode, pedagogiques, adm, alertesOverview, onGoAlertes, onGoPedagogie, onGoAdmin, auditeursNotoires,
}) {
  const section = OVERVIEW_SECTION_DEFS.find(s => s.id === sectionId)
  const header = (
    <div style={{
      padding: '0.65rem 0.85rem', margin: '-1rem -1rem 1rem',
      background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 100%)',
      borderBottom: '1px solid #e2e8f0',
    }}>
      <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
        <i className={`bi ${section?.icon || 'bi-speedometer2'} me-2`} style={{ color: section?.tagColor || '#2277C1' }}/>
        {section?.label || sectionId}
      </h3>
      {periode?.label && (
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.75rem', color: '#64748b' }}>
          <i className="bi bi-calendar-check me-1"/>
          {periode.label}{periode.periode_label ? ` — ${periode.periode_label}` : ''}
        </p>
      )}
    </div>
  )

  if (sectionId === 'alertes') {
    const indicateurs = (alertesOverview || []).filter(a => ALERTES_OVERVIEW_CODES.includes(a.indicateur))
    return (
      <div style={{ background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)', padding: '1rem', minWidth: 0 }}>
        {header}
        {indicateurs.length ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: '0.85rem', marginBottom: '1rem' }}>
            {indicateurs.map((ind, i) => (
              <div key={ind.indicateur} style={{ animationDelay: `${i * 0.05}s` }}>
                <IndicateurSurveillanceCard ind={ind}/>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '1.5rem', color: '#64748b', fontSize: '0.85rem' }}>
            <i className="bi bi-check-circle" style={{ fontSize: '2rem', color: '#2277C1', display: 'block', marginBottom: '0.5rem' }}/>
            Aucune alerte active sur les 3 indicateurs clés.
          </div>
        )}
        {onGoAlertes && (
          <button type="button" className="btn btn-sm btn-outline-success" onClick={onGoAlertes}>
            <i className="bi bi-bell me-1"/>Configurer et voir toutes les alertes
          </button>
        )}
      </div>
    )
  }

  if (sectionId === 'kpis') {
    return (
      <div style={{ background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)', padding: '1rem', minWidth: 0 }}>
        {header}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(175px,1fr))', gap: '0.85rem' }}>
          <Kpi icon="bi-journal-bookmark" label="Formations" value={kpis.formations} color="#1565C0" help={KPI_PERIOD_SCOPE_HELP}/>
          <Kpi icon="bi-book" label="Modules" value={kpis.modules} color="#2277C1" help={KPI_PERIOD_SCOPE_HELP}/>
          <Kpi icon="bi-people" label="Étudiants" value={kpis.participants} color="#F5B100" help={KPI_PERIOD_SCOPE_HELP}/>
          <Kpi icon="bi-person-video3" label="Enseignants" value={kpis.formateurs} color="#7B1FA2" help={KPI_PERIOD_SCOPE_HELP}/>
          <Kpi icon="bi-calendar-event" label={KPI_SESSIONS_TOTAL.label} value={kpis.sessions_total} color="#00838F"
            help={KPI_SESSIONS_TOTAL.help}/>
          <Kpi icon="bi-calendar-check" label={KPI_SESSIONS_COMPT.label} value={kpis.sessions_terminees} color="#082961"
            help={KPI_SESSIONS_COMPT.help}/>
          <Kpi icon="bi-clock-history" label="Vol. horaire prévu" value={`${fmtHeures(kpis.vh_prevu_heures)}h`} color="#0F70AB"/>
          <Kpi icon="bi-check2-all" label={KPI_VH_EXEC.label} value={`${kpis.taux_execution_vh}%`}
            color={kpis.taux_execution_vh >= 70 ? '#2277C1' : kpis.taux_execution_vh >= 40 ? '#F5B100' : '#C62828'}
            help={KPI_VH_EXEC.help}/>
        </div>
        <p style={{ margin: '1rem 0 0', fontSize: '0.76rem', color: '#64748b' }}>
          Effectifs et volumes sur le périmètre filtré (séances comptabilisables).
        </p>
      </div>
    )
  }

  if (sectionId === 'pedagogie') {
    const ped = pedagogiques || {}
    return (
      <div style={{ background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)', padding: '1rem', minWidth: 0 }}>
        {header}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(140px,1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
          <Kpi icon="bi-person-check" label="Inscrits" value={ped.total_inscrits} color="#1565C0"/>
          <Kpi icon="bi-check-circle" label="Présents" value={ped.total_presents} color="#2277C1"/>
          <Kpi icon="bi-x-circle" label="Absents" value={ped.total_absents} color="#C62828"/>
          <Kpi icon="bi-arrow-right-circle" label="Événements" value={ped.total_abandons} color="#F5B100"
            help={TAUX_PEDAGOGIE.evenements.help}/>
        </div>
        <PedagogieTauxPrincipaux ped={ped} auditeursNotoires={auditeursNotoires}/>
        <Card title="Indicateurs pédagogiques" icon="bi-pie-chart">
          <PedagogieTauxGrille ped={ped} withBars/>
        </Card>
        <Card title={AUDITEURS_NOTOIRES.cardTitle} icon="bi-person-x-fill" col="1/-1">
          <AuditeursNotoiresPanel data={auditeursNotoires} maxHeight={360}/>
        </Card>
        {onGoPedagogie && (
          <button type="button" className="btn btn-sm btn-outline-success mt-2" onClick={onGoPedagogie}>
            <i className="bi bi-mortarboard me-1"/>Ouvrir l&apos;onglet Pédagogique
          </button>
        )}
      </div>
    )
  }

  if (sectionId === 'operationnel') {
    return (
      <div style={{ background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)', padding: '1rem', minWidth: 0 }}>
        {header}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
          <Card title="Répartition Hommes / Femmes" icon="bi-gender-ambiguous">
            <Donut data={adm.participants_par_sexe} labelKey="sexe" valueKey="total"/>
          </Card>
          <Card title="Charge des enseignants (top 8)" icon="bi-trophy" col="1/-1">
            <HBars data={adm.charge_formateurs} labelKey="nom" valueKey="nb_sessions"/>
          </Card>
        </div>
        <Card title={AUDITEURS_NOTOIRES.cardTitle} icon="bi-person-x-fill" col="1/-1">
          <AuditeursNotoiresPanel data={auditeursNotoires} maxHeight={480}/>
        </Card>
        {onGoAdmin && (
          <button type="button" className="btn btn-sm btn-outline-success mt-2" onClick={onGoAdmin}>
            <i className="bi bi-gear me-1"/>Ouvrir l&apos;onglet Administratif
          </button>
        )}
      </div>
    )
  }

  return <Empty label="Section non disponible"/>
}

function buildPedagogieEntries(ped) {
  if (!ped) return []
  const entries = []
  ;(ped.taux_par_formation || []).forEach(r => {
    entries.push({
      id: `formation-${r.formation_id}`,
      type: 'formation',
      tag: 'FOR',
      tagColor: '#1565C0',
      label: r.formation,
      sub: `${r.inscrits} inscrits · ${Number(r.taux).toFixed(1)}% prés.`,
      row: r,
    })
  })
  ;(ped.taux_par_grade || []).forEach((r, i) => {
    entries.push({
      id: `grade-${i}`,
      type: 'grade',
      tag: 'GRD',
      tagColor: '#7B1FA2',
      label: r.grade,
      sub: `${r.inscrits} inscrits · ${Number(r.taux).toFixed(1)}% prés.`,
      row: r,
    })
  })
  ;(ped.taux_par_secretariat || []).forEach(r => {
    entries.push({
      id: `secretariat-${r.secretariat_id}`,
      type: 'secretariat',
      tag: 'SEC',
      tagColor: '#F5B100',
      label: r.secretariat,
      sub: `${r.inscrits} inscrits · ${Number(r.taux).toFixed(1)}% prés.`,
      row: r,
    })
  })
  return entries
}

function PedagogiqueEnsemblePanel({ pedagogiques, pedEntries, onSelect, auditeursNotoires }) {
  const ped = pedagogiques || {}
  const an = auditeursNotoires || ped.auditeurs_notoires
  return (
    <div style={{
      background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      overflow: 'hidden', minWidth: 0,
    }}>
      <div style={{
        padding: '0.85rem 1rem', background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 100%)',
        borderBottom: '1px solid #e2e8f0', position: 'sticky', top: 0, zIndex: 2,
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <i className="bi bi-mortarboard me-2" style={{ color: 'var(--navy)' }}/>
          Pédagogique — vue d&apos;ensemble
        </h3>
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>
          Synthèse globale et répartitions par formation, grade et secrétariat.
          Sélectionnez un périmètre à gauche pour le détail.
        </p>
      </div>
      <div style={{ maxHeight: '62vh', overflowY: 'auto', padding: '1rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))', gap: '0.8rem', marginBottom: '1.1rem' }}>
          <Kpi icon="bi-person-check" label="Inscrits" value={ped.total_inscrits} color="#1565C0"/>
          <Kpi icon="bi-check-circle" label="Présents" value={ped.total_presents} color="#2277C1"/>
          <Kpi icon="bi-x-circle" label="Absents" value={ped.total_absents} color="#C62828"/>
          <Kpi icon="bi-arrow-right-circle" label="Événements" value={ped.total_abandons} color="#F5B100"
            help={TAUX_PEDAGOGIE.evenements.help}/>
        </div>
        <PedagogieTauxPrincipaux ped={ped} auditeursNotoires={an}/>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))', gap: '0.8rem', marginBottom: '1.1rem' }}>
          <Kpi icon="bi-percent" label={TAUX_PEDAGOGIE.absence.label} value={`${TAUX_PEDAGOGIE.absence.getValue(ped)}%`} color={TAUX_PEDAGOGIE.absence.color} help={TAUX_PEDAGOGIE.absence.help}/>
          <Kpi icon="bi-percent" label={TAUX_PEDAGOGIE.evenements.label} value={`${TAUX_PEDAGOGIE.evenements.getValue(ped)}%`} color={TAUX_PEDAGOGIE.evenements.color} help={TAUX_PEDAGOGIE.evenements.help}/>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(320px,1fr))', gap: '1rem' }}>
          <Card title="Assiduité séance par formation" icon="bi-building">
            {ped.taux_par_formation?.length ? (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                      {['Formation', 'Inscrits', 'Présents', 'Taux'].map(h => (
                        <th key={h} style={{ padding: '0.45rem 0.7rem', color: '#64748b', fontWeight: 600, textAlign: h === 'Formation' ? 'left' : 'center' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {ped.taux_par_formation.map((r) => {
                      const entryId = `formation-${r.formation_id}`
                      return (
                        <tr
                          key={entryId}
                          style={{ borderBottom: '1px solid #f1f5f9', cursor: onSelect ? 'pointer' : undefined }}
                          onClick={onSelect ? () => onSelect(entryId) : undefined}
                          onMouseEnter={onSelect ? e => { e.currentTarget.style.background = '#e8eef6' } : undefined}
                          onMouseLeave={onSelect ? e => { e.currentTarget.style.background = '' } : undefined}
                        >
                          <td style={{ padding: '0.45rem 0.7rem', color: '#1e293b', maxWidth: 260 }}>{r.formation}</td>
                          <td style={{ textAlign: 'center', padding: '0.45rem 0.7rem', color: '#64748b' }}>{r.inscrits}</td>
                          <td style={{ textAlign: 'center', padding: '0.45rem 0.7rem', color: '#2277C1', fontWeight: 600 }}>{r.presents}</td>
                          <td style={{ padding: '0.45rem 0.7rem', minWidth: 140 }}><TauxBar value={r.taux} small/></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : <Empty/>}
          </Card>

          <Card title="Assiduité séance par grade" icon="bi-bar-chart-steps">
            {ped.taux_par_grade?.length ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {ped.taux_par_grade.map((r, i) => (
                  <div
                    key={i}
                    style={{ cursor: onSelect ? 'pointer' : undefined }}
                    onClick={onSelect ? () => onSelect(`grade-${i}`) : undefined}
                    role={onSelect ? 'button' : undefined}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.79rem', marginBottom: '0.15rem' }}>
                      <b style={{ color: '#334155' }}>{r.grade}</b>
                      <span style={{ color: '#64748b' }}>{r.inscrits} inscrits</span>
                    </div>
                    <TauxBar value={r.taux} small/>
                  </div>
                ))}
              </div>
            ) : <Empty label="Aucun grade renseigné"/>}
          </Card>

          <Card title="Étudiants par type de concours" icon="bi-layers">
            <HBars data={ped.par_type_concours} labelKey="type" valueKey="total"/>
          </Card>

          {ped.taux_par_secretariat?.length > 0 && (
            <Card title="Assiduité séance par secrétariat" icon="bi-building">
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                      {['N°', 'Secrétariat', 'Inscrits', 'Présents', 'Taux'].map(h => (
                        <th key={h} style={{ padding: '0.45rem 0.7rem', color: '#64748b', fontWeight: 600, textAlign: h === 'Secrétariat' ? 'left' : 'center' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {ped.taux_par_secretariat.map(r => {
                      const entryId = `secretariat-${r.secretariat_id}`
                      return (
                        <tr
                          key={entryId}
                          style={{ borderBottom: '1px solid #f1f5f9', cursor: onSelect ? 'pointer' : undefined }}
                          onClick={onSelect ? () => onSelect(entryId) : undefined}
                          onMouseEnter={onSelect ? e => { e.currentTarget.style.background = '#e8eef6' } : undefined}
                          onMouseLeave={onSelect ? e => { e.currentTarget.style.background = '' } : undefined}
                        >
                          <td style={{ padding: '0.45rem 0.7rem', color: '#94a3b8', textAlign: 'center' }}>{r.numero}</td>
                          <td style={{ padding: '0.45rem 0.7rem', color: '#1e293b', fontWeight: 500 }}>{r.secretariat}</td>
                          <td style={{ textAlign: 'center', padding: '0.45rem 0.7rem', color: '#64748b' }}>{r.inscrits}</td>
                          <td style={{ textAlign: 'center', padding: '0.45rem 0.7rem', color: '#2277C1', fontWeight: 600 }}>{r.presents}</td>
                          <td style={{ padding: '0.45rem 0.7rem', minWidth: 130 }}><TauxBar value={r.taux} small/></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>

        <div style={{ marginTop: '1rem' }}>
          <Card title={AUDITEURS_NOTOIRES.cardTitle} icon="bi-person-x-fill" col="1/-1">
            <AuditeursNotoiresPanel data={an} maxHeight={360}/>
          </Card>
        </div>

        {pedEntries.length > 0 && (
          <p style={{ margin: '1rem 0 0', fontSize: '0.76rem', color: '#64748b' }}>
            <i className="bi bi-info-circle me-1"/>
            {pedEntries.length} périmètres listés à gauche — cliquez sur une ligne pour ouvrir le détail.
          </p>
        )}
      </div>
    </div>
  )
}

function PedagogiqueDetailPanel({ entry, pedagogiques, onGoSecretariat, auditeursNotoires }) {
  const ped = pedagogiques || {}
  const baseAn = auditeursNotoires || ped.auditeurs_notoires
  const an = entry.type === 'secretariat' && entry.row?.secretariat_id != null
    ? filterAuditeursNotoires(baseAn, { secretariatId: entry.row.secretariat_id })
    : baseAn
  const r = entry.row
  const typeLabel = entry.type === 'formation' ? 'Formation' : entry.type === 'grade' ? 'Grade' : 'Secrétariat'
  const ecart = r.taux != null && ped.taux_presence != null
    ? Math.round((r.taux - ped.taux_presence) * 10) / 10
    : null

  return (
    <div style={{
      background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      overflow: 'hidden', minWidth: 0, padding: '1rem',
    }}>
      <div style={{
        padding: '0.65rem 0.85rem', margin: '-1rem -1rem 1rem',
        background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 100%)',
        borderBottom: '1px solid #e2e8f0',
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <span style={{
            background: `${entry.tagColor}18`, color: entry.tagColor, borderRadius: 4,
            padding: '0.1rem 0.4rem', marginRight: '0.4rem', fontSize: '0.72rem',
          }}>{entry.tag}</span>
          {typeLabel} — {entry.label}
        </h3>
        {entry.type === 'secretariat' && r.numero != null && (
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>N° {r.numero}</p>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(140px,1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
        <Kpi icon="bi-person-check" label="Inscrits" value={r.inscrits} color="#1565C0"/>
        <Kpi icon="bi-check-circle" label="Présents" value={r.presents} color="#2277C1"/>
        <Kpi icon="bi-percent" label={TAUX_PEDAGOGIE.assiduite.label} value={`${Number(r.taux).toFixed(1)}%`} color={TAUX_PEDAGOGIE.assiduite.color} help={TAUX_PEDAGOGIE.assiduite.help}/>
        {ecart != null && (
          <Kpi
            icon="bi-arrow-left-right"
            label="Écart vs global"
            value={`${ecart > 0 ? '+' : ''}${ecart} pt`}
            color={ecart >= 0 ? '#2277C1' : '#C62828'}
            sub={`Moyenne globale : ${ped.taux_presence}% (assiduité séance)`}
          />
        )}
      </div>

      <div style={{ marginBottom: '1rem' }}>
        <p style={{ fontSize: '0.78rem', fontWeight: 600, color: '#64748b', marginBottom: '0.35rem' }}>Assiduité séance du périmètre</p>
        <TauxBar value={r.taux}/>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: '1rem' }}>
        <Card title="Contexte global (filtre actif)" icon="bi-speedometer2">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem', fontSize: '0.8rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#64748b' }}>Inscrits (total)</span>
              <b style={{ color: '#1e293b' }}>{ped.total_inscrits}</b>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#64748b' }}>Présents (total)</span>
              <b style={{ color: '#2277C1' }}>{ped.total_presents}</b>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#64748b' }}>{TAUX_PEDAGOGIE.assiduite.label} (global)</span>
              <b style={{ color: '#1e293b' }}>{ped.taux_presence}%</b>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#64748b' }}>Séances terminées</span>
              <b style={{ color: '#1e293b' }}>{ped.nb_seances_terminees ?? '—'}</b>
            </div>
          </div>
        </Card>

        {entry.type === 'formation' && ped.taux_par_grade?.length > 0 && (
          <Card title="Grades liés (aperçu)" icon="bi-bar-chart-steps">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {ped.taux_par_grade.slice(0, 5).map((g, i) => (
                <div key={i}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '0.1rem' }}>
                    <span style={{ color: '#334155' }}>{g.grade}</span>
                    <span style={{ color: '#64748b' }}>{g.taux}%</span>
                  </div>
                  <TauxBar value={g.taux} small/>
                </div>
              ))}
            </div>
          </Card>
        )}

        {entry.type === 'secretariat' && onGoSecretariat && (
          <Card title="Aller plus loin" icon="bi-building">
            <p style={{ fontSize: '0.8rem', color: '#64748b', marginBottom: '0.65rem' }}>
              Consultez le tableau de bord complet de ce secrétariat (modules, pointages, graphiques).
            </p>
            <button
              type="button"
              className="btn btn-sm"
              style={{ background: 'var(--navy)', color: '#fff', border: 'none' }}
              onClick={() => onGoSecretariat(r.secretariat_id)}
            >
              <i className="bi bi-building me-1"/>Ouvrir l&apos;onglet Secrétariats
            </button>
          </Card>
        )}
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Card title={AUDITEURS_NOTOIRES.cardTitle} icon="bi-person-x-fill" col="1/-1">
          <AuditeursNotoiresPanel data={an} maxHeight={320} compact/>
        </Card>
      </div>
    </div>
  )
}

function HistoriqueEnsemblePanel({ historique, onSelectMois, auditeursNotoires }) {
  const { resume } = historique
  return (
    <div style={{
      background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      overflow: 'hidden', minWidth: 0,
    }}>
      <div style={{
        padding: '0.85rem 1rem', background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 100%)',
        borderBottom: '1px solid #e2e8f0', position: 'sticky', top: 0, zIndex: 2,
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <i className="bi bi-graph-up me-2" style={{ color: 'var(--navy)' }}/>
          Historique — 12 derniers mois
        </h3>
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>
          Vue d&apos;ensemble des tendances (pointages, présences, séances, modules).
          Choisissez un mois dans le panneau de gauche pour le détail mensuel.
        </p>
      </div>
      <div style={{ maxHeight: '62vh', overflowY: 'auto', padding: '1rem' }}>
        {resume && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(180px,1fr))', gap: '0.8rem', marginBottom: '1rem' }}>
            <Kpi icon="bi-qr-code-scan" label="Pointages (12 mois)" value={resume.total_pointages}
              sub={`Moy. ${resume.moy_pointages_mois}/mois actif`} color="#C62828"/>
            <Kpi icon="bi-calendar-event" label="Séances (12 mois)" value={resume.total_sessions}
              sub={resume.sessions_mois_courant != null ? `${resume.sessions_mois_courant} ce mois` : undefined} color="#1565C0"/>
            <Kpi icon="bi-percent" label={`${TAUX_PEDAGOGIE.assiduite.label} moyen`} value={`${resume.moy_taux_presence}%`} color="#2277C1" help={TAUX_PEDAGOGIE.assiduite.help}/>
            <Kpi icon="bi-book" label="Modules actifs" value={resume.modules_actifs_dernier_mois}
              sub="Dernier mois avec séances" color="#7B1FA2"/>
            <Kpi icon="bi-graph-up-arrow" label="Pointages ce mois" value={resume.pointages_mois_courant}
              sub={<TrendBadge pct={resume.variation_pointages_pct}/>} color="#F5B100"/>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(320px,1fr))', gap: '1rem' }}>
          <Card title="Pointages par mois — présents vs absents" icon="bi-people-fill">
            <StackedPresenceChart data={historique.pointages_par_mois}/>
          </Card>
          <Card title="Volume de pointages (12 mois)" icon="bi-graph-up">
            <MonthTrendChart data={historique.pointages_par_mois} valueKey="total" color="#C62828"/>
          </Card>
          <Card title={`${TAUX_PEDAGOGIE.assiduite.label} mensuel`} icon="bi-percent">
            <MonthTrendChart data={historique.taux_presence_par_mois} valueKey="total" color="#2277C1" unit="%"/>
            <p style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.5rem', marginBottom: 0 }}>
              Calculé sur présents / (présents + absents) par mois.
            </p>
          </Card>
          <Card title="Séances par mois" icon="bi-calendar-week">
            <MonthTrendChart data={historique.sessions_par_mois} valueKey="total" color="#1565C0"/>
          </Card>
          <Card title="Modules — créations et activité" icon="bi-graph-up-arrow">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <p style={{ fontSize: '0.78rem', fontWeight: 600, color: '#64748b', marginBottom: '0.4rem' }}>Nouveaux modules</p>
                <MonthTrendChart data={historique.modules_par_mois} valueKey="total" color="#2277C1" height={130}/>
              </div>
              <div>
                <p style={{ fontSize: '0.78rem', fontWeight: 600, color: '#64748b', marginBottom: '0.4rem' }}>Modules actifs</p>
                <MonthTrendChart data={historique.modules_par_mois} valueKey="actifs" color="#7B1FA2" height={130}/>
              </div>
            </div>
            <p style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.5rem', marginBottom: 0 }}>
              Stock cumulé : <b>{historique.modules_par_mois?.slice(-1)[0]?.cumul ?? '—'}</b> modules.
            </p>
          </Card>
        </div>

        <div style={{ marginTop: '1rem' }}>
          <Card title={AUDITEURS_NOTOIRES.cardTitle} icon="bi-person-x-fill" col="1/-1">
            <AuditeursNotoiresPanel data={auditeursNotoires} maxHeight={320}/>
          </Card>
        </div>

        {onSelectMois && (
          <div style={{ marginTop: '1rem', padding: '0.75rem', background: '#f8fafc', borderRadius: 8, fontSize: '0.76rem', color: '#64748b' }}>
            <i className="bi bi-info-circle me-1"/>
            Cliquez sur un mois à gauche pour afficher les indicateurs détaillés de ce mois.
          </div>
        )}
      </div>
    </div>
  )
}

function HistoriqueMoisPanel({ historique, monthIndex, auditeursNotoires }) {
  const pt = historique.pointages_par_mois[monthIndex]
  const taux = historique.taux_presence_par_mois[monthIndex]
  const sess = historique.sessions_par_mois[monthIndex]
  const mod = historique.modules_par_mois[monthIndex]
  const prevPt = monthIndex > 0 ? historique.pointages_par_mois[monthIndex - 1] : null
  const varPt = prevPt && prevPt.total > 0
    ? Math.round(((pt.total - prevPt.total) / prevPt.total) * 1000) / 10
    : (pt.total > 0 && !prevPt?.total ? 100 : null)
  const winStart = Math.max(0, monthIndex - 2)
  const windowSlice = (arr) => arr.slice(winStart, monthIndex + 1)

  return (
    <div style={{
      background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      overflow: 'hidden', minWidth: 0, padding: '1rem',
    }}>
      <div style={{
        padding: '0.65rem 0.85rem', margin: '-1rem -1rem 1rem',
        background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 100%)',
        borderBottom: '1px solid #e2e8f0',
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <i className="bi bi-calendar3 me-2" style={{ color: '#1565C0' }}/>
          {formatMoisLabelLong(pt.mois)}
        </h3>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
        <Kpi icon="bi-qr-code-scan" label="Pointages" value={pt.total} color="#C62828"
          sub={varPt != null ? <TrendBadge pct={varPt}/> : undefined}/>
        <Kpi icon="bi-person-check" label="Présents" value={pt.presents ?? 0} color="#2277C1"/>
        <Kpi icon="bi-person-x" label="Absents" value={pt.absents ?? 0} color="#C62828"/>
        <Kpi icon="bi-percent" label={TAUX_PEDAGOGIE.assiduite.label} value={`${Number(taux?.total || 0).toFixed(1)}%`} color="#2277C1" help={TAUX_PEDAGOGIE.assiduite.help}/>
        <Kpi icon="bi-calendar-event" label="Séances" value={sess?.total ?? 0} color="#1565C0"/>
        <Kpi icon="bi-book" label="Modules créés" value={mod?.total ?? 0} color="#7B1FA2"/>
        <Kpi icon="bi-book-half" label="Modules actifs" value={mod?.actifs ?? 0} color="#0F70AB"/>
        <Kpi icon="bi-layers" label="Stock modules" value={mod?.cumul ?? '—'} color="#64748b"/>
      </div>

      <AuditeursNotoiresKpiStrip data={auditeursNotoires}/>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: '1rem' }}>
        <Card title="Présents vs absents (ce mois)" icon="bi-people-fill">
          <StackedPresenceChart data={[pt]} height={140}/>
        </Card>
        <Card title={`Contexte — ${windowSlice(historique.pointages_par_mois).length} mois`} icon="bi-graph-up">
          <MonthTrendChart data={windowSlice(historique.pointages_par_mois)} valueKey="total" color="#C62828" height={140}/>
        </Card>
        <Card title={`${TAUX_PEDAGOGIE.assiduite.label} (contexte)`} icon="bi-percent">
          <MonthTrendChart data={windowSlice(historique.taux_presence_par_mois)} valueKey="total" color="#2277C1" unit="%" height={140}/>
        </Card>
        <Card title="Séances (contexte)" icon="bi-calendar-week">
          <MonthTrendChart data={windowSlice(historique.sessions_par_mois)} valueKey="total" color="#1565C0" height={140}/>
        </Card>
      </div>
    </div>
  )
}

const SEC_TABLE_HEADERS = [
  'N°', 'Secrétariat', 'Responsable', 'Modules', 'Étudiants', 'Enseignants', 'Séances',
  'Inscrits', 'Présents', 'Assiduité séance', 'Absences', 'Abs. notoires', 'Vol.H. prévu', 'Avancement VH', 'Hommes', 'Femmes', '',
]

function SecretariatsComparatifTable({ secretariats, onRowClick }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
        <thead>
          <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
            {SEC_TABLE_HEADERS.map(h => (
              <th
                key={h}
                style={{
                  padding: '0.5rem 0.65rem', color: '#64748b', fontWeight: 600,
                  textAlign: h === 'Secrétariat' || h === 'Responsable' ? 'left' : 'center',
                  whiteSpace: 'nowrap',
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {secretariats.map((s, i) => (
            <tr
              key={s.secretariat_id}
              style={{ borderBottom: '1px solid #f1f5f9', cursor: onRowClick ? 'pointer' : undefined }}
              onMouseEnter={onRowClick ? e => { e.currentTarget.style.background = '#e8eef6' } : undefined}
              onMouseLeave={onRowClick ? e => { e.currentTarget.style.background = '' } : undefined}
              onClick={onRowClick ? () => onRowClick(i) : undefined}
            >
              <td style={{ padding: '0.45rem 0.65rem', color: '#94a3b8', textAlign: 'center' }}>{s.numero}</td>
              <td style={{ padding: '0.45rem 0.65rem', color: '#1e293b', fontWeight: 600, whiteSpace: 'nowrap' }}>
                <i className="bi bi-building me-1" style={{ color: C[i % C.length] }}/>
                {s.secretariat}
              </td>
              <td style={{ padding: '0.45rem 0.65rem', color: '#64748b', whiteSpace: 'nowrap' }}>{s.responsable || '—'}</td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#2277C1', fontWeight: 700 }}>{s.nb_modules}</td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#F5B100', fontWeight: 700 }}>{s.nb_participants}</td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#7B1FA2', fontWeight: 700 }}>{s.nb_formateurs}</td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#00838F', fontWeight: 700 }}>{s.nb_sessions}</td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#64748b' }}>{s.nb_inscrits}</td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#2277C1', fontWeight: 600 }}>{s.nb_presents}</td>
              <td style={{ padding: '0.45rem 0.65rem', minWidth: 110 }}><TauxBar value={s.taux_presence} small/></td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#C62828', fontWeight: 600 }}>{s.nb_absences}</td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#C62828', fontWeight: 700 }} title={`${Number(s.pct_auditeurs_notoires || 0).toFixed(1)}% des inscrits`}>
                {s.nb_auditeurs_notoires ?? 0}
              </td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#0F70AB' }}>{fmtHeures(s.vh_prevu)}h</td>
              <td style={{ padding: '0.45rem 0.65rem', minWidth: 80 }}><TauxBar value={s.taux_execution_vh} small/></td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#1565C0' }}>{s.ratio_hf.hommes}</td>
              <td style={{ textAlign: 'center', padding: '0.45rem 0.65rem', color: '#AD1457' }}>{s.ratio_hf.femmes}</td>
              <td style={{ padding: '0.45rem 0.65rem', textAlign: 'center' }}>
                {onRowClick && <i className="bi bi-arrow-right-circle" style={{ color: 'var(--navy)' }} title="Voir le détail"/>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SecretariatsEnsemblePanel({ secStats, onSelectIndividuel }) {
  const { secretariats } = secStats
  return (
    <div style={{
      background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      overflow: 'hidden', minWidth: 0,
    }}>
      <div style={{
        padding: '0.85rem 1rem', background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 100%)',
        borderBottom: '1px solid #e2e8f0', position: 'sticky', top: 0, zIndex: 2,
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <i className="bi bi-building me-2" style={{ color: 'var(--navy)' }}/>
          {secStats.total} secrétariat{secStats.total > 1 ? 's' : ''} — vue d&apos;ensemble
        </h3>
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>
          Comparaison de tous les secrétariats (effectifs, présences, pointages).
          Cliquez sur une ligne ou choisissez un secrétariat dans le panneau de gauche pour le détail.
        </p>
      </div>
      <div style={{ maxHeight: '62vh', overflowY: 'auto', padding: '1rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))', gap: '0.8rem', marginBottom: '1.2rem' }}>
          <Kpi icon="bi-building" label="Secrétariats" value={secStats.total} color="#1565C0"/>
          <Kpi icon="bi-people" label="Étudiants total" value={secretariats.reduce((s, r) => s + r.nb_participants, 0)} color="#F5B100"/>
          <Kpi icon="bi-book" label="Modules total" value={secretariats.reduce((s, r) => s + r.nb_modules, 0)} color="#2277C1"/>
          <Kpi icon="bi-qr-code-scan" label="Pointages total" value={secretariats.reduce((s, r) => s + r.nb_pointages, 0)} color="#C62828"/>
          <Kpi icon="bi-person-x-fill" label="Absents notoires" value={secStats.auditeurs_notoires?.total ?? secretariats.reduce((s, r) => s + (r.nb_auditeurs_notoires || 0), 0)} color="#C62828"
            sub={secStats.auditeurs_notoires ? `${Number(secStats.auditeurs_notoires.pct || 0).toFixed(1).replace('.', ',')}% des inscrits` : undefined}/>
        </div>

        <div style={{ background: '#fff', borderRadius: 10, border: '1px solid #e2e8f0', overflow: 'hidden', marginBottom: '1.2rem' }}>
          <SecretariatsComparatifTable secretariats={secretariats} onRowClick={onSelectIndividuel}/>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(320px,1fr))', gap: '1rem' }}>
          <Card title="Étudiants par secrétariat" icon="bi-people">
            <HBars data={secretariats.map(s => ({ label: s.secretariat, value: s.nb_participants }))} labelKey="label" valueKey="value"/>
          </Card>
          <Card title="Modules par secrétariat" icon="bi-book">
            <Bars data={secretariats.map(s => ({ label: s.secretariat, value: s.nb_modules }))} labelKey="label" valueKey="value" color="#2277C1"/>
          </Card>
          <Card title={`${TAUX_PEDAGOGIE.assiduite.label} par secrétariat`} icon="bi-percent">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
              {secretariats.map((s, i) => (
                <div key={s.secretariat_id}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.79rem', marginBottom: '0.18rem' }}>
                    <span style={{ color: '#334155', fontWeight: 600 }}>
                      <i className="bi bi-building me-1" style={{ color: C[i % C.length] }}/>
                      {s.secretariat}
                    </span>
                    <span style={{ color: '#64748b' }}>{s.nb_inscrits} inscrits · {s.nb_presents} présents</span>
                  </div>
                  <TauxBar value={s.taux_presence} small/>
                </div>
              ))}
            </div>
          </Card>
          <Card title="Pointages par secrétariat" icon="bi-qr-code-scan">
            <Bars data={secretariats.map(s => ({ label: s.secretariat, value: s.nb_pointages }))} labelKey="label" valueKey="value" color="#C62828"/>
          </Card>
          <Card title="Absences par secrétariat" icon="bi-x-circle">
            <HBars data={secretariats.map(s => ({ label: s.secretariat, value: s.nb_absences }))} labelKey="label" valueKey="value"/>
          </Card>
        </div>

        <div style={{ marginTop: '1rem' }}>
          <Card title={AUDITEURS_NOTOIRES.cardTitle} icon="bi-person-x-fill" col="1/-1">
            <AuditeursNotoiresPanel data={secStats.auditeurs_notoires} maxHeight={360}/>
          </Card>
        </div>
      </div>
    </div>
  )
}

function SecretariatDetailPanel({ row, detail }) {
  const kpis = detail?.kpis || {}
  const pedagogiques = detail?.pedagogiques || {}
  const adm = detail?.admin_operationnel || {}

  return (
    <div style={{
      background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      overflow: 'hidden', minWidth: 0, padding: '1rem',
    }}>
      <div style={{
        padding: '0.65rem 0.85rem', margin: '-1rem -1rem 1rem', background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 100%)',
        borderBottom: '1px solid #e2e8f0',
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <i className="bi bi-building me-2" style={{ color: '#1565C0' }}/>
          {row?.secretariat || 'Secrétariat'}
        </h3>
        {row?.responsable && (
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>
            Responsable : {row.responsable}
          </p>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))', gap: '0.8rem', marginBottom: '1.1rem' }}>
        <Kpi icon="bi-book" label="Modules" value={kpis.modules} color="#2277C1"/>
        <Kpi icon="bi-people" label="Étudiants" value={kpis.participants} color="#F5B100"/>
        <Kpi icon="bi-person-video3" label="Enseignants" value={kpis.formateurs} color="#7B1FA2"/>
        <Kpi icon="bi-calendar-event" label="Séances" value={kpis.sessions_total} color="#00838F"/>
        <Kpi icon="bi-qr-code-scan" label="Pointages" value={kpis.pointages} color="#C62828"/>
        <Kpi icon="bi-percent" label={TAUX_PEDAGOGIE.assiduite.label} value={`${pedagogiques.taux_presence}%`} color="#2277C1" help={TAUX_PEDAGOGIE.assiduite.help}/>
        <Kpi icon="bi-percent" label="Taux absence" value={`${pedagogiques.taux_absence}%`} color="#C62828"/>
        <Kpi icon="bi-person-x-fill" label="Absents notoires" value={adm.auditeurs_notoires?.total ?? 0} color="#C62828"
          sub={adm.auditeurs_notoires ? `${Number(adm.auditeurs_notoires.pct || 0).toFixed(1).replace('.', ',')}% des inscrits` : undefined}/>
        <Kpi icon="bi-clock-history" label="Vol. horaire prévu" value={`${fmtHeures(kpis.vh_prevu_heures)}h`} color="#0F70AB"/>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(320px,1fr))', gap: '1rem' }}>
        <Card title="Pointages par statut" icon="bi-pie-chart">
          <Donut data={(adm.pointages_par_statut || []).map(d => ({ ...d, label: STATUT_LABELS[d.statut] || d.statut }))} labelKey="label" valueKey="total"/>
        </Card>
        <Card title="Répartition Hommes / Femmes" icon="bi-gender-ambiguous">
          <Donut data={adm.participants_par_sexe} labelKey="sexe" valueKey="total"/>
        </Card>
        <Card title="Assiduité séance par formation" icon="bi-building">
          {pedagogiques.taux_par_formation?.length
            ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {pedagogiques.taux_par_formation.map((r, i) => (
                  <div key={i}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '0.15rem' }}>
                      <span style={{ color: '#334155', fontWeight: 500, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.formation}</span>
                      <span style={{ color: '#64748b' }}>{r.inscrits} inscrits</span>
                    </div>
                    <TauxBar value={r.taux} small/>
                  </div>
                ))}
              </div>
            )
            : <Empty label="Aucune formation pour ce secrétariat"/>}
        </Card>
        <Card title="Étudiants par catégorie" icon="bi-bar-chart-steps">
          <HBars data={(adm.participants_par_categorie || []).map(d => ({ ...d, categorie: d.categorie || 'Non rens.' }))} labelKey="categorie" valueKey="total"/>
        </Card>
        <Card title="Taux par grade" icon="bi-award">
          {pedagogiques.taux_par_grade?.length
            ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {pedagogiques.taux_par_grade.map((r, i) => (
                  <div key={i}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '0.12rem' }}>
                      <b style={{ color: '#334155' }}>{r.grade}</b>
                      <span style={{ color: '#64748b' }}>{r.inscrits} inscrits</span>
                    </div>
                    <TauxBar value={r.taux} small/>
                  </div>
                ))}
              </div>
            )
            : <Empty label="Aucun grade renseigné"/>}
        </Card>
        <Card title="Charge des enseignants" icon="bi-person-video3">
          <HBars data={adm.charge_formateurs} labelKey="nom" valueKey="nb_sessions"/>
        </Card>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <Card title={AUDITEURS_NOTOIRES.cardTitle} icon="bi-person-x-fill" col="1/-1">
          <AuditeursNotoiresPanel data={adm.auditeurs_notoires} maxHeight={360}/>
        </Card>
      </div>
    </div>
  )
}

function BilansEnsemblePanel({ items, bilans, filtres, dimension, onSelectIndividuel }) {
  const dimLabel = RB_DIMENSIONS.find(d => d.id === dimension)?.label || dimension

  const selectBilan = (bilanId) => {
    const idx = (bilans || []).findIndex(b => b.id === bilanId)
    if (idx >= 0) onSelectIndividuel(idx)
  }

  if (!items?.length) {
    return (
      <div style={{
        background: '#fff', borderRadius: 10, padding: '2rem', textAlign: 'center',
        boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      }}>
        <Empty label="Aucun tableau à afficher pour cette sélection"/>
      </div>
    )
  }

  return (
    <div style={{
      background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      overflow: 'hidden', minWidth: 0,
    }}>
      <div style={{
        padding: '0.85rem 1rem', background: 'linear-gradient(135deg, #e8eef6 0%, #d4deec 100%)',
        borderBottom: '1px solid #e2e8f0', position: 'sticky', top: 0, zIndex: 2,
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 800, color: '#1e293b' }}>
          <i className="bi bi-grid-3x3-gap me-2" style={{ color: 'var(--navy)' }}/>
          {items.length} tableau{items.length > 1 ? 'x' : ''} — {dimLabel}
        </h3>
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.78rem', color: '#64748b' }}>
          Vue d&apos;ensemble ({filtres?.annee}{filtres?.periode_label ? ` · ${filtres.periode_label}` : ''}).
          Utilisez le panneau de gauche pour afficher un seul tableau en plein écran.
        </p>
      </div>
      <div style={{ maxHeight: '62vh', overflowY: 'auto', padding: '1rem' }}>
        {items.map((entry, i) => (
          <div
            key={entry.bilan_id}
            id={`rb-tableau-${entry.bilan_id}`}
            style={{
              marginBottom: i < items.length - 1 ? '1.75rem' : 0,
              paddingBottom: i < items.length - 1 ? '1.75rem' : 0,
              borderBottom: i < items.length - 1 ? '2px dashed #e2e8f0' : 'none',
            }}
          >
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
              gap: '0.5rem', marginBottom: '0.65rem', flexWrap: 'wrap',
            }}>
              <div>
                <div style={{ fontWeight: 800, fontSize: '0.88rem', color: '#1e293b' }}>
                  {entry.bilan?.libelle}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{entry.bilan?.sous_titre}</div>
              </div>
              <button
                type="button"
                className="btn btn-sm btn-outline-success"
                style={{ fontSize: '0.72rem', flexShrink: 0 }}
                onClick={() => selectBilan(entry.bilan_id)}
              >
                <i className="bi bi-arrows-fullscreen me-1"/>Plein écran
              </button>
            </div>
            <BilanDetailPanel
              bilan={entry.bilan}
              tableau={entry.tableau}
              filtres={filtres}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

function BilanEffectifsModuleTable({ data }) {
  const thBase = {
    padding: '0.45rem 0.5rem',
    border: '1px solid #000',
    fontWeight: 700,
    fontSize: '0.72rem',
    textAlign: 'center',
    verticalAlign: 'middle',
    lineHeight: 1.25,
  }
  const tdBase = {
    padding: '0.65rem 0.5rem',
    border: '1px solid #000',
    textAlign: 'center',
    verticalAlign: 'middle',
    fontSize: '0.85rem',
  }
  const Soit = ({ children }) => (
    <div style={{ fontSize: '0.72rem', fontWeight: 400, marginTop: '0.35rem', lineHeight: 1.35 }}>
      <span style={{ textDecoration: 'underline' }}>soit</span> {children}
    </div>
  )

  return (
    <div style={{ overflowX: 'auto' }}>
      <h3 style={{
        textAlign: 'center', fontWeight: 700, fontSize: '0.88rem',
        textDecoration: 'underline', textTransform: 'uppercase',
        margin: '0 0 0.85rem', color: '#1e293b', lineHeight: 1.35,
      }}>
        {data.titre}
      </h3>
      <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 620 }}>
        <thead>
          <tr>
            <th style={{ ...thBase, background: '#FCE7B4' }} rowSpan={2}>
              EFFECTIFS<br/>DES AUDITEURS
            </th>
            <th style={{ ...thBase, background: '#FCE7B4' }} rowSpan={2}>
              EFFECTIFS<br/>PRESENTS
            </th>
            <th style={{ ...thBase, background: '#D9D9D9' }} colSpan={2}>
              EFFECTIFS PRESENTS PAR GENRE
            </th>
            <th style={{ ...thBase, background: '#77BCE7' }} rowSpan={2}>
              ABSENTS
            </th>
          </tr>
          <tr>
            <th style={{ ...thBase, background: '#99CCFF' }}>MASCULIN</th>
            <th style={{ ...thBase, background: '#FFCCFF' }}>FEMININ</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style={tdBase}>
              <div style={{ fontWeight: 700, fontSize: '1rem' }}>{fmtNbFR(data.effectifs_auditeurs)}</div>
              {(data.masculin_inscrits != null || data.feminin_inscrits != null) && (
                <Soit>
                  {fmtNbFR(data.masculin_inscrits ?? 0)} H / {fmtNbFR(data.feminin_inscrits ?? 0)} F inscrits
                </Soit>
              )}
            </td>
            <td style={tdBase}>
              <div style={{ fontWeight: 700, fontSize: '1rem' }}>{fmtNbFR(data.effectifs_presents)}</div>
              <Soit>{fmtPctFR(data.pct_presents_total)}% de l&apos;effectif total</Soit>
            </td>
            <td style={tdBase}>
              <div style={{ fontWeight: 700, fontSize: '1rem' }}>{fmtNbFR(data.masculin)}</div>
              <Soit>{fmtPctFR(data.pct_masculin_presents)}% de l&apos;effectif des présents</Soit>
            </td>
            <td style={tdBase}>
              <div style={{ fontWeight: 700, fontSize: '1rem' }}>{fmtNbFR(data.feminin)}</div>
              <Soit>{fmtPctFR(data.pct_feminin_presents)}% de l&apos;effectif des présents</Soit>
            </td>
            <td style={tdBase}>
              <div style={{ fontWeight: 700, fontSize: '1rem' }}>{fmtNbFR(data.absents)}</div>
              <Soit>{fmtPctFR(data.pct_absents_total)}% de l&apos;effectif total</Soit>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function BilanDetailPanel({ bilan, tableau, filtres, justificatifsText, onJustificatifsChange }) {
  const dimLabel = RB_DIMENSIONS.find(d => d.id === bilan.dimension)?.label || bilan.dimension

  if (['module', 'matiere', 'categorie'].includes(bilan.dimension) && !tableau) {
    return (
      <div style={{
        background: '#fff', borderRadius: 10, padding: '2rem', textAlign: 'center',
        boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
      }}>
        <Empty label="Aucune séance comptabilisable sur la période filtrée — aucun tableau d'effectifs."/>
      </div>
    )
  }

  if (bilan.dimension === 'formation' && tableau?.type === 'bilan_periode_formation') {
    return (
      <div style={{ background: '#fff', borderRadius: 10, padding: '1rem', boxShadow: '0 1px 4px rgba(0,0,0,0.07)', minWidth: 0 }}>
        <BilanPeriodeFormationTable
          data={tableau}
          justificatifsText={justificatifsText}
          onJustificatifsChange={onJustificatifsChange}
        />
      </div>
    )
  }

  if (bilan.dimension === 'module' && tableau?.type === 'effectifs_module') {
    return (
      <div style={{ background: '#fff', borderRadius: 10, padding: '1rem', boxShadow: '0 1px 4px rgba(0,0,0,0.07)', minWidth: 0 }}>
        <BilanEffectifsModuleTable data={tableau} />
      </div>
    )
  }

  if (bilan.dimension === 'matiere' && tableau?.type === 'effectifs_matiere') {
    return (
      <div style={{ background: '#fff', borderRadius: 10, padding: '1rem', boxShadow: '0 1px 4px rgba(0,0,0,0.07)', minWidth: 0 }}>
        {tableau.nb_groupes != null && (
          <p style={{ margin: '0 0 0.65rem', fontSize: '0.78rem', color: '#64748b' }}>
            Agrégation de <strong>{tableau.nb_groupes}</strong> groupe{tableau.nb_groupes > 1 ? 's' : ''} —
            étudiants uniques sur tous les groupes.
          </p>
        )}
        <BilanEffectifsModuleTable data={tableau} />
      </div>
    )
  }

  if (bilan.dimension === 'categorie' && tableau?.type === 'effectifs_categorie') {
    return (
      <div style={{ background: '#fff', borderRadius: 10, padding: '1rem', boxShadow: '0 1px 4px rgba(0,0,0,0.07)', minWidth: 0 }}>
        <BilanEffectifsModuleTable data={tableau} />
      </div>
    )
  }

  return (
    <div style={{background:'#fff',borderRadius:10,padding:'1rem',boxShadow:'0 1px 4px rgba(0,0,0,0.07)',minWidth:0}}>
      <div style={{background:'#1565C0',color:'#fff',textAlign:'center',padding:'0.5rem 0.75rem',borderRadius:8,fontWeight:700,fontSize:'0.82rem',marginBottom:'0.75rem'}}>
        BILAN — {dimLabel.toUpperCase()}
      </div>
      <h4 style={{margin:'0 0 0.35rem',fontWeight:800,color:'#1e293b',fontSize:'1rem'}}>{bilan.libelle}</h4>
      <p style={{margin:'0 0 0.75rem',fontSize:'0.78rem',color:'#64748b'}}>{bilan.sous_titre}</p>

      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(140px,1fr))',gap:'0.5rem',marginBottom:'0.85rem'}}>
        {[
          ['Période', bilan.periode_label || 'Toutes périodes'],
          ['Année', bilan.annee],
          ['Catégorie', bilan.categorie || '—'],
          bilan.formation ? ['Formation', bilan.formation] : null,
          bilan.module ? ['Module', bilan.module] : null,
          bilan.inscrits != null ? ['Inscrits', bilan.inscrits] : null,
          filtres?.calendrier ? ['Calendrier prév.', filtres.calendrier] : null,
        ].filter(Boolean).map(([l,v])=>(
          <div key={l} style={{background:'#f8fafc',borderRadius:8,padding:'0.5rem 0.65rem',border:'1px solid #e2e8f0'}}>
            <div style={{fontSize:'0.68rem',color:'#94a3b8',fontWeight:600}}>{l}</div>
            <div style={{fontSize:'0.85rem',fontWeight:700,color:'#1e293b',marginTop:'0.15rem'}}>{v}</div>
          </div>
        ))}
      </div>

      <div style={{
        background:'#fffceb', border:'1px dashed #fcdf4d', borderRadius:10,
        padding:'1.25rem', textAlign:'center',
      }}>
        <i className="bi bi-table" style={{fontSize:'2rem',color:'#F5B100',display:'block',marginBottom:'0.5rem'}}/>
        <p style={{margin:0,fontSize:'0.85rem',fontWeight:700,color:'#92660e'}}>
          Zone tableau bilan
        </p>
        <p style={{margin:'0.35rem 0 0',fontSize:'0.78rem',color:'#64748b',maxWidth:420,marginLeft:'auto',marginRight:'auto'}}>
          Le modèle INJS pour ce bilan ({dimLabel}) sera intégré ici dès validation du format.
          Les filtres sélectionnés ci-dessus s&apos;appliqueront au tableau affiché et aux exports Excel, PDF et Word.
        </p>
      </div>
    </div>
  )
}
