"""
=============================================================================
AUTOMATED TEST  (simulate_games.py)
-----------------------------------------------------------------------------
Plays many complete games between computer players and checks, after EVERY
single action, that the game never reaches an impossible situation: two
pawns on one square without forming a stack, cards appearing or vanishing,
one-sided entanglement links, and so on.

Run it from a terminal:     python simulate_games.py 200
(the number is how many games to play)
=============================================================================
"""

import sys
import time
from collections import Counter

import computer_player
import game_engine as engine

MAXIMUM_TURNS_BEFORE_WE_CALL_IT_STUCK = 4000


class GameStateProblem(Exception):
    """Raised when the checker finds something impossible."""


def check_that_game_state_makes_sense(game_state: engine.GameState, situation: str) -> None:
    """Checks every rule of consistency; raises GameStateProblem if one fails."""
    def fail(problem: str):
        raise GameStateProblem(problem + "  [while: " + situation + "]")

    # Card counting: no card is ever created or lost.
    movement_total = len(game_state.movement_draw_pile) + len(game_state.movement_discard_pile) + (1 if game_state.current_movement_card else 0)
    if movement_total != 41:
        fail("Movement cards add up to " + str(movement_total))
    quantum_total = (len(game_state.quantum_draw_pile) + len(game_state.quantum_discard_pile)
                     + sum(len(player.quantum_cards_in_hand) for player in game_state.players))
    if quantum_total != 37:
        fail("Quantum cards add up to " + str(quantum_total))
    for player in game_state.players:
        if len(player.quantum_cards_in_hand) > engine.MAXIMUM_QUANTUM_CARDS_IN_HAND:
            fail(player.color_name + " holds too many quantum cards")

    # Quantum links must be two-sided and of matching kinds.
    expected_partner_state = {"entangled": "entangled", "stacked_on_top": "superposition", "superposition": "stacked_on_top"}
    for pawn in game_state.pawns:
        if pawn.location.zone in ("start", "home") and pawn.quantum_state != "none":
            fail(pawn.pawn_id + " is in Start/Home with a quantum state")
        if pawn.quantum_state == "none" and pawn.linked_pawn_id is not None:
            fail(pawn.pawn_id + " has a link but no state")
        if pawn.linked_pawn_id is not None:
            linked_pawn = engine.find_pawn_by_id(game_state, pawn.linked_pawn_id)
            if linked_pawn.linked_pawn_id != pawn.pawn_id:
                fail("One-sided link between " + pawn.pawn_id + " and " + linked_pawn.pawn_id)
            if linked_pawn.quantum_state != expected_partner_state[pawn.quantum_state]:
                fail("Mismatched link states " + pawn.pawn_id + "/" + linked_pawn.pawn_id)
            if pawn.quantum_state != "entangled" and engine.get_space_key_of_pawn(pawn) != engine.get_space_key_of_pawn(linked_pawn):
                fail("Stack split across squares " + pawn.pawn_id)
            if (pawn.quantum_state == "entangled" and pawn.owner_seat != linked_pawn.owner_seat
                    and "safety" in (pawn.location.zone, linked_pawn.location.zone)):
                fail("Cross-color entanglement inside a Safety Zone")

    # Square occupancy: one pawn per square, or exactly one stack of two.
    pawns_by_square = {}
    for pawn in game_state.pawns:
        if engine.is_pawn_on_track_or_in_safety_zone(pawn):
            pawns_by_square.setdefault(engine.get_space_key_of_pawn(pawn), []).append(pawn)
    for square_key, pawns_here in pawns_by_square.items():
        if len(pawns_here) > 2:
            fail(str(len(pawns_here)) + " pawns on " + square_key)
        if len(pawns_here) == 2 and engine.find_stack_containing_pawn(game_state, pawns_here[0]) is None:
            fail("Two unstacked pawns on " + square_key)


def play_quantum_card_with_computer_reactions(game_state, quantum_option):
    """Plays a quantum card, letting opponents counter the way the computer would."""
    possible_reactions = engine.list_possible_reactions_to_quantum_play(game_state, quantum_option)
    chosen_reaction = None
    for seat in dict.fromkeys(reaction.reacting_seat for reaction in possible_reactions):
        reactions_for_seat = [reaction for reaction in possible_reactions if reaction.reacting_seat == seat]
        chosen_reaction = computer_player.choose_reaction(game_state, seat, quantum_option, reactions_for_seat)
        if chosen_reaction:
            break
    engine.play_quantum_card(game_state, quantum_option, chosen_reaction)
    return chosen_reaction


def play_one_complete_game(game_number: int, statistics: Counter) -> engine.GameState:
    number_of_players = 2 + game_number % 3  # cycles through 3, 4 and 2 players
    seats = {2: [0, 2], 3: [0, 1, 2], 4: [0, 1, 2, 3]}[number_of_players]
    game_state = engine.create_new_game([engine.PlayerSetup(seat, "", True) for seat in seats])
    check_that_game_state_makes_sense(game_state, "new game")

    action_counter = 0
    while game_state.turn_phase != "game_over":
        if game_state.turn_number > MAXIMUM_TURNS_BEFORE_WE_CALL_IT_STUCK:
            raise GameStateProblem("Game " + str(game_number) + " never ended.")
        decision = computer_player.choose_next_action(game_state)
        statistics[decision.action_type] += 1
        description = decision.action_type
        if decision.action_type == "play_quantum_card":
            description += " " + decision.quantum_option.description
            statistics["quantum: " + decision.quantum_option.effect_kind] += 1
            if play_quantum_card_with_computer_reactions(game_state, decision.quantum_option):
                statistics["opponent counters"] += 1
        elif decision.action_type == "draw_movement_card":
            engine.draw_movement_card(game_state)
        elif decision.action_type == "use_movement_card":
            description += " " + decision.movement_option.description
            engine.use_movement_card(game_state, decision.movement_option)
        elif decision.action_type == "sacrifice_movement_card":
            engine.sacrifice_movement_card_for_quantum_card(game_state)
        elif decision.action_type == "discard_movement_card":
            engine.discard_movement_card_without_moving(game_state)
        elif decision.action_type == "end_turn":
            engine.end_turn(game_state)
        action_counter += 1
        check_that_game_state_makes_sense(game_state, "game " + str(game_number) + ", action " + str(action_counter) + ": " + description)
    return game_state


def main():
    number_of_games = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    statistics = Counter()
    wins_by_color = Counter()
    game_lengths = []
    started_at = time.time()
    for game_number in range(1, number_of_games + 1):
        finished_game = play_one_complete_game(game_number, statistics)
        game_lengths.append(finished_game.turn_number)
        wins_by_color[engine.PLAYER_COLOR_NAMES[finished_game.seat_of_winner]] += 1
    print("All", number_of_games, "games finished with no rule-consistency problems.")
    print("Average game length: %.1f turns (longest %d)." % (sum(game_lengths) / len(game_lengths), max(game_lengths)))
    print("Wins by color:", dict(wins_by_color))
    print("Actions taken:", dict(statistics))
    print("Time: %.1f seconds" % (time.time() - started_at))


if __name__ == "__main__":
    main()
