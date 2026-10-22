"""
=============================================================================
QUANTASTIC!  —  GAME ENGINE  (game_engine.py)
-----------------------------------------------------------------------------
This file contains THE RULES OF THE GAME and nothing else. It never draws
anything on the screen and never listens to the mouse. The screen code
(pygame_interface.py) and the computer opponents (computer_player.py) both
ask this file "what is allowed?" and "please make this move".

HOW TO READ PYTHON IF YOU ARE NOT A PROGRAMMER
---------------------------------------------
* Lines starting with  #  are COMMENTS: notes for people. Python ignores them.
  Text between triple quotes  \"\"\" ... \"\"\"  right under a function name is
  that function's explanation (a "docstring").
* NAME_IN_CAPITALS = 60  creates a CONSTANT: a fixed fact, like the number of
  squares on the board.
* def do_something(ingredient_one, ingredient_two):  defines a FUNCTION: a
  named recipe. The words in brackets are what the recipe receives. Indented
  lines underneath are its steps. "return" hands back the result.
* class Pawn:  describes a KIND OF THING (here: a pawn) and the facts every
  pawn has (owner, position, ...). "@dataclass" above it is a Python shortcut
  that writes the boring bookkeeping code for us.
* [1, 2, 3]  is a LIST (an ordered collection); {"a": 1} is a DICTIONARY
  (a lookup table from a name to a value).
* if condition:  ... else: ...  means: only do the first block when the
  condition is true, otherwise do the second.
* for item in collection:  means: repeat the indented block once per item.
* raise IllegalMoveError("...")  means: stop right here, this action is
  against the rules, and say why.
* "None" means "nothing / not set".
* Indentation (the spaces at the start of a line) matters in Python: it shows
  which lines belong inside which block.

THE BIG PICTURE
---------------
At any moment, the whole game is described by ONE object called the
"game state": where every pawn is, what cards are in each deck and in each
player's hand, whose turn it is, and so on. Every rule below is a function
that reads the game state and changes it.

The official rules left many things open or contradictory. Every place where
this code makes such a decision is marked  RULE CLARIFICATION  so you can find
them all by searching for those words.
=============================================================================
"""

from __future__ import annotations  # lets us mention a class before it is fully defined

import random                        # for shuffling the decks
from dataclasses import dataclass, field, replace
from typing import Callable, Optional


# =============================================================================
# SECTION 1 — FIXED NUMBERS THAT DESCRIBE THE BOARD
# =============================================================================

# The outer track is a loop of 60 squares (a 16 x 16 board, each corner counted
# once). Squares are numbered 0 to 59 going CLOCKWISE from the top-left corner.
# RULE CLARIFICATION: "16 spaces per side" = a 16 x 16 square = 60 squares.
NUMBER_OF_TRACK_SPACES = 60

# Each of the four sides "owns" 15 squares of the loop (0-14, 15-29, ...).
NUMBER_OF_TRACK_SPACES_PER_SIDE = 15

# Each player has a private lane of 5 squares (the Safety Zone), then Home.
NUMBER_OF_SAFETY_ZONE_SPACES = 5

NUMBER_OF_PAWNS_PER_PLAYER = 4

# RULE CLARIFICATION: quantum cards are kept in a hand, at most 3 at a time.
MAXIMUM_QUANTUM_CARDS_IN_HAND = 3

# RULE CLARIFICATION: positions of the special squares, counted from the
# corner where each side begins (the corner itself is position 0). They are
# identical on all four sides so the board is perfectly fair.
SAFETY_ZONE_ENTRANCE_POSITION_ON_SIDE = 2   # 3rd square of the side
START_EXIT_POSITION_ON_SIDE = 4             # 5th square of the side
QUANTUM_SPACE_POSITIONS_ON_SIDE = (7, 14)   # 8th and 15th squares
SLIDE_START_POSITION_ON_SIDE = 9            # 10th square
SLIDE_END_POSITION_ON_SIDE = 12             # 13th square

# The four seats. Seat 0 sits at the top, 1 at the right, 2 at the bottom,
# 3 at the left. Play goes clockwise: Red, Blue, Yellow, Green.
PLAYER_COLOR_NAMES = ("Red", "Blue", "Yellow", "Green")

# How long a pawn's journey is: 1 step out of Start, 58 squares around the
# board, 5 Safety squares and Home.
STEPS_FROM_START_TO_HOME = 65


def convert_side_position_to_track_space_number(side_number: int, position_on_side: int) -> int:
    """Turns 'side number + position along that side' into a square number 0-59."""
    return side_number * NUMBER_OF_TRACK_SPACES_PER_SIDE + position_on_side


def get_safety_zone_entrance_space_for_seat(seat_number: int) -> int:
    """The track square where this player's pawns turn off into their Safety Zone."""
    return convert_side_position_to_track_space_number(seat_number, SAFETY_ZONE_ENTRANCE_POSITION_ON_SIDE)


def get_start_exit_space_for_seat(seat_number: int) -> int:
    """The track square where this player's pawns arrive when they leave Start."""
    return convert_side_position_to_track_space_number(seat_number, START_EXIT_POSITION_ON_SIDE)


@dataclass(frozen=True)
class Slide:
    """One slide: a pawn landing on its first square zooms to its last square."""
    side_number: int
    slide_start_space: int
    slide_end_space: int


# RULE CLARIFICATION: four slides, one per side, each 4 squares long. They are
# neutral: every pawn of every color slides.
ALL_SLIDES_ON_THE_BOARD = tuple(
    Slide(
        side_number=side_number,
        slide_start_space=convert_side_position_to_track_space_number(side_number, SLIDE_START_POSITION_ON_SIDE),
        slide_end_space=convert_side_position_to_track_space_number(side_number, SLIDE_END_POSITION_ON_SIDE),
    )
    for side_number in range(4)
)

# RULE CLARIFICATION: eight Quantum Spaces, two per side, named Q0 to Q7.
ALL_QUANTUM_SPACES_ON_THE_BOARD = tuple(
    convert_side_position_to_track_space_number(side_number, position_on_side)
    for side_number in range(4)
    for position_on_side in QUANTUM_SPACE_POSITIONS_ON_SIDE
)

# RULE CLARIFICATION: Teleportation can send a pawn to the start or end of any
# slide, or to any Quantum Space: 16 possible target squares.
ALL_TELEPORT_DESTINATION_SPACES = tuple(sorted(
    [slide.slide_start_space for slide in ALL_SLIDES_ON_THE_BOARD]
    + [slide.slide_end_space for slide in ALL_SLIDES_ON_THE_BOARD]
    + list(ALL_QUANTUM_SPACES_ON_THE_BOARD)
))


def is_track_space_a_quantum_space(track_space_number: int) -> bool:
    return track_space_number in ALL_QUANTUM_SPACES_ON_THE_BOARD


def find_slide_that_starts_on_space(track_space_number: int) -> Optional[Slide]:
    """Returns the slide that begins on this square, or None if there is none."""
    for slide in ALL_SLIDES_ON_THE_BOARD:
        if slide.slide_start_space == track_space_number:
            return slide
    return None


def get_quantum_space_label(track_space_number: int) -> str:
    """The label of a Quantum Space, for example 'Q3'."""
    return "Q" + str(ALL_QUANTUM_SPACES_ON_THE_BOARD.index(track_space_number))


# =============================================================================
# SECTION 2 — THE CARDS
# =============================================================================

@dataclass(frozen=True)
class MovementCardRule:
    """What one kind of movement card allows."""
    can_leave_start: bool                 # may bring a pawn out of Start
    forward_step_choices: tuple           # how many squares forward
    backward_step_choices: tuple          # how many squares backward
    can_split_between_two_pawns: bool     # the 7: share the steps between two pawns
    grants_another_draw: bool             # the 2: draw again afterwards
    explanation: str                      # words shown to players


# The Movement Deck: four each of 1, 2, 3, 4, 5, 7, 8, 10, 11, 12 and one
# Paradox card = 41 cards (exactly as in the official rules).
MOVEMENT_CARD_RULES = {
    "1": MovementCardRule(True, (1,), (), False, False, "Bring a pawn out of Start, or move a pawn 1 forward."),
    "2": MovementCardRule(True, (2,), (), False, True, "Bring a pawn out of Start, or move a pawn 2 forward. Then draw again."),
    "3": MovementCardRule(False, (3,), (), False, False, "Move a pawn 3 forward."),
    "4": MovementCardRule(False, (), (4,), False, False, "Move a pawn 4 BACKWARD."),
    "5": MovementCardRule(False, (5,), (), False, False, "Move a pawn 5 forward."),
    "7": MovementCardRule(False, (7,), (), True, False, "Move a pawn 7 forward, or split the 7 between two pawns."),
    "8": MovementCardRule(False, (8,), (), False, False, "Move a pawn 8 forward."),
    "10": MovementCardRule(False, (10,), (1,), False, False, "Move a pawn 10 forward, or 1 backward."),
    # RULE CLARIFICATION: the official rules give the 11 no special power.
    "11": MovementCardRule(False, (11,), (), False, False, "Move a pawn 11 forward."),
    "12": MovementCardRule(False, (12,), (), False, False, "Move a pawn 12 forward."),
    "Paradox": MovementCardRule(True, (6, 9), (), False, False, "Your choice: bring a pawn out of Start, move 6 forward, or move 9 forward."),
}

# The official names of the five quantum cards.
SUPERPOSITION = "Superposition"
TELEPORTATION = "Teleportation"
ENTANGLEMENT = "Entanglement"
QUANTUM_BREAK = "Quantum Break"
INTERFERENCE = "Interference/Noise"

# How many copies of each quantum card are in the Quantum State Deck (37).
QUANTUM_DECK_CARD_COUNTS = {
    SUPERPOSITION: 7,
    TELEPORTATION: 7,
    ENTANGLEMENT: 7,
    QUANTUM_BREAK: 5,
    INTERFERENCE: 11,
}

# A one-line explanation of each quantum card, shown on screen.
QUANTUM_CARD_EXPLANATIONS = {
    SUPERPOSITION: "Put one of your track pawns in superposition. A pawn that lands on it stacks on top instead of bumping it.",
    TELEPORTATION: "Jump a track pawn to any slide end or Quantum Space - or, if entangled, to its partner.",
    ENTANGLEMENT: "Link two track pawns (at least one yours). When one is moved by a card, the other makes the same move.",
    QUANTUM_BREAK: "End every quantum state on the board. Every stack breaks and its bottom pawn goes back to Start.",
    INTERFERENCE: "End one pawn's quantum state, or Jam an opponent for their next turn. Can also cancel an opponent's quantum card instantly.",
}


def build_fresh_movement_deck() -> list:
    """A brand-new, unshuffled Movement Deck: a list of 41 card names."""
    deck = []
    for card_name in ("1", "2", "3", "4", "5", "7", "8", "10", "11", "12"):
        deck.extend([card_name] * 4)
    deck.append("Paradox")
    return deck


def build_fresh_quantum_deck() -> list:
    """A brand-new, unshuffled Quantum State Deck: a list of 37 card names."""
    deck = []
    for card_name, number_of_copies in QUANTUM_DECK_CARD_COUNTS.items():
        deck.extend([card_name] * number_of_copies)
    return deck


def shuffle_cards(list_of_cards: list) -> list:
    """Shuffles a list of cards into a random order (changes the list itself)."""
    random.shuffle(list_of_cards)
    return list_of_cards


# =============================================================================
# SECTION 3 — THE THINGS THAT MAKE UP A GAME
# =============================================================================

class IllegalMoveError(Exception):
    """A special kind of error that means 'this move is against the rules'.
    It carries a human-readable reason, e.g. 'That would overshoot Home'."""


@dataclass(frozen=True)
class PawnLocation:
    """Where a pawn is. 'zone' is one of:
         'start'  – in its Start circle
         'track'  – on the outer loop; track_space_number is 0-59
         'safety' – in its OWN color's Safety Zone; safety_zone_step is 0-4
         'home'   – finished
    "frozen" means a location never changes once made; moving a pawn gives it
    a brand-new location instead."""
    zone: str
    track_space_number: Optional[int] = None
    safety_zone_step: Optional[int] = None


IN_START = PawnLocation("start")
AT_HOME = PawnLocation("home")


def on_track(track_space_number: int) -> PawnLocation:
    return PawnLocation("track", track_space_number=track_space_number)


def in_safety_zone(safety_zone_step: int) -> PawnLocation:
    return PawnLocation("safety", safety_zone_step=safety_zone_step)


@dataclass
class Pawn:
    """One pawn.
    quantum_state is one of:
        'none'          – an ordinary pawn
        'superposition' – a pawn landing on it stacks instead of bumping it
                          (linked_pawn_id = the pawn on top of it, or None)
        'stacked_on_top'– sitting on a superposition pawn
                          (linked_pawn_id = the pawn underneath)
        'entangled'     – linked to a partner (linked_pawn_id = the partner)"""
    pawn_id: str
    owner_seat: int
    pawn_number: int
    location: PawnLocation = IN_START
    quantum_state: str = "none"
    linked_pawn_id: Optional[str] = None


@dataclass
class Player:
    seat_number: int
    color_name: str
    display_name: str
    is_computer_player: bool
    quantum_cards_in_hand: list = field(default_factory=list)
    is_jammed_for_their_next_turn: bool = False


@dataclass(frozen=True)
class LogEntry:
    """One line of the 'what happened' history."""
    turn_number: int
    seat_number: Optional[int]   # colors the line with that player's color
    message_text: str


@dataclass
class GameState:
    """Everything about one game in progress.
    turn_phase is one of:
        'waiting_to_draw_movement_card'    – may play a quantum card, then must draw
        'choosing_how_to_use_movement_card' – move, sacrifice, or (if stuck) discard
        'finishing_turn'                    – may still play a quantum card, then end
        'game_over'                         – somebody won"""
    players: list
    pawns: list
    movement_draw_pile: list
    movement_discard_pile: list
    quantum_draw_pile: list
    quantum_discard_pile: list
    index_of_current_player: int = 0
    turn_number: int = 1
    turn_phase: str = "waiting_to_draw_movement_card"
    current_movement_card: Optional[str] = None
    has_played_quantum_card_this_turn: bool = False
    seat_of_winner: Optional[int] = None
    game_log: list = field(default_factory=list)

    def make_independent_copy(self) -> "GameState":
        """A complete copy of the game that can be changed without touching the
        original. We use copies to TRY a move: if it turns out to be illegal,
        the real game is untouched. (Locations and log lines never change once
        made, so the copy may safely share them.)"""
        return GameState(
            players=[replace(player, quantum_cards_in_hand=list(player.quantum_cards_in_hand)) for player in self.players],
            pawns=[replace(pawn) for pawn in self.pawns],
            movement_draw_pile=list(self.movement_draw_pile),
            movement_discard_pile=list(self.movement_discard_pile),
            quantum_draw_pile=list(self.quantum_draw_pile),
            quantum_discard_pile=list(self.quantum_discard_pile),
            index_of_current_player=self.index_of_current_player,
            turn_number=self.turn_number,
            turn_phase=self.turn_phase,
            current_movement_card=self.current_movement_card,
            has_played_quantum_card_this_turn=self.has_played_quantum_card_this_turn,
            seat_of_winner=self.seat_of_winner,
            game_log=list(self.game_log),
        )

    def overwrite_with_copy(self, source_copy: "GameState") -> None:
        """Replaces everything in this game with the contents of another one.
        Used to 'commit' a move that was successfully tried on a copy."""
        fresh_copy = source_copy.make_independent_copy()
        self.__dict__.update(fresh_copy.__dict__)


@dataclass(frozen=True)
class MoveDetails:
    """One movement of one pawn (or of a whole stack)."""
    pawn_id: str
    number_of_steps: int
    direction: str              # 'forward' or 'backward'
    move_whole_stack: bool = False


@dataclass
class MovementOption:
    """One legal way to use the movement card.
    option_kind is 'leave_start', 'move' or 'split_seven'."""
    option_kind: str
    description: str
    pawn_ids_involved: list
    pawn_id: Optional[str] = None                     # for 'leave_start'
    move_details: Optional[MoveDetails] = None        # for 'move'
    first_move_details: Optional[MoveDetails] = None  # for 'split_seven'
    second_move_details: Optional[MoveDetails] = None
    resulting_game_state: Optional[GameState] = None  # what the game would look like afterwards


@dataclass
class QuantumOption:
    """One legal way to play a quantum card.
    effect_kind is one of: 'quantum_launch', 'superposition', 'teleport',
    'entangled_teleport', 'entangle', 'quantum_break', 'decohere', 'jam'."""
    card_name: str
    effect_kind: str
    description: str
    pawn_ids_involved: list
    pawn_id: Optional[str] = None
    second_pawn_id: Optional[str] = None
    destination_track_space_number: Optional[int] = None
    target_seat_number: Optional[int] = None
    resulting_game_state: Optional[GameState] = None


@dataclass(frozen=True)
class Reaction:
    """An opponent's counter to a quantum card.
    reaction_kind is 'cancel' (Interference/Noise) or 'shield' (Superposition)."""
    reacting_seat: int
    reaction_kind: str
    card_name: str
    description: str
    shielded_pawn_id: Optional[str] = None


# =============================================================================
# SECTION 4 — GENERAL HELPERS
# =============================================================================

def try_action_on_copy_of_game(game_state: GameState, action_to_try: Callable[[GameState], None]) -> Optional[GameState]:
    """Tries an action on a COPY of the game. Returns the changed copy if the
    action was legal, or None if it broke a rule."""
    copy_of_game = game_state.make_independent_copy()
    try:
        action_to_try(copy_of_game)
        return copy_of_game
    except IllegalMoveError:
        return None


def add_message_to_game_log(game_state: GameState, message_text: str, seat_number: Optional[int] = None) -> None:
    """Adds a line to the history shown on screen (keeps the newest 250 lines)."""
    game_state.game_log.append(LogEntry(game_state.turn_number, seat_number, message_text))
    if len(game_state.game_log) > 250:
        del game_state.game_log[0]


# =============================================================================
# SECTION 5 — CREATING A NEW GAME
# =============================================================================

@dataclass(frozen=True)
class PlayerSetup:
    """Who sits where, as chosen on the New Game screen."""
    seat_number: int
    display_name: str
    is_computer_player: bool


def create_new_game(list_of_player_setups: list) -> GameState:
    """Creates the game state for a brand-new game of 2 to 4 players."""
    if not 2 <= len(list_of_player_setups) <= 4:
        raise ValueError("Quantastic! needs between 2 and 4 players.")

    # Sort by seat so the turn order goes clockwise.
    sorted_setups = sorted(list_of_player_setups, key=lambda setup: setup.seat_number)

    players = [
        Player(
            seat_number=setup.seat_number,
            color_name=PLAYER_COLOR_NAMES[setup.seat_number],
            display_name=setup.display_name or PLAYER_COLOR_NAMES[setup.seat_number],
            is_computer_player=setup.is_computer_player,
        )
        for setup in sorted_setups
    ]

    pawns = [
        Pawn(pawn_id=player.color_name + "-" + str(pawn_number), owner_seat=player.seat_number, pawn_number=pawn_number)
        for player in players
        for pawn_number in range(1, NUMBER_OF_PAWNS_PER_PLAYER + 1)
    ]

    game_state = GameState(
        players=players,
        pawns=pawns,
        movement_draw_pile=shuffle_cards(build_fresh_movement_deck()),
        movement_discard_pile=[],
        quantum_draw_pile=shuffle_cards(build_fresh_quantum_deck()),
        quantum_discard_pile=[],
    )
    add_message_to_game_log(game_state, "A new game of Quantastic! begins with " + str(len(players)) + " players.")
    begin_turn_of_current_player(game_state)
    return game_state


# =============================================================================
# SECTION 6 — LOOKING THINGS UP IN THE GAME STATE
# =============================================================================

def find_pawn_by_id(game_state: GameState, pawn_id: str) -> Pawn:
    for pawn in game_state.pawns:
        if pawn.pawn_id == pawn_id:
            return pawn
    raise ValueError("No pawn named " + pawn_id)


def find_player_by_seat(game_state: GameState, seat_number: int) -> Optional[Player]:
    for player in game_state.players:
        if player.seat_number == seat_number:
            return player
    return None


def get_current_player(game_state: GameState) -> Player:
    return game_state.players[game_state.index_of_current_player]


def get_pawns_owned_by_seat(game_state: GameState, seat_number: int) -> list:
    return [pawn for pawn in game_state.pawns if pawn.owner_seat == seat_number]


def get_pawn_display_name(pawn: Pawn) -> str:
    """A friendly name for a pawn, e.g. 'Blue 3'."""
    return PLAYER_COLOR_NAMES[pawn.owner_seat] + " " + str(pawn.pawn_number)


def describe_location_for_people(location: PawnLocation) -> str:
    """Describes a location in words: 'square 23 (Q2)', 'Safety 2', 'Home'.
    Track squares are shown to people numbered 1-60 instead of 0-59."""
    if location.zone == "start":
        return "Start"
    if location.zone == "home":
        return "Home"
    if location.zone == "safety":
        return "Safety " + str(location.safety_zone_step + 1)
    description = "square " + str(location.track_space_number + 1)
    if is_track_space_a_quantum_space(location.track_space_number):
        description += " (" + get_quantum_space_label(location.track_space_number) + ")"
    return description


def get_space_key_for_location(location: PawnLocation, lane_owner_seat: int) -> str:
    """A unique text 'key' for every square, so two locations can be compared.
    Safety squares include the lane owner, because every color has its own lane."""
    if location.zone == "track":
        return "track-" + str(location.track_space_number)
    if location.zone == "safety":
        return "safety-" + str(lane_owner_seat) + "-" + str(location.safety_zone_step)
    return location.zone + "-" + str(lane_owner_seat)


def get_space_key_of_pawn(pawn: Pawn) -> str:
    return get_space_key_for_location(pawn.location, pawn.owner_seat)


def is_pawn_on_track_or_in_safety_zone(pawn: Pawn) -> bool:
    """Is the pawn somewhere it can move from (not in Start, not Home)?"""
    return pawn.location.zone in ("track", "safety")


def find_pawns_on_space(game_state: GameState, space_key: str, pawn_ids_to_ignore=()) -> list:
    """All pawns standing on a square, except those in pawn_ids_to_ignore
    (usually the pawns that are moving right now)."""
    return [
        pawn for pawn in game_state.pawns
        if pawn.pawn_id not in pawn_ids_to_ignore
        and is_pawn_on_track_or_in_safety_zone(pawn)
        and get_space_key_of_pawn(pawn) == space_key
    ]


def is_pawn_covered_at_bottom_of_stack(pawn: Pawn) -> bool:
    """A pawn at the bottom of a stack has another pawn sitting on top of it."""
    return pawn.quantum_state == "superposition" and pawn.linked_pawn_id is not None


def find_stack_containing_pawn(game_state: GameState, pawn: Pawn):
    """If the pawn is part of a stack, returns (bottom_pawn, top_pawn); else None."""
    if is_pawn_covered_at_bottom_of_stack(pawn):
        return pawn, find_pawn_by_id(game_state, pawn.linked_pawn_id)
    if pawn.quantum_state == "stacked_on_top":
        return find_pawn_by_id(game_state, pawn.linked_pawn_id), pawn
    return None


def count_steps_remaining_to_home(pawn: Pawn) -> int:
    """How many squares a pawn still has to travel to reach Home
    (65 from Start, 0 at Home). Used by the computer player."""
    location = pawn.location
    if location.zone == "home":
        return 0
    if location.zone == "start":
        return STEPS_FROM_START_TO_HOME
    if location.zone == "safety":
        return NUMBER_OF_SAFETY_ZONE_SPACES - location.safety_zone_step
    entrance_space = get_safety_zone_entrance_space_for_seat(pawn.owner_seat)
    steps_to_entrance = (entrance_space - location.track_space_number) % NUMBER_OF_TRACK_SPACES
    return steps_to_entrance + NUMBER_OF_SAFETY_ZONE_SPACES + 1


# =============================================================================
# SECTION 7 — WALKING ALONG A PAWN'S PATH
# =============================================================================

def step_one_square_along_path(location: PawnLocation, owner_seat: int, direction: str) -> Optional[PawnLocation]:
    """Moves a location ONE square forward or backward along the path of a pawn
    of the given color. Returns None if the step is impossible (e.g. past Home)."""
    if location.zone in ("start", "home"):
        return None

    if direction == "forward":
        if location.zone == "track":
            # At your own Safety Zone entrance: turn into the Safety Zone.
            if location.track_space_number == get_safety_zone_entrance_space_for_seat(owner_seat):
                return in_safety_zone(0)
            return on_track((location.track_space_number + 1) % NUMBER_OF_TRACK_SPACES)
        # In the Safety Zone: one step deeper, or Home after the last square.
        if location.safety_zone_step < NUMBER_OF_SAFETY_ZONE_SPACES - 1:
            return in_safety_zone(location.safety_zone_step + 1)
        return AT_HOME

    # Moving backward.
    if location.zone == "track":
        return on_track((location.track_space_number - 1) % NUMBER_OF_TRACK_SPACES)
    if location.safety_zone_step == 0:
        # Backing out of the Safety Zone returns to the entrance square.
        return on_track(get_safety_zone_entrance_space_for_seat(owner_seat))
    return in_safety_zone(location.safety_zone_step - 1)


def walk_along_path(starting_location: PawnLocation, owner_seat: int, number_of_steps: int, direction: str) -> Optional[PawnLocation]:
    """Walks several squares. Returns the final location, or None if the walk
    is impossible. Home needs an EXACT count: reaching Home with steps left over
    is an overshoot, which is illegal."""
    current_location = starting_location
    for _ in range(number_of_steps):
        current_location = step_one_square_along_path(current_location, owner_seat, direction)
        if current_location is None:
            return None
    return current_location


# =============================================================================
# SECTION 8 — QUANTUM STATE BOOKKEEPING
# These small functions keep the quantum_state and linked_pawn_id of two
# linked pawns consistent with each other.
# =============================================================================

def clear_quantum_state_of_pawn_and_its_link(game_state: GameState, pawn: Pawn) -> None:
    """Ends whatever quantum state this pawn is in, AND releases the pawn it was
    linked to (its entangled partner, or the other pawn of its stack)."""
    if pawn.linked_pawn_id is not None:
        linked_pawn = find_pawn_by_id(game_state, pawn.linked_pawn_id)
        linked_pawn.quantum_state = "none"
        linked_pawn.linked_pawn_id = None
    pawn.quantum_state = "none"
    pawn.linked_pawn_id = None


def send_pawn_back_to_start(game_state: GameState, pawn: Pawn, reason_text: str = "") -> None:
    """Sends a pawn back to its Start circle, ending any quantum state it had."""
    clear_quantum_state_of_pawn_and_its_link(game_state, pawn)
    pawn.location = IN_START
    add_message_to_game_log(game_state, get_pawn_display_name(pawn) + " is sent back to Start" + (" (" + reason_text + ")." if reason_text else "."), pawn.owner_seat)


def send_pawn_home(game_state: GameState, pawn: Pawn) -> None:
    """Moves a pawn into Home for good. Any quantum state ends there.
    RULE CLARIFICATION: same-color entanglement/superposition survives the
    Safety Zone and only breaks when one of the pawns reaches Home."""
    if pawn.quantum_state != "none":
        add_message_to_game_log(game_state, "The quantum state of " + get_pawn_display_name(pawn) + " ends as it reaches Home.", pawn.owner_seat)
    clear_quantum_state_of_pawn_and_its_link(game_state, pawn)
    pawn.location = AT_HOME
    add_message_to_game_log(game_state, get_pawn_display_name(pawn) + " reaches Home!", pawn.owner_seat)


def break_stack_and_send_bottom_pawn_to_start(game_state: GameState, bottom_pawn: Pawn, reason_text: str) -> None:
    """A stack is BROKEN (by a slide, Quantum Break or Interference): the top pawn
    stays put as an ordinary pawn and - as the official rules say - the bottom
    pawn is sent back to Start."""
    top_pawn = find_pawn_by_id(game_state, bottom_pawn.linked_pawn_id)
    add_message_to_game_log(game_state, "The superposition stack of " + get_pawn_display_name(bottom_pawn) + " and " + get_pawn_display_name(top_pawn) + " breaks (" + reason_text + ").")
    send_pawn_back_to_start(game_state, bottom_pawn, "its stack broke")


def dissolve_stack_peacefully_as_top_pawn_leaves(game_state: GameState, top_pawn: Pawn) -> None:
    """The top pawn simply walks off a stack: nobody is hurt, the stack
    dissolves and the bottom pawn's superposition is used up."""
    bottom_pawn = find_pawn_by_id(game_state, top_pawn.linked_pawn_id)
    add_message_to_game_log(game_state, get_pawn_display_name(top_pawn) + " steps off " + get_pawn_display_name(bottom_pawn) + "; their superposition collapses.", top_pawn.owner_seat)
    clear_quantum_state_of_pawn_and_its_link(game_state, top_pawn)


def apply_safety_zone_rule_to_entangled_pawn(game_state: GameState, pawn: Pawn) -> None:
    """Official rule: if two entangled pawns have DIFFERENT colors and either is
    inside a Safety Zone, the entanglement breaks immediately."""
    if pawn.quantum_state != "entangled":
        return
    partner_pawn = find_pawn_by_id(game_state, pawn.linked_pawn_id)
    either_is_in_safety_zone = pawn.location.zone == "safety" or partner_pawn.location.zone == "safety"
    if either_is_in_safety_zone and pawn.owner_seat != partner_pawn.owner_seat:
        add_message_to_game_log(game_state, "The entanglement between " + get_pawn_display_name(pawn) + " and " + get_pawn_display_name(partner_pawn) + " breaks at the Safety Zone (different colors).")
        clear_quantum_state_of_pawn_and_its_link(game_state, pawn)


# =============================================================================
# SECTION 9 — LANDING ON A SQUARE
# The heart of the game: what happens when one pawn (or a whole stack of two
# pawns) arrives on a square.
# =============================================================================

def land_moving_pawns_on_space(game_state: GameState, moving_pawns: list, destination: PawnLocation) -> None:
    """moving_pawns is a list of one pawn, or of the two pawns of a stack that
    moves as a unit."""
    mover_seat = moving_pawns[0].owner_seat
    lead_pawn_name = get_pawn_display_name(moving_pawns[-1])
    moving_pawn_ids = [pawn.pawn_id for pawn in moving_pawns]

    # --- Arriving Home: always allowed (Home holds any number of pawns). ---
    if destination.zone == "home":
        for pawn in moving_pawns:
            send_pawn_home(game_state, pawn)
        return

    destination_key = get_space_key_for_location(destination, mover_seat)
    pawns_already_there = find_pawns_on_space(game_state, destination_key, moving_pawn_ids)

    def place_all_moving_pawns_on_destination():
        for pawn in moving_pawns:
            pawn.location = destination

    # --- Case A: the square is empty. ---
    if not pawns_already_there:
        place_all_moving_pawns_on_destination()
        return

    # --- Case B: a stack of two pawns is already there. ---
    # RULE CLARIFICATION: the arriving pawn knocks the TOP pawn back to Start
    # and takes its place (the official teleport rule, used for every kind of
    # arrival so the game behaves the same way everywhere).
    if len(pawns_already_there) >= 2:
        if len(moving_pawns) > 1:
            raise IllegalMoveError("A stack cannot land on another stack.")
        bottom_pawn, top_pawn = find_stack_containing_pawn(game_state, pawns_already_there[0])
        if top_pawn.owner_seat == mover_seat:
            raise IllegalMoveError("Your own pawn is on top of that stack.")
        arriving_pawn = moving_pawns[0]
        if arriving_pawn.quantum_state == "entangled":
            add_message_to_game_log(game_state, "The entanglement of " + lead_pawn_name + " collapses as it joins a stack.", mover_seat)
            clear_quantum_state_of_pawn_and_its_link(game_state, arriving_pawn)
        # Knock the old top pawn off; the bottom pawn stays in superposition.
        top_pawn.quantum_state = "none"
        top_pawn.linked_pawn_id = None
        top_pawn.location = IN_START
        add_message_to_game_log(game_state, get_pawn_display_name(top_pawn) + " is knocked off the top of the stack and sent back to Start.", top_pawn.owner_seat)
        # The arriving pawn becomes the new top of the stack.
        place_all_moving_pawns_on_destination()
        arriving_pawn.quantum_state = "stacked_on_top"
        arriving_pawn.linked_pawn_id = bottom_pawn.pawn_id
        bottom_pawn.linked_pawn_id = arriving_pawn.pawn_id
        add_message_to_game_log(game_state, lead_pawn_name + " is now stacked on top of " + get_pawn_display_name(bottom_pawn) + ".", mover_seat)
        return

    # --- Case C: exactly one pawn is there. ---
    pawn_already_there = pawns_already_there[0]

    # C1: it is in superposition, so the arriving pawn stacks on top.
    if pawn_already_there.quantum_state == "superposition":
        if len(moving_pawns) > 1:
            raise IllegalMoveError("A stack cannot land on a pawn in superposition (two pawns maximum).")
        arriving_pawn = moving_pawns[0]
        if arriving_pawn.quantum_state == "entangled":
            add_message_to_game_log(game_state, "The entanglement of " + lead_pawn_name + " collapses as it joins a stack.", mover_seat)
            clear_quantum_state_of_pawn_and_its_link(game_state, arriving_pawn)
        place_all_moving_pawns_on_destination()
        arriving_pawn.quantum_state = "stacked_on_top"
        arriving_pawn.linked_pawn_id = pawn_already_there.pawn_id
        pawn_already_there.linked_pawn_id = arriving_pawn.pawn_id
        add_message_to_game_log(game_state, lead_pawn_name + " lands on " + get_pawn_display_name(pawn_already_there) + " in superposition - they stack instead of bumping.", mover_seat)
        return

    # C2: it is your own ordinary pawn: you cannot land there.
    if pawn_already_there.owner_seat == mover_seat:
        raise IllegalMoveError("You cannot land on your own pawn.")

    # C3: it is an opponent's ordinary pawn: BUMP! It goes back to Start.
    send_pawn_back_to_start(game_state, pawn_already_there, "bumped by " + lead_pawn_name)
    place_all_moving_pawns_on_destination()


# =============================================================================
# SECTION 10 — SLIDES
# =============================================================================

def perform_slide(game_state: GameState, sliding_pawns: list, slide: Slide) -> None:
    """Called when a pawn (or stack) lands on the first square of a slide by a
    normal forward move: it zooms to the slide's last square.

    RULE CLARIFICATION (the official rules contradict themselves here):
      * Every pawn standing on the slide (after its first square) is bumped to
        Start - EXCEPT that quantum mechanics offers some protection:
          - a lone pawn in superposition survives, but its superposition is used up;
          - a stack breaks: its bottom pawn goes to Start, the top pawn survives.
      * Nothing survives on the slide's LAST square, where the slider lands.
      * The slide also disrupts the sliding pawn's own quantum state."""
    sliding_pawn_ids = [pawn.pawn_id for pawn in sliding_pawns]
    add_message_to_game_log(game_state, get_pawn_display_name(sliding_pawns[-1]) + " hits a slide and zooms to " + describe_location_for_people(on_track(slide.slide_end_space)) + "!", sliding_pawns[0].owner_seat)

    # 1. Sweep every square the slide passes over.
    for track_space_number in range(slide.slide_start_space + 1, slide.slide_end_space + 1):
        is_last_square_of_slide = track_space_number == slide.slide_end_space
        pawns_on_this_square = find_pawns_on_space(game_state, "track-" + str(track_space_number), sliding_pawn_ids)
        if not pawns_on_this_square:
            continue

        stack_on_this_square = find_stack_containing_pawn(game_state, pawns_on_this_square[0])
        if stack_on_this_square:
            bottom_pawn, top_pawn = stack_on_this_square
            break_stack_and_send_bottom_pawn_to_start(game_state, bottom_pawn, "swept by a slide")
            if is_last_square_of_slide:
                send_pawn_back_to_start(game_state, top_pawn, "swept by a slide")
            else:
                add_message_to_game_log(game_state, get_pawn_display_name(top_pawn) + " survives the slide on top of the broken stack.", top_pawn.owner_seat)
            continue

        lone_pawn = pawns_on_this_square[0]
        if lone_pawn.quantum_state == "superposition" and not is_last_square_of_slide:
            lone_pawn.quantum_state = "none"
            add_message_to_game_log(game_state, get_pawn_display_name(lone_pawn) + " survives the slide thanks to superposition (which is now used up).", lone_pawn.owner_seat)
        else:
            send_pawn_back_to_start(game_state, lone_pawn, "swept by a slide")

    # 2. Move the sliding pawn(s) to the end of the slide.
    for pawn in sliding_pawns:
        pawn.location = on_track(slide.slide_end_space)

    # 3. The slide disrupts the slider's own quantum state.
    for pawn in sliding_pawns:
        if pawn.quantum_state == "stacked_on_top":
            bottom_pawn, _ = find_stack_containing_pawn(game_state, pawn)
            break_stack_and_send_bottom_pawn_to_start(game_state, bottom_pawn, "the slide disrupted it")
    for pawn in sliding_pawns:
        if pawn.location.zone == "track" and pawn.quantum_state != "none":
            add_message_to_game_log(game_state, "The slide disrupts the quantum state of " + get_pawn_display_name(pawn) + ".", pawn.owner_seat)
            clear_quantum_state_of_pawn_and_its_link(game_state, pawn)


# =============================================================================
# SECTION 11 — DRAWING CARDS
# =============================================================================

def take_top_movement_card(game_state: GameState) -> str:
    """Takes the top Movement card. An empty deck is rebuilt from the discards.
    RULE CLARIFICATION: the official rules only mention reshuffling the Quantum
    deck; the Movement deck needs the same treatment."""
    if not game_state.movement_draw_pile:
        game_state.movement_draw_pile = shuffle_cards(game_state.movement_discard_pile)
        game_state.movement_discard_pile = []
        add_message_to_game_log(game_state, "The Movement deck is reshuffled.")
    return game_state.movement_draw_pile.pop()


def give_quantum_card_to_player(game_state: GameState, seat_number: int, reason_text: str) -> Optional[str]:
    """Gives a player the top Quantum card if their hand has room.
    Returns the card name, or None if no card was given."""
    player = find_player_by_seat(game_state, seat_number)
    if player is None:
        return None
    if len(player.quantum_cards_in_hand) >= MAXIMUM_QUANTUM_CARDS_IN_HAND:
        add_message_to_game_log(game_state, player.display_name + "'s quantum hand is full, so no card is drawn.", seat_number)
        return None
    if not game_state.quantum_draw_pile:
        game_state.quantum_draw_pile = shuffle_cards(game_state.quantum_discard_pile)
        game_state.quantum_discard_pile = []
        add_message_to_game_log(game_state, "The Quantum State deck is reshuffled.")
    if not game_state.quantum_draw_pile:
        return None  # every quantum card is in someone's hand
    drawn_card_name = game_state.quantum_draw_pile.pop()
    player.quantum_cards_in_hand.append(drawn_card_name)
    add_message_to_game_log(game_state, player.display_name + " draws a Quantum State card (" + reason_text + ").", seat_number)
    return drawn_card_name


def discard_quantum_card_from_hand(game_state: GameState, player: Player, card_name: str) -> None:
    """Removes one copy of a card from a hand and puts it on the discard pile."""
    if card_name not in player.quantum_cards_in_hand:
        raise IllegalMoveError(player.display_name + " does not hold a " + card_name + " card.")
    player.quantum_cards_in_hand.remove(card_name)
    game_state.quantum_discard_pile.append(card_name)


# =============================================================================
# SECTION 12 — MOVING PAWNS WITH MOVEMENT CARDS
# =============================================================================

def move_pawn_out_of_start(game_state: GameState, pawn_id: str) -> None:
    """Brings one pawn out of Start onto its owner's exit square."""
    pawn = find_pawn_by_id(game_state, pawn_id)
    if pawn.location.zone != "start":
        raise IllegalMoveError("That pawn is not in Start.")
    land_moving_pawns_on_space(game_state, [pawn], on_track(get_start_exit_space_for_seat(pawn.owner_seat)))
    add_message_to_game_log(game_state, get_pawn_display_name(pawn) + " leaves Start.", pawn.owner_seat)


def move_pawn_along_path(game_state: GameState, move_details: MoveDetails, should_mirror_move_on_entangled_partner: bool = True) -> None:
    """Moves a pawn a number of squares forward or backward, with every
    consequence: bumping, stacking, slides, Quantum Spaces and entanglement.

    should_mirror_move_on_entangled_partner is normally True. It is False when
    this function is moving the partner itself, so the partner does not mirror
    the move back again forever."""
    chosen_pawn = find_pawn_by_id(game_state, move_details.pawn_id)
    if not is_pawn_on_track_or_in_safety_zone(chosen_pawn):
        raise IllegalMoveError("That pawn is not on the board.")

    # --- 1. Work out which pawns move together. ---
    if move_details.move_whole_stack:
        # RULE CLARIFICATION: a stack moves as one unit only if both of its
        # pawns belong to the player moving it.
        stack = find_stack_containing_pawn(game_state, chosen_pawn)
        if stack is None:
            raise IllegalMoveError("That pawn is not part of a stack.")
        bottom_pawn, top_pawn = stack
        if bottom_pawn.owner_seat != top_pawn.owner_seat:
            raise IllegalMoveError("Only a stack of two pawns of your own color can move as one unit.")
        moving_pawns = [bottom_pawn, top_pawn]
    else:
        # RULE CLARIFICATION: the bottom pawn of a stack is trapped until the
        # top pawn moves off.
        if is_pawn_covered_at_bottom_of_stack(chosen_pawn):
            raise IllegalMoveError("That pawn is trapped under another pawn in its stack.")
        if chosen_pawn.quantum_state == "stacked_on_top":
            dissolve_stack_peacefully_as_top_pawn_leaves(game_state, chosen_pawn)
        moving_pawns = [chosen_pawn]

    # Remember the entangled partner now (landing might break the link).
    entangled_partner_id = chosen_pawn.linked_pawn_id if chosen_pawn.quantum_state == "entangled" else None

    # --- 2. Walk along the path. ---
    destination = walk_along_path(chosen_pawn.location, chosen_pawn.owner_seat, move_details.number_of_steps, move_details.direction)
    if destination is None:
        raise IllegalMoveError("That move would overshoot Home (Home needs an exact count).")

    mover_words = ("The " + PLAYER_COLOR_NAMES[chosen_pawn.owner_seat] + " stack") if len(moving_pawns) > 1 else get_pawn_display_name(chosen_pawn)
    add_message_to_game_log(game_state, mover_words + " moves " + str(move_details.number_of_steps) + " " + move_details.direction + " to " + describe_location_for_people(destination) + ".", chosen_pawn.owner_seat)

    # --- 3. Land on the destination square (bumps, stacking, Home...). ---
    land_moving_pawns_on_space(game_state, moving_pawns, destination)

    # --- 4. Slides: only when moving forward onto a slide's first square. ---
    if move_details.direction == "forward" and destination.zone == "track":
        slide_starting_here = find_slide_that_starts_on_space(destination.track_space_number)
        if slide_starting_here:
            perform_slide(game_state, moving_pawns, slide_starting_here)

    # --- 5. Quantum Spaces: ending a move there earns a quantum card. ---
    for pawn in moving_pawns:
        if pawn.location.zone == "track":
            if is_track_space_a_quantum_space(pawn.location.track_space_number):
                give_quantum_card_to_player(game_state, pawn.owner_seat, "landed on Quantum Space " + get_quantum_space_label(pawn.location.track_space_number))
            break

    # --- 6. Entanglement: the partner mirrors the same move. ---
    # RULE CLARIFICATION: if the mirrored move is impossible, the entanglement
    # breaks and the partner stays where it is.
    if should_mirror_move_on_entangled_partner and entangled_partner_id is not None:
        chosen_pawn_now = find_pawn_by_id(game_state, move_details.pawn_id)
        link_still_exists = chosen_pawn_now.quantum_state == "entangled" and chosen_pawn_now.linked_pawn_id == entangled_partner_id
        if link_still_exists:
            partner_pawn = find_pawn_by_id(game_state, entangled_partner_id)
            add_message_to_game_log(game_state, "Entangled! " + get_pawn_display_name(partner_pawn) + " mirrors the move.", partner_pawn.owner_seat)
            saved_copy_before_partner_move = game_state.make_independent_copy()
            try:
                move_pawn_along_path(game_state, MoveDetails(entangled_partner_id, move_details.number_of_steps, move_details.direction), False)
            except IllegalMoveError as problem:
                # Undo the partner's attempted move and break the link instead.
                game_state.overwrite_with_copy(saved_copy_before_partner_move)
                partner_after_undo = find_pawn_by_id(game_state, entangled_partner_id)
                add_message_to_game_log(game_state, get_pawn_display_name(partner_after_undo) + " cannot mirror the move (" + str(problem) + ") - the entanglement breaks.", partner_after_undo.owner_seat)
                clear_quantum_state_of_pawn_and_its_link(game_state, partner_after_undo)

    # --- 7. The Safety Zone rule for entangled pawns of different colors. ---
    apply_safety_zone_rule_to_entangled_pawn(game_state, find_pawn_by_id(game_state, move_details.pawn_id))


# =============================================================================
# SECTION 13 — WHICH MOVEMENT OPTIONS DOES THE CURRENT CARD ALLOW?
# =============================================================================

@dataclass(frozen=True)
class MovingUnit:
    """Something a player can pick to move: a single pawn, or a whole stack of
    two of their own pawns. The bottom pawn of a stack can't be picked alone."""
    pawn_id: str
    move_whole_stack: bool
    pawn_ids_in_unit: tuple


def list_moving_units_for_seat(game_state: GameState, seat_number: int) -> list:
    moving_units = []
    for pawn in get_pawns_owned_by_seat(game_state, seat_number):
        if not is_pawn_on_track_or_in_safety_zone(pawn) or is_pawn_covered_at_bottom_of_stack(pawn):
            continue
        moving_units.append(MovingUnit(pawn.pawn_id, False, (pawn.pawn_id,)))
        if pawn.quantum_state == "stacked_on_top":
            bottom_pawn = find_pawn_by_id(game_state, pawn.linked_pawn_id)
            if bottom_pawn.owner_seat == seat_number:
                moving_units.append(MovingUnit(pawn.pawn_id, True, (bottom_pawn.pawn_id, pawn.pawn_id)))
    return moving_units


def carry_out_movement_option(game_state: GameState, movement_option: MovementOption) -> None:
    """Performs a movement option (see get_legal_movement_options)."""
    if movement_option.option_kind == "leave_start":
        move_pawn_out_of_start(game_state, movement_option.pawn_id)
    elif movement_option.option_kind == "move":
        move_pawn_along_path(game_state, movement_option.move_details)
    elif movement_option.option_kind == "split_seven":
        move_pawn_along_path(game_state, movement_option.first_move_details)
        # The second pawn may have been knocked off the board by the first part.
        second_pawn = find_pawn_by_id(game_state, movement_option.second_move_details.pawn_id)
        if not is_pawn_on_track_or_in_safety_zone(second_pawn):
            raise IllegalMoveError("The second pawn was knocked off the board by the first part of the split.")
        move_pawn_along_path(game_state, movement_option.second_move_details)
    else:
        raise ValueError("Unknown movement option: " + movement_option.option_kind)


def describe_move_details(game_state: GameState, move_details: MoveDetails) -> str:
    """Words for one move, e.g. 'Red 2 5' or 'Red 2 back 4'."""
    pawn = find_pawn_by_id(game_state, move_details.pawn_id)
    what_moves = ("Stack (" + get_pawn_display_name(pawn) + " + partner)") if move_details.move_whole_stack else get_pawn_display_name(pawn)
    backward_word = "" if move_details.direction == "forward" else " back"
    return what_moves + backward_word + " " + str(move_details.number_of_steps)


def describe_consequences(game_state_before: GameState, game_state_after: GameState, main_pawn_id: Optional[str], include_destination: bool = True) -> str:
    """Adds ' -> square 23 · bumps 1' style endings to option descriptions, so
    players see what a choice does before making it."""
    ending = ""
    if main_pawn_id and include_destination:
        ending += " -> " + describe_location_for_people(find_pawn_by_id(game_state_after, main_pawn_id).location)
    current_seat = get_current_player(game_state_before).seat_number
    number_of_opponent_pawns_bumped = 0
    number_of_own_pawns_lost = 0
    for pawn_before in game_state_before.pawns:
        pawn_after = find_pawn_by_id(game_state_after, pawn_before.pawn_id)
        if pawn_before.location.zone != "start" and pawn_after.location.zone == "start":
            if pawn_before.owner_seat == current_seat:
                number_of_own_pawns_lost += 1
            else:
                number_of_opponent_pawns_bumped += 1
    if number_of_opponent_pawns_bumped:
        ending += " · bumps " + str(number_of_opponent_pawns_bumped)
    if number_of_own_pawns_lost:
        ending += " · you lose " + str(number_of_own_pawns_lost)
    return ending


def get_legal_movement_options(game_state: GameState) -> list:
    """Lists every legal way the current player can use the movement card
    they drew (each option includes the game as it would look afterwards)."""
    card_name = game_state.current_movement_card
    if game_state.turn_phase != "choosing_how_to_use_movement_card" or card_name is None:
        return []
    card_rule = MOVEMENT_CARD_RULES[card_name]
    current_seat = get_current_player(game_state).seat_number
    candidate_options = []

    # (a) Leaving Start. Pawns in Start are identical, so one option is enough.
    if card_rule.can_leave_start:
        for pawn in get_pawns_owned_by_seat(game_state, current_seat):
            if pawn.location.zone == "start":
                candidate_options.append(MovementOption("leave_start", "Bring " + get_pawn_display_name(pawn) + " out of Start", [pawn.pawn_id], pawn_id=pawn.pawn_id))
                break

    moving_units = list_moving_units_for_seat(game_state, current_seat)

    # (b) Simple moves forward and backward.
    step_choices = [(steps, "forward") for steps in card_rule.forward_step_choices] + [(steps, "backward") for steps in card_rule.backward_step_choices]
    for moving_unit in moving_units:
        for number_of_steps, direction in step_choices:
            move_details = MoveDetails(moving_unit.pawn_id, number_of_steps, direction, moving_unit.move_whole_stack)
            candidate_options.append(MovementOption("move", describe_move_details(game_state, move_details), list(moving_unit.pawn_ids_in_unit), move_details=move_details))

    # (c) Splitting a 7 between two different moving units.
    if card_rule.can_split_between_two_pawns:
        for first_index, first_unit in enumerate(moving_units):
            for second_unit in moving_units[first_index + 1:]:
                if set(first_unit.pawn_ids_in_unit) & set(second_unit.pawn_ids_in_unit):
                    continue  # the two units share a pawn
                for steps_for_first in range(1, 7):
                    first_details = MoveDetails(first_unit.pawn_id, steps_for_first, "forward", first_unit.move_whole_stack)
                    second_details = MoveDetails(second_unit.pawn_id, 7 - steps_for_first, "forward", second_unit.move_whole_stack)
                    description = "Split: " + describe_move_details(game_state, first_details) + " + " + describe_move_details(game_state, second_details)
                    involved = list(first_unit.pawn_ids_in_unit) + list(second_unit.pawn_ids_in_unit)
                    # Try "first then second"; if that is illegal, try the other order.
                    first_then_second = MovementOption("split_seven", description, involved, first_move_details=first_details, second_move_details=second_details)
                    second_then_first = MovementOption("split_seven", description, involved, first_move_details=second_details, second_move_details=first_details)
                    works = try_action_on_copy_of_game(game_state, lambda copy: carry_out_movement_option(copy, first_then_second))
                    candidate_options.append(first_then_second if works else second_then_first)

    # Keep only the legal options, by trying each one on a copy of the game.
    legal_options = []
    for option in candidate_options:
        resulting_game_state = try_action_on_copy_of_game(game_state, lambda copy, option=option: carry_out_movement_option(copy, option))
        if resulting_game_state is not None:
            option.resulting_game_state = resulting_game_state
            main_pawn_id = option.pawn_id or (option.move_details.pawn_id if option.move_details else None)
            option.description += describe_consequences(game_state, resulting_game_state, main_pawn_id)
            legal_options.append(option)
    return legal_options


# =============================================================================
# SECTION 14 — QUANTUM CARD EFFECTS
# =============================================================================

def apply_superposition_effect(game_state: GameState, pawn_id: str) -> None:
    """SUPERPOSITION: put one of your own track pawns in superposition."""
    pawn = find_pawn_by_id(game_state, pawn_id)
    if pawn.location.zone != "track":
        raise IllegalMoveError("Superposition only works on pawns on the outer track.")
    if pawn.quantum_state != "none":
        raise IllegalMoveError("A pawn can only hold one quantum state at a time.")
    pawn.quantum_state = "superposition"
    pawn.linked_pawn_id = None
    add_message_to_game_log(game_state, get_pawn_display_name(pawn) + " enters superposition: a pawn landing here will stack instead of bumping it.", pawn.owner_seat)


def apply_teleportation_effect(game_state: GameState, pawn_id: str, destination_track_space_number: int) -> None:
    """TELEPORTATION: jump a track pawn to a target square.
    Teleporting never triggers a slide or a Quantum Space draw."""
    pawn = find_pawn_by_id(game_state, pawn_id)
    if pawn.location.zone != "track":
        raise IllegalMoveError("Only pawns on the outer track can teleport.")
    if is_pawn_covered_at_bottom_of_stack(pawn):
        raise IllegalMoveError("That pawn is trapped under another pawn in its stack.")
    if pawn.location.track_space_number == destination_track_space_number:
        raise IllegalMoveError("The pawn is already there.")
    if pawn.quantum_state == "stacked_on_top":
        dissolve_stack_peacefully_as_top_pawn_leaves(game_state, pawn)
    destination = on_track(destination_track_space_number)
    add_message_to_game_log(game_state, get_pawn_display_name(pawn) + " teleports to " + describe_location_for_people(destination) + ".", pawn.owner_seat)
    land_moving_pawns_on_space(game_state, [pawn], destination)


def apply_entangled_teleportation_effect(game_state: GameState, pawn_id: str, partner_pawn_id: str, partner_track_space_number: int) -> None:
    """ENTANGLED TELEPORTATION: jump to the entangled partner.
    RULE CLARIFICATION: with your own partner the two pawns swap places; onto an
    opponent's partner the pawn lands there and bumps it (unless countered)."""
    pawn = find_pawn_by_id(game_state, pawn_id)
    partner_pawn = find_pawn_by_id(game_state, partner_pawn_id)
    still_entangled_together = pawn.quantum_state == "entangled" and pawn.linked_pawn_id == partner_pawn_id
    if still_entangled_together and partner_pawn.owner_seat == pawn.owner_seat:
        if pawn.location.zone != "track" or partner_pawn.location.zone != "track":
            raise IllegalMoveError("Both pawns must be on the outer track to swap.")
        pawn.location, partner_pawn.location = partner_pawn.location, pawn.location
        add_message_to_game_log(game_state, get_pawn_display_name(pawn) + " and " + get_pawn_display_name(partner_pawn) + " teleport through their entanglement and swap places.", pawn.owner_seat)
        return
    # The partner is an opponent's pawn (or was turned into a superposition pawn
    # by a counter): treat it like teleporting onto that square.
    apply_teleportation_effect(game_state, pawn_id, partner_track_space_number)


def apply_entanglement_effect(game_state: GameState, first_pawn_id: str, second_pawn_id: str) -> None:
    """ENTANGLEMENT: link two track pawns."""
    if first_pawn_id == second_pawn_id:
        raise IllegalMoveError("Pick two different pawns.")
    first_pawn = find_pawn_by_id(game_state, first_pawn_id)
    second_pawn = find_pawn_by_id(game_state, second_pawn_id)
    if first_pawn.location.zone != "track" or second_pawn.location.zone != "track":
        raise IllegalMoveError("Both pawns must be on the outer track.")
    if first_pawn.quantum_state != "none" or second_pawn.quantum_state != "none":
        raise IllegalMoveError("A pawn can only hold one quantum state at a time.")
    first_pawn.quantum_state = second_pawn.quantum_state = "entangled"
    first_pawn.linked_pawn_id = second_pawn_id
    second_pawn.linked_pawn_id = first_pawn_id
    add_message_to_game_log(game_state, get_pawn_display_name(first_pawn) + " and " + get_pawn_display_name(second_pawn) + " are now entangled.", first_pawn.owner_seat)


def apply_quantum_break_effect(game_state: GameState) -> None:
    """QUANTUM BREAK: end every quantum state on the board and lift every Jam."""
    add_message_to_game_log(game_state, "QUANTUM BREAK! Every quantum state on the board collapses.")
    # First break the stacks (their bottom pawns go to Start)...
    for pawn in game_state.pawns:
        if is_pawn_covered_at_bottom_of_stack(pawn):
            break_stack_and_send_bottom_pawn_to_start(game_state, pawn, "Quantum Break")
    # ...then clear everything else.
    for pawn in game_state.pawns:
        if pawn.quantum_state != "none":
            clear_quantum_state_of_pawn_and_its_link(game_state, pawn)
    for player in game_state.players:
        player.is_jammed_for_their_next_turn = False


def apply_decohere_effect(game_state: GameState, pawn_id: str) -> None:
    """INTERFERENCE/NOISE 'Decohere': end one pawn's quantum state. Works
    anywhere, even inside a Safety Zone (official rule)."""
    pawn = find_pawn_by_id(game_state, pawn_id)
    if pawn.quantum_state == "none":
        raise IllegalMoveError("That pawn has no quantum state to disrupt.")
    stack = find_stack_containing_pawn(game_state, pawn)
    if stack:
        break_stack_and_send_bottom_pawn_to_start(game_state, stack[0], "Interference")
        return
    partner_words = " and its partner" if pawn.quantum_state == "entangled" else ""
    add_message_to_game_log(game_state, "Interference! The quantum state of " + get_pawn_display_name(pawn) + partner_words + " collapses.")
    clear_quantum_state_of_pawn_and_its_link(game_state, pawn)


def apply_jam_effect(game_state: GameState, target_seat_number: int) -> None:
    """INTERFERENCE/NOISE 'Jam': an opponent cannot play quantum cards during
    their next turn."""
    target_player = find_player_by_seat(game_state, target_seat_number)
    if target_player is None:
        raise IllegalMoveError("No such player.")
    if target_player.is_jammed_for_their_next_turn:
        raise IllegalMoveError("That player is already jammed.")
    target_player.is_jammed_for_their_next_turn = True
    add_message_to_game_log(game_state, target_player.display_name + " is jammed: no quantum cards on their next turn.", target_seat_number)


def carry_out_quantum_effect(game_state: GameState, quantum_option: QuantumOption) -> None:
    """Performs the effect of a quantum option (see get_quantum_play_options)."""
    effect = quantum_option.effect_kind
    if effect == "quantum_launch":
        move_pawn_out_of_start(game_state, quantum_option.pawn_id)
    elif effect == "superposition":
        apply_superposition_effect(game_state, quantum_option.pawn_id)
    elif effect == "teleport":
        apply_teleportation_effect(game_state, quantum_option.pawn_id, quantum_option.destination_track_space_number)
    elif effect == "entangled_teleport":
        apply_entangled_teleportation_effect(game_state, quantum_option.pawn_id, quantum_option.second_pawn_id, quantum_option.destination_track_space_number)
    elif effect == "entangle":
        apply_entanglement_effect(game_state, quantum_option.pawn_id, quantum_option.second_pawn_id)
    elif effect == "quantum_break":
        apply_quantum_break_effect(game_state)
    elif effect == "decohere":
        apply_decohere_effect(game_state, quantum_option.pawn_id)
    elif effect == "jam":
        apply_jam_effect(game_state, quantum_option.target_seat_number)
    else:
        raise ValueError("Unknown quantum effect: " + effect)


# =============================================================================
# SECTION 15 — WHICH QUANTUM PLAYS ARE AVAILABLE?
# =============================================================================

def can_current_player_play_quantum_card(game_state: GameState) -> bool:
    """One quantum card per turn, never while jammed, and only with cards in hand."""
    if game_state.turn_phase == "game_over":
        return False
    current_player = get_current_player(game_state)
    return (not game_state.has_played_quantum_card_this_turn
            and not current_player.is_jammed_for_their_next_turn
            and len(current_player.quantum_cards_in_hand) > 0)


def get_quantum_play_options(game_state: GameState) -> list:
    """Lists every legal quantum play for the current player (each option
    includes the game as it would look if nobody countered it)."""
    if not can_current_player_play_quantum_card(game_state):
        return []
    current_player = get_current_player(game_state)
    current_seat = current_player.seat_number
    own_pawns = get_pawns_owned_by_seat(game_state, current_seat)
    candidate_options = []

    # dict.fromkeys keeps one copy of each card name, in hand order.
    for card_name in dict.fromkeys(current_player.quantum_cards_in_hand):

        # RULE CLARIFICATION: ANY quantum card can be spent to launch a pawn out
        # of Start ("Pawns can leave Start ... with any Quantum State Card").
        pawn_in_start = next((pawn for pawn in own_pawns if pawn.location.zone == "start"), None)
        if pawn_in_start:
            candidate_options.append(QuantumOption(card_name, "quantum_launch", "Quantum Launch: bring " + get_pawn_display_name(pawn_in_start) + " out of Start", [pawn_in_start.pawn_id], pawn_id=pawn_in_start.pawn_id))

        if card_name == SUPERPOSITION:
            for pawn in own_pawns:
                if pawn.location.zone == "track" and pawn.quantum_state == "none":
                    candidate_options.append(QuantumOption(card_name, "superposition", "Put " + get_pawn_display_name(pawn) + " in superposition", [pawn.pawn_id], pawn_id=pawn.pawn_id))

        if card_name == TELEPORTATION:
            for pawn in own_pawns:
                if pawn.location.zone != "track" or is_pawn_covered_at_bottom_of_stack(pawn):
                    continue
                for destination_space in ALL_TELEPORT_DESTINATION_SPACES:
                    if destination_space != pawn.location.track_space_number:
                        candidate_options.append(QuantumOption(card_name, "teleport", "Teleport " + get_pawn_display_name(pawn) + " -> " + describe_location_for_people(on_track(destination_space)), [pawn.pawn_id], pawn_id=pawn.pawn_id, destination_track_space_number=destination_space))
                if pawn.quantum_state == "entangled":
                    partner_pawn = find_pawn_by_id(game_state, pawn.linked_pawn_id)
                    if partner_pawn.location.zone == "track":
                        if partner_pawn.owner_seat == current_seat:
                            description = "Entangled teleport: swap " + get_pawn_display_name(pawn) + " and " + get_pawn_display_name(partner_pawn)
                        else:
                            description = "Entangled teleport: " + get_pawn_display_name(pawn) + " jumps onto " + get_pawn_display_name(partner_pawn)
                        candidate_options.append(QuantumOption(card_name, "entangled_teleport", description, [pawn.pawn_id, partner_pawn.pawn_id], pawn_id=pawn.pawn_id, second_pawn_id=partner_pawn.pawn_id, destination_track_space_number=partner_pawn.location.track_space_number))

        if card_name == ENTANGLEMENT:
            # RULE CLARIFICATION: any two track pawns, as long as one is yours.
            free_track_pawns = [pawn for pawn in game_state.pawns if pawn.location.zone == "track" and pawn.quantum_state == "none"]
            for own_pawn in [pawn for pawn in free_track_pawns if pawn.owner_seat == current_seat]:
                for other_pawn in free_track_pawns:
                    if other_pawn.pawn_id == own_pawn.pawn_id:
                        continue
                    if other_pawn.owner_seat == current_seat and other_pawn.pawn_number < own_pawn.pawn_number:
                        continue  # don't list the same pair of your own pawns twice
                    candidate_options.append(QuantumOption(card_name, "entangle", "Entangle " + get_pawn_display_name(own_pawn) + " with " + get_pawn_display_name(other_pawn), [own_pawn.pawn_id, other_pawn.pawn_id], pawn_id=own_pawn.pawn_id, second_pawn_id=other_pawn.pawn_id))

        if card_name == QUANTUM_BREAK:
            candidate_options.append(QuantumOption(card_name, "quantum_break", "Collapse every quantum state on the board", []))

        if card_name == INTERFERENCE:
            already_listed_pairs = set()
            for pawn in game_state.pawns:
                if pawn.quantum_state == "none":
                    continue
                pair_key = frozenset([pawn.pawn_id, pawn.linked_pawn_id or ""])
                if pair_key in already_listed_pairs:
                    continue  # list each stack / entangled pair only once
                already_listed_pairs.add(pair_key)
                linked_pawn = find_pawn_by_id(game_state, pawn.linked_pawn_id) if pawn.linked_pawn_id else None
                state_words = "entanglement" if pawn.quantum_state == "entangled" else ("stack" if linked_pawn else "superposition")
                names = get_pawn_display_name(pawn) + (" & " + get_pawn_display_name(linked_pawn) if linked_pawn else "")
                involved = [pawn.pawn_id] + ([linked_pawn.pawn_id] if linked_pawn else [])
                candidate_options.append(QuantumOption(card_name, "decohere", "End the " + state_words + " of " + names, involved, pawn_id=pawn.pawn_id))
            for other_player in game_state.players:
                if other_player.seat_number != current_seat and not other_player.is_jammed_for_their_next_turn:
                    candidate_options.append(QuantumOption(card_name, "jam", "Jam " + other_player.display_name + " (no quantum cards next turn)", [], target_seat_number=other_player.seat_number))

    # Keep only the legal options, by trying each on a copy of the game.
    legal_options = []
    for option in candidate_options:
        resulting_game_state = try_action_on_copy_of_game(game_state, lambda copy, option=option: carry_out_quantum_effect(copy, option))
        if resulting_game_state is not None:
            option.resulting_game_state = resulting_game_state
            if option.effect_kind in ("teleport", "entangled_teleport"):
                option.description += describe_consequences(game_state, resulting_game_state, option.pawn_id, include_destination=False)
            legal_options.append(option)
    return legal_options


# =============================================================================
# SECTION 16 — COUNTERING ANOTHER PLAYER'S QUANTUM CARD
# =============================================================================

def list_possible_reactions_to_quantum_play(game_state: GameState, quantum_option: QuantumOption) -> list:
    """When a player plays a quantum card, opponents may react ONCE:
      * 'cancel' - play Interference/Noise to stop the card completely;
      * 'shield' - when a teleport would bump your pawn, play Superposition so
                   that pawn is in superposition: the teleporter stacks on top.
    A Quantum Launch cannot be countered (it is not a quantum effect). A jammed
    player cannot react. A counter cannot itself be countered.
    Returns the possible reactions in turn order."""
    if quantum_option.effect_kind == "quantum_launch":
        return []
    acting_seat = get_current_player(game_state).seat_number

    # Which pawn (if any) would this teleport bump?
    pawn_threatened_by_teleport = None
    if quantum_option.effect_kind in ("teleport", "entangled_teleport"):
        pawns_on_destination = find_pawns_on_space(game_state, "track-" + str(quantum_option.destination_track_space_number), [quantum_option.pawn_id])
        if len(pawns_on_destination) == 1:
            only_pawn_there = pawns_on_destination[0]
            if only_pawn_there.owner_seat != acting_seat and only_pawn_there.quantum_state in ("none", "entangled"):
                pawn_threatened_by_teleport = only_pawn_there

    possible_reactions = []
    number_of_players = len(game_state.players)
    # Visit opponents in turn order, starting with the player after the actor.
    for offset in range(1, number_of_players):
        reacting_player = game_state.players[(game_state.index_of_current_player + offset) % number_of_players]
        if reacting_player.is_jammed_for_their_next_turn:
            continue
        if INTERFERENCE in reacting_player.quantum_cards_in_hand:
            possible_reactions.append(Reaction(reacting_player.seat_number, "cancel", INTERFERENCE, "Play Interference/Noise to cancel it"))
        if (pawn_threatened_by_teleport is not None
                and pawn_threatened_by_teleport.owner_seat == reacting_player.seat_number
                and SUPERPOSITION in reacting_player.quantum_cards_in_hand):
            possible_reactions.append(Reaction(reacting_player.seat_number, "shield", SUPERPOSITION,
                                               "Play Superposition on " + get_pawn_display_name(pawn_threatened_by_teleport) + " so it stacks instead of being bumped",
                                               shielded_pawn_id=pawn_threatened_by_teleport.pawn_id))
    return possible_reactions


def play_quantum_card(game_state: GameState, quantum_option: QuantumOption, chosen_reaction: Optional[Reaction] = None) -> None:
    """Plays a quantum card for the current player, including the reaction an
    opponent chose (or None if nobody reacted)."""
    if not can_current_player_play_quantum_card(game_state):
        raise IllegalMoveError("You cannot play a quantum card right now.")

    def play_on_copy(copy: GameState) -> None:
        acting_player = get_current_player(copy)
        discard_quantum_card_from_hand(copy, acting_player, quantum_option.card_name)
        copy.has_played_quantum_card_this_turn = True
        add_message_to_game_log(copy, acting_player.display_name + " plays " + quantum_option.card_name + ": " + quantum_option.description + ".", acting_player.seat_number)

        if chosen_reaction is not None:
            reacting_player = find_player_by_seat(copy, chosen_reaction.reacting_seat)
            discard_quantum_card_from_hand(copy, reacting_player, chosen_reaction.card_name)
            if chosen_reaction.reaction_kind == "cancel":
                add_message_to_game_log(copy, reacting_player.display_name + " counters with Interference/Noise - the card has no effect!", reacting_player.seat_number)
                return  # the effect never happens
            if chosen_reaction.reaction_kind == "shield":
                shielded_pawn = find_pawn_by_id(copy, chosen_reaction.shielded_pawn_id)
                clear_quantum_state_of_pawn_and_its_link(copy, shielded_pawn)
                shielded_pawn.quantum_state = "superposition"
                add_message_to_game_log(copy, reacting_player.display_name + " counters with Superposition on " + get_pawn_display_name(shielded_pawn) + "!", reacting_player.seat_number)
        carry_out_quantum_effect(copy, quantum_option)

    # Try the whole thing on a copy first, so a problem never half-changes the game.
    resulting_game_state = try_action_on_copy_of_game(game_state, play_on_copy)
    if resulting_game_state is None:
        raise IllegalMoveError("That quantum play is not allowed right now.")
    game_state.overwrite_with_copy(resulting_game_state)
    check_for_winner(game_state)


# =============================================================================
# SECTION 17 — THE TURN SEQUENCE
# =============================================================================

def begin_turn_of_current_player(game_state: GameState) -> None:
    game_state.turn_phase = "waiting_to_draw_movement_card"
    game_state.current_movement_card = None
    game_state.has_played_quantum_card_this_turn = False
    current_player = get_current_player(game_state)
    jam_note = " (jammed: no quantum cards this turn)" if current_player.is_jammed_for_their_next_turn else ""
    add_message_to_game_log(game_state, "--- " + current_player.display_name + "'s turn ---" + jam_note, current_player.seat_number)


def draw_movement_card(game_state: GameState) -> str:
    """Draws the movement card for the current player."""
    if game_state.turn_phase != "waiting_to_draw_movement_card":
        raise IllegalMoveError("You cannot draw a movement card right now.")
    drawn_card_name = take_top_movement_card(game_state)
    game_state.current_movement_card = drawn_card_name
    game_state.turn_phase = "choosing_how_to_use_movement_card"
    current_player = get_current_player(game_state)
    add_message_to_game_log(game_state, current_player.display_name + " draws a " + drawn_card_name + ".", current_player.seat_number)
    return drawn_card_name


def finish_using_movement_card(game_state: GameState) -> None:
    """After the movement card is used (moved, sacrificed or discarded): discard
    it, check for a winner, and handle 'draw again'."""
    used_card_name = game_state.current_movement_card
    game_state.movement_discard_pile.append(used_card_name)
    game_state.current_movement_card = None
    if check_for_winner(game_state):
        return
    # RULE CLARIFICATION: a 2 always grants another draw, even if sacrificed.
    if MOVEMENT_CARD_RULES[used_card_name].grants_another_draw:
        current_player = get_current_player(game_state)
        add_message_to_game_log(game_state, "A 2 was drawn - " + current_player.display_name + " draws again!", current_player.seat_number)
        game_state.turn_phase = "waiting_to_draw_movement_card"
    else:
        game_state.turn_phase = "finishing_turn"


def use_movement_card(game_state: GameState, movement_option: MovementOption) -> None:
    """Uses the movement card for one of the options from get_legal_movement_options."""
    if game_state.turn_phase != "choosing_how_to_use_movement_card":
        raise IllegalMoveError("There is no movement card to use.")
    resulting_game_state = try_action_on_copy_of_game(game_state, lambda copy: carry_out_movement_option(copy, movement_option))
    if resulting_game_state is None:
        raise IllegalMoveError("That move is not allowed.")
    game_state.overwrite_with_copy(resulting_game_state)
    finish_using_movement_card(game_state)


def can_sacrifice_movement_card(game_state: GameState) -> bool:
    return (game_state.turn_phase == "choosing_how_to_use_movement_card"
            and len(get_current_player(game_state).quantum_cards_in_hand) < MAXIMUM_QUANTUM_CARDS_IN_HAND)


def sacrifice_movement_card_for_quantum_card(game_state: GameState) -> None:
    """Trades the movement card for a quantum card (official rule)."""
    if not can_sacrifice_movement_card(game_state):
        raise IllegalMoveError("Your quantum hand is full (3 cards), so you cannot sacrifice.")
    current_player = get_current_player(game_state)
    add_message_to_game_log(game_state, current_player.display_name + " sacrifices the " + game_state.current_movement_card + ".", current_player.seat_number)
    give_quantum_card_to_player(game_state, current_player.seat_number, "sacrificed a movement card")
    finish_using_movement_card(game_state)


def can_discard_movement_card_without_moving(game_state: GameState) -> bool:
    """RULE CLARIFICATION: you must move if you can. Discarding without moving
    is only allowed when no legal move exists."""
    return game_state.turn_phase == "choosing_how_to_use_movement_card" and not get_legal_movement_options(game_state)


def discard_movement_card_without_moving(game_state: GameState) -> None:
    if not can_discard_movement_card_without_moving(game_state):
        raise IllegalMoveError("You have a legal move, so you must use or sacrifice the card.")
    current_player = get_current_player(game_state)
    add_message_to_game_log(game_state, current_player.display_name + " cannot use the " + game_state.current_movement_card + " and discards it.", current_player.seat_number)
    finish_using_movement_card(game_state)


def end_turn(game_state: GameState) -> None:
    """Ends the current turn and passes play clockwise to the next player."""
    if game_state.turn_phase != "finishing_turn":
        raise IllegalMoveError("Finish using your movement card first.")
    finishing_player = get_current_player(game_state)
    # A jam lasts for exactly one of the jammed player's turns.
    if finishing_player.is_jammed_for_their_next_turn:
        finishing_player.is_jammed_for_their_next_turn = False
        add_message_to_game_log(game_state, finishing_player.display_name + " is no longer jammed.", finishing_player.seat_number)
    game_state.index_of_current_player = (game_state.index_of_current_player + 1) % len(game_state.players)
    game_state.turn_number += 1
    begin_turn_of_current_player(game_state)


def check_for_winner(game_state: GameState) -> bool:
    """Has somebody got all four pawns Home? If so, the game ends.
    RULE CLARIFICATION: turns happen one at a time, so the first player to bring
    the fourth pawn Home wins; a tie cannot happen."""
    if game_state.seat_of_winner is not None:
        return True
    for player in game_state.players:
        if all(pawn.location.zone == "home" for pawn in get_pawns_owned_by_seat(game_state, player.seat_number)):
            game_state.seat_of_winner = player.seat_number
            game_state.turn_phase = "game_over"
            add_message_to_game_log(game_state, player.display_name + " brings all four pawns Home and WINS Quantastic!", player.seat_number)
            return True
    return False
