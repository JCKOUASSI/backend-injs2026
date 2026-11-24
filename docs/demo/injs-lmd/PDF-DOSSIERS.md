# Dossiers PDF — parcours étudiant et génération des emplois du temps

Trois documents autonomes, rédigés d'après le code du dépôt (application `backend/injs2026`), avec cas
pratiques, tableaux de décision, codes de refus et limites mesurées.

| Fichier | Contenu | Pages |
|---|---|---|
| `pdf/01-Parcours-academique-etudiant.pdf` | Candidature → admission → inscription administrative et pédagogique → groupe → EDT et présences → évaluations → résultats → jury → diplôme et registre | 13 |
| `pdf/02-Generation-manuelle-des-emplois-du-temps.pdf` | Référentiel horaire, brouillon, pose et déplacement des séances, contrôles de conflits, workflow de statuts, publication, versions et sorties | 11 |
| `pdf/03-Generation-automatique-des-emplois-du-temps.pdf` | Quatre niveaux de moteurs, contraintes C1–C10, génération coordonnée, génération annuelle, campagnes, limites mesurées | 11 |

Le document `../Parcours-et-generation-EDT.md` reste la version Markdown de référence, plus détaillée sur les
routes et les fichiers.

## Sources et reconstruction

Les sources sont dans `pdf-src/` : trois fichiers Markdown avec un en-tête `---` (titre, sous-titre, objet,
sommaire) et un vocabulaire restreint — titres, paragraphes, listes, tableaux `|`, blocs de code, et quatre
encadrés `cas::`, `note::`, `alerte::`, `limite::`.

```bash
# dépendances de rendu (hors dépôt applicatif)
python3 -m venv /tmp/pdfenv
/tmp/pdfenv/bin/pip install reportlab

cd docs/demo/injs-lmd
for f in pdf-src/0*.md; do
  /tmp/pdfenv/bin/python pdf-src/render_pdf.py "$f" "pdf/$(basename "$f" .md).pdf"
done
```

`render_pdf.py` utilise la police DejaVu Sans (accentuation française, flèches, symboles métier), une charte
INJS (bleu #0D2B45), un en-tête et un pied de page paginés, et n'a aucune dépendance réseau ni LaTeX.
