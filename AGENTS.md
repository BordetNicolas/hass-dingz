# Contexte du projet

## Objet

Cette base contient l'integration personnalisee Home Assistant `dingz` pour les interrupteurs muraux Dingz (iolo AG). Elle fonctionne localement, sans cloud.

- Le code de l'integration est dans `custom_components/dingz/`.
- Le domaine Home Assistant est `dingz`.
- Python 3.13.2+ et Home Assistant 2025.8.0 sont les versions ciblees.
- La version Home Assistant de `pyproject.toml` doit rester identique a `hacs.json` (controlee par la CI).

## Architecture

### Cycle de vie et donnees

- `__init__.py` initialise un `DingzRuntime` par `ConfigEntry`, puis charge toutes les plateformes declarees dans `PLATFORMS`.
- `DingzRuntime` conserve le client REST, les coordinateurs, les informations du device et le desabonnement MQTT.
- `DingzCoordinator` est la source de donnees principale. Il charge la configuration complete au demarrage puis interroge `GET /api/v1/state` toutes les 10 secondes.
- Si `state.config.timestamp` change, le coordinateur recharge la configuration Dingz. Les entites sont en revanche construites au chargement des plateformes: une nouvelle categorie d'entite necessite actuellement le rechargement de l'entree.
- `DiagnosticCoordinator` interroge la RAM toutes les 60 secondes et ne devrait etre utilise que par les entites de diagnostic.
- Les constantes de temporisation, retry et throttling sont centralisees dans `const.py`.

### REST et MQTT

- REST est la source de verite et l'unique chemin de commande. Ne pas envoyer de commandes par MQTT.
- `api.Client` construit les URL sous `/api/v1`, serialize les commandes et limite les requetes a une toutes les 200 ms. Preserver ce verrouillage et les politiques de retry lors de nouvelles operations.
- Les erreurs HTTP 5xx sont verifiees contre l'etat RAM du Dingz; ne pas supprimer ce traitement.
- Les identifiants MQTT inclus dans `services_config` ne doivent jamais apparaitre dans les logs. Utiliser `_payload_for_log` pour toute journalisation de requete associee.
- MQTT est optionnel et ne s'active que si l'integration MQTT de Home Assistant est configuree. Il accelere les mises a jour et fournit les evenements de boutons indisponibles via REST.
- `mqtt.py` convertit les messages firmware en notifications internes, met a jour la copie de l'etat du coordinateur lorsque possible, puis les diffuse aux entites abonnees.

### Entites

- Chaque appareil physique correspond a un seul `DeviceInfo` et ses entites ne sont creees que lorsque leur fonctionnalite est active dans la configuration Dingz.
- Les `unique_id` doivent etre stables et derives de `runtime.dingz_id` avec `entity_unique_id()`, jamais de l'adresse IP.
- Reutiliser `DingzEntity` ou `DingzOutputEntity` pour les entites pilotees par le coordinateur et leur associer `runtime.device_info`.
- Reutiliser `CoordinatedNotificationStateEntity` pour une entite qui doit reagir a la fois au polling et aux notifications MQTT.
- Une commande REST qui modifie l'etat doit utiliser `DelayedCoordinatorRefreshMixin.delayed_request_refresh()`, car le firmware met un court delai a refleter la commande dans `GET /state`.
- Les plateformes sont separees par domaine Home Assistant (`light.py`, `cover.py`, `sensor.py`, etc.); ajouter une plateforme impose aussi de l'ajouter a `PLATFORMS` dans `__init__.py`.
- Les traductions sont dans `custom_components/dingz/translations/{en,fr,de}.json`. Toute nouvelle `translation_key`, etape de config flow ou issue persistante doit etre traduite dans ces fichiers.

### Configuration et decouverte

- `config_flow.py` accepte une adresse IP ou un hote et normalise l'URL en HTTP si aucun schema n'est fourni.
- L'identite de l'entree est l'identifiant Dingz dans `system_config.id`, avec repli sur la MAC retournee par `/info`.
- Les decouvertes Zeroconf et MQTT demandent toujours confirmation avant de creer une entree.
- Lorsqu'un appareil deja connu est decouvert avec une nouvelle IP, l'URL de l'entree est mise a jour sans recreer les entites.

## Conventions de modification

- Garder les appels bloquants hors de la boucle evenementielle; les acces reseau sont async avec `aiohttp` et la session fournie par Home Assistant.
- Les payloads firmware sont incomplets ou variables: utiliser des acces defensifs (`.get`, `LookupError`) et ne pas supposer qu'une liste est alignee avec sa configuration.
- Declarer les structures de payload dans `api.py` avec les `TypedDict` existants plutot que propager des dictionnaires non types.
- Ajouter les tests cibles dans `tests/test_<module>.py` et les payloads partages dans `tests/fixtures/payloads.py`.
- Les clients Dingz sont simules par la fixture `mock_dingz_client`; les tests Home Assistant utilisent `MockConfigEntry` de `tests/ha_helpers.py`.
- Ne pas modifier les fichiers sous `config/` pour une fonctionnalite de production: ils servent au developpement local.

## Commandes de verification

Installer les dependances de developpement comme la CI:

```bash
uv pip install --system -e ".[test]"
```

Executer les verifications sans modifier les fichiers:

```bash
pytest -q
ruff check .
ruff format --check --diff
```

`./scripts/lint.sh` lance `ruff check . --fix` puis `ruff format`; il modifie donc potentiellement le working tree. La CI execute les tests, Ruff, Hassfest et la validation HACS.
