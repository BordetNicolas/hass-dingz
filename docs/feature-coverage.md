# Couverture fonctionnelle

États : **Conforme** (implémenté et conforme), **Corrigé** (était incorrect, corrigé), **Ajouté** (manquant, ajouté), **Non implémenté**, **N/A**.
Validation réelle : *lecture* = payloads réels lus et entités recalculées depuis les 12 dingz (aucune commande envoyée) ; *non* = pas de matériel ou opération à impact non autorisée.

| Fonctionnalité | Firmware min. | Matériel | Source | État | Tests | Validation réelle |
| --- | --- | --- | --- | --- | --- | --- |
| Lumière on/off et variation | 2.0 | DZ1B, dimmer non `readonly`, type `light` | Playground | Corrigé (index relatif/absolu, sorties de moteur) | `test_real_devices`, `test_light` | lecture (2.4.3, 2.6.0) |
| Transition (`time`) | 2.0 | idem | Playground | Corrigé (bornée 0,01–10 s) | `test_real_devices::test_dimmer_commands_use_relative_index` | non |
| Prise commandée (`power_socket`) | 2.0 | idem | output_config | Corrigé | `test_power_socket_and_smart_lights` | lecture |
| Ventilateur (`fan`) on/off | 2.0 | idem | output_config | Corrigé | `test_mqtt_switch_fan_and_offset` | non (aucun configuré) |
| Sortie `smart_light` | ? | — | réel | N/A, exclue : alimentation permanente d'ampoules connectées | `test_cover_uses_config_of_its_absolute_motor` | lecture |
| Sorties `heater`, `pulse`, `garage_door`, `valve` | ? | — | output_config | Non implémenté : sémantique de commande non documentée, aucun cas réel | — | non |
| Store : ouvrir/fermer/arrêter/position | 2.0 | moteur non `readonly` | Playground | Corrigé (nom du moteur physique) | `test_cover_actions_and_push` | lecture |
| Lamelles | 2.0 | idem | Playground | Conforme | idem | non |
| Position + lamelles en une commande | 2.0 | idem | Playground (`shade/<n>?blind&lamella`) | Conforme (action `dingz.set_position_and_tilt`) | idem | non |
| Calibration (`initialize`) | 2.0 | — | Playground | Non implémenté : action à impact, rare, réalisée depuis l'app | — | non |
| Boutons de façade (événements) | 2.0 + MQTT | 4 boutons | doc MQTT | Conforme | `test_events_and_mqtt_online` | non (aucun appui pendant la capture) |
| Bouton câblé sur l'entrée | 2.1.58 + MQTT | entrée bouton | doc MQTT (`button/4`) | Ajouté | idem | non |
| Simuler un appui (`POST /button/...`) | 2.0 | — | Playground | Non implémenté : déclencherait des actions configurées sur le dingz | — | — |
| Entrée (contact) | 2.0 | entrée active | Playground, doc MQTT | Corrigé (topic selon le type) | `test_input_topic_follows_input_type`, `test_input_device_class_and_push` | lecture |
| PIR intégré / externe (mouvement) | 2.0 | `has_pir` ou PIR externe | doc MQTT (0 interne, 1 externe) | Corrigé (noms) | `test_input_and_pirs` | lecture + événement `pir/0` observé |
| Réinitialiser le délai PIR | 2.0 | PIR actif | Playground | Conforme | `test_reset_pir_and_save_config` | non |
| Activer/désactiver PIR, minuteries PIR | 2.0 | — | Playground | Non implémenté : configuration, pas d'usage HA identifié | — | — |
| Luminosité (lux), état lumineux | 2.0 | — | Playground | Conforme | `test_timestamps_and_brightness_push` | lecture |
| Température de la pièce | 2.0 | — | Playground | Conforme | `test_real_devices` | lecture |
| Températures diagnostic (non compensée, FET, CPU, base) | 2.0 | — | Playground | Corrigé (créées seulement si fournies) | `test_setup_every_captured_device` | lecture |
| Puissance par sortie | 2.0 | — | Playground | Conforme | `test_dimmer_commands_use_relative_index` | lecture |
| Énergie cumulée par sortie/moteur | 2.1.58 (doc) ; observé 2.4.3 | MQTT | doc MQTT, mesure | Ajouté | `test_energy_sensor_restore_and_push` | lecture (MQTT passif) |
| Thermostat (mode, consigne, marche/arrêt) | 2.0 | thermostat actif | Playground | Corrigé (endpoints documentés) | `test_thermostat`, `test_thermostat_partial_payload` | non (aucun actif) |
| Protection antigel | 2.6.0 (observé) | thermostat actif | réel | Ajouté | `test_frost_protection_capability` | non (aucun actif) |
| LED de façade (HSV, transition) | 2.0 | — | Playground | Conforme (rampe bornée) | `test_front_led` | lecture |
| Éclairage adaptatif (phase) | 2.0 | `dyn_light.enable` | réel | Conforme | `test_real_devices` | lecture |
| Override météo de l'éclairage adaptatif | 2.6.0 (observé) | — | réel | Non implémenté : sémantique non documentée | — | — |
| DDI (canaux, température de couleur) | ? | base DDI | siku2 | Conforme (code existant) | `test_ddi_channel` | non (pas de base DDI) |
| Décalage de température | 2.0 | — | Playground | Conforme | `test_mqtt_switch_fan_and_offset` | non |
| Configuration MQTT (activation, URI, certificat) | 2.0 | — | doc MQTT | Corrigé (certificat, mot de passe masqué) | `test_mqtt_uri_password_is_masked`, `test_certificate_too_long_for_a_state` | lecture |
| Redémarrer, enregistrer la config par défaut | 2.0 | — | Playground | Corrigé (redémarrage jamais répété) | `test_buttons_follow_device_availability` | non |
| RAM libre | 2.0 | — | Playground | Conforme | `test_coordinator_failure_paths` | lecture |
| Découverte Zeroconf / MQTT announce | 2.0 | — | doc MQTT | Corrigé (dingz injoignable) | `test_config_flow` | lecture (topics `announce`) |
| Mise à jour de firmware | — | — | — | N/A : aucun mécanisme local documenté | — | — |
| Scènes, planificateur, minuteries, veilleuse, actions URL, groupes, Wi-Fi de secours | 2.0 | — | Playground | Non implémenté : configuration interne du dingz ; les automatisations HA couvrent ces besoins | — | — |
| Authentification REST (`rest_password`, `login`) | ? | — | Playground (sans détail) | Non implémenté : schéma non documenté, aucun appareil protégé ; refus 401/403 signalé | `test_auth_required_is_reported` | non |
| Commandes MQTT (`command/...`) | 2.1.58 | — | doc MQTT | N/A volontaire : REST reste l'unique chemin de commande (règle du projet) | — | — |
