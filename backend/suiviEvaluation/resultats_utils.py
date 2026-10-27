"""Agrégation des résultats de questionnaire, ventilés par groupe."""
from collections import defaultdict

from django.db.models import Avg, Count

from .access import _normalize_groupe_value
from .models import Question


def _soumissions_par_groupe(questionnaire):
    """Retourne {groupe_normalisé: [soumission_id, …]}."""
    by_groupe = defaultdict(list)
    for s in questionnaire.reponses.select_related('participant'):
        groupe = _normalize_groupe_value(s.participant.groupe) or '—'
        by_groupe[groupe].append(s.id)

    for g in questionnaire.groupes or []:
        groupe = _normalize_groupe_value(g)
        if groupe and groupe not in by_groupe:
            by_groupe[groupe] = []

    return dict(sorted(by_groupe.items(), key=lambda x: x[0]))


def _build_questions_stats(questionnaire, soumission_ids):
    """Statistiques par question pour un sous-ensemble de soumissions."""
    if soumission_ids is not None and not soumission_ids:
        soumission_ids = set()

    result = []
    for q in questionnaire.questions.prefetch_related('choix', 'reponses').order_by('ordre'):
        item = {
            'id': q.id,
            'intitule': q.intitule,
            'type_question': q.type_question,
            'ordre': q.ordre,
        }
        rep_qs = q.reponses.all()
        if soumission_ids is not None:
            rep_qs = rep_qs.filter(soumission_id__in=soumission_ids)

        if q.type_question == Question.TypeQuestion.NOTE:
            reponses_note = rep_qs.filter(note__isnull=False)
            notes = list(reponses_note.values_list('note', flat=True))
            agg = reponses_note.aggregate(moyenne=Avg('note'), total=Count('id'))
            item['moyenne'] = round(agg['moyenne'], 2) if agg['moyenne'] else None
            item['total_reponses'] = agg['total']
            item['distribution'] = {str(i): notes.count(i) for i in range(1, 6)}
        elif q.type_question in (Question.TypeQuestion.CHOIX_UN, Question.TypeQuestion.CHOIX_MUL):
            choix_stats = []
            for c in q.choix.all():
                nb_unique = rep_qs.filter(choix=c).count()
                nb_multiple = c.reponses_choix_multiple.filter(
                    soumission__questionnaire=questionnaire,
                )
                if soumission_ids is not None:
                    nb_multiple = nb_multiple.filter(soumission_id__in=soumission_ids)
                nb_multiple = nb_multiple.count()
                choix_stats.append({
                    'id': c.id,
                    'libelle': c.libelle,
                    'nb_reponses': nb_unique + nb_multiple,
                })
            item['choix_stats'] = choix_stats
        else:
            item['nb_reponses_texte'] = rep_qs.exclude(texte='').count()

        result.append(item)
    return result


def build_resultats_payload(questionnaire, groupe_filtre=''):
    """
    Payload complet des résultats avec ventilation par groupe.
    groupe_filtre : si renseigné, le bloc `questions` correspond à ce groupe uniquement.
    """
    by_groupe = _soumissions_par_groupe(questionnaire)

    par_groupe = {
        groupe: {
            'nb_soumissions': len(ids),
            'questions': _build_questions_stats(questionnaire, set(ids)),
        }
        for groupe, ids in by_groupe.items()
    }

    distribution_groupes = {g: len(ids) for g, ids in by_groupe.items()}

    if groupe_filtre:
        ids = set(by_groupe.get(groupe_filtre, []))
        questions = _build_questions_stats(questionnaire, ids)
        nb_soumissions = len(ids)
    elif len(by_groupe) == 1:
        groupe_filtre = next(iter(by_groupe))
        ids = set(by_groupe[groupe_filtre])
        questions = _build_questions_stats(questionnaire, ids)
        nb_soumissions = len(ids)
    else:
        groupe_filtre = ''
        questions = []
        nb_soumissions = sum(len(ids) for ids in by_groupe.values())

    return {
        'id': questionnaire.pk,
        'titres': questionnaire.titres,
        'cible': questionnaire.cible,
        'statut': questionnaire.statut,
        'categories': questionnaire.categories,
        'grades': questionnaire.grades,
        'groupes': questionnaire.groupes,
        'groupe_filtre': groupe_filtre or None,
        'nb_soumissions': nb_soumissions,
        'nb_soumissions_total': sum(len(ids) for ids in by_groupe.values()),
        'distribution_groupes': distribution_groupes,
        'questions': questions,
        'par_groupe': par_groupe,
    }
