import 'package:flutter_test/flutter_test.dart';
import 'package:qr_badge_mobile/services/api_client.dart';
import 'package:qr_badge_mobile/utils/user_facing_error.dart';

void main() {
  test('timeout ne divulgue pas host ni port', () {
    const err = NetworkTimeoutException();
    final msg = userFacingErrorMessage(
      err,
      context: UserErrorContext.badgeStatus,
    );
    expect(msg, contains('badgeage'));
    expect(msg, isNot(contains('sygepcpfae')));
    expect(msg, isNot(contains(':443')));
    expect(msg, isNot(contains('app.env')));
  });

  test('erreur brute avec URL est masquée', () {
    final msg = userFacingErrorMessage(
      Exception('SocketException: failed host lookup api.sygepcpfae.org'),
      context: UserErrorContext.login,
    );
    expect(msg, contains('connexion'));
    expect(msg, isNot(contains('sygepcpfae')));
  });

  test('message métier court de l’API est conservé', () {
    final msg = userFacingErrorMessage(
      Exception('Identifiants invalides.'),
      context: UserErrorContext.login,
    );
    expect(msg, 'Identifiants invalides.');
  });

  test('ApiResponseException sans chemin API', () {
    const err = ApiResponseException(
      statusCode: 404,
      path: '/api/secret/internal/',
      message: 'Service indisponible.',
    );
    final msg = userFacingErrorMessage(err);
    expect(msg, isNot(contains('/api/')));
    expect(msg, contains('indisponible'));
  });

  test('ApiBusinessException conserve le message métier', () {
    const err = ApiBusinessException(
      'OUT_OF_GEOFENCE',
      'Vous êtes hors du périmètre autorisé.',
    );
    expect(
      userFacingErrorMessage(err, context: UserErrorContext.badgeScan),
      contains('périmètre'),
    );
  });

  test('ApiResponseException 401 conserve le message serveur', () {
    const err = ApiResponseException(
      statusCode: 401,
      path: '/api/auth/login/',
      message: 'Identifiants invalides.',
    );
    final msg = userFacingErrorMessage(
      err,
      context: UserErrorContext.login,
    );
    expect(msg, 'Identifiants invalides.');
  });
}
