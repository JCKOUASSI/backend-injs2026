#!/usr/bin/env bash
# Retourne l'UDID du premier iPhone physique connecté (sortie vide si absent).
pick_ios_device_id() {
  flutter devices --machine 2>/dev/null | python3 -c '
import json, sys
try:
    devices = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)
for d in devices:
    if (
        d.get("targetPlatform") == "ios"
        and not d.get("emulator")
        and d.get("isSupported")
    ):
        print(d["id"])
        break
'
}
