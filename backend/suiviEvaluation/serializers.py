from rest_framework import serializers
from .models import (
    Questionnaire, Question, ChoixQuestion,
    ReponseQuestionnaire, ReponseQuestion,
)

class ChoixQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChoixQuestion
        fields = ['id', 'libelle', 'ordre']


class QuestionSerializer(serializers.ModelSerializer):
    choix = ChoixQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ['id', 'intitule', 'type_question', 'section', 'ordre', 'obligatoire', 'choix']


class QuestionnaireListSerializer(serializers.ModelSerializer):
    nb_questions = serializers.SerializerMethodField()
    createur_nom = serializers.SerializerMethodField()
    module_intitule = serializers.SerializerMethodField()

    class Meta:
        model = Questionnaire
        fields = [
            'id', 'titres', 'cible', 'statut', 'categories', 'grades', 'groupes',
            'module', 'module_intitule',
            'createur', 'createur_nom',
            'date_ouverture', 'date_fermeture',
            'nb_questions', 'created_at',
        ]

    def get_nb_questions(self, obj):
        if hasattr(obj, '_nb_questions'):
            return obj._nb_questions
        return obj.questions.count()

    def get_createur_nom(self, obj):
        if obj.createur:
            return obj.createur.get_full_name() or obj.createur.username
        return ''

    def get_module_intitule(self, obj):
        if obj.module:
            return obj.module.intitule
        return ''


class QuestionnaireDetailSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    createur_nom = serializers.SerializerMethodField()
    module_intitule = serializers.SerializerMethodField()

    class Meta:
        model = Questionnaire
        fields = [
            'id', 'titres', 'cible', 'statut', 'categories', 'grades', 'groupes',
            'module', 'module_intitule',
            'createur', 'createur_nom',
            'date_ouverture', 'date_fermeture',
            'questions', 'created_at', 'updated_at',
        ]

    def get_createur_nom(self, obj):
        if obj.createur:
            return obj.createur.get_full_name() or obj.createur.username
        return ''

    def get_module_intitule(self, obj):
        if obj.module:
            return obj.module.intitule
        return ''


class QuestionWriteSerializer(serializers.ModelSerializer):
    choix = ChoixQuestionSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = ['id', 'intitule', 'type_question', 'section', 'ordre', 'obligatoire', 'choix']

    def create(self, validated_data):
        choix_data = validated_data.pop('choix', [])
        question = Question.objects.create(**validated_data)
        for c in choix_data:
            ChoixQuestion.objects.create(question=question, **c)
        return question

    def update(self, instance, validated_data):
        choix_data = validated_data.pop('choix', None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if choix_data is not None:
            instance.choix.all().delete()
            for c in choix_data:
                ChoixQuestion.objects.create(question=instance, **c)
        return instance


class ReponseQuestionSerializer(serializers.ModelSerializer):
    choix_multiples = serializers.PrimaryKeyRelatedField(
        queryset=ChoixQuestion.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = ReponseQuestion
        fields = ['question', 'note', 'texte', 'choix', 'choix_multiples']


class SoumissionSerializer(serializers.ModelSerializer):
    reponses_questions = ReponseQuestionSerializer(many=True)

    class Meta:
        model = ReponseQuestionnaire
        fields = ['id', 'questionnaire', 'participant', 'soumis_le', 'reponses_questions']
        read_only_fields = ['id', 'soumis_le']

    def validate(self, data):
        questionnaire = data['questionnaire']
        participant = data['participant']
        if questionnaire.statut != Questionnaire.Statut.PUBLIE:
            raise serializers.ValidationError("Ce questionnaire n'est pas ouvert.")
        if ReponseQuestionnaire.objects.filter(
            questionnaire=questionnaire, participant=participant
        ).exists():
            raise serializers.ValidationError("Vous avez déjà répondu à ce questionnaire.")
        return data

    def create(self, validated_data):
        reponses_data = validated_data.pop('reponses_questions')
        soumission = ReponseQuestionnaire.objects.create(**validated_data)
        for rep in reponses_data:
            choix_mult = rep.pop('choix_multiples', [])
            rq = ReponseQuestion.objects.create(soumission=soumission, **rep)
            if choix_mult:
                rq.choix_multiples.set(choix_mult)
        return soumission


class ResultatsSerializer(serializers.ModelSerializer):
    """Résumé statistique d'un questionnaire pour les superviseurs."""
    nb_soumissions = serializers.IntegerField(source='reponses.count', read_only=True)
    questions = serializers.SerializerMethodField()

    class Meta:
        model = Questionnaire
        fields = ['id', 'titres', 'cible', 'statut', 'categories', 'grades', 'groupes', 'nb_soumissions', 'questions']

    def get_questions(self, obj):
        from django.db.models import Avg, Count
        result = []
        for q in obj.questions.prefetch_related('choix', 'reponses').order_by('ordre'):
            item = {
                'id': q.id,
                'intitule': q.intitule,
                'type_question': q.type_question,
                'ordre': q.ordre,
            }
            if q.type_question == Question.TypeQuestion.NOTE:
                agg = q.reponses.filter(note__isnull=False).aggregate(
                    moyenne=Avg('note'), total=Count('id')
                )
                item['moyenne'] = round(agg['moyenne'], 2) if agg['moyenne'] else None
                item['total_reponses'] = agg['total']
            elif q.type_question in (
                Question.TypeQuestion.CHOIX_UN,
                Question.TypeQuestion.CHOIX_MUL,
            ):
                choix_stats = []
                for c in q.choix.all():
                    nb_unique = q.reponses.filter(choix=c).count()
                    nb_multiple = c.reponses_choix_multiple.filter(
                        soumission__questionnaire=obj
                    ).count()
                    choix_stats.append({
                        'id': c.id,
                        'libelle': c.libelle,
                        'nb_reponses': nb_unique + nb_multiple,
                    })
                item['choix_stats'] = choix_stats
            else:
                item['nb_reponses_texte'] = q.reponses.exclude(texte='').count()
            result.append(item)
        return result

