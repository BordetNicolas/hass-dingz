# Intégration Home Assistant Dingz

Intégration locale pour les interrupteurs muraux [Dingz](https://www.dingz.ch). Aucun cloud n’est requis.

## Installation (HACS)

1. Installez [HACS](https://hacs.xyz) si ce n’est pas déjà fait.
2. Ajoutez ce dépôt en dépôt personnalisé (catégorie **Integration**).
3. Installez **Dingz**, puis redémarrez Home Assistant.
4. Allez dans **Paramètres → Appareils et services → Ajouter une intégration** et recherchez **Dingz**.
5. Saisissez le nom d’hôte ou l’adresse IP (exemple : `192.168.2.42`).

Installation manuelle : copiez le dossier `custom_components/dingz` vers `/config/custom_components/dingz`, redémarrez, puis ajoutez l’intégration depuis l’interface.

## Découverte automatique

Les Dingz annoncés en Zeroconf (`_http._tcp.local.`) et, si MQTT est configuré, via `dingz/+/announce`, sont proposés à l’ajout. Une ConfigEntry n’est jamais créée sans confirmation.

Un changement d’adresse IP met à jour l’URL de l’entrée existante : les entités ne sont pas recréées (`unique_id` basé sur l’identifiant matériel Dingz, jamais sur l’IP).

## Entités

Un Dingz physique correspond à un Device Home Assistant. Seules les fonctions réellement configurées sur l’appareil sont exposées :

| Configuration Dingz | Entité HA |
| --- | --- |
| Sortie `light` (dimmable ou non) | `light` |
| Sortie `power_socket` | `switch` |
| Stores / moteurs | `cover` |
| Sortie `fan` | `fan` |
| Thermostat actif | `climate` |
| PIR | `binary_sensor` |
| Entrées physiques actives | `binary_sensor` |
| Température, luminosité, puissance (W) | `sensor` |
| LED RGB de façade | `light` |
| Pressions des boutons | `event` (MQTT requis) |

L’API REST Dingz n’expose **pas** d’énergie cumulée (Wh), seulement la puissance instantanée. Pour l’énergie, créez un helper Home Assistant [Intégration (Riemann)](https://www.home-assistant.io/integrations/integration/) sur le capteur de puissance.

## MQTT (optionnel)

REST reste la source de vérité et le seul chemin de commande. MQTT, s’il est disponible via l’intégration MQTT de Home Assistant, pousse les changements (boutons, PIR, lumières, stores) sans attendre le prochain polling (10 s).

Sans MQTT, l’intégration fonctionne entièrement. Les événements de boutons ne sont pas fournis par l’API REST.

Guide de configuration côté Dingz : [docs/mqtt.md](docs/mqtt.md).

## Mise à jour depuis siku2/hass-dingz 0.7.x

Les `unique_id` des entités passent de la MAC vers l’identifiant Dingz (`<dingz_id>_output_0`, …). Home Assistant créera de nouvelles entités. Mettez à jour vos automatisations, ou retirez l’ancienne entrée avant d’ajouter celle-ci.

## Développement

```bash
./scripts/setup.sh
pytest
./scripts/lint.sh
```
