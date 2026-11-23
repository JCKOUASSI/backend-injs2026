import 'package:flutter_test/flutter_test.dart';
import 'package:qr_badge_mobile/utils/open_session_recovery.dart';

void main() {
  group('shouldRestoreOpenSession', () {
    test('restaure si statut EN_SALLE', () {
      expect(
        shouldRestoreOpenSession({'statut': 'EN_SALLE'}),
        isTrue,
      );
    });

    test('restaure si prochaine action SORTIE', () {
      expect(
        shouldRestoreOpenSession({'action_suivante': 'SORTIE'}),
        isTrue,
      );
    });

    test('ne restaure pas si séance terminée', () {
      expect(
        shouldRestoreOpenSession({
          'statut': 'TERMINE',
          'action_suivante': null,
        }),
        isFalse,
      );
    });

    test('ne restaure pas si absent', () {
      expect(
        shouldRestoreOpenSession({
          'statut': 'ABSENT',
          'action_suivante': 'ENTREE',
        }),
        isFalse,
      );
    });
  });

  group('mergeOpenSessionSnapshot', () {
    test('priorise les champs serveur quand présents', () {
      const cached = OpenSessionSnapshot(
        tokenQr: 'abc-123',
        heureEntree: '09:00',
        seanceLabel: 'Ancien',
      );
      final merged = mergeOpenSessionSnapshot(
        cached: cached,
        serverStatus: {
          'heure_entree': '14:30',
          'seance_intitule': 'Module Excel',
        },
      );
      expect(merged.tokenQr, 'abc-123');
      expect(merged.heureEntree, '14:30');
      expect(merged.seanceLabel, 'Module Excel');
    });

    test('conserve le cache si le serveur ne renvoie rien', () {
      const cached = OpenSessionSnapshot(
        tokenQr: 'abc-123',
        heureEntree: '09:00',
        seanceLabel: 'Module Excel',
      );
      final merged = mergeOpenSessionSnapshot(
        cached: cached,
        serverStatus: {},
      );
      expect(merged.heureEntree, '09:00');
      expect(merged.seanceLabel, 'Module Excel');
    });
  });

  group('buildOpenSessionChipLabel', () {
    test('null si heartbeat inactif', () {
      expect(
        buildOpenSessionChipLabel(
          heartbeatRunning: false,
          heureEntree: '10:00',
        ),
        isNull,
      );
    });

    test('libellé complet avec séance et heure', () {
      expect(
        buildOpenSessionChipLabel(
          heartbeatRunning: true,
          heureEntree: '14:32',
          seanceLabel: 'Séance 1',
        ),
        'En salle · Séance 1 · depuis 14:32',
      );
    });

    test('libellé par défaut sans détails', () {
      expect(
        buildOpenSessionChipLabel(heartbeatRunning: true),
        'Session ouverte — suivi actif',
      );
    });
  });
}
