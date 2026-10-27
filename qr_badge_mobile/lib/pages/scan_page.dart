import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:provider/provider.dart';

import '../providers/session_provider.dart';
import '../services/api_client.dart';
import '../services/device_telemetry_service.dart';
import '../services/scan_service.dart';
import '../theme/qr_badge_theme.dart';
import '../utils/app_log.dart';
import '../utils/camera_permission.dart';
import '../utils/confirm_dialog.dart';
import '../utils/location_permission.dart';
import '../utils/user_facing_error.dart';
import '../widgets/scan_frame_overlay.dart';

class ScanPage extends StatefulWidget {
  const ScanPage({super.key, this.isActive = true});

  /// Quand l'onglet Scanner n'est pas sélectionné, la caméra est arrêtée.
  final bool isActive;

  @override
  State<ScanPage> createState() => _ScanPageState();
}

class _ScanPageState extends State<ScanPage> with AutomaticKeepAliveClientMixin {
  final _scanService = ScanService();
  final _telemetry = DeviceTelemetryService();
  late final MobileScannerController _camera;

  String? _tokenQr;
  bool _loadingScan = false;
  String? _error;

  /// Vrai après un badgeage réussi : la caméra est arrêtée jusqu'à ce que
  /// l'utilisateur tape sur « Scanner à nouveau ».
  bool _cameraPaused = false;

  /// Localisation indisponible : la caméra reste fermée jusqu'à activation GPS.
  bool _locationBlocked = false;

  /// Permissions déjà validées lors d'une ouverture précédente de l'onglet.
  bool _locationReadyCached = false;
  bool _cameraPermissionOk = false;

  int _syncGeneration = 0;

  // Informations de position issues de /api/scan/secure/check-status/
  Map<String, dynamic>? _statusInfo;
  DateTime? _statusFetchedAt;
  bool _loadingStatus = false;
  String? _statusError;

  static const _statusCacheTtl = Duration(seconds: 30);

  bool _geofenceBlocksBadge() {
    final info = _statusInfo;
    if (info == null) {
      return false;
    }
    final configured = info['geofence_configured'] == true;
    if (!configured) {
      return false;
    }
    final bool? inside = info['in_geofence'] as bool?;
    final bool? accuracyOk = info['accuracy_ok'] as bool?;
    final num? distance = info['distance_m'] as num?;
    if (accuracyOk == false) {
      return true;
    }
    if (distance == null || inside == null) {
      return true;
    }
    return inside != true;
  }

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _camera = MobileScannerController(autoStart: false);
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncCameraWithTab());
  }

  @override
  void didUpdateWidget(covariant ScanPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.isActive != widget.isActive) {
      _syncCameraWithTab();
    }
  }

  Future<void> _syncCameraWithTab() async {
    if (!mounted) {
      return;
    }
    final generation = ++_syncGeneration;

    bool stale() => !mounted || generation != _syncGeneration;

    if (widget.isActive && !_cameraPaused) {
      var locationOk = _locationReadyCached;
      if (!locationOk) {
        locationOk = await isLocationReady();
        if (stale() || !widget.isActive || _cameraPaused) {
          return;
        }
        _locationReadyCached = locationOk;
        if (locationOk) {
          AppLog.location('scan : localisation OK');
        }
      }
      if (!locationOk) {
        if (_camera.value.isRunning) {
          await _camera.stop();
        }
        if (!mounted || stale() || !widget.isActive || _cameraPaused) {
          return;
        }
        AppLog.location('scan bloqué : localisation indisponible');
        context.read<SessionProvider>().setGpsGranted(false);
        setState(() => _locationBlocked = true);
        return;
      }
      if (!mounted || stale() || !widget.isActive || _cameraPaused) {
        return;
      }
      context.read<SessionProvider>().setGpsGranted(true);
      if (_locationBlocked) {
        setState(() => _locationBlocked = false);
      }
      unawaited(_telemetry.capture());

      if (!_cameraPermissionOk) {
        if (!mounted) {
          return;
        }
        _cameraPermissionOk = await ensureCameraPermission(context);
      }
      if (stale() || !widget.isActive || _cameraPaused) {
        return;
      }
      if (!_cameraPermissionOk) {
        AppLog.scan('caméra refusée');
        return;
      }
      if (_camera.value.isRunning || _camera.value.isStarting) {
        return;
      }
      AppLog.scan('caméra démarrée');
      await _camera.start();
    } else if (_cameraPaused) {
      if (_camera.value.isRunning || _camera.value.isStarting) {
        AppLog.scan('caméra arrêtée (après badgeage)');
        await _camera.stop();
      }
    } else if (_camera.value.isRunning || _camera.value.isStarting) {
      AppLog.scan('caméra en pause (onglet inactif)');
      await _camera.pause();
    }
  }

  Future<void> _enableLocationAndRetry() async {
    final granted = await ensureLocationPermission(context);
    if (!mounted) {
      return;
    }
    context.read<SessionProvider>().setGpsGranted(granted);
    if (granted) {
      _locationReadyCached = true;
      setState(() => _locationBlocked = false);
      await _syncCameraWithTab();
    } else {
      _locationReadyCached = false;
    }
  }

  Widget _buildLocationRequiredPlaceholder() {
    return ColoredBox(
      color: Colors.black87,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.location_off, size: 56, color: Colors.orange.shade300),
              const SizedBox(height: 12),
              Text(
                'Activez la localisation',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                'La localisation est nécessaire pour scanner et badger.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Colors.white70,
                    ),
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _enableLocationAndRetry,
                icon: const Icon(Icons.location_on),
                label: const Text('Activer la localisation'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPausedPlaceholder() {
    return ColoredBox(
      color: Colors.black87,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.check_circle, size: 56, color: AppColors.ciSuccess),
            const SizedBox(height: 12),
            Text(
              'Scan effectué',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _resumeScan,
              icon: const Icon(Icons.qr_code_scanner),
              label: const Text('Scanner à nouveau'),
            ),
          ],
        ),
      ),
    );
  }

  String _scanButtonLabel(bool hasToken) {
    if (_loadingScan) return 'Vérification…';
    if (!hasToken) return 'Scanner un QR code';
    if (_geofenceBlocksBadge()) return 'Zone GPS non conforme';
    final action = _statusInfo?['action_suivante']?.toString();
    if (action == 'SORTIE') return 'Badger la sortie';
    if (action == 'ENTREE') return 'Badger l\u2019entrée';
    return 'Badger';
  }

  Widget _buildBottomSheet() {
    final hasToken = _tokenQr != null && _tokenQr!.isNotEmpty;
    return Material(
      color: AppColors.cardBg,
      borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      elevation: 8,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 10, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.borderColor,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            if (hasToken) ...[
              const SizedBox(height: 12),
              _GeofenceBanner(
                info: _statusInfo,
                loading: _loadingStatus,
                statusError: _statusError,
                onRefresh: () => _refreshStatus(forceRefresh: true),
              ),
            ] else ...[
              const SizedBox(height: 16),
              Text(
                'Cadrez le QR code de la séance.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: AppColors.textSecondary,
                    ),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(
                _error!,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.error,
                  fontSize: 13,
                ),
              ),
            ],
            const SizedBox(height: 14),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: (_loadingScan ||
                        !hasToken ||
                        _geofenceBlocksBadge())
                    ? null
                    : _doScan,
                icon: _loadingScan
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : Icon(hasToken ? Icons.login : Icons.qr_code_scanner),
                label: Text(_scanButtonLabel(hasToken)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _resumeScan() async {
    setState(() {
      _cameraPaused = false;
      _tokenQr = null;
      _statusInfo = null;
      _statusFetchedAt = null;
      _error = null;
    });
    await _syncCameraWithTab();
  }

  Future<String?> _onRefreshToken(SessionProvider session) =>
      session.tryRefreshToken().then((ok) => ok ? session.accessToken : null);

  bool _isStatusCacheFresh() {
    return _statusInfo != null &&
        _statusFetchedAt != null &&
        DateTime.now().difference(_statusFetchedAt!) <= _statusCacheTtl;
  }

  Future<void> _refreshStatus({bool forceRefresh = false}) async {
    final session = context.read<SessionProvider>();
    final token = _tokenQr?.trim() ?? '';
    if (token.isEmpty || session.accessToken == null) {
      return;
    }
    setState(() => _loadingStatus = true);
    try {
      final tel = await _telemetry.capture(forceRefresh: forceRefresh);
      final statut = await _scanService.checkSecureStatus(
        baseUrl: session.baseUrl,
        accessToken: session.accessToken!,
        tokenQr: token,
        latitude: tel.latitude,
        longitude: tel.longitude,
        accuracyM: tel.accuracyM,
        onRefreshToken: () => _onRefreshToken(session),
      );
      if (mounted) {
        setState(() {
          _statusInfo = statut;
          _statusFetchedAt = DateTime.now();
          _statusError = null;
        });
      }
    } catch (e, st) {
      logErrorForDebug('scan.status', e, st);
      if (mounted) {
        setState(() {
          _statusError = userFacingErrorMessage(
            e,
            context: UserErrorContext.badgeStatus,
          );
        });
      }
    } finally {
      if (mounted) {
        setState(() => _loadingStatus = false);
      }
    }
  }

  String _extractToken(String raw) {
    final parsed = Uri.tryParse(raw.trim());
    if (parsed != null && parsed.queryParameters.containsKey('token')) {
      return parsed.queryParameters['token'] ?? raw.trim();
    }
    return raw.trim();
  }

  Future<void> _doScan() async {
    final session = context.read<SessionProvider>();
    final token = _tokenQr?.trim() ?? '';
    if (token.isEmpty) {
      setState(() => _error = 'Scannez d’abord le QR code de la séance.');
      return;
    }
    if (session.accessToken == null || session.deviceId == null) {
      setState(() => _error = 'Session invalide, reconnectez-vous.');
      return;
    }
    // 1) Vérifier auprès du serveur si le prochain badge est une ENTREE ou une SORTIE.
    setState(() {
      _loadingScan = true;
      _error = null;
    });
    String? actionSuivante;
    String? heureEntree;
    String? seanceLabel;
    try {
      final Map<String, dynamic> statut;
      if (_isStatusCacheFresh()) {
        AppLog.scan('réutilisation du statut serveur en cache');
        statut = _statusInfo!;
      } else {
        final telPre = await _telemetry.capture();
        statut = await _scanService.checkSecureStatus(
          baseUrl: session.baseUrl,
          accessToken: session.accessToken!,
          tokenQr: token,
          latitude: telPre.latitude,
          longitude: telPre.longitude,
          accuracyM: telPre.accuracyM,
          onRefreshToken: () => _onRefreshToken(session),
        );
        if (mounted) {
          setState(() {
            _statusInfo = statut;
            _statusFetchedAt = DateTime.now();
          });
        }
      }
      actionSuivante = statut['action_suivante']?.toString();
      heureEntree = statut['heure_entree']?.toString();
      seanceLabel = statut['seance_intitule']?.toString();
      if (statut['statut']?.toString() == 'TERMINE') {
        setState(() {
          _loadingScan = false;
          _error =
              'Vous avez déjà pointé (entrée et sortie) pour cette séance.';
        });
        return;
      }
    } catch (e, st) {
      logErrorForDebug('scan.check', e, st);
      setState(() => _loadingScan = false);
      if (mounted) {
        await showDialog<void>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: Text(userFacingErrorTitle(
              e,
              context: UserErrorContext.badgeStatus,
            )),
            content: Text(
              userFacingErrorMessage(
                e,
                context: UserErrorContext.badgeStatus,
              ),
            ),
            actions: [
              FilledButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('OK'),
              ),
            ],
          ),
        );
      }
      return;
    }
    if (!mounted) {
      return;
    }
    setState(() => _loadingScan = false);

    final willExit = actionSuivante == 'SORTIE';
    final isExit = willExit;
    final titre = isExit ? 'Confirmer la sortie' : 'Confirmer l\u2019entrée';
    final bouton =
        isExit ? 'Badger la sortie' : 'Badger l\u2019entrée';
    final contexteSeance =
        (seanceLabel != null && seanceLabel.isNotEmpty) ? ' « $seanceLabel »' : '';
    final message = isExit
        ? 'Vous êtes actuellement en salle'
            '${heureEntree != null && heureEntree.isNotEmpty ? ' depuis $heureEntree' : ''}'
            '$contexteSeance.\n'
            'Voulez-vous enregistrer votre sortie ?'
        : 'Voulez-vous enregistrer votre entrée$contexteSeance ?';
    final ok = await confirm(
      context,
      title: titre,
      message: message,
      confirmLabel: bouton,
      destructive: isExit,
    );
    if (!ok || !mounted) {
      return;
    }
    setState(() {
      _loadingScan = true;
      _error = null;
    });
    try {
      final tel = await _telemetry.capture();
      final res = await _scanService.secureScan(
        baseUrl: session.baseUrl,
        accessToken: session.accessToken!,
        tokenQr: token,
        deviceId: session.deviceId!,
        latitude: tel.latitude,
        longitude: tel.longitude,
        accuracyM: tel.accuracyM,
        batteryLevel: tel.batteryLevel,
        isCharging: tel.isCharging,
        onRefreshToken: () => _onRefreshToken(session),
      );
      final action = res['action']?.toString();
      if (action == 'ENTREE') {
        unawaited(session.refreshMobileConfig());
        session.startSecureSessionHeartbeat(
          token,
          heureEntree:
              res['heure_entree']?.toString() ?? heureEntree,
          seanceLabel:
              res['seance_intitule']?.toString() ?? seanceLabel,
        );
      } else if (action == 'SORTIE' || action == 'SORTIE_AUTO') {
        session.stopSecureSessionHeartbeat();
      }
      session.requestHistoryRefresh();
      final confirmation = _confirmationMessage(action);
      // Caméra arrêtée tant que l'utilisateur n'a pas demandé un nouveau scan.
      await _camera.stop();
      if (!mounted) return;
      setState(() => _cameraPaused = true);
      if (mounted) {
        final isExit = action == 'SORTIE' || action == 'SORTIE_AUTO';
        await showDialog<void>(
          context: context,
          builder: (ctx) => AlertDialog(
            icon: Icon(
              Icons.check_circle,
              color: isExit ? Colors.red.shade700 : AppColors.ciSuccessDark,
              size: 48,
            ),
            title: const Text('Scan effectué'),
            content: Text(confirmation),
            actions: [
              FilledButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('OK'),
              ),
            ],
          ),
        );
      }
    } on ApiBusinessException catch (e) {
      setState(() => _error = userFacingErrorMessage(
            e,
            context: UserErrorContext.badgeScan,
          ));
    } catch (e, st) {
      logErrorForDebug('scan.badge', e, st);
      setState(
        () => _error = userFacingErrorMessage(
          e,
          context: UserErrorContext.badgeScan,
        ),
      );
    } finally {
      if (mounted) {
        setState(() => _loadingScan = false);
      }
    }
  }

  String _confirmationMessage(String? action) {
    switch (action) {
      case 'ENTREE':
        return 'Entrée enregistrée. Le suivi de présence est actif.';
      case 'SORTIE':
        return 'Sortie enregistrée. Le suivi de présence est arrêté.';
      case 'SORTIE_AUTO':
        return 'Sortie automatique enregistrée (session fermée).';
      default:
        return 'Badgeage enregistré.';
    }
  }

  @override
  void dispose() {
    _camera.dispose();
    super.dispose();
  }

  void _onQrDetected(String code) {
    final t = _extractToken(code);
    if (t.isEmpty || t == _tokenQr) {
      return;
    }
    HapticFeedback.mediumImpact();
    AppLog.scan('QR détecté tokenLen=${t.length}');
    setState(() {
      _tokenQr = t;
      _error = null;
      _statusInfo = null;
      _statusFetchedAt = null;
      _statusError = null;
    });
    _refreshStatus();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: Stack(
            fit: StackFit.expand,
            children: [
              ColoredBox(
                color: Colors.black,
                child: _cameraPaused
                    ? _buildPausedPlaceholder()
                    : _locationBlocked
                        ? _buildLocationRequiredPlaceholder()
                        : MobileScanner(
                        controller: _camera,
                        onDetect: (capture) {
                          if (!widget.isActive || _cameraPaused) {
                            return;
                          }
                          final code = capture.barcodes.first.rawValue;
                          if (code == null || code.isEmpty) {
                            return;
                          }
                          _onQrDetected(code);
                        },
                      ),
              ),
              if (!_cameraPaused && !_locationBlocked) const ScanFrameOverlay(),
            ],
          ),
        ),
        _buildBottomSheet(),
      ],
    );
  }
}

class _GeofenceBanner extends StatelessWidget {
  const _GeofenceBanner({
    required this.info,
    required this.loading,
    required this.onRefresh,
    this.statusError,
  });

  final Map<String, dynamic>? info;
  final bool loading;
  final String? statusError;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    if (statusError != null && statusError!.isNotEmpty) {
      return _wrap(
        context: context,
        color: Colors.red.withValues(alpha: 0.10),
        border: AppColors.ciDanger,
        icon: Icons.cloud_off_outlined,
        iconColor: AppColors.ciDanger,
        title: statusError!,
        trailing: _refreshBtn(),
      );
    }
    if (info == null) {
      return _wrap(
        context: context,
        color: Colors.grey.withValues(alpha: 0.12),
        border: Colors.grey.shade400,
        icon: Icons.my_location,
        iconColor: AppColors.textMuted,
        title: loading ? 'Vérification…' : 'Position en attente',
      );
    }

    final bool configured = info!['geofence_configured'] == true;
    if (!configured) {
      return _wrap(
        context: context,
        color: AppColors.ciBlue.withValues(alpha: 0.10),
        border: AppColors.ciBlue,
        icon: Icons.info_outline,
        iconColor: AppColors.ciBlue,
        title: 'Sans contrôle GPS',
      );
    }

    final num? distance = info!['distance_m'] as num?;
    final bool? inside = info!['in_geofence'] as bool?;
    final bool? accuracyOk = info!['accuracy_ok'] as bool?;

    if (distance == null || inside == null) {
      return _wrap(
        context: context,
        color: Colors.orange.withValues(alpha: 0.12),
        border: Colors.orange,
        icon: Icons.location_searching,
        iconColor: Colors.orange.shade800,
        title: 'GPS indisponible',
        trailing: _refreshBtn(),
      );
    }

    if (accuracyOk == false) {
      return _wrap(
        context: context,
        color: Colors.orange.withValues(alpha: 0.15),
        border: Colors.orange,
        icon: Icons.gps_not_fixed,
        iconColor: Colors.orange.shade800,
        title: 'Signal GPS imprécis',
        trailing: _refreshBtn(),
      );
    }

    if (inside) {
      return _wrap(
        context: context,
        color: AppColors.ciSuccess.withValues(alpha: 0.15),
        border: AppColors.ciSuccessDark,
        icon: Icons.gps_fixed,
        iconColor: AppColors.ciSuccessDark,
        title: 'Dans la zone de badgeage',
        trailing: _refreshBtn(),
      );
    }

    return _wrap(
      context: context,
      color: Colors.red.withValues(alpha: 0.12),
      border: Colors.red,
      icon: Icons.wrong_location,
      iconColor: Colors.red.shade700,
      title: 'Hors zone',
      trailing: _refreshBtn(),
    );
  }

  Widget _refreshBtn() {
    return IconButton(
      tooltip: 'Recalculer la position',
      icon: loading
          ? const SizedBox(
              height: 18,
              width: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.refresh, size: 20),
      onPressed: loading ? null : onRefresh,
    );
  }

  Widget _wrap({
    required BuildContext context,
    required Color color,
    required Color border,
    required IconData icon,
    required Color iconColor,
    required String title,
    String? subtitle,
    Widget? trailing,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Icon(icon, color: iconColor, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: AppColors.textMuted,
                        ),
                  ),
                ],
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}
