# Audit lecture seule des volumes de la base publique — Terminal macOS

**Aucune écriture en base, aucun import et aucun déploiement requis.** Ce script est exécuté dans le conteneur backend déjà en service, avec son environnement de connexion à la base réelle. Il ne redémarre ni backend, ni NPM. L'assistant n'a pas exécuté ces commandes sur votre Mac/VPS. Ne transmettez aucun secret.

1. Télécharger depuis Arena le fichier `backend/scolarite/volumes_audit.py` en `~/Downloads/volumes_audit.py` sur le Mac. Vérifier qu'il s'agit du fichier et non d'une page HTML.
2. Coller ces commandes dans le **Terminal macOS** :

```sh
AUDIT="$HOME/Downloads/volumes_audit.py"
RAPPORT="$HOME/Downloads/audit-volumes-PRODUCTION-2026-2027.json"
test -s "$AUDIT" || { echo 'STOP : script audit absent'; exit 1; }
grep -q '^def rapprocher(annee_libelle):' "$AUDIT" || { echo 'STOP : mauvais fichier'; exit 1; }
{
  printf '%s\n' 'import os' 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")' 'import django' 'django.setup()'
  cat "$AUDIT"
  printf '%s\n' 'import json' 'print(json.dumps(rapprocher("2026-2027"), ensure_ascii=False, indent=2))'
} | ssh -o StrictHostKeyChecking=yes almalinux@152.228.233.123 \
  'docker exec -i injs-getfix-backend-1 python -' > "$RAPPORT" || exit 1
python3 -m json.tool "$RAPPORT" >/dev/null || { echo 'STOP : rapport incomplet'; exit 1; }
python3 - "$RAPPORT" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding='utf-8'))
print('Année :', r['annee_cible'])
print('Toutes années :', r['inventaire_toutes_annees']['maquettes'], 'maquettes ;',
      r['inventaire_toutes_annees']['ecues'], 'ECUE ;',
      r['inventaire_toutes_annees']['ecues_avec_volume_positif'], 'ECUE volumées')
print('Année cible :', len(r['ecues_cible']), 'ECUE ; répartition :', r['comptes_cible'])
print('Rapport détaillé :', sys.argv[1])
PY
```

**STOP si la commande SSH échoue ou si le rapport n'est pas du JSON valide.** Le résultat `audit-volumes-LOCAL-2026-2027.json` fourni séparément est celui de la base locale du dépôt, **pas** celui de ce conteneur. Transmettre le fichier `audit-volumes-PRODUCTION-2026-2027.json` via la conversation Arena pour une analyse précise des rapprochements. Le rapport ne contient pas d'inscriptions ni d'identifiants étudiants, mais peut contenir des libellés pédagogiques internes : vérifier la politique de partage INJS.
