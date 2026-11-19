# Reconstitution locale du jeu démo d'après la capture Vue d'ensemble

Périmètre : **base SQLite de l'aperçu Arena uniquement** (`backend/db.sqlite3`), pas le serveur `injs.badge-qr-code.pro`. La capture du 17 novembre 2026 montre 5 016 inscriptions, 30 candidatures, 93 enseignants, 779 cours, 32 évaluations, 16 jurys, 60 diplômes, 65,1 % de réussite, 1,2 % de diplômation et 177 groupes sans affectation pédagogique. Elle ne contient ni les dossiers individuels ni les règles de répartition détaillées : les profils ajoutés sont **fictifs, étiquetés et non une copie de la base du site**.

## Préservation

Avant écriture : copie cohérente et `PRAGMA quick_check = ok` de la base actuelle dans `backups/avant-complement-dashboard-20261117-094016/db.sqlite3` (ignoré par Git ; permissions privées). Empreinte conservée dans le même dossier et vérifiée avec `sha256sum -c SHA256SUMS.txt`. Aucun profil, groupe ni inscription préexistant supprimé ou réécrit. La sauvegarde du 15 novembre (`backups/apercu-20261115-152752/`) reste intacte. Aucune donnée de production consultée ni modifiée. Ne jamais commiter ou publier ces bases : elles contiennent des comptes de démonstration.

## Méthode

La commande `completer_capture_dashboard_demo` refuse toute base autre que le SQLite local du profil `arena.settings_sandbox`, exige le chemin exact, la confirmation explicite et l'état initial attendu. Elle réutilise le générateur déterministe des inscriptions démo existantes avec des suffixes distincts pour **ajouter** 1 500 étudiants fictifs à la cohorte initiale de 3 500, ainsi que leurs candidats, dossiers et inscriptions VALIDEE. Elle attribue chacun à une section active sans dépasser la capacité, en préservant les affectations anciennes ; des sections additionnelles répartissent les nouveaux étudiants pour retrouver les 177 groupes sans charge pédagogique de la capture. Elle ajoute 26 profils enseignants explicitement nommés « ENSEIGNANT DÉMO », sans mot de passe ni compte de connexion. Une transaction annule tout si les contrôles échouent. La commande de seed historique refuse désormais de régénérer par erreur une cohorte 5 000 homogène par-dessus ce complément ; le script de reconstruction de l'aperçu préserve cette cohorte.

## Contrôles avant / après (base de l'aperçu)

| Indicateur | Avant | Après | Capture |
| --- | ---: | ---: | ---: |
| Inscriptions validées de l'année | 3 516 | **5 016** | 5 016 |
| Cohorte étudiante fictive | 3 500 | **5 000** (2 500 femmes, 2 500 hommes) | non détaillée |
| Dossiers étudiants | 3 527 | **5 027** | 5 027 (jauge) |
| Enseignants | 67 | **93** | 93 |
| Groupes sans charge pédagogique | 130 | **177** | 177 |
| Candidatures / cours / évaluations / jurys / diplômes | 30 / 779 / 32 / 16 / 60 | **inchangés** | 30 / 779 / 32 / 16 / 60 |
| Réussite / diplômation | 65,1 % / 1,7 % | **65,1 % / 1,2 %** | 65,1 % / 1,2 % |

Les répartitions détaillées par formation ne peuvent pas être reconstituées *exactement* d'une capture : les 1 500 étudiants ajoutés sont répartis selon le générateur du dépôt. Les 93 enseignants incluent 26 profils fictifs supplémentaires sans charge, non des personnes du site public. Il ne faut pas interpréter cette correspondance de KPI comme preuve d'égalité des deux bases.

Essai préalable sur copie temporaire : 5 016 inscrits, 93 enseignants, 181 groupes dont 177 sans charge, aucune surcapacité ; seconde exécution : aucune écriture. Sur la base locale mise à jour, neuf endpoints dashboard authentifiés (`overview`, `presences`, `scolarite`, `pedagogie`, `finances`, `examens`, `logistique`, `etudiant`, `enseignant`) répondent **HTTP 200** ; `manage.py check` OK, `migrate --plan` aucune opération, test de régression ciblé de la génération **2/2 OK**. Les tests ne sont pas une validation de la production ou de la CI distante.
