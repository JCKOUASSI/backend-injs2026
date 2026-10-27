/// Indique si l’URL pointe vers la machine locale (boucle).
/// Sur un **téléphone physique**, 127.0.0.1 / localhost = le téléphone lui-même,
/// pas l’ordinateur qui héberge Django.
bool isLoopbackServerUrl(String baseUrl) {
  final t = baseUrl.toLowerCase().trim();
  return t.contains('127.0.0.1') || t.contains('localhost');
}

bool looksLikeNetworkUnreachableToHost(String errorText) {
  final t = errorText.toLowerCase();
  return t.contains('connection refused') ||
      t.contains('socketexception') ||
      t.contains('failed host lookup') ||
      t.contains('network is unreachable');
}
