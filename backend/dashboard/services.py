"""
Services métier et agrégations optimisées pour le Dashboard Engine INJS-LMD 2026.
Toutes les métriques sont calculées à partir des données réelles de la base de données.
Aucune donnée fictive ou mockée silencieusement.
"""

from decimal import Decimal
from django.db.models import Count, Q, Sum, Avg
from django.db.models.functions import TruncMonth
from django.utils import timezone

from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative,
    Maquette, UE, ECUE, Groupe, AffectationPedagogique,
)
from admissions.models import CampagneAdmission, Candidature, Epreuve, Admission
from formations.models import RefFormation, Formateur, Module, ModuleParticipant, SessionModule
from jurys.models import SessionJury, DecisionJury, PVJury
from graduation.models import Diplome
from presences.models import Pointage
from edts.models import EmploiDuTemps, CreneauTemplate, AffectationCreneau, ConflitCreneau
from stages.models import ConventionStage, EvaluationStage
from finances_etudiantes.models import Paiement, Facture, Echeancier
from ressources_humaines.models import Agent, Service
from patrimoine.models import Equipement, Maintenance
from core.models import EvenementAudit


MOIS_FR = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
           'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.']


def _fmt_xof(montant):
    """Montant formaté à la française (espaces) : « 13 150 000 XOF »."""
    return f"{Decimal(montant):,.0f} XOF".replace(',', ' ')


def _situation_recouvrement():
    """Situation de recouvrement, définitions alignées sur le hub Finances.

    Base UNIQUE : les échéanciers étudiants. ``attendu`` = somme des
    lignes d'échéancier, ``encaisse`` = lignes soldées (statut PAYE),
    ``impaye`` = attendu - encaissé, ``taux`` = encaissé / attendu.
    Sans échéancier, le taux reste ``None`` (jamais 0 % ni 100 % inventés).
    """
    from finances_etudiantes.models import LigneEcheancier

    attendu = LigneEcheancier.objects.aggregate(s=Sum('montant'))['s'] or Decimal('0')
    encaisse = (LigneEcheancier.objects.filter(statut='PAYE')
                .aggregate(s=Sum('montant'))['s'] or Decimal('0'))
    taux = round(float(encaisse) / float(attendu) * 100, 1) if attendu > 0 else None
    return {
        'montant_attendu': float(attendu),
        'montant_encaisse': float(encaisse),
        'montant_impaye': float(attendu - encaisse),
        'taux_recouvrement': taux,
    }


def _supervision_du_jour(date=None):
    """Séances LMD du jour + présences rattachées (source de vérité dashboard).

    Enveloppe ``presences.seances_supervision`` : même règle de statut (horaires
    planifiés), même effectif attendu (membres actifs du groupe), mêmes
    catégories d'assiduité que le bloc « Séances en direct ». Aucun ``user`` :
    ce résumé de pilotage est global, son périmètre reste celui de l'EDT publié.
    """
    from presences import seances_supervision

    return seances_supervision.supervision_seances(None, date)


def get_current_academic_year():
    return AnneeAcademique.courante_ou_none() or AnneeAcademique.objects.order_by('-libelle').first()


def libelle_annee_courante():
    """Libellé de l'année académique réellement enregistrée, sinon ``None``.

    Aucune année n'est inventée : une constante « 2026-2027 » servait de repli
    et affichait une année qui n'existait pas dans le référentiel.
    """
    annee = get_current_academic_year()
    return annee.libelle if annee else None


def _mesure_presence(seances):
    """Assiduité des séances terminées : présents + retards / attendus connus.

    Les séances à venir ne sont pas des absences. Les séances en cours ne sont
    pas encore closes. Même numérateur que les graphiques admin et les stats
    de présence ; aucun taux sans dénominateur Strictement positif.
    """
    mesurees = [s for s in seances if s['statut'] == 'TERMINEE'
                and s['effectif_attendu'] is not None]
    attendus = sum(s['effectif_attendu'] for s in mesurees)
    presents = sum(s['presences']['presents'] + s['presences']['retards']
                   for s in mesurees)
    taux = round(presents / attendus * 100, 1) if attendus else None
    detail = (f'{presents} présent(s), retards inclus, sur {attendus} attendu(s)'
              if attendus else 'Aucune séance terminée avec effectif connu')
    return taux, detail, presents, attendus, len(mesurees)


def get_direction_overview():
    """Tableau de bord de direction / pilotage général INJS."""
    annee = get_current_academic_year()
    annee_id = annee.id if annee else None

    # Inscriptions
    inscriptions_qs = InscriptionAdministrative.objects.filter(statut=InscriptionAdministrative.Statut.VALIDEE)
    if annee_id:
        inscriptions_qs = inscriptions_qs.filter(annee_academique_id=annee_id)
    nb_inscrits = inscriptions_qs.count()

    # Candidats et admissions
    candidatures_qs = Candidature.objects.all()
    admissions_qs = Admission.objects.all()
    if annee_id:
        candidatures_qs = candidatures_qs.filter(annee_academique_id=annee_id)
        admissions_qs = admissions_qs.filter(annee_academique_id=annee_id)
    nb_candidats = candidatures_qs.count()
    nb_admis = admissions_qs.filter(decision=Admission.Decision.ADMIS).count()
    # Étape « Sélection » du parcours : candidats déclarés admissibles
    # (statut réel des candidatures), entre dépôt et admission.
    nb_selection = candidatures_qs.filter(statut=Candidature.Statut.ADMISSIBLE).count()
    taux_admission = round((nb_admis / nb_candidats * 100), 1) if nb_candidats > 0 else None

    # Enseignants & Formations
    nb_enseignants = Formateur.objects.count()
    nb_formations = RefFormation.objects.filter(actif=True).count()
    nb_groupes = Groupe.objects.count()
    # ECUE réellement enseignés : ceux des maquettes ACTIVES de l'année,
    # pas l'ensemble du catalogue historique.
    ecues_qs = ECUE.objects.filter(ue__maquette__statut=Maquette.Statut.ACTIVE)
    if annee_id:
        ecues_qs = ecues_qs.filter(ue__maquette__annee_academique_id=annee_id)
    nb_cours = ecues_qs.distinct().count()

    # Présences du jour — séances **LMD** (edts.AffectationCreneau) et non le
    # flux legacy SessionModule : le bloc « Séances en direct » doit refléter la
    # chaîne LMD, pas le module historique.
    today = timezone.localdate()
    supervision = _supervision_du_jour(today)
    nb_seances_jour = supervision['resume']['seances_total']
    taux_presence, detail_presence, presents_mesures, total_attendus, nb_mesurees = (
        _mesure_presence(supervision['seances'])
    )

    # Stages & Diplômation. « Délivrés » = diplômes VALIDÉS uniquement :
    # compter aussi les brouillons et les demandes en validation affichait
    # 60 « diplômes délivrés » alors qu'aucun n'était validé.
    nb_stages_en_cours = ConventionStage.objects.filter(statut=ConventionStage.Statut.EN_COURS).count()
    diplomes_qs = Diplome.objects.all()
    if annee_id:
        diplomes_qs = diplomes_qs.filter(annee_academique_id=annee_id)
    nb_diplomes = diplomes_qs.filter(statut=Diplome.Statut.VALIDATED).count()

    # Évaluations ACADÉMIQUES de l'année (chaîne LMD) — l'ancien compteur
    # lisait les `Module` hérités (6) au lieu des évaluations réelles (32).
    from evaluations.models import Evaluation as EvaluationAcademique
    evaluations_qs = EvaluationAcademique.objects.all()
    jurys_qs = SessionJury.objects.all()
    if annee_id:
        evaluations_qs = evaluations_qs.filter(session__annee_academique_id=annee_id)
        jurys_qs = jurys_qs.filter(annee_academique_id=annee_id)
    nb_evaluations = evaluations_qs.count()
    nb_sessions_jury = jurys_qs.count()

    # Répartition par niveau
    niveaux_counts = {}
    for niv in ['L1', 'L2', 'L3', 'M1', 'M2']:
        niveaux_counts[niv] = inscriptions_qs.filter(niveau__code=niv).count()

    # Répartition par FILIÈRE de formation (Licence + Master regroupés).
    # L'ancien code tronquait l'intitulé à 20 caractères : « ACTIVITÉS
    # PHYSIQUES » apparaissait deux fois en légende, et le total du camembert
    # (1 322) contredisait le KPI des inscrits (3 516).
    formations_dist = [
        {'label': r['ref_formation__filiere__libelle'] or 'Sans filière rattachée',
         'value': r['n']}
        for r in (inscriptions_qs.values('ref_formation__filiere__libelle')
                  .annotate(n=Count('id'))
                  .order_by('-n', 'ref_formation__filiere__libelle'))
    ]

    # Répartition par sexe (caractéristique du participant), inscrits de l'année.
    _lib_sexe = {'FEMININ': 'Femmes', 'MASCULIN': 'Hommes'}
    _comptes_sexe = {}
    for r in (inscriptions_qs.values('etudiant__participant__sexe')
              .annotate(n=Count('id'))):
        lib = _lib_sexe.get((r['etudiant__participant__sexe'] or '').upper(),
                            'Non renseigné')
        _comptes_sexe[lib] = _comptes_sexe.get(lib, 0) + r['n']
    sexe_dist = [{'label': k, 'value': v}
                 for k, v in sorted(_comptes_sexe.items(), key=lambda kv: -kv[1])]

    # Évolution des effectifs : cumul mensuel des inscriptions validées de
    # l'année courante, par date d'inscription. Aucun historique pluriannuel
    # n'est enregistré avant 2026-2027 : la courbe porte sur la rentrée en
    # cours (dates réelles), pas sur six années fabriquées.
    evolution = {'labels': [], 'inscrits_cumul': []}
    _mensuel = list(
        inscriptions_qs.exclude(date_inscription__isnull=True)
        .annotate(mois=TruncMonth('date_inscription'))
        .values('mois').annotate(n=Count('id')).order_by('mois')
    )
    if len(_mensuel) >= 2:
        _cumul = 0
        for r in _mensuel:
            _cumul += r['n']
            _d = r['mois'].date() if hasattr(r['mois'], 'date') else r['mois']
            evolution['labels'].append(f"{MOIS_FR[_d.month - 1]} {_d.year}")
            evolution['inscrits_cumul'].append(_cumul)

    # Charge d'enseignement : volumes des affectations pédagogiques de
    # l'année, par cycle (préfixe du niveau : Licence/Master/Doctorat)
    # et par type d'enseignement (CM/TD/TP).
    _par_cycle = {}
    for r in (AffectationPedagogique.objects.filter(annee_academique_id=annee_id)
              .values('niveau__libelle', 'type_enseignement')
              .annotate(h=Sum('volume_horaire'))):
        cycle = (r['niveau__libelle'] or '').split(' ')[0]
        if cycle in ('Licence', 'Master', 'Doctorat'):
            # Plusieurs lignes par cycle (Licence 1/2/3…) : ACCUMULER.
            _cell = _par_cycle.setdefault(cycle, {})
            _cell[r['type_enseignement']] = (
                _cell.get(r['type_enseignement'], 0) + float(r['h'] or 0)
            )
    _cycles = [c for c in ('Licence', 'Master', 'Doctorat') if c in _par_cycle]
    _types = [t for t in ('CM', 'TD', 'TP')
              if any(t in v for v in _par_cycle.values())]
    charge = (
        {'categories': _cycles,
         'series': [{'name': t,
                     'values': [_par_cycle[c].get(t, 0) for c in _cycles]}
                    for t in _types]}
        if _cycles and _types else {'categories': [], 'series': []}
    )

    # Taux de réussite : décisions de jury de l'année (admis + admis avec
    # réserves) / décisions rendues. Taux d'abandon : inscriptions de
    # l'année dont le statut étudiant (référentiel) est « Abandon ».
    # Taux de diplomation : diplômes VALIDÉS de l'année / inscrits validés
    # en ANNÉE TERMINALE de cycle (L3, M2, D3) — indicateur d'achèvement
    # simplifié, affiché AVEC sa fraction (``*_base``) pour rester
    # vérifiable : un vrai taux de cohorte exigerait un suivi longitudinal
    # des promotions, qui n'existe pas encore.
    # Chaque taux expose sa fraction numérateur/dénominateur : un « 0 % »
    # mesuré doit se distinguer d'un « non mesuré » (dénominateur absent).
    decisions_qs = DecisionJury.objects.all()
    if annee_id:
        decisions_qs = decisions_qs.filter(session__annee_academique_id=annee_id)
    nb_decisions = decisions_qs.count()
    nb_reussites = decisions_qs.filter(decision__in=('ADMIS', 'ADMIS_RESERVES')).count()
    taux_reussite = (round(nb_reussites / nb_decisions * 100, 1)
                     if nb_decisions else None)

    inscr_tous_qs = InscriptionAdministrative.objects.all()
    if annee_id:
        inscr_tous_qs = inscr_tous_qs.filter(annee_academique_id=annee_id)
    nb_inscr_tous = inscr_tous_qs.count()
    nb_abandons = inscr_tous_qs.filter(statut_etudiant__code='ABANDON').count()
    taux_abandon = (round(nb_abandons / nb_inscr_tous * 100, 1)
                    if nb_inscr_tous else None)

    nb_terminaux = inscriptions_qs.filter(
        niveau__code__in=('L3', 'M2', 'D3')).count()
    taux_diplomation = (round(nb_diplomes / nb_terminaux * 100, 1)
                        if nb_terminaux else None)

    def _fraction(texte):
        return texte.replace(',', ' ') if texte else None

    finances = _situation_recouvrement()

    # Activité récente : derniers événements du journal de scolarité.
    from scolarite.models import JournalScolarite

    def _icone_journal(action):
        action = action or ''
        if action.startswith('CANDIDATURE'):
            return 'bi-person-plus', '#1267D6'
        if action.startswith('ADMISSION'):
            return 'bi-check2-circle', '#16A36A'
        if action.startswith('CONCOURS'):
            return 'bi-trophy', '#F59E0B'
        if action.startswith('CAMPAGNE'):
            return 'bi-megaphone', '#8B5CF6'
        if action.startswith('INSCRIPTION'):
            return 'bi-card-checklist', '#1267D6'
        if action.startswith(('JURY', 'DELIBERATION')):
            return 'bi-award', '#0D9488'
        return 'bi-activity', '#64748B'

    activite = []
    for j in JournalScolarite.objects.order_by('-timestamp', '-id')[:6]:
        icone, couleur = _icone_journal(j.action)
        activite.append({
            # ``str(j)`` = « <action en langage métier> – <objet> » : lisible
            # tel quel dans le fil d'activité.
            'texte': str(j),
            'action': j.action,
            'acteur': j.acteur_label or '',
            'moment': j.timestamp.isoformat() if j.timestamp else None,
            'icone': icone,
            'couleur': couleur,
        })

    # Alertes institutionnelles
    alerts = []
    jurys_ouverts = SessionJury.objects.filter(statut__in=[SessionJury.Statut.DELIBERATION, SessionJury.Statut.DECISION]).count()
    if jurys_ouverts > 0:
        alerts.append({
            'type': 'warning',
            'message': f"{jurys_ouverts} session(s) de délibération de jury en attente de clôture.",
            'link': '/scolarite/jurys',
            'icon': 'bi-balance-scale',
        })

    conflits_edt = ConflitCreneau.objects.filter(actif=True).count()
    if conflits_edt > 0:
        alerts.append({
            'type': 'critical',
            'message': f"{conflits_edt} conflit(s) ou créneau(x) annulé(s) dans GET-INJS.",
            'link': '/edt',
            'icon': 'bi-calendar-x-fill',
        })

    groupes_sans_aff = Groupe.objects.filter(actif=True, affectations_pedagogiques__isnull=True).count()
    if groupes_sans_aff > 0:
        alerts.append({
            'type': 'info',
            'message': f"{groupes_sans_aff} groupe(s) sans affectation pédagogique enregistrée.",
            'link': '/scolarite/groupes',
            'icon': 'bi-people',
        })

    # Pipeline LMD global
    pipeline = [
        {'id': 'candidature', 'label': 'Candidatures', 'value': nb_candidats, 'icon': 'bi-pencil-square', 'active': True},
        {'id': 'selection', 'label': 'Sélection', 'value': nb_selection, 'icon': 'bi-check2-circle', 'active': True},
        {'id': 'admission', 'label': 'Admissions', 'value': nb_admis, 'icon': 'bi-check2-circle', 'active': True},
        {'id': 'inscription', 'label': 'Inscriptions', 'value': nb_inscrits, 'icon': 'bi-card-checklist', 'active': True},
        {'id': 'cours', 'label': 'Enseignement', 'value': nb_cours, 'icon': 'bi-journal-bookmark', 'active': True},
        {'id': 'evaluation', 'label': 'Évaluations', 'value': nb_evaluations, 'icon': 'bi-file-earmark-text', 'active': True},
        {'id': 'jury', 'label': 'Jurys', 'value': nb_sessions_jury, 'icon': 'bi-balance-scale', 'active': True},
        {'id': 'diplome', 'label': 'Diplômation', 'value': nb_diplomes, 'icon': 'bi-award', 'active': True},
    ]

    return {
        'annee_academique': annee.libelle if annee else None,
        'kpis': {
            'etudiants_inscrits': nb_inscrits,
            'candidats': nb_candidats,
            'admis': nb_admis,
            'taux_admission': (f"{taux_admission}%" if taux_admission is not None
                               else None),
            'enseignants': nb_enseignants,
            'formations': nb_formations,
            'groupes': nb_groupes,
            'cours': nb_cours,
            'taux_presence': (f"{taux_presence}%" if taux_presence is not None
                           else 'Non disponible'),
            'stages_en_cours': nb_stages_en_cours,
            'diplomes_delivres': nb_diplomes,
            'seances_jour': nb_seances_jour,
            'presence_detail': detail_presence,
            'presence_presents': presents_mesures,
            'presence_attendus': total_attendus,
            'presence_seances_mesurees': nb_mesurees,
        },
        'pipeline': pipeline,
        'charts': {
            'repartition_niveaux': [{'label': k, 'value': v} for k, v in niveaux_counts.items()],
            'repartition_formations': formations_dist,
            'repartition_sexe': sexe_dist,
            'evolution_effectifs': evolution,
            'charge_enseignement': charge,
        },
        'taux': {
            'reussite': taux_reussite,
            'reussite_base': _fraction(
                f"{nb_reussites} admis sur {nb_decisions:,} décision(s) de jury"
                if nb_decisions else None),
            'abandon': taux_abandon,
            'abandon_base': _fraction(
                f"{nb_abandons} abandon(s) sur {nb_inscr_tous:,} inscription(s)"
                if nb_inscr_tous else None),
            'diplomation': taux_diplomation,
            'diplomation_base': _fraction(
                f"{nb_diplomes} diplôme(s) validé(s) sur {nb_terminaux:,}"
                " inscrit(s) en année terminale"
                if nb_terminaux else None),
        },
        'finances': finances,
        'activite_recente': activite,
        'alerts': alerts,
        'quick_actions': [
            {'label': 'Nouvelle inscription', 'to': '/scolarite/inscriptions', 'icon': 'bi-person-plus-fill'},
            {'label': 'Planifier EDT', 'to': '/edt/nouveau', 'icon': 'bi-calendar-plus'},
            {'label': 'Sessions de Jury', 'to': '/scolarite/jurys', 'icon': 'bi-balance-scale'},
            {'label': 'Délivrer diplômes', 'to': '/scolarite/graduation', 'icon': 'bi-award'},
        ],
    }


def get_admissions_dashboard():
    """Dashboard Admissions & Concours."""
    annee = get_current_academic_year()
    campagnes = CampagneAdmission.objects.all()
    candidatures = Candidature.objects.all()
    
    total_candidatures = candidatures.count()
    total_admis = Admission.objects.filter(decision=Admission.Decision.ADMIS).count()
    total_attente = Admission.objects.filter(decision=Admission.Decision.EN_ATTENTE).count()
    total_rejetes = candidatures.filter(statut=Candidature.Statut.REFUSE).count()

    par_campagne = []
    for c in campagnes[:5]:
        par_campagne.append({
            'label': c.libelle[:18],
            'value': c.candidatures.count(),
        })

    return {
        'annee_academique': annee.libelle if annee else None,
        'kpis': {
            'campagnes_actives': campagnes.filter(statut=CampagneAdmission.Statut.OUVERTE).count(),
            'total_candidatures': total_candidatures,
            'candidats_admis': total_admis,
            'liste_attente': total_attente,
            'dossiers_rejetes': total_rejetes,
        },
        'charts': {
            'candidatures_par_campagne': par_campagne,
            'statuts_candidatures': [
                {'label': 'Admis', 'value': total_admis, 'color': '#10B981'},
                {'label': 'Attente', 'value': total_attente, 'color': '#F59E0B'},
                {'label': 'Rejetés', 'value': total_rejetes, 'color': '#EF4444'},
                {'label': 'En cours', 'value': max(0, total_candidatures - total_admis - total_attente - total_rejetes), 'color': '#2F80ED'},
            ],
        },
    }


def get_etudiant_dashboard(user):
    """Dashboard personnalisé de l'étudiant connecté.

    Deux règles :
      * **aucune donnée d'un autre étudiant** — l'ancien repli
        ``DossierEtudiant.objects.first()`` servait le dossier d'un tiers au
        compte qui n'en avait pas ;
      * **aucune valeur inventée** — moyennes, crédits, assiduité et solde
        proviennent des modèles (``DecisionJury``, ``Diplome``, …) ou restent
        ``None`` (l'interface affiche « — »).
    """
    dossier = (
        DossierEtudiant.objects.select_related('participant').filter(participant__user=user).first()
        if user else None
    )
    inscription = dossier.inscription_courante if dossier else None
    decision = None
    if dossier is not None:
        # `jurys.services.decision_officielle_pour` : source unique de vérité.
        from jurys.services import decision_officielle_pour
        decision = decision_officielle_pour(dossier.participant)

    diplome = None
    if dossier is not None:
        diplome = Diplome.objects.filter(etudiant=dossier).order_by('-created_at').first()

    nb_modules = (
        ModuleParticipant.objects.filter(participant=dossier.participant).count()
        if dossier else None
    )

    # 60 = deux semestres de 30 ECTS (règle LMD du référentiel).
    credits_requis = 60
    credits_valides = decision.credits_acquis if decision else None
    moyenne = None
    if decision and decision.moyenne_generale is not None:
        moyenne = f"{decision.moyenne_generale} / 20"

    return {
        'annee_academique': libelle_annee_courante(),
        'etudiant': dossier.nom_complet if dossier else None,
        'matricule': dossier.matricule if dossier else None,
        'formation': (
            inscription.ref_formation.intitule
            if inscription and getattr(inscription, 'ref_formation', None) else None
        ),
        'niveau': inscription.niveau.code if inscription and getattr(inscription, 'niveau', None) else None,
        'credits_valides': credits_valides,
        'credits_requis': credits_requis,
        'moyenne_generale': moyenne,
        'taux_presence': None,
        'solde_finance': None,
        # KPIs normalisés pour le Dashboard Engine
        'kpis': {
            'credits_obtenus': credits_valides,
            'credits_restants': (
                max(0, credits_requis - credits_valides) if credits_valides is not None else None
            ),
            'moyenne_generale': moyenne,
            'assiduite': None,
            'ue_validees': None,
            'ue_a_valider': None,
            'solde_finance': None,
            'stage_statut': None,
        },
        'pipeline': [
            {'label': 'Admission', 'value': 'Validée' if inscription else None,
             'active': inscription is not None, 'icon': 'bi-check2'},
            {'label': 'Inscription LMD',
             'value': inscription.get_statut_display() if inscription else None,
             'active': inscription is not None, 'icon': 'bi-card-checklist'},
            {'label': 'Enseignements',
             'value': f"{nb_modules} module(s)" if nb_modules else None,
             'active': bool(nb_modules), 'icon': 'bi-book'},
            {'label': 'Évaluations', 'value': None, 'active': False, 'icon': 'bi-pencil'},
            {'label': 'Jury',
             'value': decision.get_decision_display() if decision else None,
             'active': decision is not None, 'icon': 'bi-balance-scale'},
            {'label': 'Diplômation',
             'value': diplome.get_statut_display() if diplome else None,
             'active': diplome is not None, 'icon': 'bi-award'},
        ],
        'quick_actions': [
            {'label': 'Mon emploi du temps', 'to': '/edt', 'icon': 'bi-calendar3'},
            {'label': 'Mes notes', 'to': '/evaluations', 'icon': 'bi-journal-check'},
            {'label': 'Mes présences', 'to': '/presences', 'icon': 'bi-qr-code'},
            {'label': 'Situation financière', 'to': '/finance-dashboard', 'icon': 'bi-wallet2'},
        ],
    }


def get_enseignant_dashboard(user):
    """Dashboard Enseignant / Formateur.

    Même règle : jamais le profil d'un autre enseignant (ancien repli
    ``Formateur.objects.first()``), jamais de volume horaire ou d'effectif
    inventé (120 h, 85 h, 96 étudiants, 3 groupes…).
    """
    formateur = Formateur.objects.filter(user=user).first() if user else None

    modules = Module.objects.filter(formateur=formateur) if formateur else Module.objects.none()
    nb_modules = modules.count() if formateur else None
    groupes = (
        modules.exclude(groupe='').values('groupe').distinct().count() if formateur else None
    )
    etudiants = (
        ModuleParticipant.objects.filter(module__formateur=formateur)
        .values('participant').distinct().count() if formateur else None
    )
    heures_prevues = None
    if formateur:
        # Somme réelle des volumes prévus de SES modules (0 s'il n'en a aucun).
        heures_prevues = float(modules.aggregate(total=Sum('duree_prevue_heures'))['total'] or 0)

    return {
        'annee_academique': libelle_annee_courante(),
        'enseignant': f"{formateur.nom} {formateur.prenom}" if formateur else None,
        'specialite': (formateur.specialite or None) if formateur else None,
        'kpis': {
            'cours_assignes': nb_modules,
            'heures_prevues': heures_prevues,
            'heures_realisees': None,
            'heures_cm': None,
            'heures_td': None,
            'heures_tp': None,
            'groupes': groupes,
            'etudiants': etudiants,
            'evaluations_en_attente': None,
            'absences_a_traiter': None,
        },
        'quick_actions': [
            {'label': 'Mes groupes', 'to': '/scolarite/groupes', 'icon': 'bi-people'},
            {'label': 'Saisir notes', 'to': '/evaluations', 'icon': 'bi-pencil-square'},
            {'label': 'Lancer un appel', 'to': '/presences', 'icon': 'bi-qr-code-scan'},
            {'label': 'Mon EDT', 'to': '/edt', 'icon': 'bi-calendar3'},
        ],
    }


def get_scolarite_dashboard():
    """Dashboard Scolarité & Admissions."""
    annee = get_current_academic_year()
    annee_id = annee.id if annee else None

    inscriptions = InscriptionAdministrative.objects.all()
    candidatures = Candidature.objects.all()
    admissions = Admission.objects.all()
    groupes = Groupe.objects.all()
    maquettes = Maquette.objects.all()

    if annee_id:
        inscriptions = inscriptions.filter(annee_academique_id=annee_id)
        candidatures = candidatures.filter(annee_academique_id=annee_id)
        admissions = admissions.filter(annee_academique_id=annee_id)
        groupes = groupes.filter(annee_academique_id=annee_id)
        maquettes = maquettes.filter(annee_academique_id=annee_id)

    total_inscrits = inscriptions.count()
    total_validees = inscriptions.filter(statut=InscriptionAdministrative.Statut.VALIDEE).count()
    total_attente = inscriptions.filter(statut=InscriptionAdministrative.Statut.EN_ATTENTE).count()

    par_formation = []
    for f in RefFormation.objects.filter(actif=True)[:6]:
        nb = inscriptions.filter(ref_formation=f).count()
        par_formation.append({'label': f.intitule[:20], 'value': nb})

    return {
        'annee_academique': annee.libelle if annee else None,
        'kpis': {
            'total_inscrits': total_inscrits,
            'inscriptions_validees': total_validees,
            'en_attente_pieces': total_attente,
            'total_candidatures': candidatures.count(),
            'admissions_prononcees': admissions.filter(decision=Admission.Decision.ADMIS).count(),
            'groupes_pedagogiques': groupes.count(),
            'maquettes_actives': maquettes.filter(statut=Maquette.Statut.ACTIVE).count(),
        },
        'charts': {
            'inscriptions_par_formation': par_formation,
            'statuts_inscriptions': [
                {'label': 'Validées', 'value': total_validees, 'color': '#10B981'},
                {'label': 'En attente', 'value': total_attente, 'color': '#F59E0B'},
                {'label': 'Autres', 'value': max(0, total_inscrits - total_validees - total_attente), 'color': '#6B7280'},
            ],
        },
    }


def get_pedagogie_dashboard():
    """Dashboard Pédagogie, Enseignements & Maquettes."""
    annee = get_current_academic_year()
    enseignants = Formateur.objects.all()
    modules = Module.objects.all()
    ecues = ECUE.objects.all()
    maquettes = Maquette.objects.filter(statut=Maquette.Statut.ACTIVE)

    # Volume planifié = affectations pédagogiques (chaîne LMD). Les anciens
    # replis (310 h prévues, 245 h exécutées, 79,0 % de réalisation, 60 h
    # par enseignant) étaient des constantes de maquette affichées comme
    # des mesures : les heures « exécutées » n'ont pas de source fiable
    # (pas de pointage des séances enseignants) et restent donc ``None``.
    affectations = AffectationPedagogique.objects.all()
    if annee:
        affectations = affectations.filter(annee_academique_id=annee.id)
    heures_prevues = affectations.aggregate(total=Sum('volume_horaire'))['total'] or 0

    nb_enseignants = enseignants.count()
    nb_modules = modules.count()
    nb_ecues = ecues.count()
    nb_ue = UE.objects.count()
    vh = float(heures_prevues)

    charges_enseignants = [
        {'label': (r['enseignant__nom'] or '')[:15], 'value': float(r['h'] or 0)}
        for r in (affectations.values('enseignant__nom')
                  .annotate(h=Sum('volume_horaire')).order_by('-h')[:5])
    ]

    return {
        'annee_academique': annee.libelle if annee else None,
        'kpis': {
            'enseignants_actifs': nb_enseignants,
            'modules_ouverts': nb_modules,
            'ecues_maquettes': nb_ecues,
            'maquettes_lmd': maquettes.count(),
            'heures_prevues_totales': vh,
            'heures_executees': None,
            'taux_realisation_vh': None,
            # Clés alignées sur le Dashboard Engine frontend
            'total_ue': nb_ue,
            'total_ecue': nb_ecues,
            'volume_horaire_planifie': vh,
        },
        'charts': {
            'charges_par_enseignant': charges_enseignants,
        },
    }


def get_presences_dashboard():
    """Dashboard Assiduité & Présences — séances LMD et présences rattachées.

    Les compteurs proviennent de ``presences.seances_supervision`` : une séance
    de l'EDT (``AffectationCreneau``) et les ``Pointage`` réellement rattachés à
    elle. Aucune valeur de repli n'est inventée : un compteur sans donnée vaut 0
    (c'est un décompte), un taux sans dénominateur vaut ``None``.
    """
    today = timezone.localdate()
    supervision = _supervision_du_jour(today)
    seances = supervision['seances']

    presents_jour = sum(s['presences']['presents'] for s in seances)
    retards_jour = sum(s['presences']['retards'] for s in seances)
    absents_jour = (sum(s['presences']['absents_injustifies'] for s in seances)
                    + sum(s['presences']['absents_justifies'] for s in seances))
    pointages_jour = Pointage.objects.filter(date_journee=today).count()
    total_pointages = Pointage.objects.count()
    taux_assiduite, detail_presence, presents_mesures, total_attendus, nb_mesurees = (
        _mesure_presence(seances)
    )
    anomalies_geofence = (Pointage.objects.filter(date_journee=today)
                          .exclude(outside_geofence_count=0).count())

    return {
        'date': str(today),
        'kpis': {
            'seances_jour': supervision['resume']['seances_total'],
            'seances_en_cours': supervision['resume']['seances_en_cours'],
            'pointages_jour': pointages_jour,
            'presents_jour': presents_jour,
            'retards_jour': retards_jour,
            'absents_jour': absents_jour,
            'total_historique_pointages': total_pointages,
            'taux_assiduite_moyen': taux_assiduite,
            'presence_detail': detail_presence,
            'presence_presents': presents_mesures,
            'presence_attendus': total_attendus,
            'presence_seances_mesurees': nb_mesurees,
            'anomalies_geofence': anomalies_geofence,
        },
        'charts': {
            'repartition_du_jour': [
                {'label': 'Présents', 'value': presents_jour, 'color': '#10B981'},
                {'label': 'Retards', 'value': retards_jour, 'color': '#F59E0B'},
                {'label': 'Absents', 'value': absents_jour, 'color': '#EF4444'},
            ],
        },
    }


def get_finances_dashboard():
    """Dashboard Finances Étudiantes & Recouvrement.

    Montants réels uniquement : les anciens replis (960 000 XOF facturés ET
    recouvrés, solde « 0 XOF », taux 100 %) présentaient une situation
    soldée qui n'existait pas. Base = échéanciers (même définition que le
    hub Finances) ; l'encaissé affiché = paiements CONFIRMÉS/RAPPROCHÉS.
    """
    factures = Facture.objects.all()
    paiements = Paiement.objects.all()
    echeanciers = Echeancier.objects.all()

    situation = _situation_recouvrement()
    total_attendu = Decimal(str(situation['montant_attendu']))
    lignes_payees = Decimal(str(situation['montant_encaisse']))
    encaisse_confirme = (paiements.filter(statut__in=('CONFIRME', 'RAPPROCHE'))
                         .aggregate(s=Sum('montant'))['s'] or Decimal('0'))
    taux = situation['taux_recouvrement']

    return {
        'kpis': {
            'total_facture_xof': _fmt_xof(total_attendu),
            'total_recouvre_xof': _fmt_xof(encaisse_confirme),
            'solde_restant_xof': _fmt_xof(total_attendu - lignes_payees),
            'taux_recouvrement': (f"{taux}%".replace('.', ',') if taux is not None
                                  else None),
            'factures_soldes': factures.filter(statut='PAYEE').count(),
            'quittances_delivrees': paiements.filter(
                statut__in=('CONFIRME', 'RAPPROCHE')).count(),
            'echeanciers_actifs': echeanciers.count(),
        },
        'charts': {
            'recouvrement_statuts': [
                {'label': 'Soldé', 'value': float(lignes_payees), 'color': '#10B981'},
                {'label': 'Restant', 'value': float(total_attendu - lignes_payees),
                 'color': '#EF4444'},
            ],
        },
    }


def get_examens_dashboard():
    """Dashboard Examens, Jurys LMD & Diplômation."""
    sessions = SessionJury.objects.all()
    decisions = DecisionJury.objects.all()
    diplomes = Diplome.objects.all()

    # Compteurs réels uniquement — les anciens replis (`or diplomes.count()`,
    # `or 1`, mentions 3/3/0/0) affichaient des admis, des PV scellés et des
    # mentions qui n'existaient pas.
    total_admis = decisions.filter(decision='ADMIS').count()
    total_ajournes = decisions.filter(decision='AJOURNE').count()

    sessions_ouvertes = sessions.filter(
        statut__in=[SessionJury.Statut.DELIBERATION, SessionJury.Statut.DECISION]
    ).count()
    sessions_cloturees = sessions.filter(statut=SessionJury.Statut.PUBLIE).count()
    nb_diplomes = diplomes.count()
    pv_scelles = PVJury.objects.count()
    mentions = [
        {'label': r['mention'], 'value': r['n'], 'color': couleur}
        for r, couleur in zip(
            diplomes.exclude(mention='')
            .values('mention').annotate(n=Count('id')).order_by('-n')[:4],
            ['#10B981', '#2F80ED', '#F59E0B', '#9CA3AF'],
        )
    ]

    return {
        'kpis': {
            'sessions_jury': sessions.count(),
            'sessions_cloturees': sessions_cloturees,
            'decisions_rendues': decisions.count(),
            'admis_jury': total_admis,
            'ajournes_jury': total_ajournes,
            'diplomes_sha256': nb_diplomes,
            'diplomes_certifies': diplomes.filter(statut=Diplome.Statut.VALIDATED).count(),
            # Clés alignées sur le Dashboard Engine frontend (onglet Jurys)
            'sessions_ouvertes': sessions_ouvertes,
            'deliberations_en_cours': sessions_ouvertes,
            'pv_scelles': pv_scelles,
            'diplomes_delivres': nb_diplomes,
        },
        'charts': {
            'mentions_diplomes': mentions,
        },
    }


def get_logistique_dashboard():
    """Dashboard Patrimoine, Espaces & Stages."""
    equipements = Equipement.objects.all()
    maintenances = Maintenance.objects.all()
    conventions = ConventionStage.objects.all()

    # Aucun repli chiffré : les anciens `or 5` / `or 6` et les constantes
    # « 3 installations », « 4 organismes » étaient inventés. Les
    # installations sportives n'ont pas de référentiel compté ici → None.
    from stages.models import OrganismeAccueil

    soutenus = conventions.filter(
        statut=ConventionStage.Statut.VALIDEE_JURY).count()
    en_cours = conventions.filter(statut=ConventionStage.Statut.EN_COURS).count()
    return {
        'kpis': {
            'equipements_inventories': equipements.count(),
            'maintenances_en_cours': maintenances.filter(statut='EN_COURS').count(),
            'installations_sportives': None,
            'conventions_stage': conventions.count(),
            'stages_soutenus': soutenus,
            'organismes_partenaires': OrganismeAccueil.objects.count(),
        },
        'charts': {
            'conventions_statuts': [
                {'label': 'Validée Jury', 'value': soutenus, 'color': '#10B981'},
                {'label': 'En cours', 'value': en_cours, 'color': '#2F80ED'},
            ],
        },
    }
