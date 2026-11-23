import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../utils/open_session_recovery.dart';

/// Persistance locale.
///
/// • Tokens JWT (access + refresh) → [FlutterSecureStorage] (Keystore Android /
///   Keychain iOS) : chiffrés au repos, inaccessibles sans déverrouillage de l'appareil.
/// • Données non sensibles (device_id, username, flags) → [SharedPreferences].
class StorageService {
  static const _kDeviceId = 'device_id';
  static const _kUsername = 'username';
  static const _kMustChangePassword = 'must_change_password';

  static const _kAccessToken = 'access_token';
  static const _kRefreshToken = 'refresh_token';

  static const _kOpenSessionToken = 'open_session_token_qr';
  static const _kOpenSessionHeure = 'open_session_heure_entree';
  static const _kOpenSessionSeance = 'open_session_seance_label';

  static const _secure = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  // ── Tokens (stockage sécurisé) ──────────────────────────────────────────

  Future<String?> getAccessToken() => _secure.read(key: _kAccessToken);

  Future<String?> getRefreshToken() => _secure.read(key: _kRefreshToken);

  Future<void> saveTokens({
    required String access,
    required String refresh,
  }) async {
    await _secure.write(key: _kAccessToken, value: access);
    await _secure.write(key: _kRefreshToken, value: refresh);
  }

  Future<void> clearTokens() async {
    await _secure.delete(key: _kAccessToken);
    await _secure.delete(key: _kRefreshToken);
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kMustChangePassword);
  }

  // ── Données non sensibles (SharedPreferences) ───────────────────────────

  Future<bool> getMustChangePassword() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_kMustChangePassword) ?? false;
  }

  Future<void> setMustChangePassword(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_kMustChangePassword, value);
  }

  Future<String> getOrCreateDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    var existing = prefs.getString(_kDeviceId);
    if (kIsWeb) {
      // Préfixe dédié : le backend n’applique pas les sanctions MOBILE_HEARTBEAT_* (pas de heartbeat fiable en arrière-plan navigateur).
      if (existing != null &&
          existing.isNotEmpty &&
          existing.startsWith('MOBILE_')) {
        final migrated =
            'FLUTTER_PWA_${DateTime.now().millisecondsSinceEpoch}';
        await prefs.setString(_kDeviceId, migrated);
        return migrated;
      }
      if (existing != null && existing.isNotEmpty) {
        return existing;
      }
      final generated =
          'FLUTTER_PWA_${DateTime.now().millisecondsSinceEpoch}';
      await prefs.setString(_kDeviceId, generated);
      return generated;
    }
    if (existing != null && existing.isNotEmpty) {
      return existing;
    }
    final generated = 'MOBILE_${DateTime.now().millisecondsSinceEpoch}';
    await prefs.setString(_kDeviceId, generated);
    return generated;
  }

  Future<String?> getUsername() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kUsername);
  }

  Future<void> setUsername(String username) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kUsername, username);
  }

  Future<void> saveOpenSession({
    required String tokenQr,
    String? heureEntree,
    String? seanceLabel,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kOpenSessionToken, tokenQr.trim());
    final heure = heureEntree?.trim();
    final seance = seanceLabel?.trim();
    if (heure != null && heure.isNotEmpty) {
      await prefs.setString(_kOpenSessionHeure, heure);
    } else {
      await prefs.remove(_kOpenSessionHeure);
    }
    if (seance != null && seance.isNotEmpty) {
      await prefs.setString(_kOpenSessionSeance, seance);
    } else {
      await prefs.remove(_kOpenSessionSeance);
    }
  }

  Future<OpenSessionSnapshot?> loadOpenSession() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString(_kOpenSessionToken)?.trim();
    if (token == null || token.isEmpty) {
      return null;
    }
    return OpenSessionSnapshot(
      tokenQr: token,
      heureEntree: prefs.getString(_kOpenSessionHeure),
      seanceLabel: prefs.getString(_kOpenSessionSeance),
    );
  }

  Future<void> clearOpenSession() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kOpenSessionToken);
    await prefs.remove(_kOpenSessionHeure);
    await prefs.remove(_kOpenSessionSeance);
  }

}
