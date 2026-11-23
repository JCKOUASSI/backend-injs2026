import 'auth_service.dart';
import 'api_client.dart';
import 'scan_service.dart';

class ProfileService {
  final _auth = AuthService();
  final _scan = ScanService();

  Future<Map<String, dynamic>> myFiche({
    required String baseUrl,
    required String accessToken,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final client = ApiClient(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );
    try {
      return await client.get('/api/me/fiche/');
    } on ApiResponseException catch (e) {
      if (e.statusCode == 404) {
        return _buildFallbackFiche(
          baseUrl: baseUrl,
          accessToken: accessToken,
          onRefreshToken: onRefreshToken,
        );
      }
      rethrow;
    } catch (e) {
      final msg = e.toString();
      if (e is FormatException ||
          msg.contains('<!DOCTYPE') ||
          msg.contains('Unexpected character')) {
        return _buildFallbackFiche(
          baseUrl: baseUrl,
          accessToken: accessToken,
          onRefreshToken: onRefreshToken,
        );
      }
      rethrow;
    }
  }

  Future<Map<String, dynamic>> _buildFallbackFiche({
    required String baseUrl,
    required String accessToken,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final utilisateur = await _auth.me(
      baseUrl: baseUrl,
      accessToken: accessToken,
    );
    final historique = await _scan.myHistory(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );

    final profil = <String, dynamic>{
      'type_personne': historique['type_personne'],
      'numero': historique['numero'],
      'nom': historique['nom'],
      'prenom': historique['prenom'],
    };

    final rawModules = historique['modules'];
    List<Map<String, dynamic>> modules;
    if (rawModules is List && rawModules.isNotEmpty) {
      modules = rawModules.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } else {
      modules = _modulesFromPointages(historique['pointages']);
    }

    final rawStats = historique['stats'];
    final stats = rawStats is Map
        ? Map<String, dynamic>.from(rawStats)
        : _statsFromPointages(historique['pointages']);

    if (!stats.containsKey('nb_modules_inscrits')) {
      stats['nb_modules_inscrits'] = modules.length;
    }

    return {
      'utilisateur': utilisateur,
      'profil': profil,
      'modules': modules,
      'stats': stats,
      '_fallback': true,
    };
  }

  List<Map<String, dynamic>> _modulesFromPointages(dynamic rawPointages) {
    if (rawPointages is! List) {
      return [];
    }
    final seen = <int>{};
    final modules = <Map<String, dynamic>>[];
    for (final raw in rawPointages) {
      if (raw is! Map) {
        continue;
      }
      final m = Map<String, dynamic>.from(raw);
      final fid = m['formation_id'];
      if (fid is! int || seen.contains(fid)) {
        continue;
      }
      seen.add(fid);
      modules.add({
        'id': fid,
        'formation_id': fid,
        'formation': m['formation_titre']?.toString() ?? '',
        'module': m['formation_titre']?.toString() ?? 'Formation',
        'statut': 'EN_COURS',
      });
    }
    return modules;
  }

  Map<String, dynamic> _statsFromPointages(dynamic rawPointages) {
    if (rawPointages is! List) {
      return {
        'nb_badgeages': 0,
        'nb_seances_terminees': 0,
        'nb_seances_en_cours': 0,
        'nb_a_verifier': 0,
        'nb_sans_probleme': 0,
        'total_minutes_presence': 0,
        'nb_modules_inscrits': 0,
        'dernier_badgeage': null,
        'volume_horaire_total_heures': 0,
        'volume_horaire_effectue_heures': 0,
        'volume_horaire_effectue_taux': 0,
      };
    }

    var terminees = 0;
    var enCours = 0;
    var aVerifier = 0;
    var totalMin = 0.0;
    DateTime? dernier;

    for (final raw in rawPointages) {
      if (raw is! Map) {
        continue;
      }
      final m = Map<String, dynamic>.from(raw);
      final min = m['duree_presence_minutes'];
      if (min is num) {
        totalMin += min.toDouble();
      }
      final sortie = m['timestamp_sortie'];
      final entree = m['timestamp_entree']?.toString();
      if (sortie != null && sortie.toString().isNotEmpty) {
        terminees++;
      } else {
        enCours++;
        aVerifier++;
      }
      final statut = m['statut']?.toString() ?? '';
      if (statut == 'HORS_LIGNE_SUSPECT' ||
          statut == 'ABSENT_NON_BADGE' ||
          statut == 'SORTIE_AUTO') {
        aVerifier++;
      }
      final dt = DateTime.tryParse(entree ?? '');
      if (dt != null && (dernier == null || dt.isAfter(dernier))) {
        dernier = dt;
      }
    }

    final nb = rawPointages.length;
    return {
      'nb_badgeages': nb,
      'nb_seances_terminees': terminees,
      'nb_seances_en_cours': enCours,
      'nb_a_verifier': aVerifier,
      'nb_sans_probleme': (nb - aVerifier).clamp(0, nb),
      'total_minutes_presence': totalMin.round(),
      'nb_modules_inscrits': 0,
      'dernier_badgeage': dernier?.toIso8601String(),
      'volume_horaire_total_heures': 0,
      'volume_horaire_effectue_heures': 0,
      'volume_horaire_effectue_taux': 0,
    };
  }

  Future<Map<String, dynamic>> updateMyProfile({
    required String baseUrl,
    required String accessToken,
    required Map<String, dynamic> data,
    Future<String?> Function()? onRefreshToken,
  }) {
    return _auth.updateMyProfile(
      baseUrl: baseUrl,
      accessToken: accessToken,
      data: data,
      onRefreshToken: onRefreshToken,
    );
  }

  Future<Map<String, dynamic>> updateMySensitiveData({
    required String baseUrl,
    required String accessToken,
    required String numeroPieceIdentite,
    required String numeroCompteBancaire,
    Future<String?> Function()? onRefreshToken,
  }) async {
    final client = ApiClient(
      baseUrl: baseUrl,
      accessToken: accessToken,
      onRefreshToken: onRefreshToken,
    );
    return client.patch('/api/me/fiche/', data: {
      'numero_piece_identite': numeroPieceIdentite,
      'numero_compte_bancaire': numeroCompteBancaire,
    });
  }
}
