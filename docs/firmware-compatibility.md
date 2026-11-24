# Compatibilité firmware et matériel

## Sources et fiabilité

| Source | Contenu | Fiabilité |
| --- | --- | --- |
| [Playground API v2](http://api.dingz.ch) (iolo) | Endpoints REST v1, firmware 2.x | Élevée mais incomplète : ne mentionne ni `smart_light`, ni `pirs[]`, ni les champs 2.6.0 ; décrit `blinds[].current.blind` alors que 2.x renvoie `position` |
| [Changelog API 2.0.x](http://api.dingz.ch/en/cms/changelog-en/) (iolo) | Changements 1.3.30 → 2.0.x | Élevée |
| « dingz MQTT topics », FW 2.1.58, v1.03 janv. 2025 ([documents dingz](https://www.dingz.ch/resources/documents)) | Topics, index PIR/entrée/bouton, payloads | Élevée (ne précise pas l'unité de l'énergie) |
| Réponses réelles de 12 dingz (2026-11-24) : 11 en 2.6.0, 1 en 2.4.3 | Tous les GET listés ci-dessous, MQTT passif 15 min | Élevée pour ces versions et ce matériel |
| siku2/hass-dingz (historique de ce dépôt) | Topics MQTT, types | Moyenne |

Aucune note de version publique n'a été trouvée pour 2.6.0 (ni pour 2.1 à 2.5) : les différences 2.6.0 ci-dessous viennent de la comparaison des réponses réelles 2.4.3 / 2.6.0 sur le même matériel. Une différence observée n'est pas forcément *apparue* en 2.6.0 (elle peut dater de 2.5.x).

## Matériel

| Élément | Valeurs observées | Effet dans l'intégration |
| --- | --- | --- |
| Base `puck_hw_model` | `DZ1B-4CH` (hw 1.1.2, fw base 2.1.4 avec front 2.4.3, 2.2.4 avec front 2.6.0) | Modèle de l'appareil HA |
| Façade `front_hw_model` | `dz1f-4b`, `dz1f-pir` | `has_pir` → PIR index 0 |
| `dip_config` | 0 = 2 moteurs ; 1 = 2 dimmers + 1 moteur (moteur absolu 1) ; 2 = 1 moteur + 2 dimmers (dimmers absolus 2-3, *non observé*) ; 3 = 4 dimmers | Lu indirectement via `state.dimmers[].index` / `state.blinds[].index` |
| `ddi_base` | `false` partout | Lumières DDI : code conservé, non validé |
| dingz+ (nouvelle génération annoncée sur dingz.ch) | non disponible | Non vérifié |

## Endpoints utilisés

| Endpoint | Méthode | Vérifié sur | Usage |
| --- | --- | --- | --- |
| `/api/v1/state` | GET | 2.4.3, 2.6.0 | Polling 10 s |
| `/api/v1/device`, `system_config`, `services_config`, `output_config`, `input_config`, `button_config`, `blind_config`, `ddi_channels_config` | GET | 2.4.3, 2.6.0 | Configuration (au démarrage et quand `config.timestamp` change) |
| `/api/v1/info` | GET | 2.4.3, 2.6.0 | Repli d'identifiant (MAC) |
| `/api/v1/ram` | GET | 2.4.3, 2.6.0 | Diagnostic 60 s, contrôle après une erreur 5xx |
| `/api/v1/dimmer/<rel>/<on\|off>`, `shade/<rel>[/<action>]`, `led/set`, `pir/<n>/reset_time`, `thermostat`, `thermostat/mode/<mode>`, `system_config`, `services_config`, `save_default_config`, `reboot` | POST | documentés ; **non exécutés** pendant l'audit (opérations à impact) | Commandes |

## Différences 2.4.3 → 2.6.0 (observées)

| Élément | 2.4.3 | 2.6.0 | Traitement |
| --- | --- | --- | --- |
| `state.sensors.cpu_temperature`, `puck_temperature` | présents | **absents** | capteurs créés seulement si présents |
| `state.thermostat.frost_protection` ; `thermostat_config.frost_protection`, `frost_min_temp` | absents | présents | capteur « Protection antigel » si thermostat actif |
| `state.dyn_light.weather_dl_override` | absent | présent | non exposé (sémantique non documentée) |
| `system_config.keep_alive`, `installer_config` | absents | présents | non exposés (configuration interne) |
| `services_config.aws_default_cert` | absent | présent | masqué dans les diagnostics |
| `button_config.dingz_orientation` | présent | absent | non utilisé |
| `action.*.feedback` | présent | absent | non utilisé |
| `night_light.led.color` | absent | présent | veilleuse non exposée |
| MQTT `state/motor/<n>` | `motion`, `position`, `lamella` | + `target_position`, `target_lamella` | `target_position` lu comme objectif |
| MQTT énergie/puissance | présentes | présentes | compteurs d'énergie (watt-seconde) |

## Comportements vérifiés

| Comportement | Preuve |
| --- | --- |
| `output_config.outputs` liste toujours 4 sorties, y compris celles d'un moteur | DIP 0 : 4 sorties `light` actives, `state.dimmers = []` |
| `dimmers[].index.relative` est l'index des commandes et des topics MQTT ; `absolute` celui de `output_config` et `power_outputs` | DIP 1 : moteur relatif 0 / absolu 1, topic `state/motor/0`, nom dans `blind_config[1]` |
| Dimmer `readonly` quand la sortie sert d'entrée ou est inactive | Entrée active → sortie 0 `readonly` |
| `pirs[]` a 3 éléments ; `pirs[0]` vaut `null` sans PIR intégré | 12 appareils ; document MQTT : 0 interne, 1 externe |
| `rest_password` est un booléen | `false` sur les 12 appareils |
| Énergie MQTT en watt-seconde | Δénergie / (puissance × Δt) = 0,83–0,92 sur 600 s (messages non retenus) |
| Entrée bouton : `state/input/4` cohérent avec REST, `state/input/0` retenu incohérent | Entrée `button_toggle` active |

## Matrice de compatibilité

| Fonction | < 2.0 | 2.0–2.3 | 2.4.3 | 2.6.0 | Version inconnue |
| --- | --- | --- | --- | --- | --- |
| Configuration, polling, commandes REST | ⚠️ réparation affichée | ✅ documenté, non testé | ✅ testé (réel, lecture) | ✅ testé (réel, lecture) | ✅ accepté |
| Températures CPU/base | — | selon payload | ✅ | absent | selon payload |
| Énergie MQTT | — | non vérifié (doc 2.1.58 : oui) | ✅ | ✅ | selon payload |
| Protection antigel | — | — | — | ✅ (thermostat actif) | selon payload |

Les versions sont comparées sémantiquement (`AwesomeVersion`). La version n'est jamais globale à l'intégration : chaque entrée détecte ses capacités dans ses propres réponses.
