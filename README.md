# Quantastic! — the playable game (Python version)

A quantum-inspired race game for 2–4 players (any mix of people and computer
players), built from Johan Lingani's poster and the *Quantastic! Official Rules*.

## How to run it

1. Install Python 3.9 or newer from https://www.python.org (on Windows, tick
   "Add Python to PATH" during installation).
2. Open a terminal (Windows: "Command Prompt"; Mac: "Terminal") in this folder.
3. Install the two libraries the game uses:

       python -m pip install -r requirements.txt

   (On a Mac you may need to type `python3` instead of `python`.)
4. Start the game:

       python pygame_interface.py

The game opens with you as Red against three computer players. Click
**New game** to choose who sits where, and **How to play** for the full rules.

## The files, and what each one does

| File | What it contains |
|---|---|
| `pygame_interface.py` | **Run this to play.** Draws the window, handles the mouse and keyboard, paces the computer players, asks people whether they want to counter. |
| `game_engine.py` | **The rules of the game.** Board layout, card decks, how pawns move, slides, every quantum card, winning. It never touches the screen. Start here to understand the game logic. |
| `computer_player.py` | How the computer opponents decide what to do. Its "personality" is a table of numbers (`SCORING_WEIGHTS`) you can change. |
| `board_geometry.py` | Where everything is drawn. Uses NumPy rotation matrices to turn one side's layout into all four sides, plus the math for dashed lines, arrowheads and gliding pawns. |
| `simulate_games.py` | Automated test: plays many computer-vs-computer games and checks after every action that nothing impossible happened. Run `python simulate_games.py 200`. |
| `test_interface_headless.py` | Automated screen test: clicks through many turns invisibly and saves screenshots to `screenshots/`. Run `python test_interface_headless.py`. |
| `requirements.txt` | The libraries to install (Pygame and NumPy). |

Every file is written so a non-programmer can read along: each one opens with
a short guide to reading Python, names say exactly what they hold or do
(`send_pawn_back_to_start`, `number_of_quantum_cards_in_hand`), and every
block has a plain-English comment. Search for **RULE CLARIFICATION** to find
every place where the code had to decide something the official rules left open.

## Where NumPy is used

* **Board geometry** — the board is drawn for one side only; the other three
  sides are produced by multiplying each point by a 90° rotation matrix
  (`board_geometry.rotate_point_clockwise`).
* **Animation** — pawns glide by moving a fraction of the remaining distance
  every frame (`move_points_smoothly_toward_targets`), and the flowing
  entanglement lines and superposition halos are built from NumPy ranges.
* **Computer player** — it measures the distance from all opponent pawns to
  one of its pawns in a single array operation to spot threats
  (`count_opponents_that_could_bump_pawn`).

The game rules themselves are plain Python: they are about lists of pawns and
cards, not number crunching, so NumPy would only make them harder to read.

## Gaps and inconsistencies in the original rules, and how they were resolved

The official rules and the poster were a strong design but left a number of things
undefined or contradictory. A playable game has to decide every one of them. Each
decision below tries to stay as close as possible to the written rules and to the
spirit of the quantum concept it teaches. The same list appears in-game under
**How to play → Clarified rules**.

### Board

1. **Board size.** "16 spaces per side" was ambiguous (counting corners twice gives
   64, once gives 60). Resolved: a 16×16 square, giving **60 track spaces** in a loop.
2. **Where things are.** No positions were given for Start, Safety Zone entrances,
   slides or Quantum Spaces. Resolved, identically on all four sides (counting from
   each side's corner): Safety Zone entrance on the **3rd** space, Start exit on the
   **5th**, a **Quantum Space** on the 8th and 15th, a **slide** from the 10th to the 13th.
3. **How many Quantum Spaces.** Not specified. Resolved: **8** (two per side), shown as
   qubits Q0–Q7 — four sides plus the central deck hub echo the IBM 5-qubit chip.
4. **Who slides.** The rules don't say whether you slide on your own color. Resolved:
   the four slides are neutral — **every pawn slides**.

### Cards and turns

5. **Card 11** had no description. Resolved: **move 11 forward** (no swap — the
   rules never mention one).
6. **Card 10** — resolved as **10 forward or 1 backward**; **card 4** is **4 backward**.
7. **Draw again on a 2** — resolved: you draw again **whether you moved or sacrificed** the 2.
8. **The movement deck running out** was not covered (only the Quantum deck was).
   Resolved: both decks reshuffle their discard piles.
9. **Holding quantum cards.** The rules say cards are *drawn*, but Interference and
   Superposition can be played *as counters during an opponent's action*, which
   only works if players keep cards. Resolved: quantum cards go into your **hand
   (maximum 3)**. On your turn you may play **one** of them, at any point in the turn.
   With a full hand you cannot sacrifice and Quantum Spaces give nothing.
10. **"Any Quantum State card lets a pawn leave Start."** Resolved: any quantum card in
    your hand can be spent as a **Quantum Launch** — move a pawn from Start to your
    exit space — instead of using its effect. This counts as your one quantum play.
11. **No legal move.** Resolved: you must move if you can; otherwise you may sacrifice
    the card (if your hand has room) or discard it.

### Quantum cards

12. **Superposition — "stacked pawns move as a single unit until the top pawn moves
    off"** contradicts itself (if they always move together, the top can never leave).
    Resolved: you place one of your pawns *in superposition*. A pawn that would land
    on it **stacks on top instead of bumping it** (any color). From then on:
    the **top pawn's owner may move just the top pawn off** (the stack dissolves and
    the superposition ends), or — if both pawns are theirs — **move the whole stack as
    one unit**. The bottom pawn cannot move while covered.
13. **A third pawn arriving on a stack** was undefined for normal moves. Resolved with
    the existing teleport rule: the **top pawn is sent to Start** and the arriving
    pawn takes its place. A stack can never land on another stack or superposition pawn.
14. **"Quantum states are stackable"** (poster) vs. keeping the game understandable.
    Resolved: many quantum states can be active on the board at once, but **each
    pawn holds only one state at a time** (in superposition, stacked on top, or
    entangled). An entangled pawn that lands on a stack loses its entanglement.
15. **Entanglement duration** was undefined. Resolved: the link lasts until something
    breaks it — a slide, Interference, Quantum Break, either pawn being bumped or
    reaching Home, or the Safety Zone rule.
16. **Entangled movement** — resolved: when either pawn is moved by a movement card, the
    partner then makes the **same move (same number, same direction)** along its own
    path. If the partner's move is illegal (e.g. it would overshoot Home), the link
    breaks and the partner stays put. Entanglement may link **any two pawns on the track,
    as long as at least one is yours** — so linking to an opponent is a real tactic.
17. **"Entangled pawns can teleport to each other."** Resolved: with a Teleportation card,
    an entangled pawn can jump to its partner. If the partner is **yours**, they **swap
    places**; if it is an **opponent's**, it is bumped to Start (unless they counter).
18. **Teleportation targets** — resolved: the start or end of any slide, or any Quantum
    Space (16 targets), plus the partner rule above. Teleporting **does not** trigger a
    slide or a Quantum Space draw. Only pawns already on the track can teleport.
19. **Slides and protection.** "Pawns on slide spaces are bumped unless protected by
    quantum mechanics" vs. "slides disrupt quantum states". Resolved: a sliding pawn
    loses its own quantum state (a sliding stack breaks, its bottom pawn goes to Start).
    Pawns along the slide are bumped to Start, **except** a superposition pawn, which
    survives but loses its superposition, and the top of a stack, which survives while
    the bottom is sent to Start. Anything on the slide's **last** space is always bumped.
20. **Quantum Break vs. Teleportation "effects".** Teleportation is instant, so there
    is nothing to undo. Quantum Break **breaks every stack** (bottom pawns to Start),
    ends every superposition and entanglement, and lifts every Jam.
21. **Interference/Noise** had two vague uses. Resolved as three concrete ones:
    *Decohere* — end one pawn's quantum state (a stack broken this way sends its
    bottom pawn to Start, per the stack rule); *Jam* — an opponent cannot play any
    quantum card during their next turn; *Cancel* — played instantly, during an
    opponent's quantum play, to stop it (both cards are discarded). A Cancel cannot
    itself be canceled.
22. **Counters.** The rules allow an opponent to counter an entangled teleport with
    Superposition. Resolved: when a teleport would bump your pawn, you may play
    Superposition to put that pawn in superposition first — the teleporter stacks on
    top of it instead.
23. **Safety Zone immunity.** Pawns in a Safety Zone cannot be targeted by Superposition,
    Teleportation or Entanglement, but **can** be hit by Interference (as written).
    The cross-color Entanglement/Superposition rule in the Safety Zone is kept exactly.
24. **Simultaneous win** cannot happen in a turn-based digital game; the first player
    to get the fourth pawn Home wins.
