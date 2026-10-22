"""
=============================================================================
QUANTASTIC!  —  SCREEN AND CONTROLS  (pygame_interface.py)
-----------------------------------------------------------------------------
This is the file you RUN to play:      python pygame_interface.py

It connects the rules (game_engine.py) to a window on your screen, using the
Pygame library:
  * it DRAWS the board, the pawns, the cards and the side panel;
  * it LISTENS to the mouse and keyboard and passes choices to the engine;
  * it RUNS the computer players one step at a time, with short pauses so
    people can follow what they do;
  * it ASKS people whether they want to counter an opponent's quantum card.

The game itself (what is legal, what happens) is never decided here - this
file always asks the engine. That keeps every rule in one place.

HOW A PYGAME PROGRAM WORKS
--------------------------
A Pygame program is one big loop that runs about 60 times per second. Each
time around the loop ("one frame") it:
   1. reads what the player did (mouse clicks, key presses, closing the window),
   2. updates anything that changes over time (gliding pawns, computer timers),
   3. redraws the whole window from scratch, and shows it.
Buttons are re-created every frame while drawing: each one remembers its
rectangle and what to do when clicked, and the next click is checked against
that list.
=============================================================================
"""

import asyncio
import math
import time
from functools import lru_cache

import numpy as np
import pygame

import board_geometry as geometry
import computer_player
import game_engine as engine


# =============================================================================
# SECTION 1 — WINDOW LAYOUT AND COLORS
# =============================================================================

WINDOW_WIDTH = 1300
WINDOW_HEIGHT = 860
FRAMES_PER_SECOND = 60

PIXELS_PER_SQUARE = 47                       # the board is 16 x 47 = 752 pixels wide
BOARD_TOP_LEFT = np.array([24.0, 76.0])      # where the board starts in the window
PAWN_RADIUS = 14

PANEL_LEFT = 850                             # the side panel starts here
PANEL_WIDTH = 426

# Colors are (red, green, blue) amounts from 0 to 255.
COLOR_SUBSTRATE = (11, 16, 41)        # window background: a quantum chip's substrate
COLOR_BOARD = (18, 26, 67)
COLOR_SQUARE = (27, 37, 89)
COLOR_SQUARE_EDGE = (52, 64, 126)
COLOR_GOLD_WIRE = (217, 174, 79)      # slides and decorative traces
COLOR_QUBIT_CYAN = (95, 216, 236)     # anything quantum
COLOR_QUANTUM_SQUARE = (16, 44, 74)
COLOR_INK = (238, 240, 251)           # main text
COLOR_INK_MUTED = (163, 171, 214)
COLOR_PANEL = (20, 28, 71)
COLOR_PANEL_RAISED = (29, 39, 93)
COLOR_PANEL_EDGE = (46, 58, 120)
COLOR_CARD_FACE = (247, 245, 239)
COLOR_CARD_INK = (20, 26, 58)
COLOR_DANGER = (255, 122, 107)
COLOR_WHITE = (255, 255, 255)

# One color per seat: Red, Blue, Yellow, Green.
PLAYER_COLORS = [(255, 90, 78), (79, 141, 255), (255, 207, 58), (61, 208, 126)]

COMPUTER_SPEED_CHOICES = [("Relaxed", 1.2), ("Normal", 0.65), ("Fast", 0.22)]  # pause in seconds


def blend_colors(first_color, second_color, amount_of_second: float):
    """Mixes two colors; amount_of_second 0 = all first color, 1 = all second."""
    return tuple(int(a + (b - a) * amount_of_second) for a, b in zip(first_color, second_color))


# =============================================================================
# SECTION 2 — TEXT HELPERS
# =============================================================================

FONT_NAMES = "dejavusans,segoeui,helveticaneue,helvetica,arial"
TITLE_FONT_NAMES = "dejavusanscondensed,arialblack,impact,dejavusans,arial"


@lru_cache(maxsize=None)
def get_font(size: int, bold: bool = False, for_title: bool = False) -> pygame.font.Font:
    """Returns a font of the given size (remembered after the first time)."""
    return pygame.font.SysFont(TITLE_FONT_NAMES if for_title else FONT_NAMES, size, bold=bold)


@lru_cache(maxsize=4096)
def wrap_text_into_lines(text: str, font_size: int, bold: bool, maximum_width: int) -> tuple:
    """Splits text into lines that each fit within maximum_width pixels."""
    font = get_font(font_size, bold)
    lines = []
    for paragraph in text.split("\n"):
        current_line = ""
        for word in paragraph.split(" "):
            candidate = word if not current_line else current_line + " " + word
            if font.size(candidate)[0] <= maximum_width or not current_line:
                current_line = candidate
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
    return tuple(lines)


def draw_text(surface, text, position, font_size=15, color=COLOR_INK, bold=False, center=False, for_title=False):
    """Draws one line of text. Returns its rectangle."""
    rendered = get_font(font_size, bold, for_title).render(text, True, color)
    rectangle = rendered.get_rect()
    if center:
        rectangle.center = (int(position[0]), int(position[1]))
    else:
        rectangle.topleft = (int(position[0]), int(position[1]))
    surface.blit(rendered, rectangle)
    return rectangle


def draw_wrapped_text(surface, text, top_left, maximum_width, font_size=15, color=COLOR_INK, bold=False, line_spacing=4) -> int:
    """Draws text wrapped to a width. Returns the y position just below it."""
    x, y = int(top_left[0]), int(top_left[1])
    line_height = get_font(font_size, bold).get_linesize() + line_spacing - 4
    for line in wrap_text_into_lines(text, font_size, bold, int(maximum_width)):
        draw_text(surface, line, (x, y), font_size, color, bold)
        y += line_height
    return y


def measure_wrapped_text_height(text, maximum_width, font_size=15, bold=False, line_spacing=4) -> int:
    line_height = get_font(font_size, bold).get_linesize() + line_spacing - 4
    return line_height * len(wrap_text_into_lines(text, font_size, bold, int(maximum_width)))


# =============================================================================
# SECTION 3 — THE RULES TEXT (shown in the "How to play" window)
# =============================================================================

# Each entry is (style, text). Style 'h' = heading, 'p' = paragraph,
# 'b' = bullet point, 'n' = a muted note.
RULES_TEXT = [
    ("h", "Goal"),
    ("p", "Be the first to move all four of your pawns from Start, once around the board, up your colored Safety Zone and into Home."),
    ("h", "Your turn"),
    ("b", "Optional: play ONE quantum card from your hand, at any moment of your turn - before drawing, after seeing your card, or after moving."),
    ("b", "Draw a movement card, then either MOVE with it, or SACRIFICE it to draw a quantum card into your hand (max 3 cards). If you cannot move, you may discard it."),
    ("b", "Drew a 2? Draw again."),
    ("h", "Movement cards (41)"),
    ("b", "1, 2: bring a pawn out of Start onto your exit square, or move 1 / 2 forward. A 2 lets you draw again."),
    ("b", "3, 5, 8, 11, 12: move that many squares forward.   4: move 4 BACKWARD."),
    ("b", "7: move 7 forward, or split the 7 between two pawns.   10: move 10 forward, or 1 backward."),
    ("b", "Paradox: your choice - leave Start, move 6, or move 9."),
    ("h", "The board"),
    ("b", "Bumping: land on an opponent's pawn and it goes back to Start. You can't land on your own pawn."),
    ("b", "Slides (gold bars): land on the start of a slide by moving forward and you zoom to its end, sweeping pawns on it back to Start. Slides disrupt quantum states."),
    ("b", "Quantum Spaces (Q0-Q7): end a move there and draw a quantum card."),
    ("b", "Safety Zone: only your color may enter. Pawns there can't be bumped and are immune to quantum cards, except Interference/Noise."),
    ("b", "Home needs an exact count. Backing up from your exit square puts you only a few steps from your Safety Zone."),
    ("h", "Quantum cards (37)"),
    ("b", "Any card - Quantum Launch: spend any quantum card to bring a pawn out of Start instead of using its effect."),
    ("b", "Superposition x7: put one of your track pawns in superposition. A pawn that lands on it stacks on top instead of bumping it (2 pawns max). The top pawn's owner may move it off (the stack dissolves) or, if both pawns are theirs, move the whole stack as one. The bottom pawn is stuck while covered. A third pawn arriving knocks the top pawn to Start and takes its place. Counter: when a teleport would bump your pawn, play Superposition on it - the teleporter stacks instead."),
    ("b", "Teleportation x7: jump one of your track pawns to the start or end of any slide, or to any Quantum Space. An entangled pawn can instead jump to its partner: with your own partner they swap places; onto an opponent's partner it bumps it to Start."),
    ("b", "Entanglement x7: link two track pawns (at least one yours). Whenever a movement card moves one of them, the other makes the same move. The link breaks on a slide, Interference, Quantum Break, a bump, reaching Home, or if the partner's move is impossible. Different colors unlink as soon as one enters a Safety Zone."),
    ("b", "Quantum Break x5: every quantum state collapses. Every stack breaks and its bottom pawn returns to Start. All Jams are lifted."),
    ("b", "Interference/Noise x11: end one pawn's quantum state (a stack broken this way sends its bottom pawn to Start), or Jam an opponent so they can't play quantum cards on their next turn. Counter: play it instantly when an opponent plays a quantum card to cancel it."),
    ("p", "Each pawn holds one quantum state at a time. Many states can be active on the board at once."),
    ("h", "Clarified rules"),
    ("n", "The original rules left these points open or contradictory. This is how this version settles them."),
    ("b", "The board is a 16 x 16 square: 60 track squares."),
    ("b", "On every side, counting from the corner: Safety entrance 3rd square, Start exit 5th, Quantum Spaces 8th and 15th, slide from 10th to 13th."),
    ("b", "Slides are neutral: every color slides.   The 11 simply moves 11 forward."),
    ("b", "Quantum cards are kept in a hand of up to 3; one may be played per turn. Any quantum card can be spent as a Quantum Launch."),
    ("b", "A 2 grants another draw even when sacrificed. Both decks reshuffle when empty."),
    ("b", "You must move if you can; you may discard only when no move exists."),
    ("b", "Superposition: the top pawn can step off; a same-color stack can move as one. A pawn arriving on a full stack replaces its top pawn."),
    ("b", "Entanglement lasts until broken; an impossible mirrored move breaks it."),
    ("b", "Teleportation never triggers slides or Quantum Space draws."),
    ("b", "Slides: superposition pawns on the slide survive but lose their state; anything on the last square is bumped."),
    ("b", "Interference has three uses: Decohere, Jam and Cancel. A Cancel can't be canceled."),
    ("b", "The first player to bring all four pawns Home wins; ties cannot happen."),
]


# =============================================================================
# SECTION 4 — SMALL BUILDING BLOCKS
# =============================================================================

class ClickableArea:
    """A rectangle on screen and what to do when it is clicked."""

    def __init__(self, rectangle: pygame.Rect, action_when_clicked, label: str = ""):
        self.rectangle = rectangle
        self.action_when_clicked = action_when_clicked
        self.label = label   # the words on it (handy for automated tests)


class SeatSetupRow:
    """One row of the New Game window: a seat's name and type."""
    SEAT_TYPES = ["person", "computer", "empty"]
    SEAT_TYPE_LABELS = {"person": "Person", "computer": "Computer", "empty": "Empty seat"}

    def __init__(self, seat_number: int, seat_type: str, display_name: str):
        self.seat_number = seat_number
        self.seat_type = seat_type
        self.display_name = display_name

    def switch_to_next_seat_type(self):
        next_position = (self.SEAT_TYPES.index(self.seat_type) + 1) % len(self.SEAT_TYPES)
        self.seat_type = self.SEAT_TYPES[next_position]


def convert_squares_to_screen(point_in_squares: np.ndarray) -> np.ndarray:
    """Board position in squares -> pixel position in the window."""
    return BOARD_TOP_LEFT + point_in_squares * PIXELS_PER_SQUARE


def as_int_pair(point) -> tuple:
    return int(round(point[0])), int(round(point[1]))


def draw_dashed_circle(surface, color, center, radius, number_of_dashes=12, rotation_in_radians=0.0, width=2):
    """Draws a circle made of short arcs (used for the superposition halo)."""
    dash_angles = np.linspace(0, 2 * math.pi, number_of_dashes, endpoint=False) + rotation_in_radians
    dash_angular_length = math.pi / number_of_dashes
    for start_angle in dash_angles:
        arc_angles = np.linspace(start_angle, start_angle + dash_angular_length, 5)
        arc_points = [as_int_pair((center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))) for angle in arc_angles]
        pygame.draw.lines(surface, color, False, arc_points, width)


def draw_dashed_line(surface, color, start_point, end_point, dash_length=8, gap_length=6, width=2, phase_shift=0.0):
    for dash_start, dash_end in geometry.make_dashed_line_segments(np.asarray(start_point, float), np.asarray(end_point, float), dash_length, gap_length, phase_shift):
        pygame.draw.line(surface, color, as_int_pair(dash_start), as_int_pair(dash_end), width)


def draw_quantum_card_picture(surface, card_name, center):
    """A small symbol for each quantum card, drawn with simple shapes."""
    x, y = int(center[0]), int(center[1])
    if card_name == engine.SUPERPOSITION:
        pygame.draw.circle(surface, COLOR_QUBIT_CYAN, (x - 5, y), 11, 2)
        draw_dashed_circle(surface, COLOR_INK, (x + 5, y), 11, 10)
    elif card_name == engine.TELEPORTATION:
        pygame.draw.circle(surface, COLOR_QUBIT_CYAN, (x - 13, y), 5)
        pygame.draw.circle(surface, COLOR_QUBIT_CYAN, (x + 13, y), 5, 2)
        draw_dashed_line(surface, COLOR_INK, (x - 6, y), (x + 6, y), 3, 3)
    elif card_name == engine.ENTANGLEMENT:
        pygame.draw.circle(surface, COLOR_QUBIT_CYAN, (x - 7, y), 9, 3)
        pygame.draw.circle(surface, COLOR_GOLD_WIRE, (x + 7, y), 9, 3)
    elif card_name == engine.QUANTUM_BREAK:
        pygame.draw.circle(surface, COLOR_DANGER, (x, y), 12, 2)
        pygame.draw.lines(surface, COLOR_INK, False, [(x, y - 14), (x - 4, y - 2), (x + 4, y + 2), (x - 1, y + 14)], 2)
    elif card_name == engine.INTERFERENCE:
        wave_x = np.linspace(-16, 16, 33)
        wave_points = [as_int_pair((x + wx, y - 6 * math.sin(wx / 3.0))) for wx in wave_x]
        pygame.draw.lines(surface, COLOR_QUBIT_CYAN, False, wave_points, 2)
        pygame.draw.line(surface, COLOR_DANGER, (x - 14, y + 12), (x + 14, y - 12), 2)


# =============================================================================
# SECTION 5 — THE GAME WINDOW
# =============================================================================

class QuantasticApp:
    """Everything about the game window: what it shows and how it reacts."""

    DEFAULT_SEATS = [(0, "person", "Player 1"), (1, "computer", "Blue Bot"), (2, "computer", "Yellow Bot"), (3, "computer", "Green Bot")]

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.game_state = None

        # --- What the screen remembers between frames. ---
        self.clickable_areas = []              # rebuilt every frame while drawing
        self.quantum_card_chosen_from_hand = None   # card a person is choosing a target for
        self.pawn_id_used_as_filter = None     # show only options involving this pawn
        self.option_being_previewed = None     # option under the mouse (ghost preview)
        self.option_list_scroll_offset = 0
        self.option_list_area = None
        self.log_scroll_offset = 0              # 0 = showing the newest lines
        self.log_area = None
        self.rules_scroll_offset = 0
        self.rules_area = None
        self.cached_movement_options = []
        self.cached_quantum_options = []
        self.computer_speed_index = 1
        self.next_computer_step_time = None
        self.pending_computer_follow_up = None  # (time, action) shown as a preview first
        self.announcement_text = ""
        self.announcement_until = 0.0

        # --- Pop-up windows ("overlays"). Only one is open at a time. ---
        self.open_overlay = None               # None, 'setup', 'rules' or 'reaction'
        self.seat_setup_rows = [SeatSetupRow(seat, kind, name) for seat, kind, name in self.DEFAULT_SEATS]
        self.seat_row_with_keyboard_focus = None
        self.setup_error_message = ""
        self.pending_counter_question = None    # details while a person decides to counter

        # --- Smooth pawn movement. ---
        self.displayed_pawn_positions = {}     # pawn_id -> where it is drawn right now (squares)

        self.static_board_picture = self.draw_static_board_picture()
        self.start_game(self.make_player_setups_from_rows())

    # -------------------------------------------------------------------------
    # Starting a game
    # -------------------------------------------------------------------------

    def make_player_setups_from_rows(self) -> list:
        return [
            engine.PlayerSetup(row.seat_number, row.display_name.strip() or engine.PLAYER_COLOR_NAMES[row.seat_number], row.seat_type == "computer")
            for row in self.seat_setup_rows if row.seat_type != "empty"
        ]

    def start_game(self, player_setups: list):
        self.game_state = engine.create_new_game(player_setups)
        self.quantum_card_chosen_from_hand = None
        self.pawn_id_used_as_filter = None
        self.option_being_previewed = None
        self.pending_counter_question = None
        self.pending_computer_follow_up = None
        self.log_scroll_offset = 0
        self.displayed_pawn_positions = geometry.calculate_position_of_every_pawn(self.game_state)
        self.after_every_action()

    # =========================================================================
    # SECTION 6 — DRAWING THE BOARD THAT NEVER CHANGES (done once)
    # =========================================================================

    def draw_static_board_picture(self) -> pygame.Surface:
        """Draws the squares, lanes, circles, slides and central hub onto a
        separate picture once, so they don't have to be redrawn every frame."""
        board_pixels = PIXELS_PER_SQUARE * geometry.BOARD_SIZE_IN_SQUARES
        picture = pygame.Surface((board_pixels, board_pixels), pygame.SRCALPHA)
        pygame.draw.rect(picture, COLOR_BOARD, picture.get_rect(), border_radius=14)

        def to_picture(point_in_squares):
            return point_in_squares * PIXELS_PER_SQUARE

        hub_center = to_picture(geometry.BOARD_CENTER_IN_SQUARES)

        # Faint gold "bonding wires" from the central qubit to every Home and
        # Start: a nod to the IBM 5-qubit chip that inspired the board.
        trace_color = blend_colors(COLOR_BOARD, COLOR_GOLD_WIRE, 0.2)
        for seat_number in range(4):
            home_center = to_picture(geometry.get_center_of_home_circle(seat_number))
            start_center = to_picture(geometry.get_center_of_start_circle(seat_number))
            corner_point = np.array([home_center[0], hub_center[1]]) if seat_number % 2 == 0 else np.array([hub_center[0], home_center[1]])
            pygame.draw.lines(picture, trace_color, False, [as_int_pair(hub_center), as_int_pair(corner_point), as_int_pair(home_center)], 1)
            pygame.draw.line(picture, trace_color, as_int_pair(hub_center), as_int_pair(start_center), 1)

        # The 60 track squares (numbered 1-60 for people).
        half_square = PIXELS_PER_SQUARE * 0.39
        for track_space_number in range(engine.NUMBER_OF_TRACK_SPACES):
            center = to_picture(geometry.get_center_of_track_square(track_space_number))
            square_rectangle = pygame.Rect(0, 0, int(half_square * 2), int(half_square * 2))
            square_rectangle.center = as_int_pair(center)
            if engine.is_track_space_a_quantum_space(track_space_number):
                pygame.draw.rect(picture, COLOR_QUANTUM_SQUARE, square_rectangle, border_radius=5)
                pygame.draw.rect(picture, COLOR_QUBIT_CYAN, square_rectangle, 1, border_radius=5)
                pygame.draw.circle(picture, COLOR_QUBIT_CYAN, as_int_pair(center), 12, 2)
                draw_text(picture, engine.get_quantum_space_label(track_space_number), center, 10, COLOR_QUBIT_CYAN, bold=True, center=True)
            else:
                pygame.draw.rect(picture, COLOR_SQUARE, square_rectangle, border_radius=5)
                pygame.draw.rect(picture, COLOR_SQUARE_EDGE, square_rectangle, 1, border_radius=5)
            draw_text(picture, str(track_space_number + 1), (square_rectangle.left + 3, square_rectangle.top + 1), 8, blend_colors(COLOR_SQUARE, COLOR_INK_MUTED, 0.6))

        # Each seat's colored parts.
        for seat_number in range(4):
            seat_color = PLAYER_COLORS[seat_number]
            tinted_fill = blend_colors(COLOR_BOARD, seat_color, 0.22)

            # Outline the Safety entrance and the Start exit in the seat's color.
            for special_square in (engine.get_safety_zone_entrance_space_for_seat(seat_number), engine.get_start_exit_space_for_seat(seat_number)):
                outline = pygame.Rect(0, 0, int(half_square * 2) - 4, int(half_square * 2) - 4)
                outline.center = as_int_pair(to_picture(geometry.get_center_of_track_square(special_square)))
                pygame.draw.rect(picture, seat_color, outline, 3, border_radius=4)

            # The five Safety Zone squares.
            for safety_zone_step in range(engine.NUMBER_OF_SAFETY_ZONE_SPACES):
                safety_rectangle = pygame.Rect(0, 0, int(half_square * 2), int(half_square * 2))
                safety_rectangle.center = as_int_pair(to_picture(geometry.get_center_of_safety_square(seat_number, safety_zone_step)))
                pygame.draw.rect(picture, tinted_fill, safety_rectangle, border_radius=5)
                pygame.draw.rect(picture, seat_color, safety_rectangle, 2, border_radius=5)

            # Start circle, with a dotted path to the exit square.
            start_center = to_picture(geometry.get_center_of_start_circle(seat_number))
            exit_center = to_picture(geometry.get_center_of_track_square(engine.get_start_exit_space_for_seat(seat_number)))
            draw_dashed_line(picture, seat_color, start_center, exit_center, 3, 5, 3)
            start_radius = int(geometry.START_CIRCLE_RADIUS_IN_SQUARES * PIXELS_PER_SQUARE)
            pygame.draw.circle(picture, COLOR_BOARD, as_int_pair(start_center), start_radius)
            draw_dashed_circle(picture, seat_color, start_center, start_radius, 16, 0, 2)
            draw_text(picture, "START", start_center, 9, seat_color, bold=True, center=True)

            # Home circle.
            home_center = to_picture(geometry.get_center_of_home_circle(seat_number))
            home_radius = int(geometry.HOME_CIRCLE_RADIUS_IN_SQUARES * PIXELS_PER_SQUARE)
            pygame.draw.circle(picture, tinted_fill, as_int_pair(home_center), home_radius)
            pygame.draw.circle(picture, seat_color, as_int_pair(home_center), home_radius, 3)
            draw_text(picture, "HOME", home_center, 10, seat_color, bold=True, center=True)

        # Slides: a gold bar, a triangle at the start and a dot at the end.
        for slide in engine.ALL_SLIDES_ON_THE_BOARD:
            slide_start = to_picture(geometry.get_center_of_track_square(slide.slide_start_space))
            slide_end = to_picture(geometry.get_center_of_track_square(slide.slide_end_space))
            pygame.draw.line(picture, COLOR_GOLD_WIRE, as_int_pair(slide_start), as_int_pair(slide_end), 9)
            pygame.draw.circle(picture, COLOR_GOLD_WIRE, as_int_pair(slide_end), 9)
            direction_of_slide = slide_end - slide_start
            triangle = geometry.make_arrowhead_triangle(slide_start + direction_of_slide / np.hypot(*direction_of_slide) * 10, direction_of_slide, 18, 11)
            pygame.draw.polygon(picture, COLOR_GOLD_WIRE, [as_int_pair(corner) for corner in triangle])

        # The central qubit hub, which holds the two decks.
        hub_radius = int(geometry.CENTRAL_HUB_RADIUS_IN_SQUARES * PIXELS_PER_SQUARE)
        pygame.draw.circle(picture, (14, 21, 56), as_int_pair(hub_center), hub_radius)
        pygame.draw.circle(picture, COLOR_QUBIT_CYAN, as_int_pair(hub_center), hub_radius, 2)
        draw_dashed_circle(picture, blend_colors(COLOR_BOARD, COLOR_QUBIT_CYAN, 0.45), hub_center, hub_radius - 14, 40, 0, 1)
        draw_text(picture, "CENTRAL QUBIT", hub_center + np.array([0, -78]), 10, COLOR_INK_MUTED, center=True)
        draw_text(picture, "QUANTASTIC!", hub_center + np.array([0, -54]), 22, COLOR_INK, bold=True, center=True, for_title=True)
        return picture

    # =========================================================================
    # SECTION 7 — KEEPING THE LISTS OF OPTIONS UP TO DATE
    # =========================================================================

    def refresh_cached_options(self):
        """Working out every legal option means trying each one on a copy of the
        game, which takes a moment. So we do it once after every change, not
        60 times a second."""
        self.cached_movement_options = engine.get_legal_movement_options(self.game_state)
        self.cached_quantum_options = engine.get_quantum_play_options(self.game_state)
        self.option_list_scroll_offset = 0

    def after_every_action(self):
        """Called after anything changes the game: tidy up, skip a pointless
        'End turn' click, refresh options, and wake up the computer players."""
        self.pawn_id_used_as_filter = None
        self.option_being_previewed = None
        self.quantum_card_chosen_from_hand = None
        self.log_scroll_offset = 0

        current_player = engine.get_current_player(self.game_state)
        if (self.game_state.turn_phase == "finishing_turn" and not current_player.is_computer_player
                and not engine.get_quantum_play_options(self.game_state)):
            engine.end_turn(self.game_state)   # nothing left to do: end the person's turn

        if self.game_state.turn_phase == "game_over":
            winner = engine.find_player_by_seat(self.game_state, self.game_state.seat_of_winner)
            self.show_announcement(winner.display_name + " wins Quantastic!")

        self.refresh_cached_options()
        self.schedule_next_computer_step()

    def show_announcement(self, text: str):
        """A short message at the bottom of the window for a few seconds."""
        self.announcement_text = text
        self.announcement_until = time.time() + 3.2

    # =========================================================================
    # SECTION 8 — THE COMPUTER PLAYERS
    # =========================================================================

    def get_computer_pause_in_seconds(self) -> float:
        return COMPUTER_SPEED_CHOICES[self.computer_speed_index][1]

    def schedule_next_computer_step(self):
        """If it is a computer's turn, plan its next step after a short pause."""
        self.next_computer_step_time = None
        if self.game_state.turn_phase == "game_over" or self.open_overlay == "reaction":
            return
        if engine.get_current_player(self.game_state).is_computer_player:
            self.next_computer_step_time = time.time() + self.get_computer_pause_in_seconds()

    def perform_one_computer_step(self):
        decision = computer_player.choose_next_action(self.game_state)
        if decision is None:
            return
        action = decision.action_type
        pause = self.get_computer_pause_in_seconds()

        if action == "play_quantum_card":
            # Show what it is aiming at for a moment, then play it.
            self.option_being_previewed = decision.quantum_option
            self.pending_computer_follow_up = (time.time() + pause * 0.7, lambda: self.play_quantum_card_and_ask_for_counters(decision.quantum_option))
            return
        if action == "use_movement_card":
            self.option_being_previewed = decision.movement_option

            def move_after_preview():
                engine.use_movement_card(self.game_state, decision.movement_option)
                self.after_every_action()
            self.pending_computer_follow_up = (time.time() + pause * 0.7, move_after_preview)
            return

        if action == "draw_movement_card":
            engine.draw_movement_card(self.game_state)
        elif action == "sacrifice_movement_card":
            engine.sacrifice_movement_card_for_quantum_card(self.game_state)
        elif action == "discard_movement_card":
            engine.discard_movement_card_without_moving(self.game_state)
        elif action == "end_turn":
            engine.end_turn(self.game_state)
        self.after_every_action()

    # =========================================================================
    # SECTION 9 — PLAYING A QUANTUM CARD AND ASKING OPPONENTS TO COUNTER
    # =========================================================================

    def play_quantum_card_and_ask_for_counters(self, quantum_option: engine.QuantumOption):
        """Opponents are asked one by one, in turn order. A computer opponent
        decides instantly; a person sees a pop-up. The first opponent who
        counters stops the asking. Then the card is played for real."""
        self.pending_computer_follow_up = None
        possible_reactions = engine.list_possible_reactions_to_quantum_play(self.game_state, quantum_option)
        seats_that_can_react = list(dict.fromkeys(reaction.reacting_seat for reaction in possible_reactions))
        self.pending_counter_question = {
            "quantum_option": quantum_option,
            "possible_reactions": possible_reactions,
            "seats_that_can_react": seats_that_can_react,
            "position_in_list": 0,
            "acting_player": engine.get_current_player(self.game_state),
        }
        self.ask_next_seat_about_countering()

    def ask_next_seat_about_countering(self):
        question = self.pending_counter_question
        while question["position_in_list"] < len(question["seats_that_can_react"]):
            reacting_seat = question["seats_that_can_react"][question["position_in_list"]]
            reacting_player = engine.find_player_by_seat(self.game_state, reacting_seat)
            reactions_for_this_seat = [reaction for reaction in question["possible_reactions"] if reaction.reacting_seat == reacting_seat]
            if reacting_player.is_computer_player:
                computer_choice = computer_player.choose_reaction(self.game_state, reacting_seat, question["quantum_option"], reactions_for_this_seat)
                if computer_choice:
                    self.finish_playing_quantum_card(computer_choice)
                    return
                question["position_in_list"] += 1
                continue
            # A person: open the pop-up and wait for their click.
            question["reacting_player"] = reacting_player
            question["reactions_for_this_seat"] = reactions_for_this_seat
            self.open_overlay = "reaction"
            self.next_computer_step_time = None
            self.option_being_previewed = question["quantum_option"]
            return
        self.finish_playing_quantum_card(None)

    def person_answers_counter_question(self, chosen_reaction):
        self.open_overlay = None
        if chosen_reaction is not None:
            self.finish_playing_quantum_card(chosen_reaction)
        else:
            self.pending_counter_question["position_in_list"] += 1
            self.ask_next_seat_about_countering()

    def finish_playing_quantum_card(self, chosen_reaction):
        question = self.pending_counter_question
        self.pending_counter_question = None
        quantum_option = question["quantum_option"]
        engine.play_quantum_card(self.game_state, quantum_option, chosen_reaction)
        if chosen_reaction is not None:
            reacting_player = engine.find_player_by_seat(self.game_state, chosen_reaction.reacting_seat)
            self.show_announcement(reacting_player.display_name + " counters with " + chosen_reaction.card_name + "!")
        elif quantum_option.effect_kind != "quantum_launch":
            self.show_announcement(question["acting_player"].display_name + " plays " + quantum_option.card_name)
        self.after_every_action()

    # =========================================================================
    # SECTION 10 — WHAT HAPPENS WHEN A PERSON CLICKS
    # =========================================================================

    def is_it_a_persons_turn(self) -> bool:
        return (self.game_state.turn_phase != "game_over"
                and not engine.get_current_player(self.game_state).is_computer_player
                and self.open_overlay is None)

    def options_currently_listed(self) -> list:
        """The options shown as buttons right now (before the pawn filter)."""
        if not self.is_it_a_persons_turn():
            return []
        if self.quantum_card_chosen_from_hand:
            return [option for option in self.cached_quantum_options if option.card_name == self.quantum_card_chosen_from_hand]
        if self.game_state.turn_phase == "choosing_how_to_use_movement_card":
            return self.cached_movement_options
        return []

    def handle_click_on_board(self, mouse_position) -> bool:
        """Clicking a pawn shows only the options involving it (click again to undo)."""
        mouse_point = np.array(mouse_position, dtype=float)
        listed_options = self.options_currently_listed()
        for pawn_id, position_in_squares in self.displayed_pawn_positions.items():
            if np.hypot(*(convert_squares_to_screen(position_in_squares) - mouse_point)) <= PAWN_RADIUS + 3:
                if any(pawn_id in option.pawn_ids_involved for option in listed_options):
                    self.pawn_id_used_as_filter = None if self.pawn_id_used_as_filter == pawn_id else pawn_id
                    self.option_list_scroll_offset = 0
                    return True
        return False

    def person_draws_movement_card(self):
        drawn_card = engine.draw_movement_card(self.game_state)
        if drawn_card == "2":
            self.show_announcement("A 2 - you get another draw after this one.")
        self.after_every_action()

    def person_chooses_option(self, option):
        if isinstance(option, engine.QuantumOption):
            self.play_quantum_card_and_ask_for_counters(option)
        else:
            engine.use_movement_card(self.game_state, option)
            self.after_every_action()

    def person_sacrifices_movement_card(self):
        engine.sacrifice_movement_card_for_quantum_card(self.game_state)
        self.after_every_action()

    def person_discards_movement_card(self):
        engine.discard_movement_card_without_moving(self.game_state)
        self.after_every_action()

    def person_ends_turn(self):
        engine.end_turn(self.game_state)
        self.after_every_action()

    def person_clicks_quantum_card(self, card_name):
        self.quantum_card_chosen_from_hand = None if self.quantum_card_chosen_from_hand == card_name else card_name
        self.pawn_id_used_as_filter = None
        self.option_list_scroll_offset = 0

    def open_setup_window(self):
        self.open_overlay = "setup"
        self.setup_error_message = ""
        self.seat_row_with_keyboard_focus = None
        self.next_computer_step_time = None
        self.pending_computer_follow_up = None

    def close_setup_window(self):
        self.open_overlay = None
        self.seat_row_with_keyboard_focus = None
        self.schedule_next_computer_step()

    def submit_setup_window(self):
        player_setups = self.make_player_setups_from_rows()
        if len(player_setups) < 2:
            self.setup_error_message = "Choose at least two players (people or computers)."
            return
        self.open_overlay = None
        self.seat_row_with_keyboard_focus = None
        self.start_game(player_setups)

    def switch_computer_speed(self):
        self.computer_speed_index = (self.computer_speed_index + 1) % len(COMPUTER_SPEED_CHOICES)
        self.schedule_next_computer_step()

    # =========================================================================
    # SECTION 11 — EVENTS AND TIME
    # =========================================================================

    def handle_event(self, event) -> bool:
        """Reacts to one thing the player did. Returns False to quit."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.handle_click(event.pos)
        elif event.type == pygame.MOUSEWHEEL:
            self.handle_scroll(pygame.mouse.get_pos(), event.y)
        elif event.type == pygame.TEXTINPUT and self.seat_row_with_keyboard_focus is not None:
            focused_row = self.seat_setup_rows[self.seat_row_with_keyboard_focus]
            if len(focused_row.display_name) < 18:
                focused_row.display_name += event.text
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and self.open_overlay in ("setup", "rules"):
                if self.open_overlay == "setup":
                    self.close_setup_window()
                else:
                    self.open_overlay = None
            elif event.key == pygame.K_BACKSPACE and self.seat_row_with_keyboard_focus is not None:
                focused_row = self.seat_setup_rows[self.seat_row_with_keyboard_focus]
                focused_row.display_name = focused_row.display_name[:-1]
            elif event.key == pygame.K_RETURN and self.open_overlay == "setup":
                self.submit_setup_window()
        return True

    def handle_click(self, mouse_position):
        # Buttons drawn last are on top, so check them from last to first.
        for clickable_area in reversed(self.clickable_areas):
            if clickable_area.rectangle.collidepoint(mouse_position):
                clickable_area.action_when_clicked()
                return
        if self.open_overlay == "setup":
            self.seat_row_with_keyboard_focus = None
        if self.open_overlay is None:
            self.handle_click_on_board(mouse_position)

    def handle_scroll(self, mouse_position, wheel_steps):
        if self.open_overlay == "rules" and self.rules_area and self.rules_area.collidepoint(mouse_position):
            self.rules_scroll_offset = max(0, self.rules_scroll_offset - wheel_steps * 40)
        elif self.option_list_area and self.option_list_area.collidepoint(mouse_position):
            self.option_list_scroll_offset = max(0, self.option_list_scroll_offset - wheel_steps * 30)
        elif self.log_area and self.log_area.collidepoint(mouse_position):
            self.log_scroll_offset = max(0, self.log_scroll_offset + wheel_steps)

    def update(self, seconds_since_last_frame: float):
        """Things that change over time: gliding pawns and computer timers."""
        target_positions = geometry.calculate_position_of_every_pawn(self.game_state)
        glide_fraction = 1.0 - math.exp(-seconds_since_last_frame * 11.0)
        self.displayed_pawn_positions = geometry.move_points_smoothly_toward_targets(self.displayed_pawn_positions, target_positions, glide_fraction)

        now = time.time()
        if self.open_overlay is not None:
            return
        if self.pending_computer_follow_up and now >= self.pending_computer_follow_up[0]:
            follow_up_action = self.pending_computer_follow_up[1]
            self.pending_computer_follow_up = None
            self.option_being_previewed = None
            follow_up_action()
        elif self.next_computer_step_time is not None and now >= self.next_computer_step_time and self.pending_computer_follow_up is None:
            self.next_computer_step_time = None
            self.perform_one_computer_step()

    # =========================================================================
    # SECTION 12 — DRAWING EVERY FRAME
    # =========================================================================

    def add_button(self, rectangle, label, action_when_clicked, style="normal", font_size=14, enabled=True):
        """Draws a button and remembers it, so a click on it runs the action."""
        rectangle = pygame.Rect(rectangle)
        is_hovered = enabled and rectangle.collidepoint(pygame.mouse.get_pos())
        if style == "main":
            fill, text_color, edge = COLOR_GOLD_WIRE, COLOR_CARD_INK, COLOR_GOLD_WIRE
        elif style == "quantum":
            fill, text_color, edge = COLOR_PANEL_RAISED, COLOR_INK, COLOR_QUBIT_CYAN
        else:
            fill, text_color, edge = COLOR_PANEL_RAISED, COLOR_INK, COLOR_PANEL_EDGE
        if not enabled:
            text_color = COLOR_INK_MUTED
        if is_hovered:
            fill = blend_colors(fill, COLOR_WHITE, 0.12)
            edge = COLOR_QUBIT_CYAN if style != "main" else edge
        pygame.draw.rect(self.screen, fill, rectangle, border_radius=8)
        pygame.draw.rect(self.screen, edge, rectangle, 1, border_radius=8)
        draw_text(self.screen, label, rectangle.center, font_size, text_color, bold=(style == "main"), center=True)
        if enabled:
            self.clickable_areas.append(ClickableArea(rectangle, action_when_clicked, label))
        return rectangle

    def draw(self):
        self.clickable_areas = []
        self.screen.fill(COLOR_SUBSTRATE)
        self.draw_top_bar()
        self.draw_board()
        self.draw_side_panel()
        if self.open_overlay == "setup":
            self.draw_setup_window()
        elif self.open_overlay == "rules":
            self.draw_rules_window()
        elif self.open_overlay == "reaction":
            self.draw_counter_question_window()
        self.draw_announcement()

    # ----------------------------- top bar ----------------------------------

    def draw_top_bar(self):
        # The title, with offset red and blue shadows like the poster's box art.
        for offset, color in (((4, 4), PLAYER_COLORS[1]), ((2, 2), PLAYER_COLORS[0]), ((0, 0), COLOR_INK)):
            draw_text(self.screen, "QUANTASTIC!", (24 + offset[0], 14 + offset[1]), 36, color, bold=True, for_title=True)
        draw_text(self.screen, "A quantum-inspired race for 2-4 players", (330, 30), 15, COLOR_INK_MUTED)
        self.add_button((WINDOW_WIDTH - 140, 20, 120, 36), "New game", self.open_setup_window)
        self.add_button((WINDOW_WIDTH - 270, 20, 120, 36), "How to play", self.open_rules_window)
        speed_label = "Speed: " + COMPUTER_SPEED_CHOICES[self.computer_speed_index][0]
        self.add_button((WINDOW_WIDTH - 420, 20, 140, 36), speed_label, self.switch_computer_speed)

    def open_rules_window(self):
        self.open_overlay = "rules"
        self.rules_scroll_offset = 0

    # ------------------------------- board ----------------------------------

    def draw_board(self):
        self.screen.blit(self.static_board_picture, as_int_pair(BOARD_TOP_LEFT))
        hub_center = convert_squares_to_screen(geometry.BOARD_CENTER_IN_SQUARES)

        # The two deck piles in the central hub, with their card counts.
        movement_pile = pygame.Rect(0, 0, 60, 80)
        movement_pile.center = as_int_pair(hub_center + np.array([-44, 18]))
        quantum_pile = pygame.Rect(0, 0, 60, 80)
        quantum_pile.center = as_int_pair(hub_center + np.array([44, 18]))
        pygame.draw.rect(self.screen, COLOR_CARD_FACE, movement_pile, border_radius=7)
        pygame.draw.rect(self.screen, COLOR_GOLD_WIRE, movement_pile, 2, border_radius=7)
        pygame.draw.rect(self.screen, (23, 58, 98), quantum_pile, border_radius=7)
        pygame.draw.rect(self.screen, COLOR_QUBIT_CYAN, quantum_pile, 2, border_radius=7)
        draw_text(self.screen, str(len(self.game_state.movement_draw_pile)), movement_pile.center, 18, COLOR_CARD_INK, bold=True, center=True)
        draw_text(self.screen, str(len(self.game_state.quantum_draw_pile)), quantum_pile.center, 18, COLOR_INK, bold=True, center=True)
        draw_text(self.screen, "MOVEMENT", (movement_pile.centerx, movement_pile.bottom + 10), 9, COLOR_INK_MUTED, center=True)
        draw_text(self.screen, "QUANTUM", (quantum_pile.centerx, quantum_pile.bottom + 10), 9, COLOR_INK_MUTED, center=True)

        screen_positions = {pawn_id: convert_squares_to_screen(position) for pawn_id, position in self.displayed_pawn_positions.items()}
        now = time.time()

        # Flowing dashed lines between entangled partners.
        already_drawn_pairs = set()
        for pawn in self.game_state.pawns:
            if pawn.quantum_state != "entangled":
                continue
            pair = frozenset([pawn.pawn_id, pawn.linked_pawn_id])
            if pair in already_drawn_pairs:
                continue
            already_drawn_pairs.add(pair)
            draw_dashed_line(self.screen, COLOR_QUBIT_CYAN, screen_positions[pawn.pawn_id], screen_positions[pawn.linked_pawn_id], 9, 6, 3, phase_shift=now * 25)

        # Ghost preview: where pawns WOULD go if the option under the mouse were chosen.
        self.draw_ghost_preview(screen_positions)

        # The pawns themselves (pawns on top of a stack are drawn last).
        highlighted_pawn_ids = set(self.option_being_previewed.pawn_ids_involved) if self.option_being_previewed else set()
        selectable_pawn_ids = {pawn_id for option in self.options_currently_listed() for pawn_id in option.pawn_ids_involved}
        mouse_point = np.array(pygame.mouse.get_pos(), dtype=float)
        pawns_in_drawing_order = sorted(self.game_state.pawns, key=lambda pawn: pawn.quantum_state == "stacked_on_top")
        for pawn in pawns_in_drawing_order:
            center = screen_positions[pawn.pawn_id]
            if pawn.quantum_state == "superposition":
                draw_dashed_circle(self.screen, COLOR_QUBIT_CYAN, center, PAWN_RADIUS + 6, 10, now * 1.2, 2)
            pygame.draw.circle(self.screen, COLOR_SUBSTRATE, as_int_pair(center), PAWN_RADIUS + 2)
            pygame.draw.circle(self.screen, PLAYER_COLORS[pawn.owner_seat], as_int_pair(center), PAWN_RADIUS)
            draw_text(self.screen, str(pawn.pawn_number), center + np.array([0, 1]), 13, COLOR_SUBSTRATE, bold=True, center=True)
            is_hovered = pawn.pawn_id in selectable_pawn_ids and np.hypot(*(center - mouse_point)) <= PAWN_RADIUS + 3
            if pawn.pawn_id == self.pawn_id_used_as_filter:
                pygame.draw.circle(self.screen, COLOR_QUBIT_CYAN, as_int_pair(center), PAWN_RADIUS + 4, 3)
            elif pawn.pawn_id in highlighted_pawn_ids or is_hovered:
                pygame.draw.circle(self.screen, COLOR_WHITE, as_int_pair(center), PAWN_RADIUS + 4, 2)

        draw_text(self.screen, "Tip: click one of your pawns to show only its moves.  Hover an option to preview it.",
                  (BOARD_TOP_LEFT[0] + 376, BOARD_TOP_LEFT[1] + 16 * PIXELS_PER_SQUARE + 14), 12, COLOR_INK_MUTED, center=True)

    def draw_ghost_preview(self, screen_positions_now):
        option = self.option_being_previewed
        if option is None or option.resulting_game_state is None:
            return
        positions_after = geometry.calculate_position_of_every_pawn(option.resulting_game_state)
        for pawn_id in option.pawn_ids_involved:
            before = screen_positions_now[pawn_id]
            after = convert_squares_to_screen(positions_after[pawn_id])
            if np.hypot(*(after - before)) < 2:
                continue
            owner_seat = engine.find_pawn_by_id(self.game_state, pawn_id).owner_seat
            draw_dashed_line(self.screen, COLOR_WHITE, before, after, 3, 5, 1)
            draw_dashed_circle(self.screen, PLAYER_COLORS[owner_seat], after, PAWN_RADIUS + 1, 10, 0, 3)

    # ----------------------------- side panel -------------------------------

    def draw_side_panel(self):
        self.draw_player_overview(70)
        self.draw_turn_box(194, 352)
        self.draw_quantum_hand(560)
        self.draw_game_log(722)

    def draw_player_overview(self, top):
        chip_width = (PANEL_WIDTH - 8) // 2
        current_player = engine.get_current_player(self.game_state)
        for position, player in enumerate(self.game_state.players):
            chip = pygame.Rect(PANEL_LEFT + (position % 2) * (chip_width + 8), top + (position // 2) * 60, chip_width, 52)
            is_current = player is current_player and self.game_state.turn_phase != "game_over"
            pygame.draw.rect(self.screen, COLOR_PANEL, chip, border_radius=10)
            pygame.draw.rect(self.screen, PLAYER_COLORS[player.seat_number] if is_current else COLOR_PANEL_EDGE, chip, 2 if is_current else 1, border_radius=10)
            pygame.draw.circle(self.screen, PLAYER_COLORS[player.seat_number], (chip.left + 16, chip.top + 17), 6)
            draw_text(self.screen, player.display_name, (chip.left + 30, chip.top + 7), 15, COLOR_INK, bold=True)
            pawns_home = sum(1 for pawn in engine.get_pawns_owned_by_seat(self.game_state, player.seat_number) if pawn.location.zone == "home")
            number_of_cards = len(player.quantum_cards_in_hand)
            details = ("Computer" if player.is_computer_player else "Person") + " · Home " + str(pawns_home) + "/4 · " + str(number_of_cards) + " card" + ("" if number_of_cards == 1 else "s")
            details_rectangle = draw_text(self.screen, details, (chip.left + 30, chip.top + 29), 12, COLOR_INK_MUTED)
            if player.is_jammed_for_their_next_turn:
                draw_text(self.screen, "JAMMED", (details_rectangle.right + 6, chip.top + 29), 12, COLOR_DANGER, bold=True)

    def draw_turn_box(self, top, height):
        box = pygame.Rect(PANEL_LEFT, top, PANEL_WIDTH, height)
        pygame.draw.rect(self.screen, COLOR_PANEL, box, border_radius=14)
        pygame.draw.rect(self.screen, COLOR_PANEL_EDGE, box, 1, border_radius=14)
        self.option_list_area = None

        # --- Banner: whose turn, and what they are doing. ---
        phase = self.game_state.turn_phase
        if phase == "game_over":
            winner = engine.find_player_by_seat(self.game_state, self.game_state.seat_of_winner)
            draw_text(self.screen, winner.display_name + " wins!", (box.left + 16, box.top + 12), 22, PLAYER_COLORS[winner.seat_number], bold=True, for_title=True)
        else:
            current_player = engine.get_current_player(self.game_state)
            name_rectangle = draw_text(self.screen, current_player.display_name, (box.left + 16, box.top + 12), 20, PLAYER_COLORS[current_player.seat_number], bold=True, for_title=True)
            phase_words = {"waiting_to_draw_movement_card": "to draw a movement card", "choosing_how_to_use_movement_card": "to use the card", "finishing_turn": "to finish the turn"}
            doing_words = "is thinking..." if current_player.is_computer_player else phase_words[phase]
            draw_text(self.screen, doing_words + " · turn " + str(self.game_state.turn_number), (name_rectangle.right + 10, box.top + 18), 13, COLOR_INK_MUTED)

        # --- The movement card (or an empty slot). ---
        card_rectangle = pygame.Rect(box.left + 16, box.top + 50, 92, 128)
        card_name = self.game_state.current_movement_card
        if card_name:
            pygame.draw.rect(self.screen, COLOR_CARD_FACE, card_rectangle, border_radius=10)
            pygame.draw.rect(self.screen, COLOR_GOLD_WIRE, (card_rectangle.left, card_rectangle.top, card_rectangle.width, 12), border_top_left_radius=10, border_top_right_radius=10)
            if card_name == "Paradox":
                draw_text(self.screen, "PARADOX", (card_rectangle.centerx, card_rectangle.centery - 4), 15, COLOR_CARD_INK, bold=True, center=True, for_title=True)
                draw_text(self.screen, "leave · 6 · 9", (card_rectangle.centerx, card_rectangle.bottom - 18), 10, COLOR_CARD_INK, center=True)
            else:
                draw_text(self.screen, card_name, (card_rectangle.centerx, card_rectangle.centery - 2), 44, COLOR_CARD_INK, bold=True, center=True, for_title=True)
                draw_text(self.screen, "MOVEMENT", (card_rectangle.centerx, card_rectangle.bottom - 16), 9, COLOR_CARD_INK, center=True)
        else:
            draw_dashed_line(self.screen, COLOR_PANEL_EDGE, card_rectangle.topleft, card_rectangle.topright, 6, 4)
            draw_dashed_line(self.screen, COLOR_PANEL_EDGE, card_rectangle.bottomleft, card_rectangle.bottomright, 6, 4)
            draw_dashed_line(self.screen, COLOR_PANEL_EDGE, card_rectangle.topleft, card_rectangle.bottomleft, 6, 4)
            draw_dashed_line(self.screen, COLOR_PANEL_EDGE, card_rectangle.topright, card_rectangle.bottomright, 6, 4)
            empty_words = "Draw a card" if phase == "waiting_to_draw_movement_card" else "Card used"
            draw_text(self.screen, empty_words, card_rectangle.center, 12, COLOR_INK_MUTED, center=True)

        # --- The action column to the right of the card. ---
        action_area = pygame.Rect(box.left + 122, box.top + 50, box.width - 138, height - 64)
        self.draw_actions(action_area)

    def draw_explanation(self, text, area, y) -> int:
        return draw_wrapped_text(self.screen, text, (area.left, y), area.width, 13, COLOR_INK_MUTED) + 6

    def draw_actions(self, area: pygame.Rect):
        phase = self.game_state.turn_phase
        y = area.top

        if phase == "game_over":
            y = self.draw_explanation("All four pawns are Home. Play again?", area, y)
            self.add_button((area.left, y, area.width, 40), "New game", self.open_setup_window, "main")
            return

        current_player = engine.get_current_player(self.game_state)
        if current_player.is_computer_player:
            last_message = self.game_state.game_log[-1].message_text if self.game_state.game_log else ""
            self.draw_explanation(last_message, area, y)
            return

        if self.open_overlay == "reaction":
            self.draw_explanation("Waiting for an answer to the counter question...", area, y)
            return

        # A person is choosing a target for a quantum card from their hand.
        if self.quantum_card_chosen_from_hand:
            y = self.draw_explanation(engine.QUANTUM_CARD_EXPLANATIONS[self.quantum_card_chosen_from_hand], area, y)
            list_bottom = area.bottom - 44
            self.draw_option_list(self.options_currently_listed(), pygame.Rect(area.left, y, area.width, list_bottom - y))
            self.add_button((area.left, area.bottom - 36, area.width, 36), "Keep the card", lambda: self.person_clicks_quantum_card(self.quantum_card_chosen_from_hand))
            return

        if phase == "waiting_to_draw_movement_card":
            self.add_button((area.left, y, area.width, 42), "Draw a movement card", self.person_draws_movement_card, "main", 15)
            y += 52
            if engine.can_current_player_play_quantum_card(self.game_state):
                self.draw_explanation("You may play one quantum card from your hand first, or later this turn.", area, y)
            return

        if phase == "choosing_how_to_use_movement_card":
            y = self.draw_explanation(engine.MOVEMENT_CARD_RULES[self.game_state.current_movement_card].explanation, area, y)
            can_sacrifice = engine.can_sacrifice_movement_card(self.game_state)
            has_moves = bool(self.cached_movement_options)
            number_of_bottom_buttons = int(can_sacrifice) + int(not has_moves)
            list_bottom = area.bottom - number_of_bottom_buttons * 42
            if has_moves:
                self.draw_option_list(self.cached_movement_options, pygame.Rect(area.left, y, area.width, list_bottom - y))
            else:
                self.draw_explanation("No legal move with this card.", area, y)
            button_y = list_bottom + 6
            if can_sacrifice:
                self.add_button((area.left, button_y, area.width, 36), "Sacrifice it for a quantum card", self.person_sacrifices_movement_card, "quantum")
                button_y += 42
            if not has_moves:
                self.add_button((area.left, button_y, area.width, 36), "Discard it", self.person_discards_movement_card)
            return

        if phase == "finishing_turn":
            y = self.draw_explanation("You can still play one quantum card this turn.", area, y)
            self.add_button((area.left, y, area.width, 42), "End turn", self.person_ends_turn, "main", 15)

    def draw_option_list(self, all_options: list, list_area: pygame.Rect):
        """A scrollable list of option buttons; hovering one previews it."""
        options = all_options
        if self.pawn_id_used_as_filter:
            options = [option for option in all_options if self.pawn_id_used_as_filter in option.pawn_ids_involved]
            filter_pawn = engine.find_pawn_by_id(self.game_state, self.pawn_id_used_as_filter)
            note_rectangle = draw_text(self.screen, "Showing moves for " + engine.get_pawn_display_name(filter_pawn) + ".", (list_area.left, list_area.top), 12, COLOR_QUBIT_CYAN)
            show_all_rectangle = draw_text(self.screen, "Show all", (note_rectangle.right + 8, list_area.top), 12, COLOR_INK, bold=True)
            pygame.draw.line(self.screen, COLOR_INK, show_all_rectangle.bottomleft, show_all_rectangle.bottomright)

            def clear_filter():
                self.pawn_id_used_as_filter = None
            self.clickable_areas.append(ClickableArea(show_all_rectangle.inflate(6, 6), clear_filter))
            list_area = pygame.Rect(list_area.left, list_area.top + 22, list_area.width, list_area.height - 22)

        self.option_list_area = list_area
        text_width = list_area.width - 24
        row_heights = [measure_wrapped_text_height(option.description, text_width, 13) + 12 for option in options]
        total_height = sum(row_heights) + 5 * len(options)
        self.option_list_scroll_offset = min(self.option_list_scroll_offset, max(0, total_height - list_area.height))

        mouse_position = pygame.mouse.get_pos()
        hovered_option = None
        self.screen.set_clip(list_area)           # draw only inside the list area
        y = list_area.top - self.option_list_scroll_offset
        for option, row_height in zip(options, row_heights):
            row = pygame.Rect(list_area.left, y, list_area.width - 8, row_height)
            if row.bottom >= list_area.top and row.top <= list_area.bottom:
                is_hovered = row.collidepoint(mouse_position) and list_area.collidepoint(mouse_position)
                pygame.draw.rect(self.screen, blend_colors(COLOR_PANEL_RAISED, COLOR_WHITE, 0.1) if is_hovered else COLOR_PANEL_RAISED, row, border_radius=7)
                if is_hovered:
                    pygame.draw.rect(self.screen, COLOR_INK, row, 1, border_radius=7)
                    hovered_option = option
                draw_wrapped_text(self.screen, option.description, (row.left + 10, row.top + 6), text_width, 13, COLOR_INK)
                visible_part = row.clip(list_area)
                if visible_part.height > 0:
                    self.clickable_areas.append(ClickableArea(visible_part, lambda option=option: self.person_chooses_option(option), "option: " + option.description))
            y += row_height + 5
        self.screen.set_clip(None)

        # A thin scroll bar when the list is longer than the space.
        if total_height > list_area.height:
            bar_height = max(24, list_area.height * list_area.height // total_height)
            bar_top = list_area.top + (list_area.height - bar_height) * self.option_list_scroll_offset // max(1, total_height - list_area.height)
            pygame.draw.rect(self.screen, COLOR_PANEL_EDGE, (list_area.right - 4, bar_top, 4, bar_height), border_radius=2)
        if not options:
            draw_text(self.screen, "No options for that pawn.", list_area.topleft, 12, COLOR_INK_MUTED)

        # The ghost preview follows the mouse (computer previews are set elsewhere).
        if self.is_it_a_persons_turn():
            self.option_being_previewed = hovered_option

    def draw_quantum_hand(self, top):
        current_player = engine.get_current_player(self.game_state)
        if current_player.is_computer_player:
            shown_player = next((player for player in self.game_state.players if not player.is_computer_player), None)
        else:
            shown_player = current_player

        if shown_player is None:
            draw_text(self.screen, "QUANTUM HANDS", (PANEL_LEFT, top), 12, COLOR_INK_MUTED, bold=True)
            draw_text(self.screen, "Computer hands are hidden. Card counts are shown beside each player.", (PANEL_LEFT, top + 24), 12, COLOR_INK_MUTED)
            return

        draw_text(self.screen, (shown_player.display_name + "'s quantum hand").upper(), (PANEL_LEFT, top), 12, COLOR_INK_MUTED, bold=True)
        is_their_turn = shown_player is current_player and self.game_state.turn_phase != "game_over" and self.open_overlay is None
        playable_card_names = {option.card_name for option in self.cached_quantum_options} if is_their_turn else set()
        card_width = (PANEL_WIDTH - 16) // 3
        for slot_number in range(engine.MAXIMUM_QUANTUM_CARDS_IN_HAND):
            card_rectangle = pygame.Rect(PANEL_LEFT + slot_number * (card_width + 8), top + 22, card_width, 104)
            if slot_number >= len(shown_player.quantum_cards_in_hand):
                draw_dashed_line(self.screen, COLOR_PANEL_EDGE, card_rectangle.topleft, card_rectangle.topright, 6, 4)
                draw_dashed_line(self.screen, COLOR_PANEL_EDGE, card_rectangle.bottomleft, card_rectangle.bottomright, 6, 4)
                draw_dashed_line(self.screen, COLOR_PANEL_EDGE, card_rectangle.topleft, card_rectangle.bottomleft, 6, 4)
                draw_dashed_line(self.screen, COLOR_PANEL_EDGE, card_rectangle.topright, card_rectangle.bottomright, 6, 4)
                draw_text(self.screen, "Empty slot", card_rectangle.center, 12, COLOR_INK_MUTED, center=True)
                continue
            card_name = shown_player.quantum_cards_in_hand[slot_number]
            is_playable = card_name in playable_card_names
            is_chosen = card_name == self.quantum_card_chosen_from_hand
            is_hovered = is_playable and card_rectangle.collidepoint(pygame.mouse.get_pos())
            fill = (23, 58, 98) if is_playable else blend_colors((23, 58, 98), COLOR_PANEL, 0.6)
            if is_hovered:
                fill = blend_colors(fill, COLOR_WHITE, 0.1)
            pygame.draw.rect(self.screen, fill, card_rectangle, border_radius=10)
            pygame.draw.rect(self.screen, COLOR_QUBIT_CYAN if is_playable else COLOR_PANEL_EDGE, card_rectangle, 3 if is_chosen else 1, border_radius=10)
            draw_quantum_card_picture(self.screen, card_name, (card_rectangle.centerx, card_rectangle.top + 32))
            label_lines = card_name.replace("/", "/ ").split(" ") if len(card_name) > 14 else [card_name]
            for line_number, line in enumerate(label_lines):
                draw_text(self.screen, line, (card_rectangle.centerx, card_rectangle.top + 66 + line_number * 16), 13, COLOR_INK if is_playable else COLOR_INK_MUTED, bold=True, center=True)
            if is_playable:
                self.clickable_areas.append(ClickableArea(card_rectangle, lambda card_name=card_name: self.person_clicks_quantum_card(card_name), "card: " + card_name))

        if not is_their_turn:
            note = "Waiting for your turn. You may still be asked to counter."
        elif shown_player.is_jammed_for_their_next_turn:
            note = "You are jammed: no quantum cards this turn."
        elif self.game_state.has_played_quantum_card_this_turn:
            note = "You already played a quantum card this turn."
        elif shown_player.quantum_cards_in_hand:
            note = "Click a card to play it. Any card can also launch a pawn out of Start."
        else:
            note = "Sacrifice a movement card or land on a Quantum Space (Q) to draw cards."
        draw_text(self.screen, note, (PANEL_LEFT, top + 134), 12, COLOR_INK_MUTED)

    def draw_game_log(self, top):
        draw_text(self.screen, "WHAT HAPPENED", (PANEL_LEFT, top), 12, COLOR_INK_MUTED, bold=True)
        log_box = pygame.Rect(PANEL_LEFT, top + 20, PANEL_WIDTH, WINDOW_HEIGHT - top - 34)
        self.log_area = log_box
        pygame.draw.rect(self.screen, COLOR_PANEL, log_box, border_radius=10)
        pygame.draw.rect(self.screen, COLOR_PANEL_EDGE, log_box, 1, border_radius=10)

        # Build the wrapped lines from the newest entries, then show the bottom part.
        text_width = log_box.width - 30
        line_height = get_font(12).get_linesize()
        number_of_visible_lines = (log_box.height - 12) // line_height
        wrapped_lines = []
        for log_entry in self.game_state.game_log[-60:]:
            for line in wrap_text_into_lines(log_entry.message_text, 12, False, text_width):
                wrapped_lines.append((line, log_entry.seat_number, log_entry.message_text.startswith("---")))
        self.log_scroll_offset = min(self.log_scroll_offset, max(0, len(wrapped_lines) - number_of_visible_lines))
        last_line = len(wrapped_lines) - self.log_scroll_offset
        visible_lines = wrapped_lines[max(0, last_line - number_of_visible_lines):last_line]
        y = log_box.top + 6
        for line, seat_number, is_turn_start in visible_lines:
            if seat_number is not None:
                pygame.draw.line(self.screen, PLAYER_COLORS[seat_number], (log_box.left + 10, y + 2), (log_box.left + 10, y + line_height - 2), 3)
            draw_text(self.screen, line, (log_box.left + 20, y), 12, COLOR_INK_MUTED if is_turn_start else COLOR_INK, bold=is_turn_start)
            y += line_height

    # ------------------------------ pop-ups ---------------------------------

    def draw_dimmed_background_and_panel(self, width, height) -> pygame.Rect:
        dimmer = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        dimmer.fill((5, 8, 25, 190))
        self.screen.blit(dimmer, (0, 0))
        # Clicks outside the panel must not reach the game underneath.
        self.clickable_areas = [ClickableArea(pygame.Rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT), lambda: None)]
        panel = pygame.Rect(0, 0, width, height)
        panel.center = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        pygame.draw.rect(self.screen, COLOR_PANEL, panel, border_radius=16)
        pygame.draw.rect(self.screen, COLOR_PANEL_EDGE, panel, 1, border_radius=16)
        return panel

    def draw_setup_window(self):
        panel = self.draw_dimmed_background_and_panel(620, 440)
        draw_text(self.screen, "NEW GAME", (panel.left + 28, panel.top + 24), 24, COLOR_INK, bold=True, for_title=True)
        y = draw_wrapped_text(self.screen, "Choose who sits at each side of the board. You need at least two players. People take turns on this computer; computer players move on their own. Click a name to type a new one.",
                              (panel.left + 28, panel.top + 66), panel.width - 56, 14, COLOR_INK_MUTED) + 12
        for row_number, row in enumerate(self.seat_setup_rows):
            row_top = y + row_number * 50
            pygame.draw.circle(self.screen, PLAYER_COLORS[row.seat_number], (panel.left + 36, row_top + 18), 7)
            draw_text(self.screen, engine.PLAYER_COLOR_NAMES[row.seat_number], (panel.left + 52, row_top + 9), 15, COLOR_INK, bold=True)

            name_box = pygame.Rect(panel.left + 130, row_top, 280, 36)
            has_focus = self.seat_row_with_keyboard_focus == row_number
            pygame.draw.rect(self.screen, COLOR_PANEL_RAISED, name_box, border_radius=6)
            pygame.draw.rect(self.screen, COLOR_QUBIT_CYAN if has_focus else COLOR_PANEL_EDGE, name_box, 2 if has_focus else 1, border_radius=6)
            if row.seat_type == "empty":
                draw_text(self.screen, "(nobody)", (name_box.left + 10, name_box.top + 9), 14, COLOR_INK_MUTED)
            else:
                cursor = "|" if has_focus and int(time.time() * 2) % 2 == 0 else ""
                draw_text(self.screen, row.display_name + cursor, (name_box.left + 10, name_box.top + 9), 14, COLOR_INK)

                def focus_this_row(row_number=row_number):
                    self.seat_row_with_keyboard_focus = row_number
                self.clickable_areas.append(ClickableArea(name_box, focus_this_row))

            self.add_button((panel.left + 424, row_top, 168, 36), SeatSetupRow.SEAT_TYPE_LABELS[row.seat_type] + "  (change)", row.switch_to_next_seat_type)

        if self.setup_error_message:
            draw_text(self.screen, self.setup_error_message, (panel.left + 28, panel.bottom - 98), 14, COLOR_DANGER)
        self.add_button((panel.right - 300, panel.bottom - 60, 120, 40), "Cancel", self.close_setup_window)
        self.add_button((panel.right - 168, panel.bottom - 60, 140, 40), "Start game", self.submit_setup_window, "main", 15)

    def draw_rules_window(self):
        panel = self.draw_dimmed_background_and_panel(800, 760)
        draw_text(self.screen, "HOW TO PLAY QUANTASTIC!", (panel.left + 28, panel.top + 22), 22, COLOR_INK, bold=True, for_title=True)

        def close_rules():
            self.open_overlay = None
        self.add_button((panel.right - 120, panel.top + 18, 96, 36), "Close", close_rules)

        text_area = pygame.Rect(panel.left + 28, panel.top + 70, panel.width - 56, panel.height - 90)
        self.rules_area = text_area

        # First measure how tall all the text is, so scrolling stops at the end.
        total_height = 0
        for style, text in RULES_TEXT:
            if style == "h":
                total_height += 38
            elif style == "b":
                total_height += measure_wrapped_text_height(text, text_area.width - 30, 14) + 6
            else:
                total_height += measure_wrapped_text_height(text, text_area.width - 12, 14) + 6
        self.rules_scroll_offset = min(self.rules_scroll_offset, max(0, total_height - text_area.height))

        self.screen.set_clip(text_area)
        y = text_area.top - self.rules_scroll_offset
        for style, text in RULES_TEXT:
            if style == "h":
                y += 10
                draw_text(self.screen, text, (text_area.left, y), 17, COLOR_GOLD_WIRE, bold=True)
                y += 28
            elif style == "b":
                pygame.draw.circle(self.screen, COLOR_QUBIT_CYAN, (text_area.left + 5, y + 9), 3)
                y = draw_wrapped_text(self.screen, text, (text_area.left + 18, y), text_area.width - 30, 14, COLOR_INK) + 6
            else:
                y = draw_wrapped_text(self.screen, text, (text_area.left, y), text_area.width - 12, 14, COLOR_INK_MUTED if style == "n" else COLOR_INK) + 6
        self.screen.set_clip(None)
        if total_height > text_area.height:
            draw_text(self.screen, "Scroll with the mouse wheel for more", (panel.centerx, panel.bottom - 12), 11, COLOR_INK_MUTED, center=True)

    def draw_counter_question_window(self):
        question = self.pending_counter_question
        reacting_player = question["reacting_player"]
        acting_player = question["acting_player"]
        quantum_option = question["quantum_option"]
        description = acting_player.display_name + " is playing " + quantum_option.card_name + ": " + quantum_option.description + "."
        buttons = [(reaction.description, reaction, "quantum") for reaction in question["reactions_for_this_seat"]] + [("Let it happen", None, "main")]
        button_height = 40
        description_height = measure_wrapped_text_height(description, 504, 15)
        panel_height = 90 + description_height + len(buttons) * (button_height + 8) + 20
        panel = self.draw_dimmed_background_and_panel(560, panel_height)
        draw_text(self.screen, (reacting_player.display_name + ", counter this?").upper(), (panel.left + 28, panel.top + 22), 20, PLAYER_COLORS[reacting_player.seat_number], bold=True, for_title=True)
        y = draw_wrapped_text(self.screen, description, (panel.left + 28, panel.top + 62), 504, 15, COLOR_INK) + 14
        for label, reaction, style in buttons:
            self.add_button((panel.left + 28, y, 504, button_height), label, lambda reaction=reaction: self.person_answers_counter_question(reaction), style, 13)
            y += button_height + 8

    def draw_announcement(self):
        if not self.announcement_text or time.time() > self.announcement_until or self.open_overlay in ("setup", "rules"):
            return
        rendered = get_font(15, True).render(self.announcement_text, True, COLOR_CARD_INK)
        pill = rendered.get_rect().inflate(36, 18)
        pill.midbottom = (WINDOW_WIDTH // 2, WINDOW_HEIGHT - 20)
        pygame.draw.rect(self.screen, COLOR_GOLD_WIRE, pill, border_radius=pill.height // 2)
        self.screen.blit(rendered, rendered.get_rect(center=pill.center))


# =============================================================================
# SECTION 13 — STARTING THE PROGRAM
# =============================================================================

async def main():
    pygame.init()
    pygame.display.set_caption("Quantastic!")
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()
    app = QuantasticApp(screen)

    keep_running = True
    while keep_running:
        seconds_since_last_frame = clock.tick(FRAMES_PER_SECOND) / 1000.0
        for event in pygame.event.get():
            if not app.handle_event(event):
                keep_running = False
        app.update(seconds_since_last_frame)
        app.draw()
        pygame.display.flip()
        # Hands control back to the browser each frame. Required for the
        # game to run in a web browser (via pygbag); a harmless no-op
        # when playing the desktop version.
        await asyncio.sleep(0)
    pygame.quit()


# This line means: only start the game when this file is run directly
# (not when another file, like a test, imports it).
if __name__ == "__main__":
    asyncio.run(main())
