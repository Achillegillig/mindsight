# MindSight · Du récit aux bonnes questions

MindSight est un projet du hackathon Hack1Robo. Une personne raconte un souvenir ou une expérience. Le prototype transcrit son récit et en propose un portrait visuel qui peut faire ressortir les thèmes, le ton émotionnel et la manière dont elle parle de ses expériences. On veut aussi tester si quelques bonnes questions aident à mieux comprendre ce qu’elle raconte. [Présentation de MindSight](https://www.hack1robo.fr/projets)

## Pourquoi une première lecture peut se tromper

On parle ici d’**inférence zéro-shot** quand on demande à un modèle de langage de tirer des conclusions d’un récit sans l’avoir entraîné spécialement sur des entretiens accompagnés de mesures de personnalité.

Un récit court est un aperçu sélectif. « Je prépare mes projets, mais j’improvise quand ça change » peut décrire une personne qui s’adapte facilement, un plan peu détaillé ou une situation où quelqu’un d’autre décide. Le ton du récit peut aussi refléter l’humeur du jour, le sujet ou l’aisance à l’oral. Pour parler d’une tendance durable, il faut chercher comment le comportement se répète ou varie selon les situations. [Funder, jugement de personnalité](https://pubmed.ncbi.nlm.nih.gov/7480467/) · [Fleeson, variation des comportements](https://pubmed.ncbi.nlm.nih.gov/11414368/)

Les études sur le zéro-shot obtiennent des résultats variables selon le type de récit, le modèle et le trait étudié. Un accord avec un questionnaire indique que le modèle reproduit en partie cette mesure. Pour savoir si le résultat tient dans la durée ou dans une autre situation, il faut d’autres observations. [Étude sur les entretiens semi-structurés](https://www.jmir.org/2026/1/e87129) · [Étude sur des textes ouverts](https://pmc.ncbi.nlm.nih.gov/articles/PMC12974486/)

## Comment améliorer l’interprétation

1. **Partir des faits racontés.** Garder l’extrait et son contexte. « La personne a changé de plan après une décision du groupe » décrit un épisode. « Elle s’adapte facilement » est une hypothèse plus générale.
2. **Demander au modèle plusieurs explications.** Il peut proposer des hypothèses et imaginer quelles réponses les renforceraient ou les affaibliraient. On peut aussi lui faire produire des cas fictifs pour tester le prototype. Ces simulations aident à préparer l’entretien. Les réponses réelles permettent d’évaluer les interprétations. [Simulation de réponses pour choisir une question](https://proceedings.mlr.press/v267/wang25ff.html)
3. **S’appuyer sur des fiches de psychologie.** Une fiche résume un trait, les comportements qui peuvent éclairer son interprétation, les autres explications possibles et la source. Par exemple, pour explorer l’organisation, elle peut inviter à examiner ce que la personne a préparé, la liberté dont elle disposait et ce qu’elle fait d’habitude dans une situation comparable. [Exemple de cadre de référence, le BFI-2](https://escholarship.org/uc/item/16x6n05t)
4. **Poser une question qui peut changer l’interprétation.** Dans l’exemple des projets, on pourrait demander « Pense à la dernière fois que ça t’est arrivé. Qu’avais-tu préparé avant que la situation change, et qu’as-tu fait ensuite ? » La réponse peut renforcer une explication, en faire émerger une autre ou laisser la question ouverte. ALBA et MAQuA inspirent cette sélection adaptative. Leurs résultats portent sur des mesures de santé mentale et le transfert à la personnalité reste à tester. [ALBA](https://aclanthology.org/2024.naacl-long.136/) · [MAQuA](https://aclanthology.org/2026.eacl-long.313/)

## Ce qu’on peut tester au hackathon

Faire apparaître un premier portrait après le récit libre, puis le mettre à jour après deux ou trois relances. Pour chaque changement, montrer le passage qui l’a motivé et ce qu’il permet d’affirmer · un fait raconté, une tendance liée à un contexte ou une hypothèse encore ouverte.

Pour tester le choix adaptatif des questions, comparer des **relances fixes** et des **relances choisies selon le récit**, avec le même temps de parole et la même méthode d’analyse. Regarder si les nouvelles réponses aident à départager les explications, si les questions restent naturelles et si les changements du portrait s’appuient sur des extraits précis. On peut aussi comparer deux méthodes d’analyse sur **le même récit** pour voir ce que les hypothèses concurrentes et les fiches de psychologie apportent à elles seules.

Pour aller plus loin · [[MindSight - Inférence de personnalité|Synthèse bibliographique MindSight]]
