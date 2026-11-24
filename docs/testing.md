# Tests

## Exécution

```bash
uv pip install --system -e ".[test]"   # HA 2025.8.0, Python 3.13
pytest --cov                             # échoue sous 95 % de couverture
mypy                                     # mode strict
ruff check . && ruff format --check
```

Dernier Home Assistant testable (Python 3.14) :

```bash
uv venv --python 3.14 .venv-latest
VIRTUAL_ENV=.venv-latest uv pip install pytest-homeassistant-custom-component pytest-cov
.venv-latest/bin/pytest -q -W "error::DeprecationWarning:custom_components"
```

La CI exécute les deux (le second à titre informatif), plus Hassfest et la validation HACS.

## Fixtures

- `tests/fixtures/devices/*.json` : réponses **réelles** anonymisées (MAC, IP, SSID, numéros de série, URI MQTT, coordonnées remplacés) de cinq dingz, décrites dans `tests/fixtures/devices.py`. Les réponses 2.4.3 et 2.6.0 viennent de dingz différents mais du même matériel ; aucune réponse 2.6.0 n'est présentée comme antérieure.
- `tests/fixtures/payloads.py` : payloads synthétiques historiques (tests unitaires).
- `mock_dingz_client` simule `api.Client` ; aucun test n'accède au réseau, à Internet ni à l'instance de production.

## Scénarios couverts

Installation manuelle, hôte invalide, doublon (et mise à jour d'adresse), découverte Zeroconf/MQTT (faux positifs, appareil injoignable, nouvelle IP), reconfiguration (succès, mauvais appareil, erreurs), chargement/déchargement, appareil injoignable au démarrage, refus 401, perte et retour de connexion, réponse invalide, configuration partielle, firmware ancien/2.4.3/2.6.0/inconnu, chaque configuration DIP réelle (+ DIP 2 dérivée), sorties `readonly`/`smart_light`, index relatif ≠ absolu, MQTT (lumière, moteur 2.6.0, entrée selon le type, énergie, événements inconnus ou dupliqués, messages incomplets), conversions et bornes, masquage des secrets (diagnostics, URI MQTT), restauration de l'énergie, rechargement sur changement de structure, préservation des `unique_id`.

## Résultats (2026-11-24)

| Indicateur | Avant | Après |
| --- | --- | --- |
| Tests | 49 | 135 |
| Couverture | 80 % | 95,3 % |
| mypy | 6 erreurs (non strict) | 0 (strict) |
| HA 2025.8.0 / 2026.10.4 | ✅ / ✅ | ✅ / ✅ |

## Validation sur le matériel réel

Opérations en lecture seule uniquement (aucune commande, aucune modification de configuration, aucun déploiement) :

| Vérification | Résultat |
| --- | --- |
| GET de tous les endpoints de configuration et d'état sur 12 dingz (11 × 2.6.0, 1 × 2.4.3) | ✅ 200 partout |
| Client REST de l'intégration + détection des capacités exécutés contre les 12 dingz (`GET` uniquement) | ✅ entités attendues calculées, cohérentes avec HA (23 lumières fantômes `unknown` supprimées, 3 lumières réelles conservées) |
| Abonnement MQTT passif 15 min (`dingz/#`) | ✅ topics et index confirmés, unité d'énergie mesurée |
| Commandes (lumières, stores, thermostat, LED, redémarrage), configuration MQTT | ⏸ non effectué : autorisation requise |
| Version modifiée dans une instance HA de test ou de production | ⏸ non effectué : autorisation requise |
| Thermostat, DDI, ventilateur, protection antigel | ⛔ bloqué : aucun matériel configuré ainsi |
