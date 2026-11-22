# MindSight — Guide technique du portrait OpenGL

Le lecteur natif ouvre une fenêtre OpenGL indépendante. En direct, il reçoit les dimensions de la dernière conversation MindSight via le pont OSC existant. Le mode démo et le mode manuel permettent d’examiner le rendu seul. [Lecteur OpenGL](../../visualization/mindsight_opengl.py) · [Version de référence du 22 novembre 2026](../../visualization/mindsight_opengl_reference_2026_11_22.py)

## Installation et démarrage

Depuis la racine du dépôt, dans PowerShell, utilise l’environnement `.venv`. Python 3.12 et pyglet 2.1 ont servi à la validation. La machine doit fournir un contexte OpenGL 3.3. Pour préparer un nouvel environnement, exécute les commandes suivantes.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install "pyglet>=2.1,<3"
```

**Démo visuelle.** Elle enchaîne le repos, les dimensions isolées et plusieurs profils combinés.

```powershell
.\.venv\Scripts\python.exe -m visualization.mindsight_opengl --demo
```

**Chat et visualisation en direct.** Renseigne `OPENROUTER_API_KEY` dans `.env` pour activer l’analyse de la conversation. Installe FFmpeg avec l’encodeur `libx264` et rends `ffmpeg` accessible dans le `PATH` pour l’export vidéo. La commande suivante lance le serveur du chat et ouvre le lecteur OpenGL.

```powershell
.\.venv\Scripts\python.exe -m app.main --opengl
```

Ouvre l’adresse affichée par `app.main`, généralement `http://127.0.0.1:8000`, puis démarre une conversation. Si le port OSC `9000` est occupé, ajoute `--osc-port 9001`. Avec `--simulate`, le chat utilise des relances préparées et les scores restent à zéro.

Dès que les scores finaux sont prêts, le cercle se transforme et le lecteur lance un export par session dans `videos/`. Le MP4 de 80 secondes montre le cercle et les six curseurs visuels pendant 30 secondes, puis la transformation et l’animation pendant 50 secondes. [Script d’export](../../visualization/export_mindsight_video.py)

## Réglage des dimensions

Clique dans la fenêtre OpenGL avant d’utiliser le clavier.

| Touche | Action |
| --- | --- |
| `1` à `6` | Isole dans l’ordre Analytique, Enthousiaste, Torturée, Créative, Rêveuse et Extraversion. Le trait isolé commence à 10/10. |
| `↑` / `↓` | Ajuste le trait isolé par pas de 1. |
| `0` | Ramène les six dimensions au repos. |
| `7` / `8` | Enchaîne des profils combinés ou des variations rapides. |
| `D` / `L` | Lance la démo ou reprend l’entrée OSC. |
| `Espace` / `F` | Met en pause ou bascule le plein écran. |

Pour démarrer avec plusieurs valeurs précises sur 10, répète `--trait`. Les identifiants disponibles sont `analytique`, `enthousiasme`, `angoisse`, `creativite`, `reveur` et `extraversion`. En mode manuel, `torture` est accepté comme alias d’`angoisse`.

```powershell
.\.venv\Scripts\python.exe -m visualization.mindsight_opengl --trait analytique=8 --trait reveur=4 --trait extraversion=5
```

## Du score à l’image

1. **Conversation et OSC.** MindSight publie la dernière révision des dimensions via MCP. Le champ `appui` vaut `score / 10` lorsqu’un score est documenté. Le pont applique l’échelle et la valeur de repos du mapping pour envoyer des intensités de 0 à 10 sur `127.0.0.1:9000` en UDP. Le lecteur ramène chaque valeur reçue dans `[0, 1]` et lisse séparément les six entrées. Les constantes de temps vont de 0,28 s pour l’enthousiasme à 1 s pour la rêverie. [Quantification](../../app/quantification.py) · [Mapping OSC](../../visualization/mapping_traits.yaml)
2. **Simulation.** Chaque particule conserve sa position, sa vitesse, son âge, sa position précédente, son éclat et sa contrainte locale. Le shader compose une cible ondulante avec l’attraction vers les anneaux et rayons, les impulsions, les bifurcations, le cisaillement et la dérive diffuse. Un ressort amorti rapproche chaque particule de cette cible. Le calcul avance par pas de `1/60 s`. Le *transform feedback* alterne les buffers GPU de lecture et d’écriture à chaque pas.
3. **Rendu.** Les mêmes positions alimentent les grains, les voiles sous forme de quadrilatères translucides et les filaments qui relient des voisins d’une même fibre. La perspective et l’atténuation atmosphérique distinguent trois plans. La composition alpha dans un tampon linéaire `RGBA16F` permet aux fibres sombres de rester visibles. Le fond est interpolé en sRGB entre les repères TouchDesigner, converti en linéaire pour la composition, puis réencodé en sRGB à l’affichage. [Direction artistique et palette](<MindSight - Direction artistique du portrait OpenGL.md>)

## Validation et compatibilité

Pour valider un réglage, compare chaque trait à 0, 5 et 10, puis observe les profils mixtes avec `7` et les transitions rapides avec `8`. Le lecteur utilise par défaut 256 fibres de 96 particules, soit 24 576 particules. `--strands 160` permet de réduire la charge. Lors de la validation initiale, un profil dense à 1 920 × 1 080 a pris 15,9 ms par image en médiane sur Intel UHD.

**Trait Torturée en direct.** Le lecteur accepte le canal `/trait/torture` du mapping actuel et l’identifiant historique `angoisse`. Pour isoler la dimension, utilise la touche `3` ou `--trait torture=8`. [Mapping OSC](../../visualization/mapping_traits.yaml)
