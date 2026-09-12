# Pro MK3 : validation de la première implémentation

Cette version retire les bascules vers le firmware. Elle conserve les séquenceurs
existants, avec accès direct au drums et protections sur les relâchements de pads.

**Configuration confirmée fonctionnelle par l'utilisateur le 12 septembre 2026 :**

| Réglage dans Préférences → Link, Tempo & MIDI → Surfaces de contrôle | Valeur |
| --- | --- |
| Ancienne surface `Launchpad Pro MK3` | **None** — retirer cette affectation |
| Surface à conserver | **Launchpad Pro MK3 Custom** |
| Entrée | **LPProMK3 MIDI**, première paire |
| Sortie | **LPProMK3 MIDI**, première paire |

**Ne pas choisir MIDIIN3 / MIDIOUT3.** Retirer l'ancienne surface signifie la
désactiver dans les préférences de Live, sans supprimer les fichiers du script usine.
Après ce réglage, l'utilisateur indique que cela fonctionne très bien.

Les tests hors Live vérifient les handlers et les packages. Le retour utilisateur
valide le fonctionnement avec cette configuration ; il ne constitue pas une
validation exhaustive de tous les scénarios ci-dessous.

1. Utiliser une seule surface pour le Pro : `Launchpad Pro MK3 Custom`, entrée et
   sortie sur la première paire `LPProMK3 MIDI`. Passer tout slot usine
   `Launchpad Pro MK3` à `None`, même s'il est sur MIDIIN3/MIDIOUT3.
   Le journal de Live 12.4.2 du 11 septembre montrait les deux scripts chargés.
2. Sur une piste MIDI avec Drum Rack, sélectionner un clip, puis appuyer sur
   Sequencer : 32 pas en haut, 16 sons en bas à gauche, pages en bas à droite.
   Écrire quelques pas et vérifier les notes dans le clip Live ainsi que sa lecture.
2b. Maintenir Sequencer : les scenes 1 à 5 s'allument (drum, drum 64, drum 4 pistes,
   melodic, chord), le mode courant en pleine intensité. Taper une scene bascule le mode
   sans lancer de scène ni basculer le pin de piste. Taper la scene du mode actif renvoie
   en Session. Relâcher sans rien taper doit atterrir sur le séquenceur drum. Vérifier
   qu'un tap simple sur Sequencer se comporte comme avant.
3. Revenir avec Session, puis Sequencer, 30 fois. Maintenir Session puis la relâcher :
   le mode ne doit pas revenir automatiquement au séquenceur.
4. Tester Shift+Sequencer, puis Note/Chord/Custom/Projects seuls et avec Shift,
   Clear et Duplicate. Aucune page du firmware ne doit apparaître. Les quatre
   boutons réservés ne déclenchent aucune fonction.
5. Tester Shift+Session, choisir une zone, relâcher les touches dans les deux ordres.
   Le panneau ne doit jamais provoquer une sortie du mode Programmer.
6. Maintenir un pas, changer la couche Shift, puis relâcher : aucune nouvelle note.
   Changer de mode pendant un maintien, revenir, puis relâcher : aucune édition
   fantôme de note ou de page. Vérifier aussi les pads d'audition (note-off reçu).
7. Maintenir Clear ou Duplicate pendant Session → Sequencer → Session, puis relâcher.
   Aucun modificateur ne reste actif. Clear+Duplicate donne priorité à Clear ; son
   relâchement rend Duplicate actif s'il est encore maintenu.
8. Shift+Duplicate double la boucle une seule fois. Garder Duplicate maintenu,
   relâcher Shift et changer de mode : aucun nouveau doublement ni copie implicite.
9. Débrancher/rebrancher le Pro : la grille et le mode logiciel doivent revenir.
   Désactiver le script : le fonctionnement normal du firmware doit être restauré.

Le blocage des modes hardware par ce script ne protège pas des commandes émises
par une autre surface ou une application MIDI. Si une page hardware apparaît,
conserver le journal, la combinaison exacte et l'ordre des pressions/relâchements.
Le script usine déjà enregistré dans les préférences doit être désactivé même si
le shadow de protection contre l'auto-détection est installé.

Les chantiers suivants restent ouverts : cible piste/clip commune, conservation des
attributs lors des éditions de notes, ergonomie des variantes et optimisation LED.
