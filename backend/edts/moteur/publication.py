"""Lot L8 — Étapes S, U & 42 : publication d'un emploi du temps.

Règles non négociables :

* **jamais de publication automatique** — la génération ne publie pas, la
  validation humaine est obligatoire (étape S) ;
* **transactionnel** — la publication est atomique ; en cas d'échec, ROLLBACK
  intégral, sans publication partielle (étape U, étape 42) ;
* **idempotent** — republier le même EDT ne duplique rien (étape 43) ;
* **verrouillé** — ``select_for_update`` empêche deux administrateurs de
  publier simultanément le même EDT (étape 51) ;
* **bloquant si invalide** — une violation du validateur interdit la
  publication ; l'erreur est explicite, jamais un 500 opaque (étape 54).

Chaque séance persistée conserve le lien vers son ``AffectationPedagogique``
d'origine (L1) : c'est ce qui la rend exploitable par
``GET /api/scolarite/pedagogie/cours/`` et par les présences QR.
"""

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from edts.moteur import contraintes as C
from edts.moteur.validation import valider_emploi_du_temps

#: Motifs de refus de publication (explicites, affichables tels quels).
MOTIF_DEJA_PUBLIE = 'EDT_DEJA_PUBLIE'
MOTIF_STATUT_INVALIDE = 'STATUT_EDT_INVALIDE'
MOTIF_VERSION_CONFLIT = 'VERSION_EDT_MODIFIEE'
MOTIF_VALIDATION_BLOQUANTE = 'VALIDATION_BLOQUANTE'
MOTIF_AUCUNE_AFFECTATION = 'AUCUNE_AFFECTATION_A_PUBLIER'
MOTIF_PLAN_INCOMPLET = 'PLAN_INCOMPLET'
MOTIF_QR_V2_NON_PUBLIABLE = 'QR_V2_NON_PUBLIABLE'


def empreinte_generation(*, annee_academique_id=None, ref_formation_id=None,
                         parcours_id=None, niveau_id=None, semestre_id=None,
                         groupe_ids=None, version=1, maquette_id=None):
    """SHA-256 des paramètres de génération (étape 43).

    Deux générations strictement identiques partagent la même empreinte : c'est
    la clé d'idempotence, stockée sur ``EmploiDuTemps.empreinte``.
    """
    charge = json.dumps({
        'annee_academique_id': annee_academique_id,
        'ref_formation_id': ref_formation_id,
        'parcours_id': parcours_id,
        'niveau_id': niveau_id,
        'semestre_id': semestre_id,
        'groupe_ids': sorted(groupe_ids) if groupe_ids else None,
        'maquette_id': maquette_id,
        'version': version,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(charge.encode('utf-8')).hexdigest()



# ── Persistance du plan (étape U) ────────────────────────────────────────────

@transaction.atomic
def persister_plan(emploi_du_temps, placements, remplacer=False):
    """Matérialise un plan en ``AffectationCreneau`` — transactionnel.

    Chaque placement devient une séance rattachée à son
    ``affectation_pedagogique`` (clé L1), ce qui rend la séance traçable
    jusqu'au cours et donc exploitable par les présences QR.

    ``remplacer=True`` désactive les séances existantes de cet EDT avant
    d'écrire les nouvelles : sans cela, une régénération créerait des doublons
    (interdit par l'étape 43).
    """
    from edts.models import AffectationCreneau
    from scolarite.models import AnneeAcademique

    # Sérialiser avec les placements v2 (qui verrouillent également l'année) :
    # une simple lecture de garde hors verrou laisserait une fenêtre de course.
    AnneeAcademique.objects.select_for_update().get(pk=emploi_du_temps.annee_academique_id)

    # Les appels directs (campagnes, commandes, tests) ne passent pas toujours
    # par les gardes HTTP. Une année avec occurrences datées v2 ne doit jamais
    # être réécrite par le persisteur legacy, y compris remplacer=False :
    # ce chemin ne maintient ni la clé métier ni le registre/instantané QR.
    # Contrôler avant la première écriture et dans la transaction appelante.
    if AffectationCreneau.objects.filter(
        emploi_du_temps__annee_academique_id=emploi_du_temps.annee_academique_id,
        cle_occurrence_v2__isnull=False,
    ).exists():
        raise ValueError('QR_V2_CHEMIN_HERITE_REFUSE')

    if remplacer:
        AffectationCreneau.objects.filter(
            emploi_du_temps=emploi_du_temps,
        ).update(actif=False)

    creer = []
    for place in placements:
        besoin = place.besoin
        creer.append(AffectationCreneau(
            emploi_du_temps=emploi_du_temps,
            creneau_template=place.creneau,
            semaine_debut=place.semaine_debut,
            semaine_fin=place.semaine_fin,
            salle=place.salle,
            salle_nom=place.salle.nom if place.salle is not None else '',
            formation_id=besoin.ref_formation_id,
            groupe_id=besoin.groupe_id,
            affectation_pedagogique_id=besoin.affectation_pedagogique_id,
            ecue_id=besoin.ecue_id,
            # -- Enseignant : FK métier Formateur (identifiant INJS).
            # `TeachingNeed` est immuable et n'expose que l'identifiant ; le
            # libellé reste porté par la dénormalisation de l'EDT. Sans cette
            # FK, la détection de conflits ne peut pas comparer les enseignants.
            formateur_id=besoin.enseignant_id,
            nature=place.besoin.nature,
            intitule=besoin.intitule,
            actif=True,
        ))
    AffectationCreneau.objects.bulk_create(creer)
    return len(creer)


@transaction.atomic
def publier_emploi_du_temps(emploi_du_temps_id, *, user=None, force=False,
                            version_attendue=None, besoins_attendus=None):
    """Publie un EDT après validation — transactionnelle et idempotente.

    Refus explicites (jamais d'exception 500) :

    * ``EDT_DEJA_PUBLIE``            — republication inutile (idempotence) ;
    * ``VERSION_EDT_MODIFIEE``       — l'EDT a changé depuis le chargement ;
    * ``STATUT_EDT_INVALIDE``        — le statut n'ouvre pas la publication ;
    * ``VALIDATION_BLOQUANTE``       — le validateur a trouvé des violations ;
    * ``AUCUNE_AFFECTATION_A_PUBLIER`` — l'EDT ne contient aucune séance.

    Retourne un dict : ``{'publie': bool, 'motif_echec': str|None, ...}``.
    """
    from edts.models import EmploiDuTemps

    # Verrou pessimiste : empêche deux publications concurrentes (étape 51).
    emploi_du_temps = (
        EmploiDuTemps.objects.select_for_update().filter(pk=emploi_du_temps_id).first()
    )
    if emploi_du_temps is None:
        return {'publie': False, 'motif_echec': 'EDT_INTROUVABLE', 'detail': {}}

    # Contrôle de version AVANT l'idempotence : un client qui présente une
    # version périmée doit recharger l'EDT, même si celui-ci est déjà publié —
    # sinon le conflit resterait masqué par « déjà publié ».
    if version_attendue is not None \
            and version_attendue != emploi_du_temps.version:
        return {
            'publie': False,
            'motif_echec': MOTIF_VERSION_CONFLIT,
            'detail': {
                'explication': (
                    f'Version attendue {version_attendue}, version courante '
                    f'{emploi_du_temps.version} : rechargez l’EDT avant de publier.'
                ),
                'version_courante': emploi_du_temps.version,
                'version_attendue': version_attendue,
            },
        }

    # Idempotence : déjà publié, rien à faire (étape 43).
    if emploi_du_temps.statut == 'PUBLIE' and not force:
        return {
            'publie': False,
            'motif_echec': MOTIF_DEJA_PUBLIE,
            'detail': {
                'explication': 'Cet EDT est déjà publié.',
                'publie_le': emploi_du_temps.publie_le,
                'version': emploi_du_temps.version,
            },
        }

    if emploi_du_temps.statut not in ('BROUILLON', 'EN_VALIDATION', 'VALIDE'):
        return {
            'publie': False,
            'motif_echec': MOTIF_STATUT_INVALIDE,
            'detail': {
                'explication': (
                    f'Le statut « {emploi_du_temps.get_statut_display()} » n’ouvre '
                    'pas la publication.'
                ),
                'statuts_autorises': ['BROUILLON', 'EN_VALIDATION', 'VALIDE'],
            },
        }

    # Garde strictement additif : les EDT hérités conservent leur parcours,
    # mais une occurrence datée v2 ne peut être publiée sans rapprochement QR.
    # Même force=True n'écarte pas cette protection.
    from edts.moteur.qr_v2 import anomalies_publication_v2
    anomalies_qr = anomalies_publication_v2(emploi_du_temps)
    if anomalies_qr:
        return {'publie': False, 'motif_echec': MOTIF_QR_V2_NON_PUBLIABLE,
                'detail': {'explication': 'Présences QR non prêtes pour cet EDT v2.',
                           'anomalies': anomalies_qr}}

    rapport = valider_emploi_du_temps(emploi_du_temps, besoins_attendus)
    if not rapport.valide and not force:
        return {
            'publie': False,
            'motif_echec': MOTIF_VALIDATION_BLOQUANTE,
            'detail': {
                'explication': (
                    f'{len(rapport.violations)} violation(s) bloquante(s) : la '
                    'publication est refusée.'
                ),
                'violations': [v.as_dict() for v in rapport.violations],
                'warnings': rapport.warnings,
            },
        }

    # Refus du plan incomplet : tous les besoins attendus doivent être couverts
    # (étape E : on ne publie jamais un EDT partiellement généré sans consentement
    # explicite via ``force``).
    if (besoins_attendus is not None
            and rapport.couverture.get('seances_non_placees', 0) > 0
            and not force):
        return {
            'publie': False,
            'motif_echec': MOTIF_PLAN_INCOMPLET,
            'detail': {
                'explication': (
                    f"{rapport.couverture['seances_non_placees']} séance(s) "
                    f"sur {rapport.couverture['seances_attendues']} attendue(s) "
                    "n'est(nt) pas placée(s) : le plan est incomplet."
                ),
                'couverture': rapport.couverture,
            },
        }

    nb_seances = emploi_du_temps.affectations.filter(actif=True).count()
    if not nb_seances:
        return {
            'publie': False,
            'motif_echec': MOTIF_AUCUNE_AFFECTATION,
            'detail': {
                'explication': 'Cet EDT ne contient aucune séance active à publier.',
            },
        }

    maintenant = timezone.now()
    emploi_du_temps.statut = 'PUBLIE'
    emploi_du_temps.publie_le = maintenant
    emploi_du_temps.publie_par = user if (user and user.is_authenticated) else None
    if not emploi_du_temps.valide_le:
        emploi_du_temps.valide_le = maintenant
        emploi_du_temps.valide_par = user if (user and user.is_authenticated) else None
    emploi_du_temps.save(update_fields=[
        'statut', 'publie_le', 'publie_par', 'valide_le', 'valide_par', 'updated_at',
    ])

    return {
        'publie': True,
        'motif_echec': None,
        'nb_seances': nb_seances,
        'version': emploi_du_temps.version,
        'publie_le': maintenant,
        'warnings': rapport.warnings,
        'detail': rapport.as_dict(),
    }
