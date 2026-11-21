# Prompt pour l’agent TouchDesigner

Joindre le `.toe` du portrait et, si possible, le [guide de branchement](<MindSight - Brancher le portrait dans TouchDesigner.md>). Copier le bloc ci-dessous dans la conversation avec l’agent.

```text
Je te confie le projet TouchDesigner du portrait génératif MindSight. Ouvre le
fichier .toe joint et travaille dans une copie nommée MindSight_Portrait_OSC.toe.
Configure le récepteur puis enregistre cette copie avec un chemin où je peux la
récupérer. Utilise les composants artistiques et le panneau /controles existants.

À la racine /, crée ou réutilise le Base COMP /osc. À l’intérieur, crée ou
réutilise /osc/osc_in, un OSC In DAT actif en Messaging (UDP) avec Port 9000.
Pour le test sur un seul ordinateur, règle Local Address sur 127.0.0.1. Relie
le Text DAT /osc/osc_in_callbacks au champ Callbacks DAT et configure
onReceiveOSC avec la signature générée par la version installée. Le guide joint
contient un callback prêt à coller. Si le .toe range les traits dans un autre
réseau, adapte les chemins de destination en gardant les adresses OSC exactes.

Branche ces onze adresses sur le paramètre personnalisé Intensite du composant
indiqué. Chacune reçoit un float OSC. Borne l’intensité entre 0.0 et 10.0.

/trait/enthousiasme    → /trait_enthousiasme.Intensite
/trait/reveur          → /trait_reveur.Intensite
/trait/creativite      → /trait_creativite.Intensite
/trait/analytique      → /trait_analytique.Intensite
/trait/torture         → /trait_torture.Intensite
/trait/bienveillance   → /trait_bienveillance.Intensite
/trait/autocritique    → /trait_autocritique.Intensite
/trait/humour          → /trait_humour.Intensite
/trait/confiance_en_soi → /trait_confiance_en_soi.Intensite
/trait/extraversion    → /trait_extraversion.Intensite
/trait/impulsif        → /trait_impulsif.Intensite

Accepte aussi /profil avec exactement 11 floats dans l’ordre de la liste.
Valide toute la liste avant d’appliquer les valeurs. Ignore les adresses
inconnues et les messages mal formés. Ajoute les commandes manuelles suivantes.

- /trait/impulsif/rejouer, entier 1, appelle rejouer() via le module de
  /trait_impulsif/apparition.
- /trait/impulsif/boucle, entier 0 ou 1, règle /trait_impulsif → Boucle.
- /finition/force, un float borné entre 0.0 et 1.0, règle /finition → Force.

Vérifie les modes des paramètres. Utilise les paramètres maîtres éditables
quand un curseur est en Bind pour que les changements OSC et les changements
manuels restent synchronisés. Garde les tables etats, les liaisons du panneau
et la chaîne de rendu en place. Si une cible est pilotée par une expression ou
un export, repère la source existante avant de choisir où écrire.

Le pont Python de MindSight envoie déjà des floats sur l’échelle 0–10 avec
--mapping visualization/mapping_traits.yaml. Il transmet la créativité, le
trait analytique, la bienveillance, la confiance en soi et l’extraversion.
Les six autres adresses doivent répondre aux commandes OSC manuelles.

Teste la réception depuis un émetteur OSC vers 127.0.0.1:9000. Envoie chaque
adresse individuelle, puis /profil avec les onze valeurs 0.0 à 10.0 par pas
de 1. Vérifie la ligne reçue dans /osc/osc_in, la valeur Intensite dans chaque
composant et le curseur dans /controles. Envoie /trait/extraversion à 10.0 puis
à 0.0 et contrôle que le fond de /composition/final passe du jaune au bleu-gris.
Teste aussi une valeur hors plage, un /profil incomplet et les trois commandes
manuelles. Rétablis les valeurs artistiques de départ avant d’enregistrer.

Indique le chemin du .toe configuré, les essais réellement effectués et les
écarts éventuels. Si tu ne peux pas ouvrir TouchDesigner, fournis un script
d’installation pour son Textport et précise quels essais restent à faire.
```
