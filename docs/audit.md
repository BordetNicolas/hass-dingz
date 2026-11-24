# Audit de l'intégration Dingz (2026-11-24)

## État initial (commit `bd28107`)

- 20 modules, 11 plateformes, aucune dépendance externe (client REST interne). Domaine `dingz`, HA minimum 2025.8.0.
- 49 tests réussis, couverture 80 %, Ruff propre, 6 erreurs mypy (non strict), pas de diagnostics, pas de reconfiguration, messages d'erreur non traduits.
- Production : HA 2026.11.2, 12 dingz `DZ1B-4CH` (11 × 2.6.0, 1 × 2.4.3), MQTT activé sur tous ; un 13ᵉ dingz publie sur le broker sans être configuré dans HA.
- Avertissement HA au démarrage : `current_temperature` / `target_temperature` du climat dépréciés (suppression en 2027.11).

## Anomalies identifiées

| # | Anomalie | Criticité | Statut |
| --- | --- | --- | --- |
| A1 | Lumières créées pour les 4 sorties de `output_config`, y compris celles d'un moteur : 23 lumières `unknown` en production ; en DIP 2, commandes envoyées au mauvais dimmer (index absolu au lieu de relatif) | Critique | Corrigé |
| A2 | Lumière créée pour une sortie `readonly` (utilisée par l'entrée) | Importante | Corrigé (entité retirée) |
| A3 | Nom des stores lu à l'index relatif : « Store 1 » au lieu du nom configuré sur 8 dingz | Importante | Corrigé |
| A4 | Températures CPU/base créées en 2.6.0 alors que le firmware ne les fournit plus (22 entités `unknown`) | Importante | Corrigé |
| A5 | Les messages MQTT (`async_set_updated_data`) repoussaient le polling REST : puissance, températures, etc. figées tant que des messages arrivaient | Importante | Corrigé |
| A6 | Entrée MQTT lue sur l'index 0, en contradiction avec REST pour une entrée bouton | Importante | Corrigé (selon le type, doc officielle) |
| A7 | URI MQTT avec mot de passe exposée dans l'état de l'entité (historique, enregistreur) | Importante (sécurité) | Corrigé (masquée) |
| A8 | Entité certificat MQTT jamais lue (`server.crt` découpé sur le point) ; un vrai certificat dépasse la longueur d'un état | Mineure | Corrigé |
| A9 | Thermostat : changement de mode via `thermostat_config` en forçant `free_cooling` ; climat déprécié en 2026.11 | Importante | Corrigé (endpoints documentés, membres `native_*`) |
| A10 | Entités vides (`unknown`) jusqu'au premier polling après le démarrage | Mineure | Corrigé |
| A11 | Luminosité HA 1 → 0 % (troncature) ; transitions hors plage rejetées par le firmware | Mineure | Corrigé |
| A12 | Nouvelles tentatives sur erreurs 4xx ; `reboot` répété jusqu'à 3 fois en cas de timeout | Importante | Corrigé |
| A13 | Découverte d'un dingz injoignable : exception non gérée dans le flux | Mineure | Corrigé |
| A14 | Saisie `http://` interprétée comme l'hôte `http` | Mineure | Corrigé |
| A15 | Boutons toujours disponibles même dingz hors ligne | Mineure | Corrigé |
| A16 | PIR d'index 1 nommé « PIR interne » alors qu'il s'agit du PIR externe ; index 2 sans nom | Mineure | Corrigé |
| A17 | Type d'événement inconnu (nouveau firmware) → exception | Mineure | Corrigé |
| A18 | Erreurs non traduites, pas de `PARALLEL_UPDATES`, pas de diagnostics ni de reconfiguration, typage incomplet | Qualité | Corrigé |
| A19 | Mutation de la configuration en cache avant confirmation du dingz (activation MQTT, URI) | Mineure | Corrigé |
| A20 | Pas de bouton d'entrée ni d'énergie cumulée malgré leur disponibilité en MQTT | Fonctionnelle | Ajouté |

## Décisions

- Les `unique_id` ne changent pas ; aucune migration n'est nécessaire. Les entités devenues fantômes ne sont pas supprimées automatiquement.
- `smart_light` n'est pas exposé ; les autres types (`heater`, `pulse`, `garage_door`, `valve`) restent non implémentés faute de documentation et de cas réel.
- REST reste l'unique chemin de commande ; MQTT n'est utilisé qu'en lecture.
- Pas de bibliothèque externe ; la détection des capacités est centralisée dans `capabilities.py`.

## Sécurité

| Sujet | Constat |
| --- | --- |
| Transport | L'API locale du dingz est en HTTP sans authentification (limitation du constructeur). HTTPS est accepté si l'utilisateur le saisit, non vérifié sur le matériel. |
| Mot de passe REST | Option `rest_password` (booléen) dans le firmware ; schéma d'authentification non documenté → non pris en charge, refus signalé. |
| Secrets | URI MQTT masquée dans l'état, les journaux (`services_config`) et les diagnostics ; dépôt et historique sans secret ; fixtures anonymisées. |
| Entrées | Hôte validé (schéma http/https, hôte requis) ; payloads REST/MQTT validés défensivement (types, bornes 0–100). |
| Charge | 1 requête / 200 ms par dingz, pas de répétition sur 4xx, pas de répétition du redémarrage, délais bornés. |
| Dépendances | Aucune dépendance d'exécution hors Home Assistant. |

## Anomalies restantes

- Pas de logo dans home-assistant/brands.
- `weather_dl_override`, `keep_alive`, `installer_config` (2.6.0) et la veilleuse non exposés (sémantique inconnue).
- Thermostat, DDI, ventilateur, protection antigel, DIP 2 et entrées garage non validés sur matériel.
- Commandes et nouvelle version de l'intégration non validées en conditions réelles (autorisation requise).
- `light.entree_rez_entree_rez_lumiere_1` disparaît (sortie `readonly`) : à confirmer par l'utilisateur.

## Références

[Firmware et sources](firmware-compatibility.md) · [Couverture](feature-coverage.md) · [Quality Scale](quality-scale.md) · [Architecture](architecture.md) · [Tests](testing.md)
