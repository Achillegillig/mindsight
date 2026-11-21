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
`app/prompts.json` regroupe les textes envoyés à DeepSeek. Le bloc
`conversation` contient les questions, la clôture et les relances. À
chaque relance, le serveur relit `conversation.followup_prompts` et
assemble `common` avec `detail` ou `experience`. Les questions fixes et
les consignes `extraction.observe` et `extraction.interpret` sont lues
au démarrage. Pour les modifier, redémarrer MindSight.

## Écouter les questions

Cliquer sur **Activer la voix** pour lire la question affichée et les
suivantes. **Réécouter** répète la dernière question. **Couper la voix**
arrête la lecture. Pour utiliser Azure Speech, définir `AZURE_SPEECH_KEY`
et `AZURE_SPEECH_REGION` dans `.env`, puis redémarrer le serveur.
La région doit correspondre à celle de la ressource Azure. Par défaut,
MindSight utilise `fr-FR-Soleil:MAI-Voice-2.1-Flash` en voix douce
(`softvoice`). Pour changer la voix ou le ton, renseigner
`AZURE_SPEECH_VOICE` ou `AZURE_SPEECH_STYLE`. Le serveur garde la clé et transmet uniquement le
texte demandé pour la lecture à Azure. La voix du navigateur sert de
secours et reste disponible dans l’export HTML autonome.

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
à `POST /api/conversation/turn`. Le serveur attend les observations du tour
pour décider de la suite. Il pose toujours les trois questions fixes.
Avant de relancer, le serveur cherche un ressenti personnel clair ou un
indice de trait validé sur le tour. Si l’un des deux est présent, il avance.
Si les deux manquent, il peut relancer jusqu’à deux fois par question.
Une demande de passer fait aussi avancer. Après la dernière question,
avancer signifie terminer avec `done: true`. Le mode simulé utilise le
même plafond avec des relances préparées.

La première relance approfondit un détail de la dernière réponse. La
seconde voit aussi la première relance et sa réponse. Elle peut inviter à
raconter une situation vécue ou préciser une action déjà racontée. Un renvoi avec le même identifiant et
le même historique réutilise le résultat du premier envoi.

L’analyste Haystack relève les observations et contrôle leurs citations.
L’interprétation selon `app/dimensions.yaml` réutilise ces observations.
Le serveur attend son résultat uniquement quand il pourrait éviter une
relance. Dans les autres cas, l’interprétation continue en arrière-plan,
y compris au dernier tour. Les citations et leurs positions
sont calculées par rapport à la réponse validée par le serveur. Les clients
qui transmettent seulement l’historique à `/api/conversation/turn` reçoivent
la prochaine question et l’extraction du tour dans le même JSON.
L’extraction comprend les tableaux
`visual_elements`, `expressed_feelings`, `observations` et `dimensions`.
Pour `dimensions`, `[]` indique une analyse sans lecture retenue, et `null`
une passe d’interprétation indisponible.

## Enregistrer les résultats de test

Depuis la racine du projet, lancer le serveur avec l’option `--record` :

```sh
python3 -m app.main --open --record
```

Chaque tour analysé ajoute une ligne à `test-results.jsonl`. Elle contient
la question, la réponse de l’utilisateur, la relance et l’état de l’analyse.
Le champ `extraction` conserve les éléments visuels, les ressentis exprimés,
les observations citées et les dimensions interprétées pour ce tour.
Le champ `quantification` contient la version du catalogue, les scores,
le nombre d’épisodes et les références des indices retenus.
Pour le chat, les valeurs sont cumulées dans la session et accompagnées de
sa révision. Pour un appel sans identifiant de session, elles portent sur
le tour analysé.

Le fichier est créé à la première écriture et ignoré par Git. Le journal est
facultatif et prévu pour les essais sur des récits fictifs.

## Afficher l’analyse des traits

```sh
python3 -m app.main --reasoning
```

Le panneau du chat montre les citations validées et leur attribution, les
interprétations par tour, puis l’état des 16 dimensions. Pour une dimension
documentée, le calcul affiche les points retenus par épisode.
Les lectures sont des interprétations situées du discours.
Ajouter `--record` pour conserver également la trace de validation dans le
journal. Avec `--simulate`, le panneau indique que l’analyse est simulée.

## Scores des tempéraments au fil de la session

Le catalogue est dans `app/dimensions.yaml`. La force de proposition est
présentée dans la famille Bonus et suit le même calcul que les autres traits.
Un indice direct vaut 4 points et un indice indirect vaut 2 points. Pour
chaque trait, seul l’indice le plus fort d’un même épisode est conservé.
Les points des épisodes distincts s’additionnent jusqu’à 10. Une réponse
sans nouvel indice laisse le score tel quel. Le score commence à 0,
avec le statut `sans_indice`.

Le chat, le journal et le flux MCP reçoivent le calcul après chaque tour
analysé. Le signal `appui` vaut `score / 10` pour les consommateurs du
flux existant. L’introversion et l’absence de confiance en soi
demandent leurs propres indices. Les choix narratifs fictifs peuvent apporter
un appui indirect pour la créativité, l’humour et la rêverie.

## Architecture et raccord à TouchDesigner

| Partie | Où lire le code | Responsabilité |
| --- | --- | --- |
| Conversation | `app/dialogue.py`, `app/prompts.json`, `app/static/chat.js` | Vérifier l’historique, définir le préprompt et afficher la prochaine question. |
| Extraction | `app/extraction.py`, `app/dimensions.yaml` | Relever les observations citées, puis les interpréter avec les fiches du catalogue. |
| Serveur | `app/server.py` | Coordonner les tours et conserver en mémoire les épisodes et les analyses de la session. |
| Quantification | `app/quantification.py` | Cumuler les points d’appui par épisode avec un plafond de 10 par trait. |
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

## Tableau final des scores

À la fin de la conversation, le tableau affiche les 16 traits de la session
après l’analyse du dernier tour, y compris sans `--reasoning`.
Le tableau reprend le score cumulé de chaque trait. Le statut
`sans_indice` indique que le récit n’a fourni aucun appui pour ce trait.

`GET /api/conversation/session/{session_id}/scores` renvoie le même tableau
en JSON. Tant que la session continue ou que le dernier tour est en cours
d’analyse, `ready` vaut `false` et `traits` est vide.

```json
{
  "session_id": "identifiant-de-session",
  "catalog_version": 4,
  "through_turn": 4,
  "analysis_status": "ready",
  "ready": true,
  "traits": [
    {"id": "humour", "label": "Humour", "score": 2, "status": "documentee"}
  ]
}
```

L’exemple montre une ligne. La réponse finale comprend tout le catalogue.
Le futur raccord TouchDesigner pourra utiliser les identifiants et scores
numériques de ce format.
