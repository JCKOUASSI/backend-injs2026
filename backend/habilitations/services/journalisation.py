"""Service du journal d'habilitation : écriture append-only et vérification.

L'écriture est la SEULE voie autorisée pour créer une trace
(:func:`journaliser`) ; elle calcule sous transaction l'empreinte de la
nouvelle ligne en intégrant l'empreinte de la précédente. La vérification
:func:`verifier_chaine` recalcule tout et signale la moindre rupture, un trou
de séquence ou une altération (utilisée par la commande
``verifier_chaine_habilitations`` et par les tests, prémices du travail U7).
"""
import hashlib
import json
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models.journal import JournalHabilitation

# Empreinte racine d'une chaîne vide (première ligne).
GENESE = '0' * 64
TENTATIVES_MAX = 10


def _canonique(valeur):
    """Représentation JSON stable et déterministe d'une valeur."""
    return json.dumps(
        valeur, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
        default=str,
    )


def contenu_hache(entree: JournalHabilitation) -> str:
    """Chaîne canonique des champs couverts par l'empreinte."""
    payload = {
        'numero': entree.numero,
        'horodatage': entree.horodatage.isoformat() if entree.horodatage else None,
        'acteur_id': entree.acteur_id,
        'acteur_label': entree.acteur_label,
        'compte_id': entree.compte_concerne_id,
        'personne_id': entree.personne_concernee_id,
        'type': entree.type_evenement,
        'ct_id': entree.content_type_id,
        'object_id': str(entree.object_id or ''),
        'objet_type': entree.objet_type,
        'objet_libelle': entree.objet_libelle,
        'ancienne': entree.ancienne_valeur,
        'nouvelle': entree.nouvelle_valeur,
        'motif': entree.motif,
        'ip': entree.adresse_ip,
        'ua': entree.agent_utilisateur,
        'correlation': entree.correlation_id,
    }
    return f'{entree.empreinte_precedente}|{_canonique(payload)}'


def calculer_empreinte(entree: JournalHabilitation) -> str:
    return hashlib.sha256(contenu_hache(entree).encode('utf-8')).hexdigest()


def _resoudre_cible(cible):
    """Retourne ``(content_type, object_id, objet_type, libelle)``.

    LOT 5 (L4-04) : accepte aussi la cible décrite en dict au format du
    contrat d'API (``{'type', 'object_id', 'reference'}``) — un refus portant
    une cible sérialisée est désormais journalisé avec sa cible, sans
    ``ContentType`` (l'objet peut n'exister nulle part ; la trace prime).
    """
    if cible is None:
        return None, '', '', ''
    if isinstance(cible, dict):
        object_id = str(cible.get('object_id', '') or '')
        type_p = str(cible.get('type', '') or '')[:100]
        libelle = str(
            cible.get('reference')
            or (f'{type_p}#{object_id}' if object_id else type_p)
        )[:255]
        return None, object_id, type_p, libelle
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(cible.__class__)
    libelle = str(cible)[:255]
    return ct, str(getattr(cible, 'pk', '')), f'{ct.app_label}.{ct.model}', libelle


@transaction.atomic
def journaliser(
    type_evenement, *, acteur=None, compte=None, personne=None, cible=None,
    ancienne_valeur=None, nouvelle_valeur=None, motif='', adresse_ip=None,
    agent_utilisateur='', correlation_id='', horodatage=None,
    delegation_source=None,
):
    """Crée une entrée immuable et chaînée, et la retourne.

    La séquence et l'empreinte sont déterminées en verrouillant la dernière
    ligne. PostgreSQL fournit ``select_for_update`` ; sur SQLite (développement)
    les écritures sont sérialisées et une reprise sur collision est prévue.
    """
    ct, object_id, objet_type, objet_libelle = _resoudre_cible(cible)
    horodatage = horodatage or timezone.now()
    correlation_id = correlation_id or uuid.uuid4().hex

    derniere_erreur = None
    for _ in range(TENTATIVES_MAX):
        precedente = (
            JournalHabilitation.objects.select_for_update()
            .order_by('-numero')
            .only('numero', 'empreinte')
            .first()
        )
        numero = (precedente.numero + 1) if precedente else 1
        entree = JournalHabilitation(
            numero=numero,
            horodatage=horodatage,
            acteur=acteur,
            acteur_label=(acteur.get_username() if acteur else '') or '',
            compte_concerne=compte,
            personne_concernee=personne,
            type_evenement=type_evenement,
            content_type=ct,
            object_id=object_id,
            objet_type=objet_type,
            objet_libelle=objet_libelle,
            ancienne_valeur=ancienne_valeur or {},
            nouvelle_valeur=nouvelle_valeur or {},
            motif=motif,
            adresse_ip=adresse_ip,
            agent_utilisateur=(agent_utilisateur or '')[:250],
            correlation_id=correlation_id,
            empreinte_precedente=(precedente.empreinte if precedente else GENESE),
            empreinte='',
            # U5 : référence de délégation (hors empreinte, donc sans
            # conséquence sur le chaînage des lignes existantes).
            delegation_source=delegation_source,
        )
        entree.empreinte = calculer_empreinte(entree)
        try:
            with transaction.atomic():
                entree.save()
            return entree
        except IntegrityError as exc:  # collision de numéro/empreinte : reprise
            derniere_erreur = exc
            continue
    raise IntegrityError(
        "Impossible d'écrire dans le journal après plusieurs tentatives."
    ) from derniere_erreur


def verifier_chaine():
    """Contrôle intégral du chaînage.

    Retourne une liste de messages d'anomalie (liste vide = intègre).
    """
    anomalies = []
    empreinte_attendue = GENESE
    numero_attendu = 1
    for entree in JournalHabilitation.objects.iterator(chunk_size=500):
        if entree.numero != numero_attendu:
            anomalies.append(
                f'Trou de séquence : numéro {entree.numero}, attendu {numero_attendu}.'
            )
        if entree.empreinte_precedente != empreinte_attendue:
            anomalies.append(
                f'Rupture de chaînage sur l’événement {entree.numero} : '
                "empreinte précédente incohérente."
            )
        calculee = calculer_empreinte(entree)
        if calculee != entree.empreinte:
            anomalies.append(
                f'Empreinte altérée sur l’événement {entree.numero} ({entree.type_evenement}).'
            )
        empreinte_attendue = entree.empreinte
        numero_attendu = entree.numero + 1
    return anomalies
