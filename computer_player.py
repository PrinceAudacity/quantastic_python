"""
=============================================================================
QUANTASTIC!  —  COMPUTER PLAYER  (computer_player.py)
-----------------------------------------------------------------------------
This file decides what a computer-controlled player does.

HOW THE COMPUTER THINKS (in plain words)
----------------------------------------
The computer does not plan many turns ahead. For every choice it could make
right now, it asks the game engine "what would the board look like
afterwards?" and gives that imagined board a SCORE. Then it picks the choice
with the best score.

The score is a simple recipe, from the computer player's point of view:
  + how far its own pawns have travelled (with bonuses for safe pawns)
  - how far its opponents' pawns have travelled
  + a little for every quantum card it holds (cards are useful later)
  - a little for every one of its pawns an opponent could bump soon
Change the numbers in SCORING_WEIGHTS to make the computer play more
aggressively or more cautiously.

NumPy (imported as "np") is a library for doing arithmetic on whole lists of
numbers at once. Here it measures the distance between every opponent pawn
and one of our pawns in a single step.
=============================================================================
"""

import random

import numpy as np

import game_engine as engine


# All of the computer player's "taste" lives in these numbers.
SCORING_WEIGHTS = {
    "points_per_square_travelled": 1.0,      # each square closer to Home
    "bonus_for_pawn_out_of_start": 4.0,      # simply being on the board
    "bonus_for_pawn_in_safety_zone": 6.0,    # can no longer be bumped
    "bonus_for_pawn_at_home": 12.0,          # finished
    "bonus_for_protected_pawn": 3.0,         # own pawn in superposition on the track
    "bonus_for_own_entangled_pair": 2.5,     # per pawn: two of our pawns move together
    "bonus_for_link_to_opponent": 4.0,       # our pawn rides along when an opponent moves
    "penalty_for_trapped_under_opponent": 5.0,  # own pawn stuck under an opponent's pawn
    "penalty_per_threatening_opponent": 1.2,    # opponent pawn 1-12 squares behind ours
    "importance_of_opponent_progress": 0.7,     # how much we care about slowing opponents
    "value_per_quantum_card_in_hand": 3.5,      # a card in hand is worth this much
    "value_of_opponent_quantum_card": 1.2,      # an opponent's card is a small threat
    "minimum_gain_to_play_quantum_card": 1.0,   # only play a card if it gains at least this
    "loss_that_justifies_shield": 3.0,          # when to protect a pawn with Superposition
    "loss_that_justifies_cancel": 5.0,          # when to cancel with Interference/Noise
}


def get_value_of_keeping_card(card_name: str) -> float:
    """Interference and Superposition are worth a bit more in hand, because
    they can counter an opponent's play."""
    base_value = SCORING_WEIGHTS["value_per_quantum_card_in_hand"]
    if card_name == engine.INTERFERENCE:
        return base_value + 1.0
    if card_name == engine.SUPERPOSITION:
        return base_value + 0.5
    return base_value


def score_single_pawn_position(pawn: engine.Pawn) -> float:
    """How valuable one pawn's situation is, whoever owns it."""
    steps_travelled = engine.STEPS_FROM_START_TO_HOME - engine.count_steps_remaining_to_home(pawn)
    pawn_score = steps_travelled * SCORING_WEIGHTS["points_per_square_travelled"]
    zone = pawn.location.zone
    if zone != "start":
        pawn_score += SCORING_WEIGHTS["bonus_for_pawn_out_of_start"]
    if zone == "safety":
        pawn_score += SCORING_WEIGHTS["bonus_for_pawn_in_safety_zone"]
    if zone == "home":
        pawn_score += SCORING_WEIGHTS["bonus_for_pawn_in_safety_zone"] + SCORING_WEIGHTS["bonus_for_pawn_at_home"]
    return pawn_score


def count_opponents_that_could_bump_pawn(game_state: engine.GameState, pawn: engine.Pawn) -> int:
    """Counts opponent pawns standing 1 to 12 squares BEHIND this pawn on the
    track - they could land on it with a single card."""
    if pawn.location.zone != "track" or pawn.quantum_state == "superposition":
        return 0
    opponent_track_squares = np.array([
        other.location.track_space_number for other in game_state.pawns
        if other.owner_seat != pawn.owner_seat and other.location.zone == "track"
    ], dtype=int)
    if opponent_track_squares.size == 0:
        return 0
    # Distance behind, going around the loop (the % makes it wrap around).
    distances_behind = (pawn.location.track_space_number - opponent_track_squares) % engine.NUMBER_OF_TRACK_SPACES
    return int(np.count_nonzero((distances_behind >= 1) & (distances_behind <= 12)))


def score_board_for_seat(game_state: engine.GameState, seat_number: int) -> float:
    """THE SCORE of a whole board, as seen by the player in seat_number.
    Higher is better for that player."""
    if game_state.seat_of_winner == seat_number:
        return 100000.0
    if game_state.seat_of_winner is not None:
        return -100000.0

    board_score = 0.0
    for pawn in game_state.pawns:
        pawn_score = score_single_pawn_position(pawn)
        if pawn.owner_seat != seat_number:
            board_score -= pawn_score * SCORING_WEIGHTS["importance_of_opponent_progress"]
            continue
        board_score += pawn_score
        if pawn.location.zone == "track" and pawn.quantum_state == "superposition" and pawn.linked_pawn_id is None:
            board_score += SCORING_WEIGHTS["bonus_for_protected_pawn"]
        # Entanglement means free extra movement: when the partner is moved by
        # a card, our pawn moves too (and the other way round).
        if pawn.quantum_state == "entangled":
            partner_pawn = engine.find_pawn_by_id(game_state, pawn.linked_pawn_id)
            if partner_pawn.owner_seat == seat_number:
                board_score += SCORING_WEIGHTS["bonus_for_own_entangled_pair"]
            else:
                board_score += SCORING_WEIGHTS["bonus_for_link_to_opponent"]
        if engine.is_pawn_covered_at_bottom_of_stack(pawn):
            top_pawn = engine.find_pawn_by_id(game_state, pawn.linked_pawn_id)
            if top_pawn.owner_seat != seat_number:
                board_score -= SCORING_WEIGHTS["penalty_for_trapped_under_opponent"]
        board_score -= count_opponents_that_could_bump_pawn(game_state, pawn) * SCORING_WEIGHTS["penalty_per_threatening_opponent"]

    for player in game_state.players:
        if player.seat_number == seat_number:
            board_score += sum(get_value_of_keeping_card(card_name) for card_name in player.quantum_cards_in_hand)
        else:
            threat_factor = 0.4 if player.is_jammed_for_their_next_turn else 1.0
            board_score -= len(player.quantum_cards_in_hand) * SCORING_WEIGHTS["value_of_opponent_quantum_card"] * threat_factor
    return board_score


def find_worthwhile_quantum_play(game_state: engine.GameState):
    """The best quantum play for the current player, or None if no play is
    worth more than keeping the card."""
    if not engine.can_current_player_play_quantum_card(game_state):
        return None
    my_seat = engine.get_current_player(game_state).seat_number
    score_right_now = score_board_for_seat(game_state, my_seat)
    best_option = None
    best_gain = SCORING_WEIGHTS["minimum_gain_to_play_quantum_card"]
    for quantum_option in engine.get_quantum_play_options(game_state):
        # The imagined board still shows the card in hand, so subtract its value.
        gain = (score_board_for_seat(quantum_option.resulting_game_state, my_seat)
                - get_value_of_keeping_card(quantum_option.card_name)
                - score_right_now)
        if gain > best_gain:
            best_gain = gain
            best_option = quantum_option
    return best_option


class ComputerDecision:
    """What the computer wants to do next.
    action_type is one of: 'play_quantum_card', 'draw_movement_card',
    'use_movement_card', 'sacrifice_movement_card', 'discard_movement_card',
    'end_turn'."""

    def __init__(self, action_type, quantum_option=None, movement_option=None):
        self.action_type = action_type
        self.quantum_option = quantum_option
        self.movement_option = movement_option


def choose_next_action(game_state: engine.GameState):
    """The main question: 'it is my turn - what do I do next?'"""
    phase = game_state.turn_phase
    my_seat = engine.get_current_player(game_state).seat_number

    if phase == "waiting_to_draw_movement_card":
        quantum_play = find_worthwhile_quantum_play(game_state)
        if quantum_play:
            return ComputerDecision("play_quantum_card", quantum_option=quantum_play)
        return ComputerDecision("draw_movement_card")

    if phase == "choosing_how_to_use_movement_card":
        best_decision = None
        best_score = float("-inf")
        for movement_option in engine.get_legal_movement_options(game_state):
            # A tiny random nudge breaks ties so games don't all look the same.
            option_score = score_board_for_seat(movement_option.resulting_game_state, my_seat) + random.random() * 0.01
            if option_score > best_score:
                best_score = option_score
                best_decision = ComputerDecision("use_movement_card", movement_option=movement_option)
        if engine.can_sacrifice_movement_card(game_state):
            # Sacrificing keeps the board as it is and adds one card to the hand.
            score_if_sacrificed = score_board_for_seat(game_state, my_seat) + SCORING_WEIGHTS["value_per_quantum_card_in_hand"]
            if score_if_sacrificed > best_score:
                best_decision = ComputerDecision("sacrifice_movement_card")
        return best_decision or ComputerDecision("discard_movement_card")

    if phase == "finishing_turn":
        quantum_play = find_worthwhile_quantum_play(game_state)
        if quantum_play:
            return ComputerDecision("play_quantum_card", quantum_option=quantum_play)
        return ComputerDecision("end_turn")

    return None  # the game is over


def choose_reaction(game_state: engine.GameState, reacting_seat: int, quantum_option: engine.QuantumOption, reactions_available_to_me: list):
    """An opponent is playing a quantum card. Should this computer player
    counter it? Returns the chosen Reaction, or None to let it happen."""
    if not reactions_available_to_me or quantum_option.resulting_game_state is None:
        return None
    how_much_i_would_lose = (score_board_for_seat(game_state, reacting_seat)
                             - score_board_for_seat(quantum_option.resulting_game_state, reacting_seat))
    for reaction in reactions_available_to_me:
        if reaction.reaction_kind == "shield" and how_much_i_would_lose > SCORING_WEIGHTS["loss_that_justifies_shield"]:
            return reaction
    for reaction in reactions_available_to_me:
        if reaction.reaction_kind == "cancel" and how_much_i_would_lose > SCORING_WEIGHTS["loss_that_justifies_cancel"]:
            return reaction
    return None
