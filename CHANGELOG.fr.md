# Journal des modifications

## 1.2.0

### Prérequis (changement cassant)
- **Home Assistant 2026.3.0 ou plus récent** (`hacs.json`), c'est-à-dire la première version
  livrée avec Python 3.14. La suite de tests passe sur 2026.3.0 et 2026.9.3.

### Ajouté
- Capteur de diagnostic **Redox Brut (mV)**, à côté du pH brut existant : la valeur de la sonde
  *avant* tout décalage, pour calibrer sur une solution étalon.

### Supprimé (changement cassant)
- Capteurs **Chlore Libre Estimé** et **Chlore Actif (HOCl)**. Pourquoi :
  - **Le Redox n'est pas une concentration.** À taux de chlore égal, il varie avec le pH, la
    température, le stabilisant (CYA), les autres oxydants et le vieillissement de la sonde ; une
    valeur en mV ne peut pas devenir des ppm.
  - **La conversion pouvait afficher du chlore là où il n'y en a pas.** La formule était plafonnée
    à 415 mV, donc tout Redox inférieur donnait le même résultat : à pH 7,2 sans stabilisant,
    **100 mV** (aucun oxydant) affichait quand même 0,1 ppm de chlore libre et 0,07 mg/L de HOCl.
  - **Corrections du CYA empilées et non validées.** Le chlore libre était multiplié par CYA/40 et
    le HOCl divisé par un second facteur CYA : à Redox/pH/température identiques, le HOCl passait
    de 0,66 mg/L (sans stabilisant) à 0,02 mg/L (40 mg/L), soit ×33, sans donnée de mesure à l'appui.
  - **La documentation promettait plus que le code** (modèle de « Machine Learning »), ce qui
    donnait une fausse impression de précision.
  - **Le chlore est une mesure de sécurité** : une valeur fausse mais qui a l'air précise est pire
    que pas de valeur.
  - Utilisez la valeur Redox avec vos propres seuils, et un kit de test pour le chlore réel.
- Les entités orphelines sont supprimées automatiquement à la mise à jour (version mineure de
  l'entrée 1.1 → 1.2 : un retour en arrière reste possible). L'entité CyA, le sélecteur de
  traitement (chlore/brome) et leurs options sont **conservés** mais n'influencent plus aucune
  valeur calculée.

### Modifié (même comportement que Blue Connect Local)
- Le **capteur de signal Bluetooth (RSSI)** devient *indisponible* dès que le Flipr est hors de portée
  et redevient disponible à son retour. Avant, il affichait indéfiniment sa dernière valeur.
- Le bouton **« Nouvelle analyse »** tente désormais la connexion même sans annonce récente (avant,
  il était refusé avec un avertissement). Les analyses planifiées restent ignorées hors de portée.
  Une analyse forcée est maintenant consommée par le cycle qui la reçoit, quelle qu'en soit l'issue :
  elle ne peut plus rester armée et contourner la pause plus tard.

### Corrigé
- Les trames BLE invalides étaient retentées indéfiniment : `retry_count` était remis à zéro avant
  le décodage de la trame, donc les tentatives ne s'épuisaient jamais et l'état « injoignable »
  n'était jamais atteint.
- Le CyA saisi sur l'entité revenait à l'ancienne valeur des options dès qu'un autre réglage
  (ex. le type de traitement) changeait.
- `async_shutdown` du coordinateur n'appelait pas l'implémentation parente (rafraîchissement
  planifié et debouncer laissés actifs après le déchargement).
- Les erreurs de calibration du flux d'options n'avaient aucun texte traduit, dans aucune langue.
- `nl.json` et `pt-br.json` contenaient une clé `"sections"` en double, qui masquait les libellés
  des sections général / calibration dans le formulaire d'options.
- `validate_calibration` levait une exception sur une valeur ORP / décalage / CyA non numérique.
- Les données restaurées au démarrage ne réinjectent plus les valeurs de chlore supprimées.

### Durci
- Une calibration pH dégénérée retombe sur la calibration d'usine au lieu de renvoyer 7,0 en silence.
- Un pH calculé hors de 0–14 devient *inconnu* au lieu d'être affiché.
- L'indice de Langelier et le pH d'équilibre refusent NaN et l'infini ; de même pour la conversion mV/pH de la calibration.

### Interne
- Code découpé en modules à responsabilité unique : `coordinator.py` (cycle BLE, ~900 lignes qui
  étaient dans `__init__.py`), `frame.py` (décodage des trames), `model.py` (modèle d'après le nom
  Bluetooth), `validation.py` (validation des formulaires) ; helpers de calibration déplacés dans
  `chemistry.py` ; code de calcul dupliqué fusionné ; délais BLE en constantes nommées.
- Suite de tests réécrite (l'ancienne ne pouvait même pas être importée) : ~390 tests dont des
  tests par propriétés, faux Bluetooth, config/options flow, migration, cohérence des traductions.
- CI : workflow pytest + couverture (Python 3.14) ; configuration ruff explicite dans `pyproject.toml` ;
  `requirements_test.txt` ; fichiers de test ajoutés au `.gitignore`.
- Le coordinateur reçoit explicitement son `config_entry` ; `store_key` / `format_mac_safe` / `get_opt`
  deviennent des helpers publics de `coordinator.py`.
- Style : syntaxe Python 3.14 `except A, B:` (ce que ruff formate pour cette cible).

### Documentation
- `README.md` / `README.fr.md` : suppression du chlore expliquée, Redox brut, version minimale de
  Home Assistant, section développement. `calibration_help.md` : calibration du Redox brut, libellé
  « Chlore / Redox Statut » corrigé en « Redox Statut ». `info.md` : mention infondée de « Machine
  Learning » retirée.
