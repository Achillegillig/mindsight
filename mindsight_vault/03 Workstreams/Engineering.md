# Engineering

## Architecture overview

## Stack / repositories

## Setup instructions

## APIs and integrations
Do not paste API keys or access tokens here.

## Current blockers

## Next actions
- [ ]

## Lancer le chat avec OpenRouter

Avec Python 3.12, renseigner `OPENROUTER_API_KEY` dans le fichier `.env`
à la racine du projet. Créer une [clé API OpenRouter](https://openrouter.ai/settings/keys)
si nécessaire. Le fichier est ignoré par Git. Une variable d’environnement
`OPENROUTER_API_KEY` déjà définie est prioritaire sur le fichier.

Depuis la racine du projet, dans le Terminal de Linux Mint :

```sh
python3 -m pip install -r requirements.txt
python3 -m app.main --open
```

Garder le terminal ouvert. MindSight ouvre Firefox sur l’adresse affichée.
Si le port 8000 est occupé, MindSight utilise un port libre.
La clé reste côté serveur. Le serveur envoie le préprompt et l’historique
à OpenRouter à chaque tour. Pour la démo, utiliser des récits fictifs.

Le modèle par défaut est `deepseek/deepseek-v4-flash`. Pour le changer,
ajouter `--model fournisseur/modèle` à la commande de démarrage.
Modifier la clé `system_prompt` dans `app/prompts.json` pour
ajuster le préprompt. Le serveur le relit à chaque message. La question
d’ouverture est chargée au démarrage.

## Tester la conversation simulée

Lancer `python3 -m app.main --simulate` pour utiliser les relances
préparées avec le serveur. Pour ouvrir la démo simulée directement dans
Firefox, générer le fichier HTML puis double-cliquer dessus :

```sh
python3 -m app.main --export mindsight-demo.html
```

## Extraction par tour

Le navigateur ouvre une session avec `POST /api/conversation/session`, puis
envoie l’historique, l’identifiant de session et un identifiant d’envoi
à `POST /api/conversation/turn`. Le serveur renvoie la relance pendant que
l’analyste traite le tour. Un renvoi avec le même identifiant et le même
historique réutilise la relance obtenue lors du premier envoi.

L’analyste Haystack relève les observations et contrôle leurs citations avant
de les interpréter selon `app/dimensions.yaml`. Les citations et leurs positions
sont calculées par rapport à la réponse validée par le serveur. Les clients
qui transmettent seulement l’historique à `/api/conversation/turn` reçoivent
la relance et l’extraction locale dans le même JSON, avec les tableaux
`visual_elements`, `expressed_feelings`, `observations` et `dimensions`.
Pour `dimensions`, `[]` indique une analyse sans lecture retenue, et `null`
une passe d’interprétation indisponible.

## Enregistrer les résultats de test

Depuis la racine du projet, lancer le serveur avec l’option `--record` :

```sh
python3 -m app.main --open --record
```

Chaque tour terminé ajoute une ligne à `test-results.jsonl`. Elle contient
la question, la réponse de l’utilisateur, la relance et l’extraction.
Le fichier est créé au premier tour et ignoré par Git. Le journal est
facultatif et prévu pour les essais sur des récits fictifs.

## Architecture et raccord à TouchDesigner

| Partie | Où lire le code | Responsabilité |
| --- | --- | --- |
| Conversation | `app/dialogue.py`, `app/prompts.json`, `app/static/chat.js` | Vérifier l’historique, définir le préprompt et afficher la prochaine question. |
| Extraction | `app/extraction.py`, `app/dimensions.yaml` | Relever les observations citées, puis les interpréter avec les fiches du catalogue. |
| Serveur | `app/server.py` | Coordonner les tours et conserver en mémoire les épisodes et les analyses de la session. |
| Quantification | `app/quantification.py` | Calculer l’appui et le contre-appui en plafonnant la contribution de chaque épisode. |
| Animation | `app/mcp_server.py`, `visualization/mcp_to_osc.py` | Lire les révisions du portrait sur MCP et envoyer les valeurs configurées à TouchDesigner. |
| Démarrage et accès au modèle | `app/main.py`, `app/openrouter.py` | Démarrer le serveur local et envoyer les requêtes à OpenRouter. |

Au démarrage, MindSight affiche les adresses du chat et de MCP. Ouvrir le chat,
puis prendre l’identifiant de session affiché dans le terminal du serveur.
Dans un second terminal, lancer le pont en remplaçant `IDENTIFIANT` par cette
valeur.

```sh
python3 -m visualization.mcp_to_osc --session-id IDENTIFIANT
```

Le pont lit `mindsight://sessions/{session_id}/dimensions` sur
`http://127.0.0.1:8001/mcp` et envoie les messages OSC au port UDP 9000.
Si MindSight est démarré avec `--mcp-port`, passer l’adresse affichée au pont
avec `--mcp-url`. **Recommencer** crée une autre session. Indiquer alors son
nouvel identifiant au pont. Les sessions sont conservées jusqu’à l’arrêt du
serveur.

Modifier `app/dimensions.yaml` pour changer les dimensions ou les poids,
puis redémarrer MindSight. Modifier `visualization/mapping.yaml` pour choisir
les canaux et les valeurs de repos OSC, puis relancer le pont. Un signal absent
vaut `null` dans MCP. Le pont utilise la valeur de repos du canal si elle est
renseignée.

## Exécuter les tests

```sh
python3 -m unittest discover -s tests -v
```

Le test de bout en bout utilise un fournisseur de modèle local, la vraie
connexion MCP et un récepteur UDP. Il vérifie la déduplication des envois,
le regroupement des épisodes et les valeurs OSC avec des récits fictifs.
