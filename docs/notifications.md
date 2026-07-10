# Notification system

Comment les notifications utilisateur (status bar Live, overlay Max for Live) sont produites par ce MIDI Remote Script.

## TL;DR

Les composants n'appellent **jamais** `show_message` directement. Ils émettent des *événements sémantiques* sur un bus (`Event.DRUM_GRID_CHANGED`, `Event.SHIFT_LOCK_CHANGED`, etc.). Des *subscribers* indépendants traduisent ces événements en effets visibles :

- `StatusBarSubscriber` → string → `show_message()` Live
- `M4LSubscriber` → `(msg_id, args)` → `NotificationDispatcher` → paramètres d'un device M4L "LP Notify"

Le script fonctionne identiquement sans bus, sans dispatcher, sans device M4L. C'est le but de l'architecture.

---

## Pourquoi un event bus ?

Avant cette refacto, chaque composant connaissait le texte UI à afficher : 31 `self.show_message("Drum grid: %s" % label)` éparpillés dans `launchpad_mini_mk3.py`, `drum_step_sequencer.py`, `melodic_step_sequencer.py`. Conséquences :

1. **Couplage** : la logique métier (changement de résolution) et la présentation (libellé "Drum grid:") vivent dans le même endroit. Renommer un libellé = modifier le composant.
2. **Multiplication par canal** : ajouter un canal d'affichage (overlay M4L) imposerait d'ajouter une ligne *par site* (30+ touches), chaque site ayant ensuite à connaître les deux APIs.
3. **Pas de kill switch propre** : pour désactiver les notifs, il faudrait soit commenter chaque ligne, soit no-op `show_message` au niveau du control surface (effet de bord sur d'autres usages éventuels).

La solution : un seul point de couplage par composant (la méthode `_emit`), un seul point de traduction par canal (un subscriber par cible).

---

## Architecture en 3 couches

```
┌─────────────────────────────────────────────────────────────────┐
│  Couche 1 — Composants (drum, melodic, control surface)         │
│                                                                  │
│    self._emit(Event.DRUM_GRID_CHANGED,                           │
│               label="1/16", is_triplet=False)                    │
│                                                                  │
│    Pas de connaissance de show_message, Msg, dispatcher, M4L.    │
│    Avec event_bus=None : _emit() est un no-op.                   │
└──────────────────────────────────┬──────────────────────────────┘
                                   │ EventBus.emit(name, **payload)
                                   v
┌─────────────────────────────────────────────────────────────────┐
│  Couche 2 — Subscribers (event → présentation)                  │
│                                                                  │
│    StatusBarSubscriber                                           │
│      _FORMATTERS[Event.DRUM_GRID_CHANGED](payload)               │
│        -> "Drum grid: 1/16"                                      │
│        -> show_message(...)                                      │
│                                                                  │
│    M4LSubscriber                                                 │
│      _MAPPING[Event.DRUM_GRID_CHANGED](payload)                  │
│        -> (Msg.DRUM_GRID, (1, 0))                                │
│        -> dispatcher.send(Msg.DRUM_GRID, 1, 0)                   │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
                                   v
┌─────────────────────────────────────────────────────────────────┐
│  Couche 3 — Transport (NotificationDispatcher)                  │
│                                                                  │
│    Trouve un device M4L nommé "LP Notify" sur n'importe quelle   │
│    track (regular/return/master). Cache ses parameters par nom.  │
│    .send() : msg_id -> arg1 -> arg2 -> arg3 -> seq (bump)        │
│    Listeners refresh sur add/remove/rename.                      │
│    Pas de device = is_ready() False = M4LSubscriber no-op.       │
└─────────────────────────────────────────────────────────────────┘
```

### Pourquoi ce découpage

| Propriété | Bénéfice |
|---|---|
| Composants n'importent que `events.py` | Aucun composant ne sait qu'un canal M4L existe |
| Subscribers indépendants | Couper l'un n'affecte pas l'autre |
| Dispatcher peut être absent | `is_ready()` False = M4LSubscriber no-op silencieux |
| Bus peut être None | Composants no-op-ent, code marche à 100% sans UI feedback |
| Wire protocol stable (`Msg.*`) | Le `.amxd` n'est jamais re-déployé sur un rename d'event Python |

---

## Comment ajouter une nouvelle notification

Disons qu'on veut notifier que la sélection de pad drum a changé (`DRUM_PAD_SELECTED` avec le pitch sélectionné).

### 1. Déclarer l'événement

`events.py` :

```python
class Event(object):
    # ... existant ...
    DRUM_PAD_SELECTED   = "drum_pad_selected"   # pitch=int (0..127), name=str|None
```

### 2. Émettre depuis le composant

`drum_step_sequencer.py`, dans `_select_note_by_grid_position` (ou autre point de changement) :

```python
self._emit(Event.DRUM_PAD_SELECTED,
           pitch=self._selected_pitch,
           name=self._pad_name_for_pitch(self._selected_pitch))
```

Le composant ne sait rien de plus. Pas de string. Pas de `Msg.*`.

### 3. Ajouter un formatter status bar

`status_bar_subscriber.py`, dans `_FORMATTERS` :

```python
Event.DRUM_PAD_SELECTED:
    lambda p: "Pad: {} (pitch {})".format(p["name"] or "—", p["pitch"]),
```

À ce stade, la status bar marche déjà. Plus de modifs nécessaires si tu ne veux que le status bar.

### 4. (Optionnel) Si tu veux aussi l'overlay M4L

Append un ID dans `notification_catalog.py` (jamais renuméroter d'IDs existants) :

```python
class Msg(object):
    # ... existant ...
    DRUM_PAD_SELECTED = 27  # (pitch)
```

Puis ajouter le mapping dans `m4l_subscriber.py`, dans `_MAPPING` :

```python
Event.DRUM_PAD_SELECTED:
    lambda p: (Msg.DRUM_PAD_SELECTED, (p["pitch"],)),
```

Et côté `.amxd` : ajouter une entrée dans le `[coll]` ou `[dict]` indexé par `msg_id` :

```
27, "Pad: pitch %d";
```

(Le nom du pad n'est pas envoyé sur le wire — si tu en veux un dans l'overlay, fournis une lookup table côté Max.)

### Règle d'or

**Aucune string user-facing ne quitte le composant.** Si tu te retrouves à construire un libellé dans `drum_step_sequencer.py` ou `melodic_step_sequencer.py`, tu es probablement en train de violer l'abstraction. Passe la donnée brute dans le payload, formate côté subscriber.

---

## Wire protocol (`Msg.*`)

Le fichier `notification_catalog.py` est la source unique des IDs entiers échangés avec le device M4L. **Règles** :

- IDs entiers `0..127` (range `live.numbox`)
- **Append-only** : ne renuméroter jamais un ID en cours d'usage, ne pas réutiliser un ID supprimé
- Les groupes sont décimaux par convention (0-9 modes, 10-19 shift, 20-29 drum, 30-39 melodic, 90-99 erreurs)
- **Args sont des entiers** `-128..127`, jamais des strings

### IDs actuels

| ID | Constante | Args | Émis sur l'event |
|---|---|---|---|
| 0 | `MODE_SESSION` | () | `MAIN_MODE_CHANGED` mode="session" |
| 1 | `MODE_DRUM_SEQ` | () | `MAIN_MODE_CHANGED` mode="drum_sequence" |
| 2 | `MODE_MELODIC_SEQ` | () | `MAIN_MODE_CHANGED` mode="melodic_sequence" |
| 10 | `SHIFT_LOCKED` | () | `SHIFT_LOCK_CHANGED` locked=True |
| 11 | `SHIFT_UNLOCKED` | () | `SHIFT_LOCK_CHANGED` locked=False |
| 20 | `DRUM_PAGE_SCOPED` | `(page_1based)` | `DRUM_PAGE_SCOPED` start==end |
| 21 | `DRUM_PAGE_RANGE` | `(start, end)` | `DRUM_PAGE_SCOPED` start!=end |
| 22 | `DRUM_GRID` | `(resolution_index, is_triplet)` | `DRUM_GRID_CHANGED` |
| 23 | `DRUM_TRIPLET` | `(on)` | `DRUM_TRIPLET_CHANGED` |
| 24 | `DRUM_VELOCITY` | `(velocity)` | `DRUM_VELOCITY_CHANGED` |
| 25 | `DRUM_BOTTOM_RIGHT` | `(0=loop, 1=velocity)` | `DRUM_BOTTOM_RIGHT_MODE` |
| 26 | `DRUM_NAV` | `(page, octave, semitone)` | `DRUM_NAV_CHANGED` |
| 30 | `MELODIC_PAGE_SCOPED` | `(page_1based)` | `MELODIC_PAGE_SCOPED` start==end |
| 31 | `MELODIC_PAGE_RANGE` | `(start, end)` | `MELODIC_PAGE_SCOPED` start!=end |
| 32 | `MELODIC_GRID` | `(resolution_index, is_triplet)` | `MELODIC_GRID_CHANGED` |
| 33 | `MELODIC_TRIPLET` | `(on)` | `MELODIC_TRIPLET_CHANGED` |
| 34 | `MELODIC_SCALE` | `(scale_index)` | `MELODIC_SCALE_CHANGED` |
| 35 | `MELODIC_CHROMATIC` | `(on)` | `MELODIC_CHROMATIC_MODE` |
| 36 | `MELODIC_PREVIEW` | `(on)` | `MELODIC_PREVIEW_MODE` |
| 37 | `MELODIC_NAV` | `(page, octave, semitone)` | `MELODIC_NAV_CHANGED` |
| 90 | `ERR_NEED_MIDI_SLOT` | `(mode_id)` | `ERR_NEED_MIDI_SLOT` |
| 91 | `ERR_NEED_MIDI_TRACK` | `(mode_id)` | `ERR_NEED_MIDI_TRACK` |
| 92 | `ERR_NOT_MIDI` | `(mode_id)` | `ERR_NOT_MIDI` |

### Lookup tables secondaires (côté `.amxd` uniquement)

Les indices entiers envoyés sur le wire doivent être résolus localement par le patch Max via des `[coll]` / `[dict]` :

**Resolution index** (arg de `DRUM_GRID` / `MELODIC_GRID`) :
```
0 -> "1/32"
1 -> "1/16"
2 -> "1/8"
3 -> "1/4"
```
Source côté Python : `notification_catalog.GRID_RESOLUTION_INDICES`.

**Scale index** (arg de `MELODIC_SCALE`) :
```
0  -> "Major"
1  -> "Minor"
2  -> "Dorian"
3  -> "Mixolydian"
4  -> "Lydian"
5  -> "Phrygian"
6  -> "Locrian"
7  -> "Harmonic Minor"
8  -> "Melodic Minor"
9  -> "Pentatonic Major"
10 -> "Pentatonic Minor"
11 -> "Blues"
```
Source côté Python : `melodic_step_sequencer.MELODIC_SCALES`. Si tu ajoutes une scale côté Python, ajoute-la aussi à la lookup table du `.amxd` au même index.

**Mode discriminator** (arg de `ERR_*`) :
```
0 -> "Drum"
1 -> "Melodic"
```
Source côté Python : `notification_catalog.MODE_ID_DRUM` / `MODE_ID_MELODIC`.

---

## Contrat du device Max for Live

Le device s'appelle **`LP Notify`** (constante `notification_dispatcher.DEVICE_NAME`). Renommer le device = le script perd la ref.

### Paramètres exposés (obligatoires)

Chacun doit être un `live.numbox` ou `live.toggle` avec, dans l'Inspector Max :
- **Long Name** = exactement la string du tableau ci-dessous (matching par nom dans `device.parameters[i].name`)
- **Parameter Visibility** = "Stored Only" ou "Automation Mapping" (pour apparaître dans `device.parameters`)

| Long Name | Type Max | Range | Rôle |
|---|---|---|---|
| `msg_id` | live.numbox int | 0..127 | Index dans le catalogue de messages (`Msg.*`) |
| `arg1` | live.numbox int | -128..127 | Premier argument |
| `arg2` | live.numbox int | -128..127 | Deuxième argument |
| `arg3` | live.numbox int | -128..127 | Troisième argument (peu utilisé) |
| `seq` | live.numbox int | 0..127 | **Compteur déclencheur** — c'est sur lui que `live.observer` doit écouter |
| `enabled` | live.toggle | 0/1 | Désactive l'overlay sans retirer le device |

### Paramètres optionnels (purement UX)

| Nom | Type | Rôle |
|---|---|---|
| `open_window` | live.button | Bouton qui envoie un message à `[thispatcher]` pour rouvrir la fenêtre flottante |

### Ordre d'écriture côté script

```python
def send(self, msg_id, arg1=0, arg2=0, arg3=0):
    self._set("msg_id", msg_id)
    self._set("arg1",   arg1)
    self._set("arg2",   arg2)
    self._set("arg3",   arg3)
    self._seq = (self._seq + 1) & 0x7F
    self._set("seq",    self._seq)
```

`seq` est écrit **en dernier**. Côté Max, mettre un `live.observer` sur **`seq` uniquement**. Quand il fire, lire `msg_id`/`arg1`/`arg2`/`arg3` qui sont déjà à jour, puis faire le lookup et l'affichage.

**Pourquoi `seq` plutôt qu'observer `msg_id` directement** : deux notifs consécutives identiques (ex: deux "Shift LOCKED" l'un après l'autre) auraient les mêmes valeurs et `live.observer` ne re-firerait pas. Le bump monotone de `seq` (0..127 wrap) garantit le re-fire.

### Architecture suggérée du patch

- **Device chrome** (visible dans le device chain de Live, ~700×90px) : les 6 params, le toggle `enabled`, le bouton `open_window`. Peut rester très compact.
- **Sub-patcher fenêtre flottante** :
  - `live.observer` sur `seq`
  - lecture des autres params via `live.object` ou `pattrstorage`
  - lookup `msg_id` → format string dans un `[coll]` ou `[dict]`
  - lookup secondaire pour les enums (résolution, scale, mode_id) via d'autres `[coll]`
  - formatage avec `sprintf`
  - affichage en grosse font via `jsui`, `lcd`, ou `textbutton` (fontsize 96+)
  - fade out via `[delay 1500] → [line 0 200]` sur l'alpha
- **Au load** : `[loadbang] → [thispatcher window ...]` pour ouvrir la fenêtre automatiquement
- **Persistence position/taille** : `live.savestate` ou attributs window

Le `.amxd` n'est PAS dans le repo (à toi de le construire). On peut le versionner dans `m4l/` à la racine si voulu — install.sh ignore.

### Discovery & édge cases

- Le scan visite **dans cet ordre** : `song.tracks` → `song.return_tracks` → `[song.master_track]`. Premier device trouvé gagne.
- Plusieurs devices `LP Notify` simultanés : warning logué, premier gagne, les autres ignorés.
- Rename du device en cours d'usage → listener fire → re-scan → device perdu (ou retrouvé si rename vers `LP Notify`).
- Add/remove de track → re-scan complet.
- Add/remove de device dans une track → re-scan complet (la track émet `devices_listener`).
- Device introuvable → `is_ready() == False` → tous les `dispatcher.send()` no-op. Le status bar continue.

---

## Kill switches

Tu peux désactiver les notifications à plusieurs granularités sans toucher au code des composants :

### Couper uniquement le M4L (status bar continue)

`launchpad_mini_mk3.py::_create_notification_subscribers`, commenter ou supprimer :

```python
self._event_bus.subscribe(self._m4l_subscriber)
```

### Couper status bar ET M4L (silence total côté UI, composants émettent toujours)

Commenter les deux `subscribe(...)`. Utile pour debugger sans bruit visuel — `_log` continue de marcher.

### Couper le bus entier (composants émettent dans le vide)

Plus radical. Deux options :

1. Dans `launchpad_mini_mk3.py::__init__` :
   ```python
   self._event_bus = None  # au lieu de EventBus(logger=self._log)
   ```
   Les `_emit()` au niveau du control surface no-op-ent.

2. Pour aussi désactiver les sequencers : passer `event_bus=None` à leurs constructeurs dans `_create_drum_sequencer` et `_create_melodic_sequencer` (au lieu de `event_bus=self._event_bus`). Les composants no-op-ent.

Dans tous ces cas, la logique métier (sequencer, copy, transport, navigation, LED rendering) est **identique**. C'est ce qu'on vérifie en Phase D du plan de test.

---

## Troubleshooting

### "Le M4L ne reçoit rien"

1. Vérifier le nom du device : il doit être exactement `LP Notify` (Inspector → Name). Pas `LP_Notify`, pas `LPNotify`. La constante `DEVICE_NAME` est dans `notification_dispatcher.py:6`.
2. Vérifier Log.txt côté Live : tu dois voir `[NotificationDispatcher] notification device found on track '...' (bound: [...])`. Si tu vois `missing parameters: [...]`, c'est que les Long Names des `live.numbox` ne correspondent pas. Re-checker l'Inspector dans Max.
3. Vérifier que `Parameter Visibility` est sur "Stored Only" ou "Automation Mapping" (pas "Hidden").
4. Vérifier que `enabled` est à 1 sur le device. À 0, `dispatcher.send()` no-op.
5. Vérifier qu'il n'y a pas un message identique répété : si on émet 2× exactement le même `(msg_id, args)` mais que `seq` ne change pas (bug script), `live.observer` ne re-fire pas. Vérifier que le compteur s'incrémente dans Log.txt.

### "La status bar ne montre plus rien après ma modif"

1. Vérifier que tu as bien ajouté un entry dans `status_bar_subscriber._FORMATTERS`. Sans entry, l'event est silencieusement ignoré (c'est délibéré pour la robustesse — on ne crash pas sur un event inconnu).
2. Vérifier que tu n'as pas tapé une typo dans le nom de l'`Event.XXX`. Python ne lèvera pas une erreur à l'attribut access si tu utilises `Event.XYZ` qui n'existe pas — *en fait si*, ça lève `AttributeError`. Mais si tu utilises la string littérale, pas de check.
3. Vérifier dans Log.txt qu'il n'y a pas une traceback "[EventBus] subscriber raised on ...". Le bus loggue les exceptions des subscribers (sans les propager).

### "Listeners orphelins après reload du script"

Le control surface a un `disconnect()` qui appelle `self._notification_dispatcher.disconnect()`. Ce dernier détache tous les listeners Live (`song.tracks`, `song.return_tracks`, par-track `devices`, `device.name`). Si tu modifies le dispatcher, assure-toi que chaque nouveau listener est détaché dans `disconnect()`.

### "Le device a été déplacé sur une autre track et le script ne le retrouve plus"

C'est censé être supporté via le `track.devices_listener` qui fire au remove. Vérifier dans Log.txt :
```
[NotificationDispatcher] notification device lost
[NotificationDispatcher] notification device found on track 'NewTrack' (bound: [...])
```
Si le "lost" apparaît mais pas le "found", il manque un listener sur la nouvelle track — probablement parce qu'elle vient d'être créée et le `tracks_listener` côté song n'a pas encore re-scanné. Couper/réactiver le control surface dans les MIDI prefs Live force un re-scan complet.

---

## Référence des fichiers

| Fichier | Couche | Rôle |
|---|---|---|
| `event_bus.py` | 1 | `EventBus` pubsub sync minimal — `emit()` + `subscribe()` |
| `events.py` | 1 | `Event.*` constantes string, source unique des noms d'événements |
| `status_bar_subscriber.py` | 2 | `_FORMATTERS` : `Event → string`, appel `show_message` |
| `m4l_subscriber.py` | 2 | `_MAPPING` : `Event → (Msg.*, args)`, appel `dispatcher.send()` |
| `notification_catalog.py` | wire | `Msg.*` IDs entiers + lookup tables partagées (résolutions, mode_ids) |
| `notification_dispatcher.py` | 3 | Discovery + listeners + `send()` + parameter writes |
| `launchpad_mini_mk3.py` | wiring | Instancie le bus, le dispatcher, les subscribers ; passe `event_bus=` aux composants ; détache à `disconnect()` |
| `drum_step_sequencer.py` | emitter | `self._emit(Event.DRUM_*, ...)` sur 10 sites |
| `melodic_step_sequencer.py` | emitter | `self._emit(Event.MELODIC_*, ...)` sur 11 sites |
