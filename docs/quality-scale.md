# Integration Quality Scale

Évaluation technique par rapport aux [règles](https://contributors.home-assistant.io/core/quality-scale/rules/) (54 règles). Il ne s'agit pas d'une certification : seules les intégrations du cœur sont classées officiellement.

Légende : ✅ conforme · 🟡 partiel · ❌ non conforme · ➖ non applicable.

## Bronze

| Règle | État | Détail |
| --- | --- | --- |
| action-setup | ✅ | `dingz.set_position_and_tilt` enregistrée dans `async_setup` quand HA fournit `async_register_platform_entity_service` ; repli par plateforme pour HA 2025.8 |
| appropriate-polling | ✅ | 10 s pour l'état (une requête), 60 s pour la RAM |
| brands | ❌ | Pas de logo dans home-assistant/brands (validation HACS « brands » ignorée) |
| common-modules | ✅ | `coordinator.py`, `entity.py` |
| config-flow | ✅ | `data_description` ajouté ; uniquement `ConfigEntry.data` (URL) |
| config-flow-test-coverage | ✅ | `config_flow.py` couvert à 95 % : erreurs, doublons, découverte, reconfiguration |
| dependency-transparency | ✅ | Aucune dépendance externe (client REST interne, aiohttp de HA) |
| docs-actions | ✅ | README |
| docs-conditions | ➖ | Aucune condition d'appareil |
| docs-high-level-description | ✅ | README |
| docs-installation-instructions | ✅ | README (prérequis inclus) |
| docs-removal-instructions | ✅ | README |
| docs-triggers | ✅ | Entités `event` documentées (pas de déclencheurs d'appareil dédiés) |
| entity-event-setup | ✅ | Abonnements dans `async_added_to_hass` via `async_on_remove` |
| entity-unique-id | ✅ | `<dingz_id>_<suffixe>`, jamais l'IP |
| has-entity-name | ✅ | |
| runtime-data | ✅ | `entry.runtime_data` |
| test-before-configure | ✅ | |
| test-before-setup | ✅ | `async_config_entry_first_refresh` → `ConfigEntryNotReady` |
| unique-config-entry | ✅ | `system_config.id` (repli MAC) |

## Silver

| Règle | État | Détail |
| --- | --- | --- |
| action-exceptions | ✅ | `async_command` → `HomeAssistantError` traduite |
| config-entry-unloading | ✅ | Plateformes et MQTT désinscrits (testé) |
| docs-configuration-parameters | ➖ | Pas d'options flow (aucune option utile) |
| docs-installation-parameters | ✅ | README |
| entity-unavailable | ✅ | Toutes les entités suivent le coordinateur (boutons inclus désormais) |
| integration-owner | ✅ | `codeowners` |
| log-when-unavailable | ✅ | Géré par `DataUpdateCoordinator` |
| parallel-updates | ✅ | `PARALLEL_UPDATES = 0` partout (commandes sérialisées par le client) |
| reauthentication-flow | ➖ | Pas d'identifiants : l'API REST est sans authentification ; l'option `rest_password` du firmware n'est pas documentée (refus 401/403 signalé) |
| test-coverage | 🟡 | 95,3 % au total ; quelques modules sous 95 % (`climate.py` 84 % : une branche par version de HA, `light.py` 89 %) |

## Gold

| Règle | État | Détail |
| --- | --- | --- |
| devices | ✅ | Fabricant, modèle, versions, MAC, n° de série (identifiant), zone suggérée |
| diagnostics | ✅ | `diagnostics.py`, données sensibles masquées (testé) |
| discovery | ✅ | Zeroconf et MQTT |
| discovery-update-info | ✅ | Adresse mise à jour par la découverte et par l'ajout manuel |
| docs-data-update | ✅ | README |
| docs-examples | ✅ | README |
| docs-known-limitations | ✅ | README |
| docs-supported-devices | ✅ | README, `firmware-compatibility.md` |
| docs-supported-functions | ✅ | README, `feature-coverage.md` |
| docs-troubleshooting | ✅ | README |
| docs-use-cases | ✅ | README (exemples) |
| dynamic-devices | ➖/✅ | Une entrée = un appareil ; un changement de configuration recharge l'entrée automatiquement |
| entity-category | ✅ | |
| entity-device-class | ✅ | Prise : `outlet` ajouté |
| entity-disabled-by-default | ✅ | Températures internes, RAM, horodatage d'état |
| entity-translations | ✅ | en, fr, de |
| exception-translations | ✅ | Coordinateur et commandes |
| icon-translations | ✅ | `icons.json` |
| reconfiguration-flow | ✅ | Étape `reconfigure` |
| repair-issues | ✅ | Firmware < 2.0, migration 1.1 |
| stale-devices | ➖ | Un appareil par entrée : supprimer l'entrée supprime l'appareil |

## Platinum

| Règle | État | Détail |
| --- | --- | --- |
| async-dependency | ✅ | Client asyncio |
| inject-websession | ✅ | `async_get_clientsession(hass)` |
| strict-typing | ✅ | `mypy --strict` sans erreur (imposé en CI) ; le client n'est pas une bibliothèque PyPI séparée |

## Écarts résiduels

- **brands** : nécessite une contribution au dépôt `home-assistant/brands`.
- **test-coverage par module** : la branche climat de l'autre version de HA n'est exécutée que par le job correspondant.
- Hassfest et la validation HACS sont exécutés par la CI GitHub (non exécutables localement dans cet environnement).
