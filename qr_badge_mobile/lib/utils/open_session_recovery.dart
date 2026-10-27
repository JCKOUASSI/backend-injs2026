/// Logique pure de reprise de session ouverte (testable sans Flutter).
class OpenSessionSnapshot {
  const OpenSessionSnapshot({
    required this.tokenQr,
    this.heureEntree,
    this.seanceLabel,
  });

  final String tokenQr;
  final String? heureEntree;
  final String? seanceLabel;

  bool get isValid => tokenQr.trim().isNotEmpty;
}

/// Indique si le serveur confirme une session encore ouverte pour le QR sauvegardé.
bool shouldRestoreOpenSession(Map<String, dynamic> checkStatus) {
  final statut = checkStatus['statut']?.toString();
  final action = checkStatus['action_suivante']?.toString();
  if (statut == 'EN_SALLE') {
    return true;
  }
  if (action == 'SORTIE') {
    return true;
  }
  return false;
}

/// Fusionne la réponse serveur et le cache local pour relancer le heartbeat.
OpenSessionSnapshot mergeOpenSessionSnapshot({
  required OpenSessionSnapshot cached,
  Map<String, dynamic>? serverStatus,
}) {
  if (serverStatus == null) {
    return cached;
  }
  final heure = serverStatus['heure_entree']?.toString().trim();
  final seance = serverStatus['seance_intitule']?.toString().trim();
  return OpenSessionSnapshot(
    tokenQr: cached.tokenQr,
    heureEntree: (heure != null && heure.isNotEmpty) ? heure : cached.heureEntree,
    seanceLabel: (seance != null && seance.isNotEmpty) ? seance : cached.seanceLabel,
  );
}

/// Libellé du bandeau « en salle » affiché dans toute l'app.
String? buildOpenSessionChipLabel({
  required bool heartbeatRunning,
  String? heureEntree,
  String? seanceLabel,
}) {
  if (!heartbeatRunning) {
    return null;
  }
  final heure = heureEntree?.trim();
  final seance = seanceLabel?.trim();
  if (heure != null && heure.isNotEmpty) {
    if (seance != null && seance.isNotEmpty) {
      return 'En salle · $seance · depuis $heure';
    }
    return 'En salle depuis $heure';
  }
  if (seance != null && seance.isNotEmpty) {
    return 'En salle · $seance';
  }
  return 'Session ouverte — suivi actif';
}
