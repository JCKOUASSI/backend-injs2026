"""C1 — Serializers des évaluations académiques.

Volontairement limités au **structurel** : aucune moyenne n'est calculée,
aucune règle métier n'est appliquée. Les champs Decimal sont sérialisés en
nombre (et non en chaîne) pour rester compatibles avec le frontend React et
l'application mobile, sans modifier le réglage global de DRF.
"""
import json

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    ConvocationEvaluation,
    ECUEResult,
    Epreuve,
    EpreuveSurveillant,
    Evaluation,
    EvaluationAttendance,
    EvaluationComponent,
    EvaluationGrade,
    EvaluationGradeHistory,
    EvaluationParticipant,
    RegleCalcul,
    RegleCalculVersion,
    ReleveNotes,
    SemesterResult,
    SessionEvaluation,
    TypeEvaluation,
    UEResult,
)

DEC = dict(coerce_to_string=False)


def _identite(inscription_pedagogique):
    """(matricule, nom affiché) lus par la chaîne d'inscription.

    Aucune donnée n'est stockée : la lecture évite toute dénormalisation
    divergente (B.1 §16).
    """
    dossier = inscription_pedagogique.inscription.etudiant
    return dossier.matricule, dossier.nom_complet


class RegleCalculSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegleCalcul
        fields = ['id', 'code', 'libelle', 'categorie', 'source', 'description', 'actif']


class RegleCalculVersionSerializer(serializers.ModelSerializer):
    regle_code = serializers.CharField(source='regle.code', read_only=True)

    class Meta:
        model = RegleCalculVersion
        fields = [
            'id', 'regle', 'regle_code', 'version', 'ref_formation', 'niveau',
            'semestre', 'date_effet', 'date_fin', 'parametres', 'verrouillee',
            'publiee_le', 'publiee_par',
        ]
        read_only_fields = ['verrouillee', 'publiee_le', 'publiee_par']


class TypeEvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeEvaluation
        fields = ['id', 'code', 'libelle', 'categorie', 'actif']


class SessionEvaluationSerializer(serializers.ModelSerializer):
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True)
    niveau_code = serializers.CharField(source='niveau.code', read_only=True)
    maquette_version = serializers.IntegerField(source='maquette.version', read_only=True)
    nb_evaluations = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = SessionEvaluation
        fields = [
            'id', 'annee_academique', 'annee_libelle', 'ref_formation', 'parcours',
            'niveau', 'niveau_code', 'semestre', 'maquette', 'maquette_version',
            'type_session', 'session_origine', 'libelle', 'date_debut', 'date_fin',
            'statut', 'verrouillee', 'regle_version', 'nb_evaluations', 'created_at',
        ]
        read_only_fields = ['verrouillee', 'created_at', 'updated_at']


class EvaluationComponentSerializer(serializers.ModelSerializer):
    poids = serializers.DecimalField(max_digits=5, decimal_places=2, **DEC)
    bareme = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, **DEC,
    )

    class Meta:
        model = EvaluationComponent
        fields = [
            'id', 'evaluation', 'code', 'libelle', 'poids', 'bareme', 'ordre',
            'obligatoire', 'actif',
        ]
        # L'évaluation parente vient de l'URL imbriquée : elle n'est jamais
        # acceptée depuis le corps de la requête.
        read_only_fields = ['evaluation']


class EvaluationSerializer(serializers.ModelSerializer):
    poids = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, **DEC,
    )
    bareme = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, **DEC,
    )
    ecue_code = serializers.CharField(source='ecue.code', read_only=True)
    type_code = serializers.CharField(source='type_evaluation.code', read_only=True)
    composants = EvaluationComponentSerializer(source='components', many=True, read_only=True)

    class Meta:
        model = Evaluation
        fields = [
            'id', 'session', 'ecue', 'ecue_code', 'affectation_pedagogique',
            'type_evaluation', 'type_code', 'libelle', 'description', 'bareme',
            'poids', 'date_prevue', 'statut', 'composition_verrouillee',
            'regle_version', 'composants', 'created_at',
        ]


class EpreuveSurveillantSerializer(serializers.ModelSerializer):
    formateur_nom = serializers.SerializerMethodField()

    class Meta:
        model = EpreuveSurveillant
        fields = ['id', 'epreuve', 'formateur', 'formateur_nom', 'role']

    @extend_schema_field(serializers.CharField())
    def get_formateur_nom(self, obj):
        return f'{obj.formateur.nom} {obj.formateur.prenom}'.strip()


class EpreuveSerializer(serializers.ModelSerializer):
    bareme = serializers.DecimalField(max_digits=5, decimal_places=2, **DEC)
    salle_nom = serializers.CharField(source='salle.nom', read_only=True, default='')
    surveillants = EpreuveSurveillantSerializer(many=True, read_only=True)

    class Meta:
        model = Epreuve
        fields = [
            'id', 'evaluation', 'groupe', 'date', 'heure_debut', 'heure_fin',
            'duree_minutes', 'salle', 'salle_nom', 'enseignant_responsable',
            'bareme', 'statut', 'motif_annulation', 'surveillants',
        ]


class EvaluationParticipantSerializer(serializers.ModelSerializer):
    matricule = serializers.SerializerMethodField()
    nom_affiche = serializers.SerializerMethodField()

    class Meta:
        model = EvaluationParticipant
        fields = [
            'id', 'evaluation', 'inscription_pedagogique', 'matricule',
            'nom_affiche', 'groupe', 'statut_participation', 'motif', 'source',
            'eligible_rattrapage',
        ]
        read_only_fields = ['evaluation', 'source', 'eligible_rattrapage']

    @extend_schema_field(serializers.CharField())
    def get_matricule(self, obj):
        return _identite(obj.inscription_pedagogique)[0]

    @extend_schema_field(serializers.CharField())
    def get_nom_affiche(self, obj):
        return _identite(obj.inscription_pedagogique)[1]


class EvaluationAttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationAttendance
        fields = [
            'id', 'evaluation_participant', 'epreuve', 'statut', 'heure_arrivee',
            'heure_depart', 'observation', 'motif', 'saisi_par', 'saisi_le',
        ]
        read_only_fields = ['saisi_par', 'saisi_le']


class EvaluationGradeSerializer(serializers.ModelSerializer):
    valeur = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, allow_null=True, **DEC,
    )
    bareme = serializers.DecimalField(max_digits=6, decimal_places=2, **DEC)

    class Meta:
        model = EvaluationGrade
        fields = [
            'id', 'evaluation_participant', 'component', 'valeur', 'bareme',
            'statut', 'verrouillee', 'saisie_par', 'saisie_le', 'motif_correction',
        ]
        read_only_fields = ['statut', 'verrouillee', 'saisie_par', 'saisie_le', 'bareme']


class EvaluationGradeSaisieSerializer(serializers.Serializer):
    """Écriture d'une valeur de note (C1 : saisie brute, sans workflow).

    Le contrôle ``0 ≤ valeur ≤ barème`` est appliqué ici **et** dans le
    modèle. Toute écriture produit une ligne d'historique append-only.
    """

    evaluation_participant_id = serializers.IntegerField()
    valeur = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, allow_null=True, **DEC,
    )


class EvaluationGradeHistorySerializer(serializers.ModelSerializer):
    ancienne_valeur = serializers.DecimalField(max_digits=6, decimal_places=2, **DEC)
    nouvelle_valeur = serializers.DecimalField(max_digits=6, decimal_places=2, **DEC)

    class Meta:
        model = EvaluationGradeHistory
        fields = [
            'id', 'grade', 'action', 'ancienne_valeur', 'nouvelle_valeur',
            'motif', 'auteur', 'created_at',
        ]


class ConvocationEvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConvocationEvaluation
        fields = [
            'id', 'evaluation_participant', 'epreuve', 'reference', 'statut',
            'date_generation', 'date_envoi', 'support',
        ]
        read_only_fields = ['reference', 'date_generation']


# ── Résultats : lecture seule en C1 (aucun calcul) ──────────────────────────
class _ResultatReadOnly(serializers.ModelSerializer):
    """Toutes les expositions sont en lecture seule (C1).

    ``read_only_fields`` ne peut pas valoir ``'__all__'`` (DRF exige une
    liste) et énumérer les champs ici figerait le schéma à chaque évolution
    du modèle : les champs sont donc rendus non modifiables à la construction.
    """

    moyenne = serializers.DecimalField(max_digits=6, decimal_places=2, **DEC)

    def get_fields(self):
        champs = super().get_fields()
        for champ in champs.values():
            champ.read_only = True
        return champs

    class Meta:
        abstract = True


class ECUEResultSerializer(_ResultatReadOnly):
    class Meta(_ResultatReadOnly.Meta):
        model = ECUEResult
        fields = [
            'id', 'inscription_pedagogique', 'session', 'ecue', 'moyenne',
            'moyenne_brute', 'bareme', 'statut', 'source', 'migration_status',
            'regle_version', 'regle_snapshot', 'formule_version', 'detail',
            'empreinte', 'complet', 'avec_dispense', 'imputation_absence',
            'calcule_le', 'verrouillee',
        ]


class UEResultSerializer(_ResultatReadOnly):
    class Meta(_ResultatReadOnly.Meta):
        model = UEResult
        fields = [
            'id', 'inscription', 'session', 'ue', 'moyenne', 'moyenne_brute',
            'bareme', 'credits', 'statut', 'statut_ue', 'source',
            'migration_status', 'regle_version', 'regle_snapshot', 'detail',
            'empreinte', 'calcule_le', 'verrouillee',
        ]


class SemesterResultSerializer(_ResultatReadOnly):
    class Meta(_ResultatReadOnly.Meta):
        model = SemesterResult
        fields = [
            'id', 'inscription', 'session', 'semestre', 'moyenne', 'moyenne_brute',
            'bareme', 'credits_attendus', 'credits_acquis', 'compense', 'statut',
            'statut_semestre', 'source', 'migration_status', 'regle_version',
            'regle_snapshot', 'detail', 'empreinte', 'calcule_le', 'verrouillee',
        ]


class PreparationComposantSerializer(serializers.Serializer):
    """Projection d'un composant : ce que la saisie a produit, tel quel."""

    composant_id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    libelle = serializers.CharField(read_only=True)
    poids = serializers.CharField(read_only=True)
    bareme = serializers.CharField(read_only=True)
    obligatoire = serializers.BooleanField(read_only=True)
    valeur = serializers.FloatField(read_only=True, allow_null=True)
    quotient = serializers.FloatField(read_only=True, allow_null=True)
    note_id = serializers.IntegerField(read_only=True, allow_null=True)
    statut_note = serializers.CharField(read_only=True)
    absent = serializers.BooleanField(read_only=True)


class PreparationDiagnosticSerializer(serializers.Serializer):
    """Point bloquant et décision métier qui devra trancher."""

    code = serializers.CharField(read_only=True)
    decision = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    consequence = serializers.CharField(read_only=True)
    detail = serializers.DictField(read_only=True, allow_null=True)


class PreparationSerializer(serializers.Serializer):
    """Préparation d'un résultat : projet traçable, sans moyenne.

    ``moyenne`` reste ``null`` tant que les décisions D1/D2/D5/D6 ne sont
    pas validées : le schéma expose la place, le moteur ne la remplit pas.
    """

    schema_version = serializers.CharField(read_only=True)
    formule_version = serializers.CharField(read_only=True)
    evaluation_id = serializers.IntegerField(read_only=True)
    session_id = serializers.IntegerField(read_only=True)
    participant_id = serializers.IntegerField(read_only=True)
    statut_participation = serializers.CharField(read_only=True)
    regle_snapshot = serializers.DictField(read_only=True, allow_null=True)
    composants = PreparationComposantSerializer(many=True, read_only=True)
    complet = serializers.BooleanField(read_only=True)
    avec_dispense = serializers.BooleanField(read_only=True)
    imputation_absence = serializers.BooleanField(read_only=True)
    imputation_absence_decision = serializers.CharField(read_only=True)
    moyenne = serializers.FloatField(read_only=True, allow_null=True)
    calculable = serializers.BooleanField(read_only=True)
    diagnostics = PreparationDiagnosticSerializer(many=True, read_only=True)
    empreinte = serializers.CharField(read_only=True)


class ReleveNotesSerializer(serializers.ModelSerializer):
    """Relevé de notes — métadonnées + contenu canonique persisté.

    `contenu` est relu depuis le fichier JSON stocké par le service : aucune
    donnée n'est reconstruite côté API, et `sha256` reste l'empreinte du
    contenu réellement archivé.
    """

    nom_fichier = serializers.CharField(source='fichier.name', read_only=True)
    contenu = serializers.SerializerMethodField()
    participant_matricule = serializers.SerializerMethodField()
    decision_valeur = serializers.SerializerMethodField()

    class Meta:
        model = ReleveNotes
        fields = [
            'id', 'inscription', 'session', 'version', 'sha256', 'genere_le',
            'genere_par', 'verrouillee', 'nom_fichier', 'contenu',
            'participant_matricule', 'decision_valeur',
        ]
        read_only_fields = fields

    def get_contenu(self, obj):
        """Contenu canonique archivé (lecture seule du fichier).

        `FieldFile` met en cache le flux sous-jacent : sans réouverture
        explicite, une seconde lecture renvoie un flux vide.
        """
        try:
            with obj.fichier.open('rb') as flux:
                return json.loads(flux.read().decode('utf-8'))
        except (OSError, ValueError):
            return None

    def get_participant_matricule(self, obj):
        return obj.inscription.etudiant.participant.matricule

    def get_decision_valeur(self, obj):
        """Décision officielle du jury reproduite telle quelle, ou `None`."""
        contenu = self.get_contenu(obj)
        if not contenu:
            return None
        decision = contenu.get('decision')
        return decision['valeur'] if decision else None


class PassageNiveauSerializer(serializers.Serializer):
    """Contrat de sortie du moteur de passage de niveau (lecture seule).

    Le moteur ne produit **aucune** décision de jury : `decision_jury` est
    reprise telle quelle lorsqu'elle existe, absente sinon.
    """

    niveau_cible = serializers.CharField(allow_null=True)
    eligibilite = serializers.CharField()
    code = serializers.CharField()
    credits_acquis = serializers.IntegerField(allow_null=True)
    credits_requis = serializers.IntegerField(allow_null=True)
    justification = serializers.CharField()
    empreinte = serializers.CharField()
    decision_jury = serializers.DictField(allow_null=True)
    semestres = serializers.ListField(child=serializers.DictField())