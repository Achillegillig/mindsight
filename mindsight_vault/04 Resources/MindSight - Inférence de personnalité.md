# MindSight — Inférence de personnalité à partir d’un récit

Liens internes · [[Project Brief]] · [[Research]] · [[Design]]

MindSight transforme un court récit oral en portrait visuel de la manière dont une personne se raconte. Pour Hack1Robo, la piste proposée est de partir d’un récit libre, puis de poser quelques relances qui aident à départager des interprétations concrètes. La visualisation peut évoluer à mesure que le récit s’enrichit. [Fiche officielle de MindSight](https://www.hack1robo.fr/projets)

## Travaux les plus proches du prototype

| Travail | Résultat ou méthode | Ce que MindSight peut reprendre |
| --- | --- | --- |
| [Beyond Scales and Essays: Artificial Intelligence Chatbots as Personality Interviewers](https://doi.org/10.1080/00223891.2026.2664795) | Évalue un chatbot qui recueille des réponses ouvertes pour estimer les Big Five et compare l’entretien à des formats écrits. | C’est le précédent le plus direct pour l’interface d’entretien. Prévoir une condition récit seul pour mesurer l’apport des relances. |
| [The AI interviewer: multi-faceted evaluation of adaptive questioning by large language models](https://www.nature.com/articles/s41598-026-46517-7) | Sur des entretiens biographiques, un agent décide quand relancer. Des évaluateurs jugent notamment la nécessité, l’ancrage dans le contexte, le caractère ouvert et le ton de la question. | Reprendre ces critères pour relire les relances françaises du prototype. L’étude évalue les questions, tandis que la validité des inférences demande sa propre évaluation. |
| [Personality Inference From Semistructured Interviews Using Large Language Models](https://pmc.ncbi.nlm.nih.gov/articles/PMC13674523/) | Sur 518 transcriptions associées à un BFI-10, l’apprentissage supervisé donne les meilleurs résultats globaux, avec des performances variables selon les traits. Les résultats avec des prompts seuls sont faibles et irréguliers. | Prendre l’inférence directe sur transcription comme point de comparaison. Afficher des hypothèses étayées et réserver les scores à une version évaluée sur des données humaines. |
| [An interviewer–evaluator–judger LLM framework for text-based personality inference](https://www.nature.com/articles/s41598-026-62333-5) | Construit des personas par entretien simulé, puis évalue des explications concurrentes pour classer les traits. Les gains dépendent du corpus et sont les plus nets sur les essais suffisamment détaillés. | Reprendre la comparaison explicite des interprétations. Les réponses simulées peuvent éprouver la logique de sélection d’une relance avant de l’essayer en entretien réel. |
| [Reise et Henson — Computerization and Adaptive Administration of the NEO PI-R](https://doi.org/10.1177/107319110000700404) | Étudie une version adaptative du NEO PI-R qui choisit des items calibrés selon leur information, sur des simulations fondées sur des données réelles (N = 1 059). | S’inspirer de la sélection selon le gain attendu. Pour des questions libres générées au fil de l’entretien, ce gain reste une estimation qualitative jusqu’à calibration. |
| [McAdams — The Life Story Interview](https://cpb-us-e1.wpmucdn.com/sites.northwestern.edu/dist/4/3901/files/2020/11/The-Life-Story-Interview-1995.pdf) | Protocole d’entretien autobiographique centré sur des événements, des relations et des thèmes récurrents. | S’appuyer sur des scènes concrètes pour alimenter le portrait narratif, notamment le rapport au temps, aux autres et à soi. |

## Autres repères

- **Le langage écrit comme signal.** Park et al. entraînent des modèles sur le langage Facebook de 66 732 personnes et les évaluent sur 4 824 autres. Leur protocole examine notamment la convergence avec les questionnaires et la stabilité à six mois. Le volume et le contexte des écrits diffèrent sensiblement d’un court récit oral. [Automatic Personality Assessment Through Social Media Language](https://www.gsb.stanford.edu/faculty-research/publications/automatic-personality-assessment-through-social-media-language)
- **Les traces numériques comme point de comparaison.** Youyou et al. prédisent des scores Big Five à partir de mentions « J’aime » sur Facebook et comparent les prédictions aux jugements de proches. Le principal intérêt pour MindSight est le protocole de comparaison avec plusieurs références. [Computer-based personality judgments are more accurate than those made by humans](https://pubmed.ncbi.nlm.nih.gov/25583507/)
- **La simulation de réponses.** Joon Sung Park et al. construisent des agents à partir d’entretiens approfondis avec 1 052 personnes et les confrontent à des réponses humaines recueillies séparément. Pour MindSight, des personnages fictifs peuvent servir à vérifier la logique des relances. La capacité à généraliser doit être mesurée avec des participants humains. [Generative Agent Simulations of 1,000 People](https://arxiv.org/abs/2411.10109)

## Ce que les simulations MindSight ont montré

La première simulation s’est attardée sur un même thème. La seconde a mieux diversifié les sujets, mais les réponses ont surtout produit des descriptions plausibles. Le nombre de facettes abordées est un mauvais indicateur si les réponses possibles ne permettent guère de départager les hypothèses.

Conserver trois niveaux dans le prototype et sa suite de recherche.

1. **Observations.** Garder le passage, le comportement décrit, le contexte et les contre-exemples.
2. **Hypothèses concurrentes.** Documenter les indices favorables et défavorables. Exemple fictif pour la démo · Une personne lance des sorties et délègue les voyages. Cela peut refléter une initiative liée au type d’activité, une préférence pour les tâches peu logistiques ou la répartition habituelle des rôles. Demander un exemple dans un projet collectif aide à départager ces explications.
3. **Estimations des traits.** Les cinq domaines et les 30 facettes du NEO-PI-R fournissent une grille de recherche. Un modèle probabiliste exploitable demanderait des entretiens humains appariés à des questionnaires et une calibration de l’incertitude.

## Démo et évaluation proposées

- **Parcours.** Récit oral, transcription, première constellation, puis deux ou trois relances et mise à jour visuelle. Chaque élément interprétatif peut renvoyer à un extrait et afficher l’état de l’hypothèse, par exemple « à explorer » ou « indices contradictoires ».
- **Sélection des relances.** Générer plusieurs questions ouvertes. Pour chacune, indiquer les hypothèses qu’elle peut départager, les réponses plausibles et la façon dont elles changeraient l’interprétation. Choisir selon le gain d’information estimé, la continuité avec le récit, la redondance et le coût pour la personne.
- **Comparaison pendant le hackathon.** À durée comparable, confronter récit seul et récit avec relances. Faire juger la fluidité, la traçabilité des interprétations et la présence de nouveaux éléments qui départagent les hypothèses. Le portrait montre les indices narratifs observés et les interprétations provisoires.
- **Suite de recherche.** Comparer un entretien piloté par les facettes, un entretien piloté par des hypothèses individuelles et une approche hybride. Mesurer la convergence avec un questionnaire indépendant à mesure que la durée augmente, ainsi que la capacité à prévoir des réponses dans de nouveaux contextes.

*Périmètre documentaire · Le bilan des simulations était accessible dans l’échange « Personality Inference Methods ». La liste bibliographique de sa partie initiale n’était pas accessible. Les publications ci-dessus ont été vérifiées comme références pertinentes pour MindSight.*
