"""Mode observation du moteur d'habilitation (unité U2, règle R3).

L'observation **ne change jamais une réponse** : elle compte ce que le moteur
aurait décidé et, quand une décision legacy est connue, mesure les écarts.
Les compteurs vivent dans le cache Django (LocMem en démonstration, Redis
plus tard sans changement de code). Le journal append-only n'est jamais
alimenté par l'observation (il le sera par les refus effectifs, en mode
application, unités ultérieures).

Trois principes :

* interrupteurs OFF : ``enregistrer_*`` et la classe DRF deviennent des
  *no-op* totaux (aucune lecture de cache, aucun log) ;
* un compte non gouverné (sans profil) n'est PAS un écart : il relève de
  l'ancien dispositif jusqu'à la migration U8 ; il est seulement décompté
  pour mesurer la progression de la bascule ;
* un écart où l'ancien dispositif autorisait là où le moteur refuse est
  compté à part : c'est le risque « perte d'accès » (S1) qui conditionne le
  passage en application.
"""
import logging

from django.core.cache import cache
from django.utils import timezone

from .codes import MODE_OFF
from .moteur import mode_moteur

logger = logging.getLogger(__name__)

CLE_CACHE = 'habilitations:observations:v1'

# Noms de compteurs (le schéma est versionné par la clé de cache).
_CHAMPS = (
    'evaluations_total',
    'non_gouvernees',
    'autorisees_moteur',
    'refusees_moteur',
    'ecarts_total',
    'ecarts_legacy_autorise_moteur_refuse',
    'ecarts_legacy_refuse_moteur_autorise',
)


def _etat_vide():
    etat = {cle: 0 for cle in _CHAMPS}
    etat['motifs'] = {}
    etat['premiere_observation'] = None
    etat['derniere_observation'] = None
    return etat


def etat_observation():
    """Retourne une copie de l'état d'observation (vide si aucun appel)."""
    etat = cache.get(CLE_CACHE)
    return dict(etat) if etat else _etat_vide()


def remettre_a_zero():
    """Vide les compteurs d'observation (action admin tracée par la vue)."""
    cache.delete(CLE_CACHE)
    return _etat_vide()


def _incrementer(etat, cle, quantite=1):
    etat[cle] = etat.get(cle, 0) + quantite


def enregistrer_decision(decision, decision_legacy=None, username=''):
    """Enregistre le résultat d'une évaluation ; no-op si le moteur est OFF.

    ``decision_legacy`` est le verdict de l'ancien dispositif pour le même
    accès (``True``/``False``/``None`` si non connu). Retourne ``True`` si un
    écart a été constaté.
    """
    if mode_moteur() == MODE_OFF:
        return False
    etat = cache.get(CLE_CACHE) or _etat_vide()
    maintenant = timezone.now().isoformat(timespec='seconds')
    if etat['premiere_observation'] is None:
        etat['premiere_observation'] = maintenant
    etat['derniere_observation'] = maintenant
    _incrementer(etat, 'evaluations_total')

    if not decision.gouverne:
        _incrementer(etat, 'non_gouvernees')
        cache.set(CLE_CACHE, etat)
        return False

    if decision.autorise:
        _incrementer(etat, 'autorisees_moteur')
    else:
        _incrementer(etat, 'refusees_moteur')
        for code in decision.motifs:
            etat['motifs'][code] = etat['motifs'].get(code, 0) + 1

    ecart = (
        decision_legacy is not None
        and bool(decision_legacy) != bool(decision.autorise)
    )
    if ecart:
        _incrementer(etat, 'ecarts_total')
        if decision_legacy and not decision.autorise:
            _incrementer(etat, 'ecarts_legacy_autorise_moteur_refuse')
            niveau = logging.WARNING
        else:
            _incrementer(etat, 'ecarts_legacy_refuse_moteur_autorise')
            niveau = logging.INFO
        logger.log(
            niveau,
            'habilitation_ecart permission=%s canal=%s utilisateur=%s '
            'legacy=%s moteur=%s motifs=%s',
            decision.permission,
            decision.canal,
            username,
            bool(decision_legacy),
            bool(decision.autorise),
            ','.join(decision.motifs) or '-',
        )
    cache.set(CLE_CACHE, etat)
    return ecart


def synthese_pour_api():
    """Vue sérialisable de la synthèse, avec le mode courant."""
    etat = etat_observation()
    return {
        'mode': mode_moteur(),
        'observations': etat,
        'explication': (
            "En mode OBSERVATION, aucune réponse n'est modifiée : ces "
            "compteurs mesurent les écarts qui seraient constatés si le "
            "moteur décidait. Les comptes non gouvernés relèvent de "
            "l'ancien dispositif jusqu'à la migration des comptes (U8)."
        ),
    }


def executer_campagne(permissions=None, canal='WEB'):
    """Évalue hors-ligne tous les comptes gouvernés sur le référentiel.

    Retourne un dict de synthèse (n'écrit PAS dans les compteurs HTTP). En
    U2, le référentiel et les profils sont vides : la campagne est sans
    objet, ce qui est explicitement signalé. Elle devient parlante en U3
    (référentiel) puis U8 (comptes rattachés).
    """
    from ..models import CompteUtilisateur, PermissionMetier
    permissions = list(
        permissions
        if permissions is not None
        else PermissionMetier.objects.filter(actif=True)
    )
    comptes = CompteUtilisateur.objects.select_related('user')
    evaluations = 0
    refus = 0
    par_motif = {}
    comptes_avec_refus = {}
    for compte in comptes.iterator():
        for permission in permissions:
            decision_moteur = _evaluer_compte(compte, permission.code, canal)
            evaluations += 1
            if not decision_moteur.autorise:
                # Le « rien n'est encore attribué » est la norme avant U3/U8,
                # pas un écart significatif.
                motifs_significatifs = [
                    m for m in decision_moteur.motifs
                    if m != 'AUCUNE_ATTRIBUTION_PERMETTANTE'
                ]
                if not motifs_significatifs:
                    continue
                refus += 1
                libelle_compte = compte.user.get_username()
                comptes_avec_refus.setdefault(libelle_compte, [])
                comptes_avec_refus[libelle_compte].append(permission.code)
                for code in motifs_significatifs:
                    par_motif[code] = par_motif.get(code, 0) + 1
    return {
        'comptes_gouverves': comptes.count(),
        'permissions_reference': len(permissions),
        'evaluations': evaluations,
        'refus_significatifs': refus,
        'motifs': par_motif,
        'comptes_avec_refus': comptes_avec_refus,
    }


def _evaluer_compte(compte, code, canal):
    from .moteur import est_autorise
    return est_autorise(compte, code, canal=canal)
