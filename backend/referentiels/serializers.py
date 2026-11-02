"""Serializers des référentiels (lot L0/L7).

Contrat : le `code` est fourni à la création puis immuable ; l'archivage
ne passe pas par le serializer (action dédiée) — règle 2.
"""
import re

from rest_framework import serializers

from .models import (
    ReferentielJournal,
    RefModuleOfficiel,
    RefVolumeHoraireFormation,
    RefGradeEnseignant,
    RefModePaiement,
    RefTypeDecision,
    RefTypeDocument,
    RefTypeEspaceSportif,
    RefTypeEvaluation,
    RefTypeFrais,
    RefTypeNotification,
)

# Le tiret est admis : les codes métier des salles suivent la convention
# AMP-001 / GYM-002 de l'inventaire des lieux. Le premier caractère reste
# alphanumérique pour interdire les codes purement ponctuation.
CODE_RE = re.compile(r'^[A-Z0-9][A-Z0-9_-]{1,49}$')


class RefSocleSerializer(serializers.ModelSerializer):
    """Serializer partagé par tous les référentiels du socle."""

    class Meta:
        # `source_document` et `fiabilite` font partie du contrat : sans eux,
        # l'écran affichait une colonne « Fiabilité » toujours vide et les deux
        # champs de traçabilité saisis dans le formulaire étaient silencieusement
        # ignorés par l'API (les 8 routes historiques du routeur).
        fields = [
            'id', 'code', 'libelle', 'description',
            'actif', 'date_activation', 'date_desactivation',
            'archive', 'annee_academique',
            'source_document', 'fiabilite',
            'cree_le', 'modifie_le',
        ]
        read_only_fields = ['archive', 'date_activation', 'date_desactivation']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Le code métier est fourni à la création puis immuable.
        if self.instance is not None and 'code' in self.fields:
            self.fields['code'].read_only = True

    def validate_code(self, value):
        value = value.strip().upper()
        if not value:
            # Code facultatif sur certains modèles hérités (vagues) :
            # l'obligation éventuelle est portée par allow_blank du champ.
            return value
        if not CODE_RE.match(value):
            raise serializers.ValidationError(
                "Code invalide : 2 à 50 caractères parmi A-Z, 0-9, _ et - "
                "(ex. GYM-001)."
            )
        return value

    def validate_libelle(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Le libellé est obligatoire.')
        return value


# Un serializer par modèle (mécanique commune, meta differente)
class RefTypeEvaluationSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeEvaluation


class RefTypeDocumentSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeDocument


class RefGradeEnseignantSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefGradeEnseignant


class RefTypeFraisSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeFrais


class RefModePaiementSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefModePaiement


class RefTypeDecisionSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeDecision


class RefTypeNotificationSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeNotification


class RefTypeEspaceSportifSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeEspaceSportif


class ReferentielJournalSerializer(serializers.ModelSerializer):
    """Lecture seule — journal des modifications (règle 6)."""

    class Meta:
        model = ReferentielJournal
        fields = ['id', 'action', 'object_id', 'horodatage', 'detail', 'utilisateur']
        read_only_fields = fields


# ═══════════════════════════════════════════════════════════════════════════
# Refonte « Référentiels » — sérialiseurs générés depuis le registre.
#
# Un seul sérialiseur paramétré sert tous les référentiels déclarés au
# registre : champs du socle + champs métier propres au référentiel + libellés
# des clés étrangères (pour que le front n'ait jamais à recoder une liste).
# ═══════════════════════════════════════════════════════════════════════════
from .registre import REGISTRE, modele_de  # noqa: E402  (après le socle)

CHAMPS_SOCLE = [
    'id', 'code', 'libelle', 'description',
    'actif', 'date_activation', 'date_desactivation',
    'archive', 'annee_academique',
    'source_document', 'fiabilite',
    'cree_le', 'modifie_le',
]

_CACHE_SERIALISEURS = {}


def _libelle_de_la_cible(obj, fk):
    """Intitulé d'affichage d'une clé étrangère, quel que soit son modèle.

    Les modèles du socle exposent ``libelle`` ; les modèles hérités
    (formations.RefFormation, scolarité…) exposent ``intitule`` ou ``nom``.
    """
    cible = getattr(obj, fk, None)
    if cible is None:
        return None
    for attribut in ('libelle', 'intitule', 'nom'):
        valeur = getattr(cible, attribut, None)
        if valeur:
            return valeur
    return str(cible)


def serializer_pour_ref(slug):
    """Construit (et mémorise) le sérialiseur d'une entrée du registre.

    Le contrat d'API est unifié (``code`` / ``libelle``) même pour les
    modèles hors socle : l'entrée de registre déclare les champs réels
    (``champ_code`` / ``champ_libelle``) et le sérialiseur les aliasse, de
    sorte que l'écran générique n'a aucune correspondance de noms à coder.
    Les champs du socle absents du modèle (provenance, archivage…) sont
    simplement omis.
    """
    if slug in _CACHE_SERIALISEURS:
        return _CACHE_SERIALISEURS[slug]
    entree = REGISTRE[slug]
    modele = modele_de(entree)
    champ_libelle = entree.get('champ_libelle', 'libelle')
    champ_code = entree.get('champ_code', 'code')
    concrets = {f.name for f in modele._meta.concrete_fields}

    attributs = {}
    champs = ['id']
    # Code : champ distinct éditable à la création, ou alias en lecture
    # seule quand le modèle n'a pas de colonne code (le libellé en tient
    # lieu — ex. scolarite.Semestre).
    if champ_code in concrets and champ_code != champ_libelle:
        champs.append('code')
        if champ_code != 'code':
            attributs['code'] = serializers.CharField(source=champ_code)
    elif champ_libelle in concrets:
        champs.append('code')
        attributs['code'] = serializers.CharField(
            source=champ_libelle, read_only=True,
        )
    # Libellé : aliasé vers le champ d'intitulé réel (ex. ``intitule``).
    champs.append('libelle')
    if champ_libelle != 'libelle':
        attributs['libelle'] = serializers.CharField(source=champ_libelle)
    champs.extend(
        nom for nom in CHAMPS_SOCLE
        if nom not in ('id', 'code', 'libelle') and nom in concrets
    )
    champs.extend(nom for nom in entree['champs'] if nom in concrets)
    for fk in entree['selecteurs']:
        champs.extend([fk, f'{fk}_libelle'])
        nom_getter = f'get_{fk}_libelle'
        attributs[f'{fk}_libelle'] = serializers.SerializerMethodField(
            method_name=nom_getter,
        )
        attributs[nom_getter] = (
            lambda self, obj, _fk=fk: _libelle_de_la_cible(obj, _fk)
        )

    bascule = entree.get('bascule_unique')
    if bascule and bascule in champs:
        # Drapeau « un seul vrai » (année courante) : DRF déduit de la
        # contrainte d'unicité conditionnelle un UniqueValidator porté
        # par le champ, qui refuserait le formulaire avant même que la
        # vue ait basculé les autres lignes (règle de processus). Le
        # champ est donc déclaré explicitement, sans ce validateur ;
        # la contrainte de base reste le garde-fou.
        attributs[bascule] = serializers.BooleanField(required=False)

    attributs['Meta'] = type('Meta', (), {
        'model': modele,
        'fields': champs,
        'read_only_fields': [
            nom
            for nom in ('archive', 'date_activation', 'date_desactivation')
            if nom in champs
        ],
    })
    serie = type(
        f'{modele.__name__}Serializer',
        (RefSocleSerializer,),
        attributs,
    )
    _CACHE_SERIALISEURS[slug] = serie
    return serie


class RefModuleOfficielSerializer(serializers.ModelSerializer):
    """Modules officiels des maquettes (lecture seule : issus de l'import)."""

    formation_intitule = serializers.CharField(source='formation.intitule', read_only=True)

    class Meta:
        model = RefModuleOfficiel
        fields = [
            'id', 'formation', 'formation_intitule', 'filiere_code',
            'semestre', 'libelle', 'ordre', 'etat_ventilation',
            'source_document', 'fiabilite',
        ]


class RefVolumeHoraireFormationSerializer(serializers.ModelSerializer):
    """Volumes horaires de modélisation (lecture seule)."""

    formation_intitule = serializers.CharField(source='formation.intitule', read_only=True)

    class Meta:
        model = RefVolumeHoraireFormation
        fields = [
            'id', 'formation', 'formation_intitule', 'intitule_module',
            'heures_cm', 'heures_td', 'heures_tp', 'heures_stage', 'heures_total',
            'source_document', 'fiabilite',
        ]
