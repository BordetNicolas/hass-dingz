# Intégration Home Assistant Dingz

Intégration locale pour les interrupteurs muraux [dingz](https://www.dingz.ch) d'iolo AG. Elle dialogue directement avec chaque dingz sur le réseau local (API REST, MQTT optionnel). Aucun cloud n'est requis.

## Équipements et versions

| Élément | Support |
| --- | --- |
| Base (puck) | `DZ1B-4CH` (4 sorties, configurations DIP 0 à 3) ; base DDI : code présent, non validé physiquement |
| Façades | `dz1f-4b` (sans PIR) et `dz1f-pir` validées ; autres façades acceptées sans garantie |
| Firmware | 2.x requis (API REST v1 documentée par iolo). Validé sur **2.4.3** et **2.6.0**. Une version inconnue ou plus récente est acceptée ; une version < 2.0 déclenche un avertissement (réparation) |
| Home Assistant | 2025.8.0 minimum ; testé jusqu'à 2026.10.4 (CI) et compatible avec les membres « natifs » du climat de 2026.11 |

Détails : [docs/firmware-compatibility.md](docs/firmware-compatibility.md).

## Prérequis

- Le dingz est joignable en HTTP depuis Home Assistant (même réseau ou routage).
- La protection par mot de passe de l'API REST (option `rest_password` du firmware) est **désactivée** : son mécanisme d'authentification n'est pas documenté et n'est pas pris en charge.
- Optionnel : l'intégration MQTT de Home Assistant et un broker, pour les événements de boutons, la poussée d'état et l'énergie cumulée.

## Installation

### HACS

1. Ajoutez ce dépôt en dépôt personnalisé (catégorie **Integration**).
2. Installez **Dingz**, puis redémarrez Home Assistant.

### Manuelle

Copiez `custom_components/dingz` vers `/config/custom_components/dingz`, puis redémarrez.

## Configuration

**Paramètres → Appareils et services → Ajouter une intégration → Dingz.**

| Champ | Description |
| --- | --- |
| Hôte | Adresse IP, nom d'hôte ou URL (`192.168.2.42`, `dingz.local`, `http://192.168.2.42`). HTTP est utilisé si aucun schéma n'est donné ; le chemin éventuel est ignoré. |

L'intégration contacte le dingz avant de créer l'entrée, puis demande confirmation. Un même dingz (identifié par son identifiant `system_config.id`, c'est-à-dire sa MAC par défaut) ne peut être ajouté qu'une fois.

- **Découverte** : Zeroconf (`_http._tcp.local.`) et, si MQTT est configuré, `dingz/+/announce`. Une entrée n'est jamais créée sans confirmation.
- **Changement d'adresse IP** : la découverte met à jour l'adresse de l'entrée existante ; vous pouvez aussi utiliser **Reconfigurer** sur l'entrée. Les entités ne sont pas recréées.
- **Suppression** : **Paramètres → Appareils et services → Dingz → ⋮ → Supprimer**. Rien n'est modifié sur le dingz.

## Entités

Un dingz correspond à un appareil Home Assistant. Seules les fonctions réellement présentes et configurées sont exposées :

| Fonction dingz | Entité | Condition |
| --- | --- | --- |
| Sortie `light` (variable ou non) | `light` | dimmer présent dans `GET /state`, non `readonly`, sortie active |
| Sortie `power_socket` | `switch` | idem |
| Sortie `fan` | `fan` | idem |
| Moteur (store, lamelles) | `cover` | moteur présent et non `readonly` |
| Thermostat | `climate` | thermostat actif |
| Protection antigel (firmware 2.6.0+) | `binary_sensor` (diagnostic) | thermostat actif et champ fourni |
| PIR (0 = intégré, 1 = externe) | `binary_sensor`, `event`, bouton « réinitialiser le délai » | PIR activé |
| Entrée | `binary_sensor` | entrée active |
| Bouton câblé sur l'entrée | `event` | entrée de type bouton, MQTT activé sur le dingz |
| Boutons de façade | `event` (simple, double… quintuple clic, maintien, relâchement) | MQTT activé sur le dingz |
| Luminosité, état lumineux, éclairage adaptatif | `sensor` | — |
| Températures (pièce ; non compensée, FET, CPU, base) | `sensor` | les diagnostics seulement si le firmware les fournit (2.6.0 ne fournit plus CPU/base) |
| Puissance par sortie | `sensor` (W) | sortie active |
| Énergie cumulée par sortie et par moteur | `sensor` (kWh) | MQTT activé sur le dingz |
| LED de façade | `light` (HS) | — |
| Décalage de température, MQTT (activation, URI, certificat) | `number`, `switch`, `text` (configuration) | — |
| Redémarrer, enregistrer la configuration par défaut | `button` | — |
| Mémoire libre, horodatages | `sensor` (diagnostic, désactivés par défaut) | — |

Non exposé volontairement : les sorties `smart_light` (alimentation permanente d'ampoules connectées : les couper les priverait de courant) et les sorties utilisées par une entrée ou un moteur. Liste complète et justifications : [docs/feature-coverage.md](docs/feature-coverage.md).

## Actions

`dingz.set_position_and_tilt` déplace un store et oriente ses lamelles en **une seule commande** (les actions `cover.*` standard n'envoient que l'un ou l'autre, et deux appels successifs s'interrompent) :

```yaml
action: dingz.set_position_and_tilt
target:
  entity_id: cover.salon_store
data:
  position: 0        # store fermé
  tilt_position: 100 # lamelles ouvertes
```

## Exemples

Double clic sur le bouton 1 (MQTT requis) :

```yaml
triggers:
  - trigger: state
    entity_id: event.salon_bouton_1
    attribute: event_type
    to: m2
actions:
  - action: light.toggle
    target:
      entity_id: light.salon_lampadaire
```

Fermer le store et orienter les lamelles quand la pièce est vide depuis 10 minutes :

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.salon_mouvement_pir
    to: "off"
    for: "00:10:00"
actions:
  - action: dingz.set_position_and_tilt
    target:
      entity_id: cover.salon_store
    data:
      position: 0
      tilt_position: 50
```

Les compteurs d'énergie (MQTT) peuvent être ajoutés directement au tableau de bord **Énergie**.

## Mise à jour des données

- REST est la source de vérité et le seul chemin de commande : `GET /api/v1/state` toutes les 10 s (une requête, au plus une toutes les 200 ms par dingz), la mémoire libre toutes les 60 s.
- La configuration est relue quand `config.timestamp` change ; si les entités à créer changent (sortie, moteur, PIR, MQTT…), l'entrée est rechargée automatiquement.
- MQTT, s'il est disponible, pousse lumières, moteurs, entrée, capteurs, boutons, PIR et énergie sans attendre le polling. Sans MQTT, tout fonctionne sauf les boutons, le bouton de l'entrée et l'énergie cumulée.

Guide MQTT : [docs/mqtt.md](docs/mqtt.md).

## Limitations connues

- L'API REST ne fournit pas d'événements de boutons ni d'énergie cumulée : MQTT est nécessaire pour ces entités.
- La protection par mot de passe de l'API REST n'est pas prise en charge (l'intégration signale un refus HTTP 401/403).
- Pas de mise à jour de firmware : aucun mécanisme local n'est documenté par iolo (mise à jour via l'application dingz).
- Les entités sont construites au chargement : un changement de configuration du dingz recharge l'entrée (quelques secondes d'indisponibilité).
- Le certificat MQTT (PEM) dépasse la taille d'un état Home Assistant : l'entité affiche « inconnu » quand un certificat est défini.
- Thermostat, DDI, ventilateur, protection antigel et entrées de type porte de garage ne sont pas validés sur du matériel réel.

## Dépannage

| Symptôme | Piste |
| --- | --- |
| « Connexion impossible » | Vérifiez l'adresse (`http://<ip>/api/v1/info` dans un navigateur) ; le dingz répond lentement quand sa mémoire est faible. |
| « Accès refusé (401/403) » | Désactivez la protection par mot de passe de l'API dans l'application dingz. |
| Pas d'entités `event` | Activez MQTT sur le dingz (entités *MQTT Enable* / *MQTT URI*), configurez l'intégration MQTT, puis rechargez l'entrée. |
| Entités « plus fournies » après mise à jour | Normal pour les anciennes lumières fantômes (sorties de moteur) et les températures CPU/base en 2.6.0 : supprimez-les depuis la liste des entités. |
| Diagnostic | **⋮ → Télécharger les diagnostics** (les secrets, adresses et identifiants sont masqués) ; journaux : `logger: logs: custom_components.dingz: debug`. |

## Mise à jour depuis siku2/hass-dingz 0.7.x

Les `unique_id` sont passés de la MAC à l'identifiant dingz (`<dingz_id>_output_0`, …) : Home Assistant crée de nouvelles entités. Mettez à jour vos automatisations ou retirez l'ancienne entrée avant d'ajouter celle-ci.

Mise à jour depuis une version antérieure de ce dépôt : voir [CHANGELOG.md](CHANGELOG.md) (entités supprimées, noms corrigés).

## Développement

```bash
./scripts/setup.sh
pytest --cov
mypy
./scripts/lint.sh
```

Documentation technique : [architecture](docs/architecture.md), [tests](docs/testing.md), [audit](docs/audit.md), [Quality Scale](docs/quality-scale.md).
