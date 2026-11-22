# Brancher le portrait MindSight dans TouchDesigner

Ouvre [MindSight_Portrait_OSC.toe](../../visualization/MindSight_Portrait_OSC.toe), préparé à partir de `NewProject.2.toe` pour TouchDesigner 2025.33230. Vérifie que tu vois le récepteur `/osc`, les composants `/trait_…`, le panneau `/controles` et la sortie `/composition/final`.

Si TouchDesigner reste à installer, récupère l’installeur de la version utilisée par l’artiste et active ta licence au premier lancement dans **Key Manager**. [Installation Windows et macOS](https://docs.derivative.ca/Install_TouchDesigner)

Chaque trait a un curseur `Intensite` de `0.0` à `10.0`. Le réseau visuel interpole les valeurs de sa table `etats` entre les repères `0`, `5` et `10`. Le récepteur OSC sert à écrire dans le même paramètre que le curseur. La composition finale utilise ensuite ce paramètre pour recalculer l’image.

## 1. Choisir le port et le réseau

| Connexion | Valeur dans MindSight | Où la configurer |
| --- | --- | --- |
| Python → TouchDesigner | `127.0.0.1:9000` en UDP, par défaut | `Port` dans l’OSC In DAT. Options `--osc-host` et `--osc-port` dans le pont Python. |
| Application → pont Python | `http://127.0.0.1:8001/mcp` par défaut | Utiliser l’URL `MCP` affichée au démarrage. Le pont accepte `--mcp-url`. |

Commence avec les deux programmes sur le même ordinateur. Pour un montage sur deux machines, laisse **Local Address** vide ou indique l’IP locale de la machine TouchDesigner. Passe cette même IP au pont via `--osc-host`. Autorise la réception UDP `9000` dans le pare-feu de cette machine si nécessaire.

## 2. Brancher les dix adresses

Chaque adresse reçoit un float OSC compris entre `0.0` et `10.0`. Le préréglage `visualization/mapping_traits.yaml` émet les six dimensions d’`app/dimensions.yaml`. Le récepteur conserve les dix adresses historiques dans la première colonne. La colonne **Dimension MindSight** donne la source et, si le nom diffère, son adresse OSC canonique.

| Adresse OSC historique | Paramètre `Intensite` du composant | Effet dans l’image | Dimension MindSight |
| --- | --- | --- | --- |
| `/trait/enthousiasme` | `/trait_enthousiasme` | De l’absence de fleur à une fleur explosive | `enthousiasme` |
| `/trait/reveur` | `/trait_reveur` | Densité des nuages et des étoiles | `reveur` |
| `/trait/creativite` | `/trait_creativite` | Portée des explosions et nombre de figures | `creativite` |
| `/trait/analytique` | `/trait_analytique` | Construction des anneaux et des modules | `analytique` |
| `/trait/torture` | `/trait_torture` | Lignes accidentées et coups de pinceau au premier plan | `angoisse` via `/trait/angoisse` |
| `/trait/bienveillance` | `/trait_bienveillance` | Densité des flocons et de la neige déposée | `bienveillance` |
| `/trait/autocritique` | `/trait_autocritique` | Étirement, torsion et ondulation | `autocritique` |
| `/trait/confiance_en_soi` | `/trait_confiance_en_soi` | Bord du cadre, du fondu au net | `confiance_en_soi` |
| `/trait/extraversion` | `/trait_extraversion` | Fond bleu-gris à `0`, ocre à `5` et jaune à `10` | `extraversion` |
| `/trait/impulsif` | `/trait_impulsif` | Durée, flou et flashs de l’apparition | `impulsivite` via `/trait/impulsivite` |

Les valeurs reçues sont visibles dans `/osc/dimensions`. Les canaux `/trait/passionne`, `/trait/force_de_proposition`, `/trait/domination`, `/trait/introversion` et `/trait/manque_de_confiance_en_soi` ont une ligne dans cette table avec une destination vide, car la scène ne contient pas de contrôles dédiés. Le préréglage multiplie l’appui MCP par `10` pour retrouver le score sur dix, avec `0.0` comme valeur de repos. L’ouverture du `.toe` seul conserve les valeurs artistiques enregistrées.

### Messages pour le pilotage manuel

| Adresse | Arguments OSC | Effet |
| --- | --- | --- |
| `/profil` | 10 floats de `0.0` à `10.0`, dans l’ordre du tableau | Applique toutes les intensités dans un seul callback. |
| `/trait/impulsif/rejouer` | Un entier `1` | Appelle `rejouer()` dans `/trait_impulsif/apparition`. |
| `/trait/impulsif/boucle` | Un entier `0` ou `1` | Règle `Boucle`. À `1`, l’apparition repart toutes les 12 s. |
| `/finition/force` | Un float de `0.0` à `1.0` | Règle la quantité de matière picturale via `/finition` → `Force`. |

L’ordre de `/profil` est `enthousiasme`, `reveur`, `creativite`, `analytique`, `torture`, `bienveillance`, `autocritique`, `confiance_en_soi`, `extraversion`, `impulsif`. Le pont MindSight utilise des messages individuels. Les commandes de ce tableau sont disponibles pour une répétition ou une régie manuelle.

## 3. Vérifier ou recréer le récepteur

Dans le **Network Editor**, remonte à la racine `/`, puis entre dans le **Base COMP** `osc`. Sélectionne `osc_in` et appuie sur **P** pour voir ses paramètres. Dans **Connect**, vérifie **Active** sur On, **Protocol** sur **Messaging (UDP)**, **Port** sur `9000` et **Local Address** sur `127.0.0.1` pour un test local. Dans **Received Messages**, vérifie **OSC Address Scope** sur `*`, **Callbacks DAT** sur `osc_in_callbacks` et **Maximum Lines** sur `100` pour conserver des lots complets de six messages. [OSC In DAT](https://docs.derivative.ca/OSC_In_DAT)

Pour réinstaller le récepteur depuis le fichier original, ouvre `NewProject.2.toe` dans TouchDesigner puis **Dialogs → Textport and DATs** en mode Python. Charge le script d’installation avec `run_path`. Adapte le chemin si le dépôt est ailleurs et choisis un autre nom de sortie si le fichier livré existe déjà. [Script d’installation](../../visualization/setup_touchdesigner_osc.py)

```python
from runpy import run_path
script = run_path(r"C:/Users/achil/Documents/projets_hack1robo/mindsight/visualization/setup_touchdesigner_osc.py")
script["install"](r"C:/Users/achil/Documents/projets_hack1robo/mindsight/visualization/MindSight_Portrait_OSC_reconstruit.toe")
```

Pour éditer le récepteur à la main, ouvre le Text DAT `/osc/osc_in_callbacks` avec **Edit Contents…** et utilise le fichier du callback comme référence. Les curseurs de `/controles` sont liés aux paramètres `Intensite` des traits. Le script écrit dans le maître du lien **Bind** et signale les cibles pilotées par expression ou export. [Callback](../../visualization/touchdesigner_osc_callbacks.py) · [Liaisons de paramètres](https://docs.derivative.ca/Binding)

## 4. Tester avant de lancer MindSight

Depuis la racine du dépôt, crée un environnement Python 3.12 et installe les dépendances du projet. Si `.venv` existe déjà, commence à la deuxième ligne. `python-osc` est déjà dans `requirements.txt`. Lance la commande de test depuis le terminal avec TouchDesigner ouvert.

**Windows PowerShell**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "from pythonosc.udp_client import SimpleUDPClient; SimpleUDPClient('127.0.0.1', 9000).send_message('/trait/extraversion', 10.0)"
```

**macOS**

```sh
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -c "from pythonosc.udp_client import SimpleUDPClient; SimpleUDPClient('127.0.0.1', 9000).send_message('/trait/extraversion', 10.0)"
```

1. Dans le panneau du nœud `/osc/osc_in`, vérifie qu’une ligne contient `/trait/extraversion` et `10.0`. Elle confirme la réception UDP.
2. Ouvre **Dialogs → Textport and DATs**. `op('/trait_extraversion').par.Intensite.eval()` doit renvoyer `10.0`. Vérifie aussi le curseur dans `/controles`. Ouvre le viewer de `/composition/final` pour voir le fond jaune, puis renvoie la même commande avec `0.0` pour retrouver le bleu-gris. [Textport](https://docs.derivative.ca/Textport)
3. Pour contrôler l’ordre des dix traits, envoie `/profil` avec `[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]` comme deuxième argument de `send_message`. Dans `/controles`, compare les valeurs avec le tableau des adresses. Tu peux aussi tester chaque adresse seule en remplaçant `/trait/extraversion` par son nom dans la commande.

| Symptôme | À vérifier |
| --- | --- |
| Le DAT reste vide | **Active**, protocole UDP, port `9000` et adresse de destination. Ferme une autre instance TouchDesigner qui écouterait déjà sur le même port, par exemple la constellation. |
| Enthousiasme ou créativité disparaissent du journal | Vérifie **Maximum Lines** dans `osc_in`. `/osc/dimensions` conserve une ligne par dimension et affiche le dernier score reçu. |
| La ligne arrive et le paramètre ne bouge pas | Référence **Callbacks DAT**, contenu enregistré, adresse exacte et erreurs du Textport. Vérifie le nom interne `Intensite` et le mode du paramètre maître. |
| La valeur change et l’image semble fixe | Consulte `/apercu/out1` et `/composition/final`. L’apparition démarre au premier calcul du rendu. La neige accumulée fond en environ 12 s. Pour revoir l’effet d’`impulsif`, envoie `/trait/impulsif/rejouer` avec l’entier `1`. |

## 5. Lancer MindSight avec le pont OSC

Laisse le portrait ouvert dans TouchDesigner. À la racine du dépôt, lance cette commande dans PowerShell.

```powershell
.\.venv\Scripts\python.exe -m app.main --open --osc
```

Sous macOS, utilise `./.venv/bin/python -m app.main --open --osc`. Quand le chat s’ouvre, le terminal affiche la session suivie sur la ligne `OSC — session …`. Le pont envoie les scores à `127.0.0.1:9000` en UDP et suit la nouvelle session si tu cliques sur **Recommencer**. `Ctrl+C` dans le terminal arrête le chat et son pont.

Le mode réel utilise `OPENROUTER_API_KEY` dans `.env` ou dans l’environnement. Avec `--simulate`, les seize valeurs de repos permettent de vérifier la connexion. Si tu as changé le port du DAT, passe le même numéro à `--osc-port`.

### Raccorder un chat déjà ouvert

Si tu as démarré le chat seul, relève `Session MindSight` dans le terminal du serveur. Dans un second terminal, remplace `IDENTIFIANT` par cette valeur.

```sh
python -m visualization.mcp_to_osc --session-id IDENTIFIANT --mapping visualization/mapping_traits.yaml
```

Ajoute `--once` pour un envoi de test. Si le terminal de MindSight affiche une autre URL MCP, ajoute `--mcp-url URL_AFFICHEE`. En cas de changement de port OSC, règle la même valeur sur le DAT et avec `--osc-port`. En mode manuel, relance le pont avec le nouvel identifiant après **Recommencer**.

## 6. Lire la chaîne de rendu

```text
/composition/out1  (rêveur → analytique → créativité → enthousiasme → torturé)
        ↓
trait_bienveillance → trait_autocritique
        ↓
trait_confiance_en_soi  (fond de trait_extraversion et bord du cadre)
        ↓
/finition → trait_impulsif → /composition/final  (1080 × 1080)
```

`/apercu/out1` affiche la grille des traits et `/trait_<nom>/out1` isole la sortie d’un trait. Les réglages de câblage `Source`, `Fond`, `Image` et `Formes` se font dans le réseau. Pour l’usage courant, utilise `Intensite` et les commandes manuelles du tableau. Si des transitions saccadent entre deux révisions, teste le lissage sur un trait avant de le généraliser et vérifie que le curseur manuel reste opérationnel.

Pour déléguer le branchement du `.toe`, utilise le [prompt pour l’agent TouchDesigner](<MindSight - Prompt pour configurer le portrait OSC.md>).

## Annexe des réglages artistiques

Les tables reprennent les valeurs de référence du fichier de l’artiste. Les colonnes 0, 5 et 10 sont les paliers de la table `etats`. Les constantes servent à ajuster le style dans TouchDesigner.

### Enthousiasme (`/trait_enthousiasme`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| taille | 0 | 0.5 | 1.0 | rayon de la fleur |
| opacite | 0 | 0.9 | 1.0 | opacité |
| deploiement | 0 | 0.5 | 1.0 | ouverture des pétales, éclats, particules |
| *constantes* |  |  |  | rayon_max 0.29, 12 pétales, vitesse 0.4, couleur #FF206E, cycle feu d'artifice 7 s, touches 16 px, impressionnisme 0.6 |

### Rêveur (`/trait_reveur`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| couverture | 0 | 0.55 | 1.0 | part des 10 nuages présents |
| taille | 0 | 0.75 | 1.0 | échelle des nuages |
| opacite | 0 | 0.8 | 0.92 | opacité |
| etoiles | 0 | 0.4 | 1.0 | densité d'étoiles |
| *constantes* |  |  |  | couleurs #7EDDC2 #97DFFC #CDEDF6 #A1C6EA #33A1FD, étoiles #FFE66D, vitesse 0.12 |

### Créativité (`/trait_creativite`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| etendue | 0 | 0.5 | 1.0 | portée des feux depuis le centre |
| nombre | 0 | 6 | 14 | explosions simultanées |
| taille | 0 | 0.7 | 1.0 | taille des gerbes |
| trainees | 0 | 0.5 | 1.0 | traînées pointillées |
| opacite | 0 | 0.85 | 1.0 | opacité |
| figures | 0 | 3 | 8 | figures flottantes (Kandinsky) |
| taille_figures | 0 | 0.8 | 1.0 | taille des figures |
| *constantes* |  |  |  | portée max 0.72, cycle 4,5 s, couleur #FF206E, palette k1–k6, touches 10 px, impressionnisme 0.6 |

### Analytique (`/trait_analytique`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| construction | 0 | 0.5 | 1.0 | part des modules construits |
| lignes | 3 | 4 | 6 | lignes par module |
| opacite | 0 | 0.75 | 0.9 | opacité |
| *constantes* |  |  |  | taille 0.78, 6 unités, marge 0.08, épaisseur 2 px, cycle 14 s, couleur #7E7F83 |

### Torturé / angoissé (`/trait_torture`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| lignes | 0 | 4 | 9 | lignes accidentées |
| agitation | 0 | 0.5 | 1.0 | fréquence et force des sursauts |
| epaisseur | 0 | 3 | 5 | épaisseur des lignes (px) |
| coups_pinceau | 0 | 2 | 6 | blocs de pinceau (Soulages) |
| opacite | 0 | 0.85 | 1.0 | opacité |
| *constantes* |  |  |  | durée d'un coup 5 s, couleur #000000 |

### Bienveillance (`/trait_bienveillance`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| densite | 0 | 0.45 | 1.0 | part des flocons présents |
| taille | 0 | 0.8 | 1.0 | taille des flocons |
| danse | 0 | 0.6 | 1.0 | balancement / tourbillon |
| depot | 0 | 0.5 | 1.0 | neige qui se pose sur les formes |
| opacite | 0 | 0.85 | 1.0 | opacité des flocons |
| *constantes* |  |  |  | chute 0.05, fonte 12 s, couleur #FFFFFF |

### Autocritique (`/trait_autocritique`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| deformation | 0 | 0.02 | 0.05 | ondulation fluide |
| torsion | 0 | 0.6 | 1.4 | tourbillon (radians) |
| etirement | 0 | 0.12 | 0.3 | étirement directionnel |
| *constantes* |  |  |  | cycle 6 s, échelle 2.5 |

### Confiance en soi (`/trait_confiance_en_soi`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| flou_bord | 230 | 70 | 0 | dégradé du bord du cadre (px) |
| irregularite | 90 | 20 | 0 | bord qui se dissout (px) |
| *constantes* |  |  |  | vitesse 0.15, couleur de secours #1B1433 (utilisée seulement si `Fond` est vide) |

### Extraversion (`/trait_extraversion`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| couleur | #D2D7DF | #E8D190 | #FDCA40 | couleur du fond |
| *constantes* |  |  |  | marbrure 0.6, brosse 0.5, bords clairs 0.45 |

### Impulsif (`/trait_impulsif`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| brutalite | 0 | 0.5 | 1.0 | fondu doux ↔ clignotements |
| duree_apparition | 3.5 | 1.5 | 0.5 | durée de l'apparition (s) |
| flash | 0 | 0.6 | 1.0 | flashs |
| flou | 40 | 15 | 0 | flou pendant l'apparition (px) |
| duree_disparition | 2.5 | 1.0 | 0.05 | disparition avant réapparition (s) |
| *constantes* |  |  |  | période de boucle 12 s, rythme des clignotements 0,07 s |

### Finition (`/finition`)

Le paramètre `Force` règle l’intensité de la finition de 0 à 1. La table `reglages` fixe la trame à 0.55 (échelle de 5 px), le grain à 0.5, la réserve claire à 0.45 (45 px), le bord d’aquarelle à 0.35 et la marbrure à 0.35.
