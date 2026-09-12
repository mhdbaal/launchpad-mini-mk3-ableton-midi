# Plan : séquenceur de clips Ableton pour Launchpad Pro MK3

Audit du 12 septembre 2026, sur le commit `fcae083`. Proposition de travail ; aucune modification du script ni installation effectuée pendant cet audit.

**Première implémentation, après l'audit :** bascules firmware et poll retirés du Pro,
Sequencer relié aux clips Ableton, transitions de modificateurs et relâchements drums
protégés, archives Mini/Pro corrigées. Les 15 tests hors Live passent. Le 12 septembre,
l'utilisateur confirme le bon fonctionnement après désactivation de la surface
usine et sélection de `Launchpad Pro MK3 Custom` sur `LPProMK3 MIDI` en entrée et
sortie (première paire, pas MIDIIN3/MIDIOUT3). Les scénarios détaillés de la
[procédure dédiée](pro-programmer-validation.md) restent à vérifier individuellement.
Le journal de Live 12.4.2 retrouvé depuis confirme que les surfaces usine et custom
étaient chargées ensemble le 11 septembre : désactiver le slot usine pour l'essai.

L'objectif est un contrôleur de séquençage à la Push 2 : les notes appartiennent aux clips MIDI de Live, Live assure leur lecture et leur timing, et la grille permet de jouer, éditer et naviguer. Le séquenceur matériel du Launchpad ne participe pas à ce fonctionnement.

**Recommandation : conserver les éléments utiles du projet, simplifier d'abord le fonctionnement du Pro, puis consolider un seul séquenceur drums avant de réintroduire les variantes.**

**Précision utilisateur après l'audit : le problème principal était la collision avec les modes matériels ; des combinaisons de touches affichaient le séquenceur hardware.** La priorité est donc de garantir la possession des commandes avant de refactorer le moteur de notes. Le symptôme est confirmé par l'utilisateur ; la séquence exacte de messages qui provoquait la sortie reste à relever.

## Ce que montre le code

| Constat | Preuve dans le dépôt | Conséquence |
| --- | --- | --- |
| Le moteur actuel édite déjà les clips de Live. | `drum_step_sequencer.py`, `_ensure_clip`, `_toggle_step`, `_on_playing_position_changed` : `create_clip`, `add_new_notes`, `remove_notes_extended`, lecture de `clip.playing_position`. | La direction technique est bonne. Il existe déjà une base à reprendre. |
| Le bouton Sequencer ouvre le séquenceur matériel. | `pro/launchpad_pro_mk3.py`, `__on_sequencer_mode_button_value` appelle `_enter_native_passthrough`. Les modes maison passent par Shift+Session. | L'accès principal ne correspond pas à l'objectif annoncé. |
| Le port Pro combine plusieurs systèmes de modes. | Mode Programmer, sortie vers les modes firmware, poll de layout toutes les 0,8 s, puis reprise de contrôle. | Le fonctionnement du séquenceur dépend d'une mécanique de bascule difficile à diagnostiquer. |
| Le dernier correctif MIDI repose encore sur des hypothèses matérielles. | `CLAUDE.md`, section Pro : validation sur appareil encore demandée pour les canaux des modes natifs ; dernier commit consacré à ce passthrough. | Ne pas considérer les commentaires sur le routage comme une validation expérimentale. |
| La piste, le clip et l'instrument ne sont pas résolus ensemble. | `_refresh_clip` préfère tout `detail_clip` MIDI, tandis que `_resolve_target_track` prend la piste sélectionnée ou épinglée. Le Pro appelle `set_controlled_track(selected_track)`, même si un séquenceur est épinglé ailleurs. | Risque d'éditer un clip et d'auditionner un autre instrument. Scénarios à reproduire dans Live. |
| L'édition d'une note peut en supprimer plusieurs et perdre des attributs. | `_replace_note` dans les trois séquenceurs drums et `_replace_note_at` dans le mélodique suppriment une fenêtre temporelle, puis recréent seulement pitch/start/duration/velocity/mute. | Deux notes de même hauteur très proches peuvent être touchées ; probabilité et variations de vélocité ne sont pas préservées explicitement. |
| Beaucoup de logique est dupliquée. | Environ 6 400 lignes entre les quatre fichiers de séquenceurs : résolution du clip, notes, pages, gestes, LEDs, translations MIDI. | Une correction doit être répétée et les variantes divergent déjà sur leurs commandes disponibles. |
| Les LEDs sont réécrites largement pendant la lecture. | `_on_playing_position_changed` rafraîchit les trois zones ; `palette.send_pad_color` utilise `optimized=False`. | Trafic inutile potentiel ; mesurer avant d'attribuer une latence à cette cause. |
| Le packaging de release n'assemble plus un script complet. | `.github/workflows/release.yml` copie uniquement les `.py` racine et le README, sans overlay `mini/` ni `pro/`. | Avec l'arborescence actuelle, le ZIP manque notamment d'`__init__.py`, d'`elements.py` et de la surface principale. |
| L'installation complique le diagnostic et la maintenance. | `install.sh` cible les ressources de Live, ajoute un shadow au script usine et supprime le Log.txt ; chemins Live 12.3 codés en dur. | Prévoir une installation isolée et des journaux conservés. Le shadow est une solution à un conflit documenté, à remplacer proprement. |

Les notes internes rapportent une grille noire avec le mauvais port, une concurrence avec le script usine et un ancien poll qui s'arrêtait après un cycle. Ce sont des observations historiques du projet, pas des pannes reproduites pendant cet audit. Le correctif du poll est déjà présent : ne pas le présenter comme restant à faire.

La vérification de syntaxe des 33 fichiers Python partagés et des overlays réussit. Elle ne vérifie ni les API de Live ni le matériel. Le Log.txt n'est pas présent au chemin documenté dans cet environnement. Les sources de référence locales correspondent à Live 12.0.1 ; il faudra comparer les signatures à la version réellement utilisée.

## Références à exploiter

| Référence | Intérêt | Limite |
| --- | --- | --- |
| [Launchpad Pro95](https://github.com/hdavid/Launchpad_Pro95) et son [manuel](https://motscousus.com/stuff/2015-12_Novation_Launchpad_Pro_Ableton_Live_Scripts/) | Séquenceurs de clips Live en Python, Drum Rack, pages, verrouillage piste/clip, jeu façon Push. | Projet issu du Launchpad Pro original et de Live 9.5 ; aucune compatibilité Pro MK3 / Live 12 établie par les pages consultées. Inspiration, pas installation prête à l'emploi. |
| [Launchpad95](https://github.com/hdavid/Launchpad95) | Autre référence d'édition de clips via une grille et de séparation instrument/séquenceur. | Ne pas déduire une compatibilité Pro MK3 du seul nom Launchpad. |
| [DrivenByMoss — documentation Launchpad](https://github.com/git-moss/DrivenByMoss-Documentation/blob/master/Novation/Novation-Launchpad.md) | Prise en compte explicite du Pro MK3 ; modes drums et mélodiques, édition de notes sans écran, pages et longueurs. | Écosystème Bitwig, pas une base Python Ableton directement réutilisable. |
| [fl-launchpad-pro-mk3](https://github.com/htakeuchi/fl-launchpad-pro-mk3) | Exemple spécifique MK3 qui sépare les interfaces MIDI/DAW et distingue son édition de pas du séquenceur firmware. | FL Studio ; utile pour le protocole et les transitions uniquement. |
| Sources locales `midi-remote-scripts/Launchpad_Pro_MK3/` et `midi-remote-scripts/pushbase/` | Script usine pour le matériel ; `StepSeqComponent`, `NoteEditorComponent`, `LoopSelectorComponent`, `NoteEditorPaginator`, `PlayheadComponent` pour le découpage du moteur. | Sources décompilées de référence, anciennes et susceptibles d'artefacts ; vérifier les dépendances et la redistribution avant toute copie. |

La recherche n'a pas identifié de script Ableton Pro MK3 prêt à l'emploi dont la compatibilité actuelle et le séquenceur de clips répondent clairement à ce besoin. Cela ne prouve pas qu'il n'en existe pas.

Le [guide de programmation Novation, pages 8 et 18–19](https://fael-downloads-prod.focusrite.com/customer/prod/s3fs-public/downloads/LPP3_prog_ref_guide_200415.pdf) confirme que Programmer donne accès aux boutons et pads, neutralise leurs changements de mode automatiques et reçoit les LEDs sur l'interface MIDI. C'est la base proposée pour le premier jalon. Les commandes de feedback/sleep actuellement supposées communes aux Novation devront être justifiées ou retirées du protocole minimal.

## Architecture proposée

Une seule session Programmer pendant l'utilisation du script. Des modes logiciels explicites possèdent chacun leurs contrôles ; les boutons du Pro deviennent des entrées du script. Une éventuelle sortie vers le firmware sera une fonction distincte, ajoutée après validation du séquenceur.

```text
Boutons et pads du Pro → modes / gestes → commandes d'édition → clip MIDI Live
                                            ↑                       ↓
                                       cible commune ← événements de Live
                                            ↓                       ↓
                                   audition vers piste       rendu grille / LEDs

                         Live assure la lecture musicale du clip
```

Découpage cible, extrait progressivement des composants existants :

- `ClipTargetComponent` : un ensemble cohérent piste + clip slot + clip + instrument ; écoute sélection, disparition et remplacement des objets.
- `ClipNoteEditor` : ajout, suppression et modification des notes, regroupement Undo, conservation des propriétés non éditées.
- `GridResolution` / `Paginator` : conversion temps ↔ pas ↔ page et boucle, indépendante du matériel.
- `DrumSequencerView`, puis `MelodicSequencerView` : coordonnées, sélection et gestes propres à chaque vue.
- Couche d'audition : notes jouées, piste contrôlée, translations, relâchements et nettoyage aux changements de mode.
- Rendu LED : état désiré et cache du dernier état envoyé ; rafraîchissement complet après reconnexion, puis différences seulement.

Les composants Push servent de référence au découpage. Un essai ciblé dans la version de Live installée déterminera si leur réutilisation directe réduit réellement le travail ; le projet ne doit pas dépendre d'un import massif de Push2 ou d'une émulation de son écran.

## Étapes et critères de réussite

### 0. Éliminer les bascules involontaires vers le firmware

- Reproduire les combinaisons problématiques avec traces des pressions, relâchements, modes logiciels et SysEx sortants. Distinguer une sortie demandée par notre script d'une commande provenant d'une autre surface de contrôle.
- Établir l'invariant : pendant Session et les séquenceurs maison, le Pro reste en Programmer ; aucune touche ni combinaison de ces modes n'envoie Programmer OFF ou ne sélectionne un layout firmware.
- Pour le MVP, retirer du câblage actif les entrées de passthrough Note/Chord/Custom/Sequencer. Sequencer ouvre le séquenceur Ableton ; Session ouvre la grille de clips. Les fonctions non encore implémentées restent inactives. La sortie du script restaure proprement le fonctionnement normal du contrôleur.
- Vérifier qu'aucune deuxième surface, notamment le script usine sur le port DAW, ne change le mode du même appareil. Préserver le mécanisme de protection existant tant que son remplacement n'est pas validé.
- Tester les boutons de mode seuls et avec Shift, Clear et Duplicate ; varier l'ordre des relâchements et répéter les changements rapides. Tester aussi l'identification et la reconnexion.

**Terminé quand :** aucune combinaison du parcours maison n'affiche le séquenceur matériel ni ses pages de réglages. Le guide Novation indique que les boutons ne changent pas automatiquement de mode en Programmer : si le symptôme persiste, vérifier d'abord le mode réellement actif et les émetteurs de commandes MIDI, plutôt qu'ajouter de nouvelles combinaisons de contournement.

### 1. Établir un diagnostic reproductible et un package isolé

- Relever version/build de Live, firmware du Pro et noms exacts des ports.
- Produire un package Pro complet, vérifier ses imports locaux et corriger la recette de release. Garder la génération Mini distincte.
- Préparer l'installation dans la bibliothèque utilisateur, avec sélection manuelle du script ; vérifier qu'une seule surface contrôle le Pro. Étudier la déclaration de capacités pour éviter la double auto-détection avant de retirer le shadow existant.
- Conserver le journal précédent ; ajouter un identifiant de build et des traces activables : port configuré, identification, mode, entrée MIDI brute, cible piste/clip, erreur avec contexte.
- Tester un pad, une LED, chaque catégorie de bouton et une note jouée vers une piste armée, sur l'interface MIDI du mode Programmer.

**Terminé quand :** installation reproductible, carte des messages vérifiée, commandes et audition fonctionnelles avec une seule instance ; diagnostic lisible si identification ou port échoue.

### 2. Livrer un parcours minimal Session ↔ Drums

- Conserver Session 8×8, transport et sélection de piste.
- Affecter le bouton Sequencer au séquenceur de clips drums ; Session revient directement à Session. Supprimer la dépendance au passthrough dans ce parcours.
- Garder un seul layout drums : 32 pas en haut, 16 pads Drum Rack en bas à gauche, 16 pages en bas à droite. À la résolution 1/16, les 32 pas représentent deux mesures en 4/4.
- Garder la rangée de sélection des pistes utilisable en séquenceur. Séparer ses ressources de celles du lancement des clips.
- Commencer avec ajout/suppression de pas, audition, navigation des pages et curseur de lecture. Reporter les variantes 64 pas / quatre sons, Chord et les gestes secondaires.

**Terminé quand :** depuis une piste avec Drum Rack, choisir un son, écrire quelques pas, les entendre lus par Live, modifier les notes à la souris et voir la grille suivre. Répéter 30 allers-retours Session/Drums sans note parasite, LED bloquée ni perte de contrôle.

### 3. Fiabiliser le modèle de clip et les notes

- Fixer la règle MVP : clip du slot sélectionné de la piste cible ; slot vide MIDI → création au premier geste d'écriture. Aucun clip créé par une simple navigation de page.
- Traiter audio, groupe, retour et master comme cibles non éditables. L'édition Arrangement pourra ensuite avoir une politique explicite et cohérente avec la piste propriétaire.
- Définir séparément navigation de page, suivi de lecture et modification de boucle. Une navigation ne doit pas déplacer la boucle. Le premier ajout ne doit pas démarrer le transport implicitement ; Play pilote Live.
- Remplacer suppression/recréation pour une modification par l'API de modification des notes existantes. Utiliser leurs identifiants pour les cibles précises et relire après Undo ou remplacement du clip.
- Préserver les attributs non modifiés ; définir une action Undo par geste, y compris pour une édition maintenue ou plusieurs notes.
- Ajouter les écouteurs nécessaires pour slot vide/rempli, changement de Drum Rack et banque de pads. Au changement de cible, annuler les gestes en cours et remettre à zéro les sélections devenues invalides.
- Réintroduire l'épinglage seulement lorsque édition, Drum Rack et audition partagent tous la même cible.

La [documentation du modèle Live](https://docs.cycling74.com/apiref/lom/clip/#apply_note_modifications) recommande `apply_note_modifications` pour modifier les notes existantes. Le code Python local de `pushbase/note_editor_component.py` utilise déjà cette méthode. La documentation LOM expose la forme Max : vérifier les types Python exacts dans Live plutôt que lui transmettre directement ses dictionnaires d'exemple.

**Terminé quand :** éditer une note laisse sa probabilité et ses variations intactes ; deux notes très rapprochées restent distinctes ; Undo/Redo restaure le geste ; changer ou supprimer piste/clip ne détourne aucune écriture.

### 4. Ajouter les gestes Push et stabiliser le feedback

- Maintien d'un pas : vélocité, longueur, microdécalage ; Clear et Duplicate pour leurs opérations explicites ; Quantise sur une sélection clairement définie.
- Sélection/range de boucle, résolutions binaires puis triolets, suivi de page activable.
- Rendre les usages de Shift explicites ; vérifier relâchement après changement de mode, de hauteur, de page ou de cible, notamment pendant une audition.
- Mesurer les émissions MIDI ; envoyer uniquement les LEDs modifiées et limiter le travail du curseur aux changements visibles. Valider l'affichage au tempo élevé et à la résolution fine.

**Terminé quand :** gestes reproductibles, pas de notes coincées, réponse utilisable pendant la lecture et aucun effacement collatéral de notes ou de boucle.

### 5. Ajouter le mélodique sur le même moteur

- Porter la vue piano-roll existante sur l'éditeur commun ; synchroniser tonalité et gamme selon les propriétés disponibles dans la version cible de Live.
- Ajouter ensuite une vue polyphonique façon Push : jouer/sélectionner un accord, puis le poser sur les pas, avec durée et vélocité.
- Réévaluer les variantes drums après usage réel du premier layout. Les traiter comme des vues du moteur commun.
- N'ajouter les modes firmware, les accords autonomes ou les fonctions device/mixer avancées qu'avec un parcours séparé et testé.

**Terminé quand :** drums et mélodique partagent les mêmes garanties sur clips, notes, pages et Undo ; aucune horloge musicale Python ou matérielle n'est nécessaire.

## Validation à prévoir pendant l'implémentation

| Hors Live | Dans Live avec le Pro |
| --- | --- |
| Syntaxe et intégrité du package assemblé. | Chargement du script, bons ports, identification, reconnexion USB. |
| Calculs pas/page/boucle : triolets, limites, début de boucle décalé. | LEDs et curseur cohérents avec Live, navigation sans modifier la boucle. |
| Sélection des notes : doublons, notes rapprochées, chevauchements, conservation des champs. | Propriétés avancées intactes, Undo/Redo, modifications au piano-roll. |
| Résolution de cible avec faux objets : changement/suppression de clip ou de piste. | Deux pistes armées, épinglage, remplacement de Drum Rack, slot vide puis rempli. |
| États de gestes : changement de mode ou cible entre pression et relâchement. | Audition et enregistrement sans doublons, sans sons de pads de commande ni notes coincées. |

Le premier livrable utile est donc **une installation Pro fiable et un beat de Drum Rack éditable depuis un unique mode Sequencer**, avec les notes visibles et persistantes dans le clip Ableton. Les tests logiciels complètent cette validation matérielle ; ils ne la remplacent pas.
