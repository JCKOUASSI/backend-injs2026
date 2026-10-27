# U0 — Restauration de l'état initial

> U0 est **strictement additive** (règle R2) : aucune migration, aucune
> modification de schéma, aucun changement de comportement du produit.
> Le repli est donc un simple revert de code, sans manipulation de base.
> Date : 2026-09-13.

## 1. Ce que U0 ajoute

Fichiers ajoutés :

```
backend/authentication/management/commands/inventaire_habilitation.py
backend/authentication/management/commands/creer_comptes_temoins.py
backend/authentication/management/commands/fumee_authentification.py
backend/authentication/tests_caracterisation/__init__.py
backend/authentication/tests_caracterisation/test_01_referentiel_roles.py
backend/authentication/tests_caracterisation/test_02_synchronisation_groupes.py
backend/authentication/tests_caracterisation/test_03_canaux_connexion.py
backend/authentication/tests_caracterisation/test_04_permissions_effectives.py
backend/authentication/tests_caracterisation/test_05_cloisonnement_secretariats.py
backend/authentication/tests_caracterisation/test_06_endpoints_reference.py
docs/curp/00-references-initiales.md
docs/curp/00-restauration.md
docs/curp/01-etat-des-droits.md
docs/curp/02-inventaire-comptes.md
docs/curp/inventaires/2026-09-13-etat-des-droits.md
docs/curp/inventaires/2026-09-13-inventaire-comptes.md
```

Fichier modifié (une seule étape CI ajoutée, aucune étape existante
changée) :

```
.github/workflows/ci.yml
```

Aucun fichier de l'application (modèles, vues, permissions, serializers,
URLs, front, mobile) n'est modifié.

## 2. Restauration du code

Le commit U0 est identifié par son message (`U0 … [CURP]`). Pour l'annuler
tout en conservant l'historique :

```bash
git revert <commit-U0>
```

Pour un abandon pur avant toute fusion (branche de travail) :

```bash
# À n'utiliser que si le commit n'a pas été partagé :
git revert --no-commit <commit-U0> ; # ou reset selon la situation
```

Après revert, les commandes, le paquet de tests et l'étape CI disparaissent ;
le comportement du produit redevient rigoureusement celui d'avant U0.

## 3. Restauration de la base de démonstration/recette

Les outils U0 ne créent des données que lorsqu'on les invoque
explicitement (`creer_comptes_temoins`, ou `fumee_authentification --creer`).

### 3.1 En intégration continue

La base de CI est éphémère (service PostgreSQL puis `migrate`) : aucune
action, les données témoins disparaissent avec le conteneur.

### 3.2 Base de démonstration locale (SQLite sandbox)

La façon la plus simple de revenir à une base propre est de la
réinitialiser puis de remonter le compte d'administration :

```bash
cd backend
rm -f db.sqlite3
USE_SQLITE=1 python manage.py migrate --noinput
USE_SQLITE=1 DJANGO_SUPERUSER_USERNAME=admin \
  DJANGO_SUPERUSER_EMAIL=admin@recette.injs.local \
  DJANGO_SUPERUSER_PASSWORD='<mot de passe fort>' \
  python manage.py migrate  # le super-utilisateur est créé au post-migrate
```

(La procédure de bootstrap de la sandbox reste
`bash arena/bootstrap.sh`, qui applique ces étapes.)

### 3.3 Retirer uniquement les comptes témoins (sans toucher aux autres données)

Conformément à la règle **S5 (désactivation, jamais de suppression
physique depuis l'application)**, la méthode de repli sur une base que l'on
souhaite conserver est la **désactivation** :

```bash
cd backend
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
User = get_user_model()
# Désactive les comptes témoins (aucun compte réel n'est concerné) :
User.objects.filter(username__startswith='temoin_').update(is_active=False)
```

Les secrétariats `SECR-DEMO-A/B`, participants `TEMOIN-PART-A/B` ne sont
référencés que par ces comptes ; sur une base jetable, la réinitialisation
du 3.2 est préférée à toute suppression. Aucun ordre SQL de suppression
n'est fourni dans le dépôt.

## 4. Aucun retour arrière de schéma nécessaire

U0 n'introduit **aucune migration**. Le module applicatif (U1) utilisera
plus tard un profil `OneToOne` additif avec des migrations réversibles ;
les présentes documentations ne décendent que du périmètre U0.

## 5. Procédure de secours hors application (règle S8)

En cas de perte totale d'accès administrateur, indépendante du module
utilisateurs, deux issues hors application existent déjà :

1. au `migrate`, si les variables `DJANGO_SUPERUSER_USERNAME`,
   `DJANGO_SUPERUSER_EMAIL` et `DJANGO_SUPERUSER_PASSWORD` sont présentes,
   un super-utilisateur est créé automatiquement (commande idempotente
   `create_superuser_from_env`, voir `authentication/apps.py`) ;
2. par la CLI, sur le serveur :
   ```bash
   python manage.py createsuperuser
   ```

Ces issues sont les garanties « brise-glace » des garde-fous S6 (pas
d'auto-élévation) et S7 (au moins deux administrateurs actifs) : elles ne
passent pas par l'interface dont elles restaurent précisément l'accès.
