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

`POST /api/conversation/turn` utilise la dernière question et la dernière
réponse pour un second appel OpenRouter, lancé en parallèle de la relance.
Le serveur renvoie les deux résultats dans le même JSON :

```json
{
  "reply": "Qu’est-ce qui te plaît dans ce paysage ?",
  "extraction": {
    "visual_elements": [{"label": "rivière", "quote": "au fond d’une rivière"}],
    "expressed_feelings": [{"label": "calme", "quote": "Le courant me calme"}]
  }
}
```

Les extraits doivent figurer textuellement dans la réponse de l’utilisateur.
Un tableau vide indique qu’aucun élément de ce type n’a été retenu.
`extraction` vaut `null` en mode simulé ou si l’extraction échoue.
La discussion reste affichée dans le chat et le JSON est visible dans
l’onglet Réseau de Firefox, sur la requête `turn`.

## Enregistrer les résultats de test

Depuis la racine du projet, lancer le serveur avec l’option `--record` :

```sh
python3 -m app.main --open --record
```

Chaque tour terminé ajoute une ligne à `test-results.jsonl`. Elle contient
la question, la réponse de l’utilisateur, la relance et l’extraction.
Le fichier est créé au premier tour et ignoré par Git. Le journal est
facultatif et prévu pour les essais sur des récits fictifs.

## Architecture et plan pour l’animation

| Partie | Où lire le code | Responsabilité |
| --- | --- | --- |
| Conversation | `app/dialogue.py`, `app/prompts.json`, `app/static/chat.js` | Vérifier l’historique, définir le préprompt et afficher la prochaine question. |
| Extraction | `app/extraction.py` | Recevoir la dernière question et la réponse, puis relever des éléments visuels et des ressentis exprimés, avec citations. |
| Animation | Futur module côté navigateur | Recevoir le champ `extraction` du JSON et décider comment faire évoluer le paysage. |
| Serveur | `app/server.py` | Recevoir le tour, lancer la relance et l’extraction, renvoyer leur résultat et enregistrer le tour sur demande. |
| Démarrage et accès au modèle | `app/main.py`, `app/openrouter.py` | Démarrer le serveur local et envoyer les requêtes à OpenRouter. |

Quand une personne envoie un message, le navigateur transmet l’historique au
serveur. Le modèle reçoit cet historique pour la relance. En parallèle,
l’extraction reçoit uniquement la dernière question et la dernière réponse.
Le serveur réunit les résultats dans le JSON décrit plus haut.

Plan de raccord pour le futur module d’animation :

1. Prendre quelques extractions du journal de test comme entrées et définir
   avec les artistes les détails que le premier rendu peut représenter.
2. Vérifier hors ligne qu’une suite de ces entrées fait évoluer une même
   scène. Un champ `extraction` à `null` laisse la scène dans son état actuel.
3. Brancher le rendu sur le champ `extraction` déjà renvoyé à chaque tour,
   puis vérifier avec un nouveau récit que les changements suivent les mots
   de la personne.
