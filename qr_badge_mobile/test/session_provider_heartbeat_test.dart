import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:qr_badge_mobile/providers/session_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    dotenv.testLoad(
      fileInput: 'API_BASE_URL=https://api.sygepcpfae.org\nHEARTBEAT_ENABLED=true\n',
    );
  });

  test('startSecureSessionHeartbeat active le suivi', () {
    final session = SessionProvider();

    session.startSecureSessionHeartbeat(
      'token-test',
      heureEntree: '09:15',
      seanceLabel: 'Module Excel',
      persist: false,
    );

    expect(session.isSecureHeartbeatRunning, isTrue);
    expect(session.openSessionChipLabel, contains('Module Excel'));
  });
}
