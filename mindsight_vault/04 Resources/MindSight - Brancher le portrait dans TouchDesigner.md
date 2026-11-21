# Brancher le portrait MindSight dans TouchDesigner

Ce guide part du projet de portrait `NewProject.1.toe` (TouchDesigner 2025.33230 dans la fiche de l’artiste). Ouvre le fichier et crée une copie avec **File → Save As…**, par exemple `MindSight_Portrait_OSC.toe`. Vérifie que tu vois les composants `/trait_…`, le panneau `/controles` et la sortie `/composition/final`.

Si TouchDesigner reste à installer, récupère l’installeur de la version utilisée par l’artiste et active ta licence au premier lancement dans **Key Manager**. [Installation Windows et macOS](https://docs.derivative.ca/Install_TouchDesigner)

Chaque trait a un curseur `Intensite` de `0.0` à `10.0`. Le réseau visuel interpole les valeurs de sa table `etats` entre les repères `0`, `5` et `10`. Le récepteur OSC sert à écrire dans le même paramètre que le curseur. La composition finale utilise ensuite ce paramètre pour recalculer l’image.

## 1. Choisir le port et le réseau

| Connexion | Valeur dans MindSight | Où la configurer |
| --- | --- | --- |
| Python → TouchDesigner | `127.0.0.1:9000` en UDP, par défaut | `Port` dans l’OSC In DAT. Options `--osc-host` et `--osc-port` dans le pont Python. |
| Application → pont Python | `http://127.0.0.1:8001/mcp` par défaut | Utiliser l’URL `MCP` affichée au démarrage. Le pont accepte `--mcp-url`. |

Commence avec les deux programmes sur le même ordinateur. Pour un montage sur deux machines, laisse **Local Address** vide ou indique l’IP locale de la machine TouchDesigner. Passe cette même IP au pont via `--osc-host`. Autorise la réception UDP `9000` dans le pare-feu de cette machine si nécessaire.

## 2. Brancher les onze adresses

Chaque adresse reçoit un float OSC compris entre `0.0` et `10.0`. Les composants et leurs paramètres existent dans le fichier de l’artiste. La colonne **Source MindSight** indique ce que le préréglage `visualization/mapping_traits.yaml` transmet automatiquement. Les autres curseurs restent disponibles dans `/controles` et par OSC pour les essais ou le pilotage artistique.

| Adresse OSC | Paramètre `Intensite` du composant | Effet dans l’image | Source MindSight |
| --- | --- | --- | --- |
| `/trait/enthousiasme` | `/trait_enthousiasme` | De l’absence de fleur à une fleur explosive | Réglage artistique |
| `/trait/reveur` | `/trait_reveur` | Densité des nuages et des étoiles | Réglage artistique |
| `/trait/creativite` | `/trait_creativite` | Portée des explosions et nombre de figures | Appui de `creativite` |
| `/trait/analytique` | `/trait_analytique` | Construction des anneaux et des modules | Appui d’`analyse` |
| `/trait/torture` | `/trait_torture` | Lignes accidentées et coups de pinceau au premier plan | Réglage artistique |
| `/trait/bienveillance` | `/trait_bienveillance` | Densité des flocons et de la neige déposée | Appui d’`empathie`, par choix de rendu |
| `/trait/autocritique` | `/trait_autocritique` | Étirement, torsion et ondulation | Réglage artistique |
| `/trait/humour` | `/trait_humour` | Gonflements et sauts rythmés | Réglage artistique |
| `/trait/confiance_en_soi` | `/trait_confiance_en_soi` | Bord du cadre, du fondu au net | Appui d’`assurance` |
| `/trait/extraversion` | `/trait_extraversion` | Fond bleu-gris à `0`, ocre à `5` et jaune à `10` | Appui d’`extraversion` |
| `/trait/impulsif` | `/trait_impulsif` | Durée, flou et flashs de l’apparition | Réglage artistique |

Le préréglage multiplie les appuis MCP par `10` pour passer de l’échelle `0–1` à l’échelle `0–10`. Un appui de `0.6` devient donc une intensité de `6.0`. Pour ces cinq canaux, l’intensité de repos est `0.0` lorsqu’aucun signal n’est disponible. Les six autres traits gardent leur réglage dans le projet. Les intensités traduisent les indices du récit en effets visuels.

### Messages pour le pilotage manuel

| Adresse | Arguments OSC | Effet |
| --- | --- | --- |
| `/profil` | 11 floats de `0.0` à `10.0`, dans l’ordre du tableau | Applique toutes les intensités dans un seul callback. |
| `/trait/impulsif/rejouer` | Un entier `1` | Appelle `rejouer()` dans `/trait_impulsif/apparition`. |
| `/trait/impulsif/boucle` | Un entier `0` ou `1` | Règle `Boucle`. À `1`, l’apparition repart toutes les 12 s. |
| `/finition/force` | Un float de `0.0` à `1.0` | Règle la quantité de matière picturale via `/finition` → `Force`. |

L’ordre de `/profil` est `enthousiasme`, `reveur`, `creativite`, `analytique`, `torture`, `bienveillance`, `autocritique`, `humour`, `confiance_en_soi`, `extraversion`, `impulsif`. Le pont MindSight utilise des messages individuels. Les commandes de ce tableau sont disponibles pour une répétition ou une régie manuelle.

## 3. Installer le récepteur dans TouchDesigner

1. Dans le **Network Editor**, remonte à la racine `/`, au même niveau que les composants `trait_…`. Appuie sur **Tab**, choisis **Base** dans **COMP** et donne-lui le nom `osc`. Entre dans le composant. Son chemin doit être `/osc`.
2. Dans `/osc`, ajoute un **OSC In** de la famille **DAT** et nomme-le `osc_in`. Un DAT affiche les messages reçus dans une table et peut appeler du Python à chaque réception. Le callback ci-dessous se charge de retrouver le paramètre correspondant dans le réseau.
3. Sélectionne `osc_in` et appuie sur **P** pour afficher les paramètres. Dans **Connect**, règle **Active** sur Off le temps de préparer le callback, **Protocol** sur **Messaging (UDP)**, **Port** sur `9000` et **Local Address** sur `127.0.0.1` pour le test local. Dans **OSC Address Scope** de la page **Received Messages**, laisse `*` pour accepter les adresses du tableau. [Référence OSC In DAT](https://docs.derivative.ca/OSC_In_DAT)
4. Repère le **Text DAT** référencé dans **Received Messages → Callbacks DAT**. Renomme-le `osc_in_callbacks`, ou crée un **Text DAT** de ce nom si le champ est vide. Indique `/osc/osc_in_callbacks` dans **Callbacks DAT** et sélectionne **Callbacks DAT** dans **Execute From**. Sur le Text DAT, clic droit → **Edit Contents…**, colle le code ci-dessous puis enregistre l’édition. Tu peux aussi utiliser **Edit Contents in Textport…**. [Éditer un DAT](https://docs.derivative.ca/DAT) · [Signature du callback](https://derivative.ca/UserGuide/OscinDAT_Class)
5. Remets **Active** sur On. Aucun câble ne relie le récepteur à la composition. Chaque adresse est aiguillée par `onReceiveOSC` vers le paramètre du trait. Le callback suit les liens **Bind** jusqu’au paramètre maître s’il est en mode **Constant**. Si le fichier utilise une expression, un export ou un autre type de maître, le Textport indique la cible à examiner pour conserver son câblage. [Liaisons de paramètres](https://docs.derivative.ca/Binding)

### Code à coller dans `osc_in_callbacks`

```python
from math import isfinite

TRAITS = (
    'enthousiasme', 'reveur', 'creativite', 'analytique', 'torture',
    'bienveillance', 'autocritique', 'humour', 'confiance_en_soi',
    'extraversion', 'impulsif',
)
ADRESSES = {f'/trait/{nom}': nom for nom in TRAITS}


def _borner(valeur, maximum):
    if type(valeur) not in (int, float) or not isfinite(valeur):
        return None
    return max(0.0, min(maximum, float(valeur)))


def _cible(chemin, nom):
    comp = op(chemin)
    param = getattr(comp.par, nom, None) if comp is not None else None
    # Écrire dans le maître préserve les liens avec le panneau de contrôle.
    while getattr(param, 'mode', None) == ParMode.BIND:
        param = param.bindMaster
    if getattr(param, 'mode', None) != ParMode.CONSTANT:
        print(f'OSC — vérifier la cible ou le maître de {chemin}.{nom}')
        return None
    return param


def _intensites(noms, args):
    if len(args) != len(noms):
        return
    valeurs = [_borner(valeur, 10.0) for valeur in args]
    if None in valeurs:
        return
    cibles = [_cible(f'/trait_{nom}', 'Intensite') for nom in noms]
    if any(cible is None for cible in cibles):
        return
    for cible, valeur in zip(cibles, valeurs):
        cible.val = valeur


def onReceiveOSC(dat, rowIndex, message, byteData, timeStamp, address, args, peer):
    if address in ADRESSES:
        _intensites((ADRESSES[address],), args)
    elif address == '/profil':
        _intensites(TRAITS, args)
    elif len(args) == 1:
        valeur = args[0]
        if address == '/trait/impulsif/rejouer' and type(valeur) is int and valeur == 1:
            apparition = op('/trait_impulsif/apparition')
            rejouer = getattr(apparition.module, 'rejouer', None) if apparition is not None else None
            if callable(rejouer):
                rejouer()
            else:
                print('OSC — vérifier rejouer() dans /trait_impulsif/apparition')
        elif address == '/trait/impulsif/boucle' and type(valeur) is int and valeur in (0, 1):
            cible = _cible('/trait_impulsif', 'Boucle')
            if cible is not None:
                cible.val = bool(valeur)
        elif address == '/finition/force':
            force = _borner(valeur, 1.0)
            if force is not None:
                cible = _cible('/finition', 'Force')
                if cible is not None:
                    cible.val = force
```

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
3. Pour contrôler l’ordre des onze traits, envoie `/profil` avec `[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]` comme deuxième argument de `send_message`. Dans `/controles`, compare les valeurs avec le tableau des adresses. Tu peux aussi tester chaque adresse seule en remplaçant `/trait/extraversion` par son nom dans la commande.

| Symptôme | À vérifier |
| --- | --- |
| Le DAT reste vide | **Active**, protocole UDP, port `9000` et adresse de destination. Ferme une autre instance TouchDesigner qui écouterait déjà sur le même port, par exemple la constellation. |
| La ligne arrive et le paramètre ne bouge pas | Référence **Callbacks DAT**, contenu enregistré, adresse exacte et erreurs du Textport. Vérifie le nom interne `Intensite` et le mode du paramètre maître. |
| La valeur change et l’image semble fixe | Consulte `/apercu/out1` et `/composition/final`. La neige accumulée fond en environ 12 s. Pour voir l’effet d’`impulsif`, envoie aussi `/trait/impulsif/rejouer` avec l’entier `1`. |

## 5. Relier la session MindSight

1. Dans un premier terminal à la racine du dépôt, lance `python -m app.main` depuis ton environnement virtuel. Le mode réel utilise `OPENROUTER_API_KEY` dans `.env` ou dans l’environnement. Pour vérifier la connexion sans analyse, lance `python -m app.main --simulate`. Dans ce mode, le pont émet les cinq valeurs de repos. Pour faire varier le rendu avec des valeurs fictives, utilise le test direct ci-dessus.
2. Ouvre l’URL du chat affichée par MindSight et relève `Session MindSight` dans le terminal du serveur. Elle identifie la conversation affichée.
3. Dans un second terminal, lance le pont et remplace `IDENTIFIANT` par cette valeur. Si l’environnement n’est pas activé, remplace `python` par `.\.venv\Scripts\python.exe` sous Windows ou `./.venv/bin/python` sous macOS.

```sh
python -m visualization.mcp_to_osc --session-id IDENTIFIANT --mapping visualization/mapping_traits.yaml
```

Le pont envoie la révision courante, puis les nouvelles révisions quand l’analyse avance. Ajoute `--once` pour un envoi de test. Si le terminal de MindSight affiche une autre URL MCP, ajoute `--mcp-url URL_AFFICHEE`. En cas de changement de port OSC, règle la même valeur sur le DAT et avec `--osc-port`. Si tu cliques sur **Recommencer** dans le chat, relance le pont avec le nouvel identifiant de session.

## 6. Lire la chaîne de rendu

```text
/composition/out1  (rêveur → analytique → créativité → enthousiasme → torturé)
        ↓
trait_bienveillance → trait_autocritique → trait_humour
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

### Humour (`/trait_humour`)

| Paramètre | 0 | 5 | 10 | Rôle |
| --- | --- | --- | --- | --- |
| enflure | 0 | 0.06 | 0.14 | gonflement |
| saut | 0 | 0.015 | 0.035 | hauteur des sauts |
| rotation | 0 | 0.015 | 0.04 | bascule (radians) |
| coups | 0 | 3 | 6 | « ha » par éclat |
| *constantes* |  |  |  | période 3,5 s, 5,5 ha/s |

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
