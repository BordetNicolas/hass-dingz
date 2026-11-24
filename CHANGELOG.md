# Changelog

## [1.3.0] - 2026-11-24

### ⚠️ À lire avant la mise à jour

- **Entités qui ne sont plus fournies** (elles apparaissent comme « plus fournies » ; supprimez-les depuis **Paramètres → Entités**) :
  - lumières créées pour des sorties qui pilotent un moteur (configurations DIP 0, 1 et 2) ou qui servent d'entrée (`readonly`) : elles restaient `unknown` ou envoyaient la commande au mauvais dimmer ;
  - températures CPU et base sur firmware 2.6.0 (le firmware ne les fournit plus).
- **Noms corrigés** (les `entity_id` ne changent pas) : les stores prennent le nom configuré du moteur physique ; « PIR interne » devient « PIR externe » pour le PIR d'index 1 (document MQTT officiel : 0 = intégré, 1 = externe).
- Aucun `unique_id` existant n'est modifié ; aucune migration d'entrée n'est nécessaire.

### Corrections (firmwares antérieurs à 2.6.0)

- Lumières, prises et ventilateurs construits à partir des dimmers réellement présents (`GET /state`), avec correspondance index relatif (commandes) / absolu (configuration, puissance).
- Noms des stores lus dans `blind_config` à l'index du moteur physique.
- Entrée MQTT : `state/input/0` pour une entrée « contact », `state/input/4` pour une entrée bouton (un `state/input/0` retenu contredisait REST).
- Les messages MQTT ne repoussent plus le polling REST (puissance et températures restaient figées tant que des messages arrivaient).
- États affichés dès le démarrage au lieu de « inconnu » jusqu'au prochain polling.
- Le certificat MQTT n'était jamais lu (`server.crt` découpé sur le point).
- Mot de passe du broker masqué dans l'état de l'entité URI MQTT (il était enregistré dans l'historique).
- Thermostat : endpoints documentés (`POST /thermostat`, `/thermostat/mode/<mode>`) au lieu de réécrire `thermostat_config` (qui activait le *free cooling* à chaque changement de mode) ; marche/arrêt.
- Luminosité : arrondi au lieu d'une troncature (luminosité HA 1 envoyée à 0 %) ; transitions bornées aux plages documentées.
- Client REST : pas de nouvelle tentative sur une erreur 4xx ; redémarrage jamais répété ; horloge monotone pour la limitation de débit.
- Erreurs de commande traduites (`HomeAssistantError`) ; boutons indisponibles quand le dingz l'est ; types d'événements inconnus ignorés.
- Découverte d'un dingz injoignable : abandon propre au lieu d'une exception ; validation de l'hôte saisi.
- Noms configurés sur le dingz débarrassés des espaces finaux.
- LED de façade : le fondu (`ramp`) n'est plus envoyé sans transition demandée (il écrasait un réglage permanent du dingz, par exemple 1023 ms → 25 ms).
- L'import du client MQTT n'a plus lieu quand l'intégration MQTT de Home Assistant n'est pas configurée (avertissements « blocking call »).

### Fonctionnalités ajoutées (firmwares antérieurs à 2.6.0)

- Compteurs d'énergie par sortie et par moteur (MQTT, firmware 2.4.3+ ; unité mesurée : watt-seconde, affichée en kWh), restaurés au redémarrage.
- Entité `event` pour un bouton câblé sur l'entrée (MQTT `event/button/4`).
- Diagnostics téléchargeables (données sensibles masquées).
- Reconfiguration de l'adresse depuis l'interface.
- Rechargement automatique quand la configuration du dingz change les entités à créer.
- Avertissement (réparation) pour un firmware < 2.0.

### Firmware 2.6.0

- Capteur de diagnostic « Protection antigel » (`thermostat.frost_protection`), créé seulement si le thermostat est actif et si le firmware fournit le champ.
- Températures CPU/base absentes en 2.6.0 : plus d'entités créées pour elles.
- Messages MQTT moteur `target_position` / `target_lamella` pris en charge.

### Améliorations techniques

- Détection des capacités centralisée (`capabilities.py`), version de firmware comparée sémantiquement.
- Compatibilité Home Assistant 2026.11 (membres `native_*` du climat) tout en restant compatible 2025.8.
- `PARALLEL_UPDATES`, icônes, action enregistrée dans `async_setup` (HA récents), typage `mypy --strict`, couverture 95 % imposée en CI, job de tests sur le dernier Home Assistant.
- Fixtures de tests issues de réponses réelles anonymisées (2.4.3 et 2.6.0).

### Validation

Testé en conditions réelles (lecture sur 12 dingz, puis commandes sur deux dingz avec une instance Home Assistant 2026.11.3 jetable) : plafonnier (30 %, 100 % avec transition, extinction), store (0 → 10 % → 0 %, dans les deux sens), état identique côté dingz et côté Home Assistant. Détails dans [docs/testing.md](docs/testing.md).

### Limitations restantes

- La LED de façade d'un dingz réglé pour suivre le soleil (blanc le jour, bleu la nuit, orange au lever/coucher) n'affiche pas la couleur envoyée par l'API : le dingz l'enregistre mais la réécrase (observé sur 2.4.3, hypothèse non confirmée). Désactivez ce mode dans la configuration du dingz pour commander la LED.
- Voir aussi [docs/audit.md](docs/audit.md#anomalies-restantes).
