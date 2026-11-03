Jeu d'icônes embarqué : Material Symbols Outlined (Google), Apache 2.0.

Ces deux fichiers sont volontairement versionnés (ils sont servis par
`staticfiles`) : l'administration ne doit dépendre d'aucun réseau externe.

  material-symbols-outlined-subset.woff2
      Sous-ensemble du fichier officiel `material-symbols-outlined.woff2`
      (paquet npm `material-symbols` 0.48.2), réduit par pyftsubset aux
      seuls glyphes réellement utilisés par l'admin, ligatures `rlig`/`rclt`
      conservées (les icônes sont écrites en toutes lettres dans le HTML :
      <span class="material-symbols-outlined">chevron_right</span>).
      6660 glyphes d'origine -> 38. Poids : 35 Ko au lieu de 3,9 Mo.

  inter-latin-wght.woff2
      Inter variable (axe `wght`), couverture latine — fichier
      `inter-latin-wght-normal.woff2` du paquet npm `@fontsource-variable/inter`
      5.3.0. Contient les diacritiques français (é è à ç ô û î ï œ « » —).

Glyphes conservés dans le sous-ensemble d'icônes :

  - add
  - admin_panel_settings
  - apartment
  - arrow_back
  - bar_chart
  - category
  - chevron_right
  - close
  - dashboard
  - devices
  - event
  - fact_check
  - filter_list
  - fingerprint
  - groups
  - history
  - inventory_2
  - label
  - layers
  - library_books
  - lock
  - logout
  - manage_accounts
  - menu
  - menu_book
  - military_tech
  - mobile
  - monitoring
  - open_in_new
  - payments
  - person
  - pie_chart
  - place
  - qr_code_2
  - school
  - search
  - settings
  - stacked_bar_chart

Pour ajouter une icône : ajouter son nom ci-dessus, puis régénérer le
sous-ensemble (recette dans docs/getinjs/RAPPORT-FINAL-GETINJS.md) ou
changer de fichier pour la version complète.