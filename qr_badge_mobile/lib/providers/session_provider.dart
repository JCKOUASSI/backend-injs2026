import 'dart:async';

import 'package:flutter/foundation.dart';

import '../config/app_env.dart';
import '../services/auth_service.dart';
import '../services/background_keepalive.dart';
import '../services/device_telemetry_service.dart';
import '../services/evaluation_service.dart';
import '../services/mobile_config_service.dart';
import '../services/scan_service.dart';
import '../services/storage_service.dart';
import '../utils/dev_api_defaults.dart';
import '../utils/device_label.dart';
import '../utils/app_log.dart';
import '../utils/open_session_recovery.dart';

class SessionProvider extends ChangeNotifier {
  final StorageService _storage = StorageService();
  final AuthService _auth = AuthService();
  final ScanService _heartbeatScan = ScanService();
  final DeviceTelemetryService _heartbeatTelemetry = DeviceTelemetryService();

  final MobileConfigService _mobileConfig = MobileConfigService();
  final EvaluationService _evaluations = EvaluationService();

  bool _loginInFlight = false;
  Future<bool>? _refreshInFlight;

  Timer? _heartbeatTimer;
  String? _heartbeatTokenQr;
  String? _openSessionHeureEntree;
  String? _openSessionSeanceLabel;
  bool _heartbeatBusy = false;
  int _heartbeatGpsMisses = 0;
  static const _kGpsMissThreshold = 3;

  bool isBootstrapping = true;
  bool isAuthenticated = false;
  String baseUrl = AppEnv.initialApiBaseUrl;
  String? accessToken;
  String? refreshToken;
  String? username;
  String? deviceId;
  Map<String, dynamic>? user;
  bool mustChangePassword = false;

  /// Incrémenté après un badgeage pour rafraîchir accueil / historique.
  int historyRefreshTick = 0;

  /// Résultat de la demande de permission GPS au démarrage.
  /// Initialisé à `true` pour éviter un flash d'avertissement avant
  /// que la permission ait été vérifiée.
  bool gpsGranted = true;

  /// Vrai quand le heartbeat échoue ≥ [_kGpsMissThreshold] fois de suite
  /// faute de position GPS disponible.
  bool heartbeatGpsBlocked = false;

  /// Heartbeat automatique actif (après une entrée, jusqu'à sortie ou fin de session).
  bool get isSecureHeartbeatRunning => _heartbeatTimer != null;

  /// Libellé du bandeau « session ouverte » (persistant sur tous les écrans).
  String? get openSessionChipLabel => buildOpenSessionChipLabel(
        heartbeatRunning: isSecureHeartbeatRunning,
        heureEntree: _openSessionHeureEntree,
        seanceLabel: _openSessionSeanceLabel,
      );

  /// Questionnaires d'évaluation non encore remplis (étudiants).
  int pendingEvaluationsCount = 0;

  /// Vrai une fois si une session ouverte a été reprise au démarrage (snackbar unique).
  bool _openSessionRestoredOnBoot = false;
  bool get openSessionRestoredOnBoot => _openSessionRestoredOnBoot;

  /// Consomme le message de reprise (affiché une seule fois au lancement).
  String? consumeOpenSessionRestoredSnack() {
    if (!_openSessionRestoredOnBoot) {
      return null;
    }
    _openSessionRestoredOnBoot = false;
    final label = openSessionChipLabel;
    if (label != null && label.isNotEmpty) {
      return 'Session reprise — $label';
    }
    return 'Session reprise — suivi de présence actif';
  }

  bool? _remoteHeartbeatEnabled;
  int? _remoteHeartbeatIntervalSec;
  bool? _remoteEvaluationsEnabled;

  /// Onglet « Évaluations » visible pour les comptes étudiant (participant).
  bool get evaluationsEnabled {
    if (_remoteEvaluationsEnabled != null) {
      return _remoteEvaluationsEnabled!;
    }
    return user?['role']?.toString() == 'AUDITEUR';
  }

  bool get _effectiveHeartbeatEnabled {
    if (!AppEnv.heartbeatEnabled) {
      return false;
    }
    if (_remoteHeartbeatEnabled == false) {
      return false;
    }
    return true;
  }

  Duration get _effectiveHeartbeatInterval {
    final remote = _remoteHeartbeatIntervalSec;
    if (remote != null) {
      return Duration(seconds: remote.clamp(30, 600));
    }
    return AppEnv.heartbeatInterval;
  }

  /// Notifie l'app du résultat de la demande de permission GPS.
  void setGpsGranted(bool granted) {
    if (gpsGranted == granted) return;
    gpsGranted = granted;
    notifyListeners();
  }

  /// Démarre l'envoi périodique de `/api/scan/secure/heartbeat/` pour le QR courant.
  void startSecureSessionHeartbeat(
    String tokenQr, {
    String? heureEntree,
    String? seanceLabel,
    bool persist = true,
  }) {
    stopSecureSessionHeartbeat(notify: false);
    if (!_effectiveHeartbeatEnabled) {
      return;
    }
    final t = tokenQr.trim();
    if (t.isEmpty) {
      return;
    }
    _heartbeatTokenQr = t;
    _openSessionHeureEntree = heureEntree?.trim();
    _openSessionSeanceLabel = seanceLabel?.trim();
    final every = _effectiveHeartbeatInterval;
    void schedulePulse() {
      scheduleMicrotask(_heartbeatPulse);
    }

    schedulePulse();
    _heartbeatTimer = Timer.periodic(every, (_) => schedulePulse());
    unawaited(BackgroundKeepalive.instance.start());
    if (persist) {
      unawaited(
        _storage.saveOpenSession(
          tokenQr: t,
          heureEntree: _openSessionHeureEntree,
          seanceLabel: _openSessionSeanceLabel,
        ),
      );
    }
    notifyListeners();
  }

  /// Déclenche immédiatement un pulse de heartbeat (sans attendre le timer).
  /// Utile au retour d'arrière-plan pour rattraper un éventuel délai Doze.
  void pulseHeartbeatNow() {
    if (_heartbeatTimer == null) {
      return;
    }
    scheduleMicrotask(_heartbeatPulse);
  }

  void stopSecureSessionHeartbeat({bool notify = true}) {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _heartbeatTokenQr = null;
    _openSessionHeureEntree = null;
    _openSessionSeanceLabel = null;
    _heartbeatBusy = false;
    _heartbeatGpsMisses = 0;
    heartbeatGpsBlocked = false;
    unawaited(BackgroundKeepalive.instance.stop());
    unawaited(_storage.clearOpenSession());
    if (notify) {
      notifyListeners();
    }
  }

  Future<void> _heartbeatPulse() async {
    if (_heartbeatBusy) {
      return;
    }
    final token = _heartbeatTokenQr;
    final tokenAccess = accessToken;
    final dev = deviceId;
    if (token == null ||
        token.isEmpty ||
        tokenAccess == null ||
        tokenAccess.isEmpty ||
        dev == null ||
        dev.isEmpty) {
      stopSecureSessionHeartbeat();
      return;
    }
    _heartbeatBusy = true;
    try {
      final tel = await _heartbeatTelemetry.capture();
      if (!tel.hasPosition) {
        _heartbeatGpsMisses++;
        if (_heartbeatGpsMisses >= _kGpsMissThreshold && !heartbeatGpsBlocked) {
          heartbeatGpsBlocked = true;
          notifyListeners();
        }
        return;
      }
      // GPS OK : réinitialise le compteur de ratés.
      if (_heartbeatGpsMisses > 0 || heartbeatGpsBlocked) {
        _heartbeatGpsMisses = 0;
        heartbeatGpsBlocked = false;
        notifyListeners();
      }
      final res = await _heartbeatScan.heartbeat(
        baseUrl: baseUrl,
        accessToken: tokenAccess,
        tokenQr: token,
        deviceId: dev,
        latitude: tel.latitude!,
        longitude: tel.longitude!,
        accuracyM: tel.accuracyM,
        batteryLevel: tel.batteryLevel,
        isCharging: tel.isCharging,
        onRefreshToken: _refreshTokenForApi,
      );
      if (res['action']?.toString() == 'SORTIE_AUTO') {
        stopSecureSessionHeartbeat();
      }
    } catch (e, st) {
      final msg = e.toString();
      debugPrint('[qr_badge.session] Heartbeat auto: $e\n$st');
      if (msg.contains('NO_OPEN_SESSION') ||
          msg.contains('Aucune session ouverte') ||
          msg.contains('SESSION_TERMINATED') ||
          msg.contains('TOKEN_EXPIRED') ||
          msg.contains('INVALID_TOKEN')) {
        stopSecureSessionHeartbeat();
      }
    } finally {
      _heartbeatBusy = false;
    }
  }

  Future<void> refreshMobileConfig() async {
    final token = accessToken;
    if (token == null || token.isEmpty) {
      return;
    }
    try {
      final cfg = await _mobileConfig.fetch(
        baseUrl: baseUrl,
        accessToken: token,
        onRefreshToken: _refreshTokenForApi,
      );
      final enabled = cfg['heartbeat_enabled'];
      if (enabled is bool) {
        _remoteHeartbeatEnabled = enabled;
      } else if (enabled != null) {
        _remoteHeartbeatEnabled = enabled.toString().toLowerCase() != 'false';
      }
      final sec = cfg['heartbeat_interval_seconds'];
      if (sec is int) {
        _remoteHeartbeatIntervalSec = sec;
      } else if (sec != null) {
        _remoteHeartbeatIntervalSec = int.tryParse(sec.toString());
      }
      final evalEnabled = cfg['evaluations_enabled'];
      if (evalEnabled is bool) {
        _remoteEvaluationsEnabled = evalEnabled;
      } else if (evalEnabled != null) {
        _remoteEvaluationsEnabled =
            evalEnabled.toString().toLowerCase() != 'false';
      }
      final role = cfg['role']?.toString();
      if (role != null &&
          role.isNotEmpty &&
          user != null &&
          user!['role']?.toString() != role) {
        user = Map<String, dynamic>.from(user!);
        user!['role'] = role;
      }
      if (!_effectiveHeartbeatEnabled && _heartbeatTimer != null) {
        stopSecureSessionHeartbeat();
      }
      notifyListeners();
    } catch (e, st) {
      debugPrint('[qr_badge.session] Config mobile: $e\n$st');
    }
  }

  Future<String?> _refreshTokenForApi() async {
    final ok = await tryRefreshToken();
    return ok ? accessToken : null;
  }

  Future<void> bootstrap() async {
    isBootstrapping = true;
    notifyListeners();
    baseUrl = await _resolveBaseUrlFromEnv();
    AppLog.session('bootstrap démarré baseUrl=$baseUrl');
    accessToken = await _storage.getAccessToken();
    refreshToken = await _storage.getRefreshToken();
    username = await _storage.getUsername();
    deviceId = await _storage.getOrCreateDeviceId();
    mustChangePassword = await _storage.getMustChangePassword();
    isAuthenticated = accessToken != null && accessToken!.isNotEmpty;
    if (isAuthenticated) {
      try {
        final me = await _auth.me(baseUrl: baseUrl, accessToken: accessToken!);
        user = me;
        mustChangePassword = _readMustChangePassword(<String, dynamic>{}, user);
        await _storage.setMustChangePassword(mustChangePassword);
      } catch (_) {
        // Token probablement expiré — tenter un refresh silencieux.
        final refreshed = await tryRefreshToken();
        if (refreshed) {
          try {
            final me = await _auth.me(baseUrl: baseUrl, accessToken: accessToken!);
            user = me;
            mustChangePassword = _readMustChangePassword(<String, dynamic>{}, user);
            await _storage.setMustChangePassword(mustChangePassword);
          } catch (_) {
            // Hors-ligne après refresh : conserver le dernier état local.
          }
        }
      }
      await refreshMobileConfig();
      await refreshPendingEvaluationsCount();
      await _tryRestoreOpenSession();
    }
    isBootstrapping = false;
    AppLog.session(
      'bootstrap terminé auth=$isAuthenticated mustChangePassword=$mustChangePassword',
    );
    notifyListeners();
  }

  Future<void> _tryRestoreOpenSession() async {
    if (!_effectiveHeartbeatEnabled || isSecureHeartbeatRunning) {
      return;
    }
    final token = accessToken;
    if (token == null || token.isEmpty) {
      return;
    }
    final cached = await _storage.loadOpenSession();
    if (cached == null || !cached.isValid) {
      return;
    }

    OpenSessionSnapshot snapshot = cached;
    try {
      final status = await _heartbeatScan.checkSecureStatus(
        baseUrl: baseUrl,
        accessToken: token,
        tokenQr: cached.tokenQr,
        onRefreshToken: _refreshTokenForApi,
      );
      if (!shouldRestoreOpenSession(status)) {
        await _storage.clearOpenSession();
        return;
      }
      snapshot = mergeOpenSessionSnapshot(cached: cached, serverStatus: status);
    } catch (e, st) {
      debugPrint(
        '[qr_badge.session] Reprise session (hors-ligne ou erreur): $e\n$st',
      );
    }

    startSecureSessionHeartbeat(
      snapshot.tokenQr,
      heureEntree: snapshot.heureEntree,
      seanceLabel: snapshot.seanceLabel,
      persist: true,
    );
    _openSessionRestoredOnBoot = true;
  }

  /// Priorité : dart-define > app.env > fallback.
  Future<String> _resolveBaseUrlFromEnv() async {
    final explicit = AppEnv.explicitApiBaseUrl;
    if (explicit != null && explicit.isNotEmpty) {
      return explicit;
    }
    return DevApiDefaults.resolve();
  }

  Future<void> login({
    required String usernameInput,
    required String passwordInput,
  }) async {
    if (_loginInFlight) {
      AppLog.session('login ignoré (déjà en cours)');
      return;
    }
    _loginInFlight = true;
    try {
      await _loginImpl(
        usernameInput: usernameInput,
        passwordInput: passwordInput,
      );
    } finally {
      _loginInFlight = false;
    }
  }

  Future<void> _loginImpl({
    required String usernameInput,
    required String passwordInput,
  }) async {
    final id = deviceId ?? await _storage.getOrCreateDeviceId();
    final info = await DeviceLabel.resolve();
    AppLog.session('login tentative user=${usernameInput.trim()} device=$id');
    late final Map<String, dynamic> payload;
    try {
      payload = await _auth.login(
        baseUrl: baseUrl,
        username: usernameInput.trim(),
        password: passwordInput,
        deviceId: id,
        deviceInfo: info,
      );
    } catch (e, st) {
      AppLog.error('session', 'Connexion échouée: $e', st);
      rethrow;
    }
    final access = payload['access']?.toString() ?? '';
    final refresh = payload['refresh']?.toString() ?? '';
    if (access.isEmpty || refresh.isEmpty) {
      throw Exception('Réponse de connexion invalide.');
    }

    accessToken = access;
    refreshToken = refresh;
    user = payload['user'] is Map<String, dynamic>
        ? payload['user'] as Map<String, dynamic>
        : null;
    username = usernameInput.trim();
    deviceId = id;
    mustChangePassword = _readMustChangePassword(payload, user);

    await _storage.saveTokens(access: access, refresh: refresh);
    await _storage.setUsername(username!);
    await _storage.setMustChangePassword(mustChangePassword);
    isAuthenticated = true;
    await refreshMobileConfig();
    await refreshPendingEvaluationsCount();
    AppLog.session(
      'login OK user=$username mustChangePassword=$mustChangePassword',
    );
    notifyListeners();
  }

  /// Compte les questionnaires publiés non encore soumis (badge menu ⋮).
  Future<void> refreshPendingEvaluationsCount() async {
    if (!evaluationsEnabled) {
      pendingEvaluationsCount = 0;
      notifyListeners();
      return;
    }
    final token = accessToken;
    if (token == null || token.isEmpty) {
      pendingEvaluationsCount = 0;
      notifyListeners();
      return;
    }
    try {
      final list = await _evaluations.mesQuestionnaires(
        baseUrl: baseUrl,
        accessToken: token,
        onRefreshToken: _refreshTokenForApi,
      );
      pendingEvaluationsCount = list.length;
      notifyListeners();
    } catch (e, st) {
      debugPrint('[qr_badge.session] Évaluations en attente: $e\n$st');
    }
  }

  /// Tente de rafraîchir le token d'accès avec le refresh token.
  /// Retourne true si le rafraîchissement a réussi, false sinon.
  Future<bool> tryRefreshToken() async {
    if (_refreshInFlight != null) {
      return _refreshInFlight!;
    }
    _refreshInFlight = _tryRefreshTokenImpl();
    try {
      return await _refreshInFlight!;
    } finally {
      _refreshInFlight = null;
    }
  }

  Future<bool> _tryRefreshTokenImpl() async {
    final rt = refreshToken;
    if (rt == null || rt.isEmpty) {
      return false;
    }
    try {
      final payload = await _auth.refreshToken(baseUrl: baseUrl, refreshToken: rt);
      final newAccess = payload['access']?.toString() ?? '';
      if (newAccess.isEmpty) {
        return false;
      }
      accessToken = newAccess;
      await _storage.saveTokens(access: newAccess, refresh: rt);
      notifyListeners();
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> changePassword({
    required String oldPassword,
    required String newPassword,
  }) async {
    final token = accessToken;
    if (token == null || token.isEmpty) {
      throw Exception('Session expirée. Reconnectez-vous.');
    }
    await _auth.changePassword(
      baseUrl: baseUrl,
      accessToken: token,
      oldPassword: oldPassword,
      newPassword: newPassword,
    );
    mustChangePassword = false;
    if (user != null) {
      user = Map<String, dynamic>.from(user!);
      user!['must_change_password'] = false;
    }
    await _storage.setMustChangePassword(false);
    notifyListeners();
  }

  void requestHistoryRefresh() {
    historyRefreshTick++;
    notifyListeners();
  }

  void applyUserProfile(Map<String, dynamic> data) {
    user = Map<String, dynamic>.from(data);
    notifyListeners();
  }

  Future<void> logout() async {
    AppLog.session('logout user=$username');
    stopSecureSessionHeartbeat();
    _remoteHeartbeatEnabled = null;
    _remoteHeartbeatIntervalSec = null;
    _remoteEvaluationsEnabled = null;
    pendingEvaluationsCount = 0;
    await _storage.clearTokens();
    accessToken = null;
    refreshToken = null;
    user = null;
    mustChangePassword = false;
    isAuthenticated = false;
    notifyListeners();
  }

  bool _readMustChangePassword(
    Map<String, dynamic> payload,
    Map<String, dynamic>? userMap,
  ) {
    final top = payload['must_change_password'];
    if (top is bool) {
      return top;
    }
    if (top is String) {
      return top.toLowerCase() == 'true';
    }
    final fromUser = userMap?['must_change_password'];
    if (fromUser is bool) {
      return fromUser;
    }
    if (fromUser is String) {
      return fromUser.toLowerCase() == 'true';
    }
    return false;
  }

  @override
  void dispose() {
    stopSecureSessionHeartbeat(notify: false);
    super.dispose();
  }
}
