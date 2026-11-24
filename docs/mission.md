# Suivi de mission — audit et mise en conformité Dingz

Fichier de reprise : état courant, décisions et blocages. Branche de travail : `audit/quality-and-fw-2.6.0`.

## État de référence (commit `bd28107`, avant intervention)

| Indicateur | Valeur |
| --- | --- |
| Tests | 49 réussis (HA 2025.8.0, Python 3.13) ; 49 réussis sur HA 2026.10.4 / Python 3.14 |
| Couverture | 80 % (2019 instructions, 412 non couvertes) |
| Ruff check / format | OK |
| mypy (`--ignore-missing-imports`) | 6 erreurs (api.py, mqtt.py, text.py, switch.py) |
| HA de production | 2026.11.2 (Container) ; dernière stable : 2026.11.3 |
| Parc réel | 12 Dingz `DZ1B-4CH`, façades `dz1f-4b` (10) et `dz1f-pir` (2) ; 11 en 2.6.0, 1 en 2.4.3 |

## Tâches

- [x] Analyse initiale du dépôt, des AGENTS.md et des outils MCP
- [x] État de référence (tests, lint, typage, couverture)
- [x] Inventaire réel non destructif (GET REST, MQTT passif, entités HA)
- [x] Corrections firmwares < 2.6.0 (commits `902dcfc`, `451e34b`, `48ece8a`, `6a993dc`)
- [x] Conformité Quality Scale (diagnostics, reconfiguration, exceptions traduites, typage strict) — `c492daf`, `422e260`
- [x] Commit de référence pré-2.6.0 (tag local `pre-fw-2.6.0-baseline`)
- [ ] Évolutions 2.6.0
- [ ] Documentation finale et rapport

## Décisions

- Les sorties `smart_light` (alimentation permanente d'ampoules connectées) ne sont pas exposées : les couper priverait les ampoules d'alimentation.
- Les `unique_id` existants sont conservés : `output_{index absolu}`, `cover_{index relatif}`, `pir_{n}`, etc.
- Les entités fantômes supprimées du code ne sont pas effacées automatiquement du registre : l'utilisateur les retire depuis l'interface (« entité plus fournie »).

## Sources découvertes

- Document officiel « dingz MQTT topics » (iolo, FW 2.1.58, janv. 2025) : https://www.dingz.ch/resources/documents — index PIR (0 interne, 1 externe), bouton 4 = entrée, `state/input/0` pour les entrées « state ».
- Aucune note de version publique pour 2.6.0.

## Blocages

- Pas de note de version officielle publique pour le firmware 2.6.0 trouvée ; les évolutions 2.6.0 sont déduites de la comparaison des réponses réelles 2.4.3 / 2.6.0.
- Aucun thermostat, DDI, ventilateur ni entrée `garage_door` actif sur le parc réel : comportements non validables physiquement.
