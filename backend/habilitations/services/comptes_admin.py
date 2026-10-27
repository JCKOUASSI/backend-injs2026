"""Services de la console d'administration CURP (unité U4).

Logique métier des écrans C2 : recherche de personne, création de compte,
calcul du **différentiel de droits obligatoire**, modification bornée,
changements de statut, garde des deux administrateurs et simulation
d'import. Tous les gestes sont tracés via :func:`journaliser` et
s'exécutent en transaction.

Cette couche n'écrit que les tables de gouvernance CURP, à l'exception
documentée du miroir ``User.is_active`` sur les changements de statut (la
suspension doit avoir un effet réel, comme sur l'écran Utilisateurs
existant). Le moteur d'autorisation reste en mode observation.
"""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from ..models import (
    AttributionRole,
    CompteUtilisateur,
    DelegationHabilitation,
    JournalHabilitation,
    PermissionAttribuee,
    PermissionMetier,
    Perimetre,
    Personne,
    RoleMetier,
)
from .identite import generer_matricule_personne
from .journalisation import journaliser
from .machine_etats import (
    TRANSITIONS as _GRAPHE_ETATS,
    TransitionIllegale,
    transition_legale,
)

User = get_user_model()

#: Rôle d'administration technique du nouveau référentiel.
ROLE_ADMIN_SYSTEME = 'ADMIN_SYSTEME'
#: Trio d'administration INJS-LMD (renommé en L4b : anciennement
#: `ROLES_LEGACY_ADMIN`, un nom devenu trompeur puisque son contenu est
#: entièrement canonique). Sert à garder au moins deux administrateurs actifs.
ROLES_ADMIN_SYSTEME = frozenset({'ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN'})

SEUIL_ADMINISTRATEURS = 2


class ErreurConsole(Exception):
    """Erreur métier de la console (code + message français)."""

    def __init__(self, code, message, statut=400):
        self.code = code
        self.statut = statut
        super().__init__(message)


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------
def permissions_des_roles(roles):
    """Ensemble des codes de permissions portés par des rôles donnés."""
    return set(
        PermissionMetier.objects.filter(
            roles_octroyants__in=roles
        ).values_list('code', flat=True).distinct()
    )


def _derogations_actives(compte):
    return compte.derogations.filter(
        statut=PermissionAttribuee.Statut.ACTIVE
    ).select_related('permission')


def permissions_effectives(compte):
    """Codes de permissions actuellement octroyés au compte (rôles +
    dérogations actives, les RETRAIT étant prioritaires)."""
    aujourdhui = timezone.localdate()
    attributions = compte.attributions.filter(
        statut=AttributionRole.Statut.ACTIVE
    ).select_related('role')
    roles = [a.role for a in attributions if a.est_active(aujourdhui)]
    codes = permissions_des_roles(roles)
    for derogation in _derogations_actives(compte):
        if not derogation.est_active(aujourdhui):
            continue
        if derogation.sens == PermissionAttribuee.Sens.OCTROI:
            codes.add(derogation.permission.code)
        else:
            codes.discard(derogation.permission.code)
    return codes


# ---------------------------------------------------------------------------
# Différentiel de droits
# ---------------------------------------------------------------------------
def _avertissements_roles(roles, compte=None):
    """Contrôles de cohérence purs (non bloquants en U4, montrés à l'écran)."""
    avertissements = []
    codes = [r.code for r in roles]
    # Rôles incompatibles deux à deux (séparation des tâches) : une seule
    # alerte par couple, la paire étant normalisée dans l'ordre des codes.
    paires = set()
    for role in roles:
        conflits = role.incompatible_avec.filter(
            code__in=codes
        ).values_list('code', flat=True)
        for code_conflit in conflits:
            paire = tuple(sorted((role.code, code_conflit)))
            if paire in paires:
                continue
            paires.add(paire)
            avertissements.append({
                'code': 'ROLES_INCOMPATIBLES',
                'message': f'Rôles incompatibles cumulés : {paire[0]} et {paire[1]}.',
            })
        if not role.module_est_installe():
            avertissements.append({
                'code': 'MODULE_REQUIS_ABSENT',
                'message': f'Le module requis par {role.code} est indisponible.',
            })
    return avertissements


def calculer_differential(compte, roles_cibles, derogations_cibles=None):
    """Retourne gagnes/perdus/conservés (codes de permissions) + rôles +
    avertissements, entre l'état actuel du compte et l'état cible proposé.
    """
    roles_cibles = list(roles_cibles)
    actuels = permissions_effectives(compte)

    codes_cibles = permissions_des_roles(roles_cibles)
    for code_perm, sens in (derogations_cibles or {}).items():
        if sens == PermissionAttribuee.Sens.OCTROI:
            codes_cibles.add(code_perm)
        else:
            codes_cibles.discard(code_perm)

    roles_actuels = set(
        compte.attributions.filter(statut=AttributionRole.Statut.ACTIVE)
        .values_list('role__code', flat=True)
    )
    roles_cible_codes = {r.code for r in roles_cibles}

    # Garde des administrateurs : ne pas retirer le dernier rôle admin si ça
    # faisait descendre le parc sous le seuil.
    avertissements = _avertissements_roles(roles_cibles, compte)
    if (
        ROLE_ADMIN_SYSTEME in roles_actuels
        and ROLE_ADMIN_SYSTEME not in roles_cible_codes
        and compte.statut == CompteUtilisateur.Statut.ACTIF
        and administrateurs_actifs() <= SEUIL_ADMINISTRATEURS
    ):
        avertissements.append({
            'code': 'SEUIL_ADMINISTRATEURS',
            'message': (
                'Cette opération ferait passer le nombre d’administrateurs '
                'actifs sous deux : elle sera refusée.'
            ),
        })

    return {
        'gagnes': sorted(codes_cibles - actuels),
        'perdus': sorted(actuels - codes_cibles),
        'conserves': sorted(actuels & codes_cibles),
        'roles_ajoutes': sorted(roles_cible_codes - roles_actuels),
        'roles_retires': sorted(roles_actuels - roles_cible_codes),
        'avertissements': avertissements,
        'total_actuel': len(actuels),
        'total_cible': len(codes_cibles),
    }


def administrateurs_actifs():
    """Nombre de comptes d'administration encore capables d'agir.

    Combine les comptes legacy (rôle du trio, actif) et les comptes CURP
    (attribution active ADMIN_SYSTEME, statut ACTIF). Un profil CURP
    suspendu/désactivé fait sortir son User du décompte.
    """
    users = User.objects.filter(
        role__in=ROLES_ADMIN_SYSTEME, is_active=True
    ).select_related('profil_habilitation')
    nombre = 0
    for user in users:
        profil = getattr(user, 'profil_habilitation', None)
        if profil is not None and profil.statut != CompteUtilisateur.Statut.ACTIF:
            continue
        nombre += 1
    # Éventuels administrateurs CURP sans rôle legacy admin (attribution
    # directe ADMIN_SYSTEME) : les compter une seule fois.
    ids_comptes = (
        AttributionRole.objects.filter(
            statut=AttributionRole.Statut.ACTIVE,
            role__code=ROLE_ADMIN_SYSTEME,
            compte__statut=CompteUtilisateur.Statut.ACTIF,
        )
        .exclude(compte__user__role__in=ROLES_ADMIN_SYSTEME)
        .values_list('compte__user_id', flat=True)
    )
    nombre += User.objects.filter(pk__in=list(ids_comptes), is_active=True).count()
    return nombre


def _verifier_seuil_admin(si_retrait_admin=False, compte=None):
    if administrateurs_actifs() < SEUIL_ADMINISTRATEURS:
        raise ErreurConsole(
            'SEUIL_ADMINISTRATEURS',
            'Au moins deux administrateurs actifs doivent être conservés.',
            statut=409,
        )


# ---------------------------------------------------------------------------
# Périmètres
# ---------------------------------------------------------------------------
def _perimetre_borne(type_p, object_id):
    """Pose un périmètre borné sur un objet métier quelconque (LOT 5, L4-02).

    Les types admissibles sont ceux du registre du résolveur
    (``resolveurs.TYPES_OBJETS``) : la console ne peut borner que sur des
    objets réels, vérifiés ici. ``PERIMETRE_INCONNU`` (400) sur type inconnu
    ou objet introuvable — la saisie ne crée jamais de périmètre fantôme.
    """
    from habilitations.services.resolveurs import TYPES_OBJETS
    if type_p not in TYPES_OBJETS:
        raise ErreurConsole(
            'PERIMETRE_INCONNU',
            f'Type de périmètre « {type_p} » non posable par la console.',
        )
    app, model = TYPES_OBJETS[type_p]
    ct = ContentType.objects.get_by_natural_key(app, model)
    classe = ct.model_class()
    objet = classe.objects.filter(pk=object_id).first()
    if objet is None:
        raise ErreurConsole(
            'PERIMETRE_INCONNU',
            f'{type_p} {object_id} introuvable.',
        )
    reference = (
        str(getattr(objet, 'numero', '') or getattr(objet, 'code', '')
            or getattr(objet, 'nom', '') or getattr(objet, 'libelle', '')
            or objet.pk)
    )[:100]
    libelle = (
        str(getattr(objet, 'nom', '') or getattr(objet, 'libelle', '') or '')
    )[:255]
    perimetre, _ = Perimetre.objects.get_or_create(
        type=type_p, content_type=ct, object_id=objet.pk,
        defaults={'reference_lisible': reference, 'libelle': libelle},
    )
    return perimetre


def _perimetre_secretariat(secretariat_id):
    # Alliage historique de la console (LOT 4) : conservé, additif.
    return _perimetre_borne(Perimetre.Type.SECRETARIAT, secretariat_id)


# ---------------------------------------------------------------------------
# Création de compte (assistant, 5 étapes)
# ---------------------------------------------------------------------------
def _creer_personne(donnees):
    matricule = (donnees.get('matricule') or '').strip()
    if matricule:
        personne = Personne.objects.filter(matricule=matricule).first()
        if personne is not None:
            return personne, False
    else:
        matricule = generer_matricule_personne()
    personne = Personne.objects.create(
        matricule=matricule,
        nom=(donnees.get('nom') or '').strip() or 'Sans nom',
        prenoms=(donnees.get('prenoms') or '').strip(),
        email_institutionnel=(donnees.get('email') or '').strip(),
        telephone=(donnees.get('telephone') or '').strip(),
        service=(donnees.get('service') or '').strip(),
    )
    return personne, True


def _resoudre_attribution(ligne):
    role = RoleMetier.objects.filter(code=ligne.get('role')).first()
    if role is None:
        raise ErreurConsole('ROLE_INCONNU', f"Rôle {ligne.get('role')} inconnu.")
    niveau = ligne.get('niveau') or role.niveau_defaut
    return role, niveau, ligne


@transaction.atomic
def creer_compte(acteur, payload, meta=None):
    """Crée User + Personne + CompteUtilisateur + attributions.

    ``payload`` est validé en amont par le sérialiseur DRF.
    """
    meta = meta or {}
    identifiants = payload['identifiants']
    username = identifiants['username'].strip()
    if User.objects.filter(username=username).exists():
        raise ErreurConsole('IDENTIFIANT_EXISTANT',
                            f'Le nom d’utilisateur « {username} » existe déjà.', 409)

    personne, _ = _creer_personne(payload.get('personne') or {})
    role_legacy = identifiants['role_legacy']
    if role_legacy not in User.Role.values:
        raise ErreurConsole('ROLE_LEGACY_INCONNU',
                            f'Rôle d’accès de transition {role_legacy} inconnu.')

    user = User.objects.create_user(
        username=username,
        email=identifiants.get('email', ''),
        password=identifiants['mot_de_passe'],
        role=role_legacy,
    )
    user.is_active = True
    user.save(update_fields=['is_active', 'role'])

    compte = CompteUtilisateur.objects.create(
        user=user,
        personne=personne,
        statut=CompteUtilisateur.Statut.ACTIF,
        canal=payload.get('canal', 'WEB'),
        date_activation=timezone.now(),
        cree_par=acteur,
        notes=payload.get('notes', ''),
    )
    journaliser(
        'COMPTE_CREE', acteur=acteur, compte=compte, personne=personne,
        nouvelle_valeur={
            'username': username, 'role_legacy': role_legacy,
            'canal': compte.canal,
        },
        motif=payload.get('motif', 'Création par la console d’habilitation.'),
        adresse_ip=meta.get('ip', ''), agent_utilisateur=meta.get('ua', ''),
    )
    _appliquer_roles(compte, payload.get('roles', []), acteur, meta)
    return compte


@transaction.atomic
def modifier_compte(compte, acteur, payload, meta=None):
    """Applique une modification après différentiel accepté.

    Exige ``differential_accepte`` vrai dès que des droits changent et un
    motif pour les gestes sensibles (révocation, rôle sensible).
    """
    meta = meta or {}
    if 'canal' in payload:
        compte.canal = payload['canal']
    if payload.get('notes') is not None:
        compte.notes = payload['notes']
    compte.save()

    roles_voulus = payload.get('roles')
    if roles_voulus is not None:
        change = (
            {r['role'] for r in roles_voulus}
            != set(compte.attributions.filter(
                statut=AttributionRole.Statut.ACTIVE).values_list('role__code', flat=True))
        )
        if change and not payload.get('differential_accepte'):
            raise ErreurConsole(
                'DIFFERENTIEL_REQUIS',
                'Le différentiel de droits doit être affiché et accepté avant validation.',
                409,
            )
        if change and not (payload.get('motif') or '').strip():
            raise ErreurConsole(
                'MOTIF_REQUIS',
                'Un motif est obligatoire pour modifier les droits d’un compte.',
            )
        _appliquer_roles(compte, roles_voulus, acteur, meta,
                         motif=payload.get('motif', ''))
    return compte


def _appliquer_roles(compte, lignes, acteur, meta, motif=''):
    aujourd_hui = timezone.localdate()
    codes_voulus = {ligne['role'] for ligne in lignes}
    # Révocations des attributions actives retirées.
    for attribution in compte.attributions.filter(statut=AttributionRole.Statut.ACTIVE):
        if attribution.role.code not in codes_voulus:
            attribution.statut = AttributionRole.Statut.REVOQUEE
            attribution.motif_revocation = motif or 'Rôle retiré par la console.'
            attribution.save(update_fields=['statut', 'motif_revocation', 'date_modification'])
            journaliser(
                'ROLE_REVOQUE', acteur=acteur, compte=compte, cible=attribution,
                ancienne_valeur={'role': attribution.role.code},
                motif=motif or 'Rôle retiré.', adresse_ip=meta.get('ip', ''),
                agent_utilisateur=meta.get('ua', ''),
            )
    # Créations / mises à jour.
    for ligne in lignes:
        role, niveau, ligne = _resoudre_attribution(ligne)
        existante = compte.attributions.filter(
            role=role, statut=AttributionRole.Statut.ACTIVE
        ).first()
        # LOT 5 (L4-02) : le sélecteur de périmètre est généralisé — la ligne
        # peut porter « perimetres » (liste de {type, object_id}) en plus de
        # l'alliage historique « perimetres_secretariats » (additif, combiné).
        périmètres = [
            _perimetre_secretariat(sid)
            for sid in ligne.get('perimetres_secretariats', [])
        ]
        for spec in ligne.get('perimetres', []):
            périmètres.append(_perimetre_borne(
                (spec or {}).get('type'), (spec or {}).get('object_id')))
        champs = {
            'niveau_effectif': niveau,
            'date_fin': ligne.get('date_fin') or None,
            'motif': ligne.get('motif') or motif or 'Attribution par la console.',
        }
        if existante is None:
            attribution = AttributionRole.objects.create(
                compte=compte, role=role,
                statut=AttributionRole.Statut.ACTIVE,
                attribue_par=acteur,
                valide_par=acteur if ligne.get('sensible_valide') and role.sensible else None,
                date_validation=timezone.now() if ligne.get('sensible_valide') and role.sensible else None,
                **champs,
            )
            if périmètres:
                attribution.perimetres.set(périmètres)
            journaliser(
                'ROLE_ATTRIBUE', acteur=acteur, compte=compte, cible=attribution,
                nouvelle_valeur={'role': role.code, 'niveau': niveau},
                motif=champs['motif'], adresse_ip=meta.get('ip', ''),
                agent_utilisateur=meta.get('ua', ''),
            )
        else:
            for champ, valeur in champs.items():
                setattr(existante, champ, valeur)
            existante.save()
            if périmètres:
                existante.perimetres.set(périmètres)


# ---------------------------------------------------------------------------
# Changements de statut — machine à états stricte A5 (U5, L1)
# ---------------------------------------------------------------------------
#: Vue nom -> (statut cible, événement, miroir User.is_active), dérivée du
#: graphe de :mod:`habilitations.services.machine_etats`.
TRANSITIONS_STATUT = {
    nom: {'cible': regle[0], 'evenement': regle[2], 'actif': regle[3]}
    for nom, regle in _GRAPHE_ETATS.items()
}


def changer_statut(compte, acteur, transition, motif, meta=None):
    """Applique une transition en respectant strictement le graphe A5.

    Les vérifications REJETANT l'opération ont lieu AVANT l'ouverture de la
    transaction d'écriture : la trace d'une tentative interdite (transition
    illégale, comme pour l'auto-élévation S6) est ainsi bien conservée et
    n'est pas emportée par une annulation de transaction.
    """
    meta = meta or {}
    if transition not in _GRAPHE_ETATS:
        raise ErreurConsole('TRANSITION_INCONNUE', f'Transition {transition} inconnue.')
    if not (motif or '').strip():
        raise ErreurConsole('MOTIF_REQUIS',
                            'Un motif est obligatoire pour changer le statut d’un compte.')
    if not transition_legale(compte.statut, transition):
        journaliser(
            JournalHabilitation.TypeEvenement.TRANSITION_REFUSEE,
            acteur=acteur, compte=compte,
            nouvelle_valeur={
                'transition': transition,
                'statut_source': compte.statut,
            },
            motif=(motif or 'Tentative de transition interdite.')[:1000],
            adresse_ip=meta.get('ip', ''),
            agent_utilisateur=meta.get('ua', ''),
        )
        raise ErreurConsole(
            'TRANSITION_ILLEGALE',
            f"La transition « {transition} » n'est pas autorisée depuis le statut "
            f"« {compte.statut} » (machine à états A5).",
            409,
        )
    return _appliquer_transition(compte, acteur, transition, motif, meta)


def _revoquer_sessions_utilisateur(user):
    """Supprime les sessions Django actives d'un utilisateur (A5).

    Retourne le nombre de sessions révoquées. La fonction est défensive :
    si le moteur de sessions ne publie pas le modèle ``Session`` (moteur
    déporté en production), elle ne fait rien.
    """
    try:
        from django.contrib.sessions.models import Session
    except Exception:  # pragma: no cover - moteur de sessions absent
        return 0
    from django.utils import timezone as _tz
    nombre = 0
    for session in Session.objects.filter(expire_date__gte=_tz.now()):
        donnees = session.get_decoded()
        if str(donnees.get('_auth_user_id')) == str(user.pk):
            session.delete()
            nombre += 1
    return nombre


@transaction.atomic
def _appliquer_transition(compte, acteur, transition, motif, meta):
    statut_cible, evenement, actif = TRANSITIONS_STATUT[transition].values()
    statut_source = compte.statut
    etait_admin = (
        compte.user.role in ROLES_ADMIN_SYSTEME
        or compte.attributions.filter(
            statut=AttributionRole.Statut.ACTIVE, role__code=ROLE_ADMIN_SYSTEME
        ).exists()
    )
    if etait_admin and not actif:
        # Simuler le retrait pour vérifier le seuil avant d'écrire (S7).
        if administrateurs_actifs() <= SEUIL_ADMINISTRATEURS:
            raise ErreurConsole(
                'SEUIL_ADMINISTRATEURS',
                'Impossible de rendre cet administrateur inactif : au moins deux '
                'administrateurs actifs doivent être conservés.',
                409,
            )
    compte.statut = statut_cible
    if statut_cible == CompteUtilisateur.Statut.ACTIF and transition == 'deverrouiller':
        # LOT 2 (U6) : la levée d'un verrouillage (auto ou admin) remet le
        # compteur d'échecs à zéro — de nouveaux échecs complets sont
        # requis pour re-verrouiller.
        compte.echecs_consecutifs = 0
    if actif:
        compte.date_activation = compte.date_activation or timezone.now()
        compte.date_suspension = None
    elif statut_cible == CompteUtilisateur.Statut.SUSPENDU:
        compte.date_suspension = timezone.now()
    elif statut_cible == CompteUtilisateur.Statut.VERROUILLE:
        # LOT 2 (U6) : l'horodatage du verrouillage pilote le délai de
        # déverrouillage automatique à la connexion.
        compte.date_verrouillage = timezone.now()
    compte.motif_statut = motif
    compte.save()
    # Miroir réel sur le compte de connexion.
    compte.user.is_active = actif
    compte.user.save(update_fields=['is_active'])
    sessions_revoquees = 0
    if not actif:
        # A5 : une transition bloquante (suspension, verrouillage,
        # désactivation, expiration) coupe immédiatement les sessions
        # existantes, sans attendre leur expiration naturelle.
        sessions_revoquees = _revoquer_sessions_utilisateur(compte.user)
    journaliser(
        evenement, acteur=acteur, compte=compte,
        ancienne_valeur={'statut': statut_source},
        nouvelle_valeur={'statut': statut_cible.value,
                         'sessions_revoquees': sessions_revoquees},
        motif=motif, adresse_ip=meta.get('ip', ''),
        agent_utilisateur=meta.get('ua', ''),
    )
    if sessions_revoquees:
        journaliser(
            JournalHabilitation.TypeEvenement.SESSION_REVOQUEE,
            acteur=acteur, compte=compte,
            nouvelle_valeur={'nombre': sessions_revoquees,
                             'transition': transition},
            motif=f"Sessions actives révoquées lors de la transition « {transition} ».",
            adresse_ip=meta.get('ip', ''),
            agent_utilisateur=meta.get('ua', ''),
        )
    return compte


# ---------------------------------------------------------------------------
# Simulation d'import (aucune écriture ; l'écriture en transaction est U5)
# ---------------------------------------------------------------------------
def simuler_import(lignes):
    """Valide ligne à ligne sans rien écrire. Retourne un rapport."""
    rapport = {'total': len(lignes), 'valides': 0, 'erreurs': 0, 'lignes': []}
    for index, ligne in enumerate(lignes, start=1):
        problemes = []
        if not (ligne.get('username') or '').strip():
            problemes.append('Nom d’utilisateur manquant.')
        elif User.objects.filter(username=ligne['username'].strip()).exists():
            problemes.append('Nom d’utilisateur déjà existant.')
        if not (ligne.get('nom') or '').strip():
            problemes.append('Nom manquant.')
        if not (ligne.get('mot_de_passe') or '').strip():
            problemes.append('Mot de passe initial manquant.')
        roles = [r.strip() for r in (ligne.get('roles') or '').split(',') if r.strip()]
        roles_inconnus = [r for r in roles if not RoleMetier.objects.filter(code=r).exists()]
        if roles_inconnus:
            problemes.append('Rôles inconnus : ' + ', '.join(roles_inconnus))
        entree = {'numero': index, 'valeurs': ligne, 'problemes': problemes}
        if problemes:
            rapport['erreurs'] += 1
            entree['etat'] = 'ERREUR'
        else:
            rapport['valides'] += 1
            entree['etat'] = 'VALIDE'
            entree['roles'] = roles
        rapport['lignes'].append(entree)
    return rapport
