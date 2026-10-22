"""
=============================================================================
AUTOMATED SCREEN TEST  (test_interface_headless.py)
-----------------------------------------------------------------------------
Runs the real game window invisibly (no screen needed), "clicks" through
many turns as the person in seat Red - drawing cards, choosing options,
playing quantum cards, answering counter questions, opening every pop-up -
and saves screenshots to the "screenshots" folder. If anything crashes, the
test fails with the error.

Run it with:   python test_interface_headless.py
=============================================================================
"""

import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # draw into memory instead of a window

import pygame

import pygame_interface as interface

SCREENSHOT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")


def draw_one_frame(app):
    app.update(1 / 60)
    app.draw()


def save_screenshot(app, file_name):
    os.makedirs(SCREENSHOT_FOLDER, exist_ok=True)
    draw_one_frame(app)
    pygame.image.save(app.screen, os.path.join(SCREENSHOT_FOLDER, file_name))


def click_area_whose_label_starts_with(app, label_start) -> bool:
    """Finds a button by its words and clicks its middle."""
    draw_one_frame(app)
    for area in reversed(app.clickable_areas):
        if area.label.startswith(label_start):
            app.handle_click(area.rectangle.center)
            return True
    return False


def labels_on_screen(app):
    draw_one_frame(app)
    return [area.label for area in app.clickable_areas if area.label]


def let_computers_play_until_the_person_can_act(app, maximum_steps=3000):
    """Skips the computers' thinking pauses so the test runs quickly."""
    for _ in range(maximum_steps):
        if app.open_overlay == "reaction":
            return "reaction"
        if app.game_state.turn_phase == "game_over":
            return "game_over"
        if not interface.engine.get_current_player(app.game_state).is_computer_player:
            return "person"
        if app.next_computer_step_time is not None:
            app.next_computer_step_time = 0
        if app.pending_computer_follow_up is not None:
            app.pending_computer_follow_up = (0, app.pending_computer_follow_up[1])
        app.update(1 / 60)
    raise RuntimeError("The computers never finished their turns.")


def main():
    random.seed(7)
    pygame.display.init()   # only the parts we need (no sound)
    pygame.font.init()
    screen = pygame.display.set_mode((interface.WINDOW_WIDTH, interface.WINDOW_HEIGHT))
    app = interface.QuantasticApp(screen)
    save_screenshot(app, "01-start.png")

    quantum_cards_played = 0
    counter_questions_answered = 0
    took_hover_screenshot = False
    for turn_counter in range(60):
        situation = let_computers_play_until_the_person_can_act(app)
        if situation == "reaction":
            if counter_questions_answered == 0:
                save_screenshot(app, "04-counter-question.png")
            click_area_whose_label_starts_with(app, "Let it happen")
            counter_questions_answered += 1
            continue
        if situation == "game_over":
            break

        # Sometimes play a quantum card (not a plain launch) before drawing.
        card_labels = [label for label in labels_on_screen(app) if label.startswith("card: ")]
        if card_labels:
            click_area_whose_label_starts_with(app, card_labels[0])
            option_labels = [label for label in labels_on_screen(app) if label.startswith("option: ") and "Quantum Launch" not in label]
            if option_labels:
                if quantum_cards_played == 0:
                    save_screenshot(app, "03-choosing-quantum-target.png")
                click_area_whose_label_starts_with(app, option_labels[0])
                quantum_cards_played += 1
                for _ in range(60):
                    app.update(1 / 60)   # let the pawns glide
                if quantum_cards_played == 1:
                    save_screenshot(app, "05-after-quantum-card.png")
                if app.open_overlay == "reaction":
                    click_area_whose_label_starts_with(app, "Let it happen")
            else:
                click_area_whose_label_starts_with(app, "Keep the card")

        while app.game_state.turn_phase == "waiting_to_draw_movement_card" and not interface.engine.get_current_player(app.game_state).is_computer_player:
            click_area_whose_label_starts_with(app, "Draw a movement card")
            option_labels = [label for label in labels_on_screen(app) if label.startswith("option: ")]
            if option_labels:
                if not took_hover_screenshot and len(option_labels) > 1:
                    # Hover the first option to show the ghost preview.
                    for area in app.clickable_areas:
                        if area.label == option_labels[0]:
                            pygame.mouse.set_pos(area.rectangle.center)
                    save_screenshot(app, "02-choosing-move.png")
                    took_hover_screenshot = True
                click_area_whose_label_starts_with(app, random.choice(option_labels))
            elif not click_area_whose_label_starts_with(app, "Sacrifice"):
                click_area_whose_label_starts_with(app, "Discard")
        click_area_whose_label_starts_with(app, "End turn")

    save_screenshot(app, "06-later-in-the-game.png")
    click_area_whose_label_starts_with(app, "How to play")
    save_screenshot(app, "07-rules.png")
    app.handle_scroll(app.rules_area.center, -30)
    save_screenshot(app, "08-rules-scrolled.png")
    click_area_whose_label_starts_with(app, "Close")
    click_area_whose_label_starts_with(app, "New game")
    save_screenshot(app, "09-new-game-window.png")
    # Make every seat a computer and start a fresh game.
    for row in app.seat_setup_rows:
        row.seat_type = "computer"
    click_area_whose_label_starts_with(app, "Start game")
    let_computers_play_until_the_person_can_act(app, maximum_steps=200000)
    save_screenshot(app, "10-computers-only-finished.png")
    all_computer_game_phase = app.game_state.turn_phase

    # --- Force a counter question: Blue (computer) plays Quantum Break while
    #     Player 1 (a person) holds Interference/Noise. ---
    app.start_game([interface.engine.PlayerSetup(seat, name, kind == "computer") for seat, kind, name in app.DEFAULT_SEATS])
    game = app.game_state
    blue_player = interface.engine.find_player_by_seat(game, 1)
    person_player = interface.engine.find_player_by_seat(game, 0)
    game.quantum_draw_pile.remove(interface.engine.QUANTUM_BREAK)
    blue_player.quantum_cards_in_hand.append(interface.engine.QUANTUM_BREAK)
    game.quantum_draw_pile.remove(interface.engine.INTERFERENCE)
    person_player.quantum_cards_in_hand.append(interface.engine.INTERFERENCE)
    game.index_of_current_player = 1
    app.refresh_cached_options()
    break_option = next(option for option in interface.engine.get_quantum_play_options(game) if option.effect_kind == "quantum_break")
    app.play_quantum_card_and_ask_for_counters(break_option)
    assert app.open_overlay == "reaction", "The person should have been asked to counter."
    save_screenshot(app, "04-counter-question.png")
    click_area_whose_label_starts_with(app, "Play Interference")
    assert app.open_overlay is None
    assert "counters with Interference" in " ".join(entry.message_text for entry in game.game_log[-3:])
    counter_questions_answered += 1

    print("Screen test passed.")
    print("Quantum cards played by the person:", quantum_cards_played)
    print("Counter questions answered:", counter_questions_answered)
    print("Final phase of the all-computer game:", all_computer_game_phase)
    pygame.quit()


if __name__ == "__main__":
    main()
