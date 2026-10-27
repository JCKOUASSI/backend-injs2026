import 'api_client.dart';

class EvaluationService {
  /// Récupère les questionnaires publiés accessibles à l'étudiant connecté.
  Future<List<Map<String, dynamic>>> mesQuestionnaires({
    required String baseUrl,
    required String accessToken,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final client = ApiClient(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );
    final res = await client.get('/api/evaluations/mes-questionnaires/');
    final raw = res['data'] ?? res;
    if (raw is List) {
      return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    }
    return [];
  }

  /// Soumet les réponses d'un étudiant à un questionnaire.
  /// [questionnaire] : id du questionnaire
  /// [reponses] : liste de { question: id, note?: int, texte?: str, choix?: id, choix_multiples?: [id] }
  Future<void> soumettre({
    required String baseUrl,
    required String accessToken,
    required int questionnaireId,
    required List<Map<String, dynamic>> reponses,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final client = ApiClient(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );
    await client.post('/api/evaluations/soumettre/', data: {
      'questionnaire': questionnaireId,
      'reponses_questions': reponses,
    });
  }
}
