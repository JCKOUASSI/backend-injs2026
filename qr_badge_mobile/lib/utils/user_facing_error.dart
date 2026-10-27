import '../services/api_client.dart';
import 'app_log.dart';
import 'server_url.dart';

/// Contexte d'affichage pour adapter le message sans données sensibles.
enum UserErrorContext {
  generic,
  login,
  badgeStatus,
  badgeScan,
  profile,
  history,
  evaluations,
}

/// Journalise l'erreur complète en debug uniquement (jamais montrée à l'utilisateur).
void logErrorForDebug(String scope, Object error, [StackTrace? stackTrace]) {
  AppLog.error(scope, error, stackTrace);
}

/// Titre de dialogues d'erreur (sans détail technique).
String userFacingErrorTitle(
  Object error, {
  UserErrorContext context = UserErrorContext.generic,
}) {
  if (error is ApiBusinessException) {
    return switch (context) {
      UserErrorContext.badgeStatus || UserErrorContext.badgeScan =>
        'Badgeage impossible',
      UserErrorContext.login => 'Connexion impossible',
      _ => 'Action impossible',
    };
  }
  if (error is SessionExpiredException) {
    return 'Session expirée';
  }
  if (_isNetworkError(error)) {
    return 'Serveur injoignable';
  }
  return switch (context) {
    UserErrorContext.login => 'Connexion impossible',
    UserErrorContext.badgeStatus || UserErrorContext.badgeScan =>
      'Badgeage impossible',
    _ => 'Erreur',
  };
}

/// Message utilisateur sans URL, IP, chemins API, config interne ni stack trace.
String userFacingErrorMessage(
  Object error, {
  UserErrorContext context = UserErrorContext.generic,
  String? serverBaseUrl,
  String? fallback,
}) {
  if (error is ApiBusinessException ||
      error is SessionExpiredException ||
      error is NoProfileException) {
    return error.toString();
  }
  if (error is NetworkTimeoutException || error is NetworkUnreachableException) {
    return _networkMessage(context);
  }
  if (error is ApiResponseException) {
    return _apiResponseMessage(error);
  }

  final raw = _stripExceptionPrefix(error.toString());
  if (serverBaseUrl != null &&
      isLoopbackServerUrl(serverBaseUrl) &&
      looksLikeNetworkUnreachableToHost(raw)) {
    return _loopbackHintMessage();
  }
  if (_looksLikeNetworkIssue(raw)) {
    return _networkMessage(context);
  }
  if (_looksLikeSafeUserMessage(raw)) {
    return raw;
  }

  return fallback ?? _genericMessage(context);
}

String _networkMessage(UserErrorContext context) {
  return switch (context) {
    UserErrorContext.login =>
      'Impossible de contacter le serveur. Vérifiez votre connexion '
      'internet (Wi‑Fi ou données mobiles) et réessayez.',
    UserErrorContext.badgeStatus =>
      'Impossible de vérifier le statut de badgeage. '
      'Vérifiez votre connexion internet et réessayez.',
    UserErrorContext.badgeScan =>
      'Impossible d\u2019enregistrer le badgeage. '
      'Vérifiez votre connexion internet et réessayez.',
    UserErrorContext.profile =>
      'Impossible de charger votre profil. Vérifiez votre connexion internet.',
    UserErrorContext.history =>
      'Impossible de charger l\u2019historique. Vérifiez votre connexion internet.',
    UserErrorContext.evaluations =>
      'Impossible de charger les évaluations. Vérifiez votre connexion internet.',
    UserErrorContext.generic =>
      'Impossible de contacter le serveur. Vérifiez votre connexion internet '
      'et réessayez dans quelques instants.',
  };
}

String _apiResponseMessage(ApiResponseException error) {
  if (error.statusCode == 404) {
    return 'Service indisponible. Mettez à jour l\u2019application ou réessayez plus tard.';
  }
  if (error.statusCode == 429 || error.statusCode == 401) {
    return error.message;
  }
  if (error.message.isNotEmpty) {
    return error.message;
  }
  return 'Le serveur a renvoyé une réponse inattendue. Réessayez plus tard.';
}

String _loopbackHintMessage() {
  return 'Connexion impossible depuis cet appareil. En environnement de test, '
      'l\u2019adresse du serveur doit être celle de l\u2019ordinateur qui héberge '
      'l\u2019application, pas une adresse locale de l\u2019appareil.';
}

String _genericMessage(UserErrorContext context) {
  return switch (context) {
    UserErrorContext.login =>
      'Connexion impossible. Vérifiez vos identifiants ou réessayez plus tard.',
    UserErrorContext.badgeStatus =>
      'Impossible de vérifier le statut de badgeage. Réessayez plus tard.',
    UserErrorContext.badgeScan =>
      'Le badgeage n\u2019a pas pu être enregistré. Réessayez plus tard.',
    UserErrorContext.profile =>
      'Impossible de charger votre profil. Réessayez plus tard.',
    UserErrorContext.history =>
      'Impossible de charger l\u2019historique. Réessayez plus tard.',
    UserErrorContext.evaluations =>
      'Impossible de charger les évaluations. Réessayez plus tard.',
    UserErrorContext.generic =>
      'Une erreur est survenue. Réessayez ou contactez le secrétariat.',
  };
}

bool _isNetworkError(Object error) {
  return error is NetworkTimeoutException || error is NetworkUnreachableException;
}

String _stripExceptionPrefix(String raw) {
  return raw.replaceFirst(RegExp(r'^(\w+Exception:\s*|Exception:\s*)+'), '').trim();
}

bool _looksLikeNetworkIssue(String raw) {
  final t = raw.toLowerCase();
  return t.contains('connection refused') ||
      t.contains('socketexception') ||
      t.contains('failed host lookup') ||
      t.contains('network is unreachable') ||
      t.contains('handshakeexception') ||
      t.contains('connection timed out') ||
      t.contains('connection closed') ||
      t.contains('serveur injoignable');
}

/// Messages métier courts renvoyés par l'API (identifiants, validation…).
bool _looksLikeSafeUserMessage(String raw) {
  if (raw.isEmpty || raw.length > 280) {
    return false;
  }
  if (_containsSensitivePattern(raw)) {
    return false;
  }
  return !raw.contains('\n');
}

bool _containsSensitivePattern(String raw) {
  final t = raw.toLowerCase();
  return t.contains('http://') ||
      t.contains('https://') ||
      t.contains('api/') ||
      t.contains('app.env') ||
      t.contains('django') ||
      t.contains('token') ||
      t.contains('bearer') ||
      t.contains('secret') ||
      t.contains('127.0.0.1') ||
      t.contains('localhost') ||
      t.contains('192.168.') ||
      t.contains('10.') ||
      RegExp(r':\d{2,5}').hasMatch(raw) ||
      RegExp(r'\b\d{1,3}(\.\d{1,3}){3}\b').hasMatch(raw);
}
