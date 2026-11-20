# MindSight — Démarrer la constellation dans TouchDesigner

Dans la performance MindSight, un **agent LLM** dialogue avec la personne participante. La constellation traduit les impressions de l’agent en une animation qui se révèle au drop musical. Pour le premier essai, deux curseurs remplacent les valeurs de l’agent. L’équipe artistique peut ainsi régler le mouvement et décider ce que chaque dimension change à l’écran. [Déroulé de la performance](MindSight%20-%20Livrable%20attendu%20pour%20le%20hackathon.md)

## 1. Faire apparaître les étoiles

Sur Windows ou macOS, ouvre un nouveau projet TouchDesigner et travaille dans `/project1`. Appuie sur **Tab** pour ajouter un nœud. Le menu sépare notamment les **SOP** (géométrie), les **CHOP** (signaux numériques), les **COMP** (composants), les **MAT** (matériaux) et les **TOP** (images). [Installation et prise en main](https://docs.derivative.ca/Getting_Started_With_TouchDesigner)

1. Ajoute un **Sphere SOP** nommé `distribution`. Choisis le type **Polygon** et un rayon de `1` sur les trois axes. Branche-le à un **Sprinkle SOP** en mode **Surface** pour répartir les étoiles de façon irrégulière. Tu peux aussi utiliser directement les sommets de la sphère pour vérifier le montage.
2. Ajoute un **SOP to CHOP** nommé `positions`. Glisse le Sprinkle SOP dans son champ **SOP** et vérifie que **Position** est activé. Son aperçu doit afficher les canaux `tx`, `ty` et `tz`.
3. Ajoute un **Geometry COMP** nommé `etoiles`. Entre dedans et remplace la géométrie par une petite **Sphere SOP** de type **Polygon**, de rayon `0.015` sur les trois axes. Active ses drapeaux **Display** et **Render**. Remonte dans `/project1`, active **Instancing** dans la page **Instance** de `etoiles`, puis glisse `positions` dans **Default Instance OP**. Renseigne **Translate X**, **Y** et **Z** avec `tx`, `ty` et `tz`. Chaque position reçoit alors une petite sphère.
4. Ajoute un **Constant MAT** et glisse-le dans le champ **Material** de `etoiles`. Choisis une couleur claire pour voir les étoiles sans ajouter de lumière. Crée un **Camera COMP** à `Translate Z = 5` et un **Render TOP**. Dans le Render TOP, indique la caméra créée dans **Camera** et `etoiles` dans **Geometry**. Vérifie l’image dans l’aperçu du Render TOP.

[Répartition des points](https://docs.derivative.ca/Sprinkle_SOP) · [Conversion en canaux](https://docs.derivative.ca/SOP_to_CHOP) · [Instancing](https://docs.derivative.ca/Geometry_COMP) · [Rendu 3D](https://docs.derivative.ca/Render_TOP)

## 2. Simuler deux dimensions avec des curseurs

1. Ajoute deux **Slider COMP**. Dans **Slider**, choisis **Slider U** pour chacun et saisis les étiquettes **Ouverture** et **Énergie**. Active **Viewer Active** sur chaque curseur pour le manipuler dans le graphe. Relie chaque sortie à un **Rename CHOP** et renomme son unique canal en `ouverture` ou `energie`. Relie les deux sorties à un **Merge CHOP**. Tu dois voir deux canaux distincts, chacun entre `0` et `1`.
2. Relie le Merge à un **Lag CHOP**. Choisis **Seconds** dans **Lag Unit** et règle les deux valeurs de **Lag** à `0.5`. Après le Lag, fais deux branches avec un **Select CHOP** par canal, puis un **Math CHOP** par branche. Dans la page **Range**, règle **From Range** à `0–1` et choisis les plages suivantes.

   | Canal | To Range | Paramètre à piloter |
   | --- | --- | --- |
   | `ouverture` | `0.65–1.4` | **Uniform Scale** du Geometry COMP `etoiles` |
   | `energie` | `2–35` | **Amplitude** d’un **LFO CHOP** sinusoïdal à `0.2 Hz` |

3. Pour relier un canal à un paramètre, active **Viewer Active** sur le CHOP, glisse le canal depuis son aperçu sur le champ du paramètre et choisis **Export CHOP**. Exporte aussi la sortie du LFO vers **Rotate Y** de `etoiles`. Avec la lecture active, le nuage oscille, et le curseur **Énergie** règle l’ampleur de cette oscillation.

Essaie trois profils fictifs avec **Ouverture / Énergie** à `0.2 / 0.2`, `0.8 / 0.2` et `0.8 / 0.8`. Le premier doit paraître compact, le deuxième plus étendu et le troisième plus animé. Ces correspondances sont des choix artistiques. L’échelle globale agrandit aussi les petites sphères. Pour les garder à taille fixe, exporte le canal d’ouverture vers les trois champs **Scale** d’un **Transform SOP** placé entre le Sprinkle et la conversion en CHOP, puis remets l’échelle de `etoiles` à `1`.

[Slider COMP](https://docs.derivative.ca/Slider_COMP) · [Lag CHOP](https://docs.derivative.ca/Lag_CHOP) · [Math CHOP](https://docs.derivative.ca/Math_CHOP) · [Export vers un paramètre](https://docs.derivative.ca/CHOP_Export)

## 3. Brancher l’agent quand le visuel est prêt

Ajoute un **OSC In CHOP** sur le port UDP `9000`. Insère un **Switch CHOP** juste avant le Lag. Branche la sortie du Merge en entrée `0` pour les répétitions, et l’OSC In en entrée `1` pour la démo. Vérifie dans l’aperçu OSC que les canaux portent les mêmes noms que les curseurs. Au besoin, renomme-les avec un **Rename CHOP** avant le Switch.

Pour vérifier le branchement sur la même machine, installe `python-osc` dans ton environnement Python (`python -m pip install python-osc`), puis envoie deux valeurs fictives avec ce test. Passe ensuite le Switch à `1`.

```python
from pythonosc.udp_client import SimpleUDPClient

client = SimpleUDPClient("127.0.0.1", 9000)
client.send_message("/ouverture", 0.8)
client.send_message("/energie", 0.6)
```

Pour la performance, l’agent pourra envoyer les deux valeurs entre `0` et `1` lorsqu’il actualise ses impressions. La scène pourra préparer le mouvement pendant la montée musicale et afficher l’image au drop. [Réception OSC](https://docs.derivative.ca/OSC_In_CHOP) · [Switch CHOP](https://docs.derivative.ca/Switch_CHOP)
