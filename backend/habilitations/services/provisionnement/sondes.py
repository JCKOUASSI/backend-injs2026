"""Sondes événementielles (C3 point 1) — lecture SEULE des apps métier.

Chaque sonde est une fonction qui retourne des :class:`Fait` sans rien
écrire dans les comptes : la mise en file puis l'approbation humaine sont
des étapes distinctes (:mod:`...file` et :mod:`...approbation`).

Les imports des applications métier sont faits À L'INTÉRIEUR des fonctions
et protégés par ``try/except ImportError`` : le dispositif d'habilitation
reste autonome et une application absente ne fait que rendre sa sonde vide.
Aucune règle métier n'est inventée : seuls les statuts/états écrits dans
les modèles existants sont observés.
"""
from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone


@dataclass
class Fait:
    """Un fait métier pouvant donner lieu à une proposition."""

    declencheur: str
    action: str
    source_app: str
    source_modele: str
    source_objet_id: str
    source_libelle: str
    proposition: dict
    username_cible: str = ''
    version: str = ''

    def cle(self):
        """Clé de déduplication (la version permet de re-proposer après changement)."""
        return '|'.join([
            self.declencheur, self.action,
            f'{self.source_app}.{self.source_modele}',
            str(self.source_objet_id), self.version,
        ])


def _charge_etudiant(*, username, nom='', prenoms='', email='', telephone='',
                    motif='', roles=None, perimetres=None):
    """Charge utile type d'un compte étudiant (rôle ETUDIANT, mobile)."""
    return {
        'identifiants': {
            'username': username,
            'email': email or '',
            'role_legacy': 'AUDITEUR',
        },
        'personne': {
            'nom': nom, 'prenoms': prenoms, 'email': email, 'telephone': telephone or '',
        },
        'canal': 'MOBILE',
        'motif': motif,
        'roles': roles if roles is not None else [
            {'role': 'ETUDIANT', 'niveau': 'N1',
             'perimetres_generiques': perimetres or []},
        ],
    }


def _deja_gouveme(user):
    """Vrai si l'utilisateur métier a déjà un profil CURP ACTIF."""
    if user is None:
        return False
    profil = getattr(user, 'profil_habilitation', None)
    return profil is not None


# ---------------------------------------------------------------------------
# 1. Admission d'un candidat validée → proposition de compte étudiant
# ---------------------------------------------------------------------------
def sonde_admission():
    try:
        from admissions.models import Admission
    except ImportError:
        return []
    faits = []
    admissions = (
        Admission.objects
        .filter(decision__in=['ADMIS', 'ADMIS_SOUS_RESERVE'])
        .select_related('candidat', 'candidat__participant', 'ref_formation')
    )
    for adm in admissions:
        participant = getattr(adm.candidat, 'participant', None)
        user = getattr(participant, 'user', None) if participant is not None else None
        if _deja_gouveme(user):
            continue
        username = (
            getattr(participant, 'matricule', '') or ''
        ).strip().lower().replace(' ', '') or f'admis-{adm.pk}'
        libelle_formation = getattr(adm.ref_formation, 'intitule', '') or getattr(adm.ref_formation, 'nom', '') or ''
        charge = _charge_etudiant(
            username=username,
            nom=adm.candidat.nom, prenoms=adm.candidat.prenom,
            email=adm.candidat.email or '', telephone=adm.candidat.telephone or '',
            motif=f"Admission {adm.reference_decision or ('#' + str(adm.pk))} "
                  f"({adm.get_decision_display()}){(' — ' + libelle_formation) if libelle_formation else ''}.",
        )
        faits.append(Fait(
            'ADMISSION', 'CREER_COMPTE', 'admissions', 'Admission', str(adm.pk),
            f"{adm.candidat.prenom} {adm.candidat.nom} — {libelle_formation}",
            charge, username_cible=username,
        ))
    return faits


# ---------------------------------------------------------------------------
# 2. Inscription administrative validée → activation + périmètres
# ---------------------------------------------------------------------------
def sonde_inscription():
    try:
        from scolarite.models import InscriptionAdministrative
    except ImportError:
        return []
    faits = []
    insc = (
        InscriptionAdministrative.objects
        .filter(statut='VALIDEE')
        .select_related(
            'etudiant', 'etudiant__participant', 'etudiant__participant__user',
            'ref_formation', 'niveau',
        )
    )
    for ia in insc:
        participant = getattr(ia.etudiant, 'participant', None)
        user = getattr(participant, 'user', None) if participant is not None else None
        profil = getattr(user, 'profil_habilitation', None)
        if profil is not None and profil.statut == 'ACTIF' and profil.attributions.filter(
            statut='ACTIVE', role__code='ETUDIANT',
        ).exists():
            continue
        username = (getattr(participant, 'matricule', '') or '').strip().lower() or f'etudiant-{ia.etudiant_id}'
        libelle_formation = getattr(ia.ref_formation, 'intitule', '') or getattr(ia.ref_formation, 'nom', '') or ''
        charge = _charge_etudiant(
            username=username,
            nom=getattr(participant, 'nom', ''), prenoms=getattr(participant, 'prenom', ''),
            email=getattr(participant, 'email', '') or '',
            telephone=getattr(participant, 'telephone', '') or '',
            motif=f"Inscription administrative validée ({ia.annee_academique_id}) — {libelle_formation}.",
        )
        action = 'ACTIVER_COMPTE' if user is not None else 'CREER_COMPTE'
        faits.append(Fait(
            'INSCRIPTION', action, 'scolarite', 'InscriptionAdministrative', str(ia.pk),
            f"{getattr(participant, 'prenom', '')} {getattr(participant, 'nom', '')} — {libelle_formation}",
            charge, username_cible=username, version=str(ia.annee_academique_id),
        ))
    return faits


# ---------------------------------------------------------------------------
# 3. Recrutement d'un agent en RH → proposition de compte agent
# ---------------------------------------------------------------------------
def sonde_recrutement():
    try:
        from ressources_humaines.models import Agent
    except ImportError:
        return []
    faits = []
    agents = (
        Agent.objects
        .filter(statut='ACTIF')
        .select_related('user')
        .prefetch_related('affectations__fonction')
    )
    aujourd_hui = timezone.localdate()
    for agent in agents:
        if agent.date_entree and agent.date_entree > aujourd_hui:
            continue
        if _deja_gouveme(agent.user):
            continue
        username = (agent.matricule or '').strip().lower().replace(' ', '') or f'agent-{agent.pk}'
        fonctions = ', '.join(sorted({
            a.fonction.intitule for a in agent.affectations.all()
            if a.date_fin is None
        }))
        # Le rôle n'est pas déductible sans décision explicite : le valideur
        # le complète à l'approbation (aucun droit n'est supposé).
        charge = {
            'identifiants': {'username': username, 'email': agent.email or '',
                              'role_legacy': ''},
            'personne': {
                'nom': agent.nom, 'prenoms': agent.prenom, 'email': agent.email or '',
                'telephone': agent.telephone or '', 'service': fonctions,
            },
            'canal': 'WEB',
            'motif': f"Recrutement enregistré en RH (matricule {agent.matricule})"
                     f"{(' — fonction : ' + fonctions) if fonctions else ''}. "
                     f"Rôle à déterminer par le valideur.",
            'roles': [],
            'role_a_completer': True,
        }
        faits.append(Fait(
            'RECRUTEMENT', 'CREER_COMPTE', 'ressources_humaines', 'Agent', str(agent.pk),
            f"{agent.prenom} {agent.nom} ({agent.matricule})",
            charge, username_cible=username,
        ))
    return faits


# ---------------------------------------------------------------------------
# 4. Affectation pédagogique d'un enseignant → rôle ENSEIGNANT + ECUE
# ---------------------------------------------------------------------------
def sonde_affectation_enseignant():
    try:
        from scolarite.models import AffectationPedagogique
    except ImportError:
        return []
    faits = []
    vues = {}
    affectations = (
        AffectationPedagogique.objects
        .filter(statut__in=['VALIDEE', 'REALISEE'])
        .select_related('enseignant', 'enseignant__user', 'ecue', 'ue', 'annee_academique')
    )
    for af in affectations:
        formateur = af.enseignant
        user = getattr(formateur, 'user', None)
        annee = str(af.annee_academique_id)
        vues.setdefault(formateur.pk, {'af': af, 'ecues': [], 'user': user, 'annee': annee})
        if af.ecue_id:
            vues[formateur.pk]['ecues'].append((af.ecue_id, str(af.ecue)))
        elif af.ue_id:
            vues[formateur.pk]['ecues'].append((af.ue_id, str(af.ue)))

    for formateur_pk, vue in vues.items():
        af = vue['af']
        profil = getattr(vue['user'], 'profil_habilitation', None)
        ecues = vue['ecues']
        # Périmètres génériques pointant vers les ECUE/UE affectées (référence
        # polymorphe, voir Perimetre.obtenir_ou_creer à l'approbation).
        perimetres = [
            {'type': 'MODULE_ECUE', 'app': 'scolarite', 'modele': 'ECUE',
             'objet_id': pid, 'reference': libelle}
            for pid, libelle in ecues
        ]
        roles = [{'role': 'ENSEIGNANT', 'niveau': 'N2',
                  'perimetres_generiques': perimetres}]
        motif = (f"Affectation pédagogique validée ({vue['annee']}) : "
                 f"{len(ecues)} élément(s) pédagogiques.")
        if profil is None or vue['user'] is None:
            username = (getattr(af.enseignant, 'numerobadge', '') or '').strip().lower() or f'formateur-{formateur_pk}'
            charge = {
                'identifiants': {'username': username, 'email': af.enseignant.email or '',
                                  'role_legacy': 'FORMATEUR'},
                'personne': {'nom': af.enseignant.nom, 'prenoms': af.enseignant.prenom,
                              'email': af.enseignant.email or '',
                              'telephone': af.enseignant.telephone or ''},
                'canal': 'MOBILE', 'motif': motif, 'roles': roles,
            }
            action = 'CREER_COMPTE'
            username_cible = username
        else:
            deja_role = profil.attributions.filter(
                statut='ACTIVE', role__code='ENSEIGNANT').exists()
            if deja_role:
                continue
            charge = {'motif': motif, 'roles': roles}
            action = 'ATTRIBUER_ROLE'
            username_cible = vue['user'].get_username()
        faits.append(Fait(
            'AFFECTATION_ENSEIGNANT', action, 'scolarite',
            'AffectationPedagogique', str(formateur_pk),
            f"{af.enseignant.prenom} {af.enseignant.nom} ({vue['annee']})",
            charge, username_cible=username_cible, version=vue['annee'],
        ))
    return faits


# ---------------------------------------------------------------------------
# 5. Fin de relation (départ agent / fin d'inscription) → suspension
# ---------------------------------------------------------------------------
def sonde_fin_relation(grace_jours=7):
    faits = []
    date_limite = timezone.localdate() - timedelta(days=grace_jours)

    # 5a. Agents dont la date de sortie est passée (délai de grâce inclus).
    try:
        from ressources_humaines.models import Agent
        for agent in (
            Agent.objects
            .filter(date_sortie__isnull=False, date_sortie__lte=date_limite)
            .select_related('user')
        ):
            profil = getattr(agent.user, 'profil_habilitation', None)
            if profil is None or profil.statut != 'ACTIF':
                continue
            faits.append(Fait(
                'FIN_RELATION', 'SUSPENDRE_COMPTE', 'ressources_humaines', 'Agent',
                str(agent.pk), f"Fin de relation agent {agent.prenom} {agent.nom}",
                {
                    'motif': f"Fin de relation au {agent.date_sortie.isoformat()} "
                             f"(délai de grâce de {grace_jours} jours écoulé).",
                    'transition': 'suspendre',
                },
                username_cible=agent.user.get_username(),
                version=agent.date_sortie.isoformat(),
            ))
    except ImportError:
        pass

    # 5b. Étudiants dont la dernière inscription est TERMINÉE, sans
    # inscription validée postérieure, après délai de grâce.
    try:
        from scolarite.models import InscriptionAdministrative
        for ia in (
            InscriptionAdministrative.objects
            .filter(statut='TERMINEE')
            .select_related('etudiant', 'etudiant__participant', 'etudiant__participant__user')
        ):
            participant = getattr(ia.etudiant, 'participant', None)
            user = getattr(participant, 'user', None) if participant is not None else None
            profil = getattr(user, 'profil_habilitation', None)
            if profil is None or profil.statut != 'ACTIF':
                continue
            # Une inscription validée, quelle que soit l'année, annule la fin.
            if ia.etudiant.inscriptions.filter(statut='VALIDEE').exclude(pk=ia.pk).exists():
                continue
            # Le délai de grâce s'appuie sur la dernière modification de l'IA.
            if timezone.localdate(ia.updated_at.date()) > date_limite:
                continue
            faits.append(Fait(
                'FIN_RELATION', 'SUSPENDRE_COMPTE', 'scolarite',
                'InscriptionAdministrative', str(ia.pk),
                f"Fin d'inscription — {getattr(participant, 'nom', '')}",
                {
                    'motif': f"Fin d'inscription (statut TERMINÉE), délai de grâce de "
                             f"{grace_jours} jours écoulé.",
                    'transition': 'suspendre',
                },
                username_cible=user.get_username(),
                version=str(ia.pk),
            ))
    except ImportError:
        pass
    return faits


# ---------------------------------------------------------------------------
# 6. Désignation d'un membre de jury → rôle MEMBRE_JURY (+ périmètre
#    formation de la session). ``jurys.MembreJury.user`` référence un User
#    EXISTANT (PROTECT) ; la sonde se limite aux utilisateurs qui ont déjà
#    un compte CURP : un membre sans compte passe par la proposition
#    manuelle depuis la fiche de compte (écran U4), pas par la sonde
#    (aucun droit d'accès n'est deviné automatiquement).
# ---------------------------------------------------------------------------
def sonde_jury():
    try:
        from jurys.models import MembreJury
    except ImportError:
        return []
    faits = []
    membres = (
        MembreJury.objects
        .select_related(
            'session', 'session__annee_academique',
            'session__ref_formation', 'session__niveau', 'user',
        )
        .order_by('pk')
    )
    for membre in membres:
        session = membre.session
        user = membre.user
        profil = getattr(user, 'profil_habilitation', None)
        if profil is None:
            # Pas de compte CURP : le création passe par l'écran U4
            # (proposition manuelle), pas par la sonde.
            continue
        if profil.attributions.filter(
            statut='ACTIVE', role__code='MEMBRE_JURY',
        ).exists():
            continue
        formation = getattr(session, 'ref_formation', None)
        libelle_formation = (
            getattr(formation, 'intitule', '') or str(formation or '')
        )
        # Périmètre du rôle : la formation de la session de jury
        # (catalogue des rôles : MEMBRE_JURY est borné sur FORMATION).
        perimetres = []
        if formation is not None:
            perimetres.append({
                'type': 'FORMATION', 'app': 'formations',
                'modele': 'RefFormation', 'objet_id': formation.pk,
                'reference': libelle_formation,
            })
        roles = [{'role': 'MEMBRE_JURY', 'niveau': 'N2',
                  'perimetres_generiques': perimetres}]
        fonction = membre.get_fonction_display()
        motif = (
            f"Désignation au jury en tant que {fonction.lower()} "
            f"({session})."
        )
        faits.append(Fait(
            'JURY', 'ATTRIBUER_ROLE', 'jurys', 'MembreJury', str(membre.pk),
            f"{user.get_full_name() or user.get_username()} — "
            f"{fonction} — {libelle_formation}",
            {'motif': motif, 'roles': roles},
            username_cible=user.get_username(),
            version=str(session.pk),
        ))
    return faits


#: Ordre de parcours et fonction associée (la déclaration active se fait
#: via :func:`habilitations.services.drapeaux.sonde_active`).
SONDES = {
    'ADMISSION': sonde_admission,
    'INSCRIPTION': sonde_inscription,
    'RECRUTEMENT': sonde_recrutement,
    'AFFECTATION_ENSEIGNANT': sonde_affectation_enseignant,
    'FIN_RELATION': sonde_fin_relation,
    'JURY': sonde_jury,
}
