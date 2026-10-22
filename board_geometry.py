"""
=============================================================================
QUANTASTIC!  —  BOARD GEOMETRY  (board_geometry.py)
-----------------------------------------------------------------------------
Where is each square, circle and pawn on the screen? This file answers that
with a bit of geometry, using NumPy (imported as "np"), a library for doing
arithmetic on points and lists of numbers.

THE KEY IDEA
------------
Positions are first worked out in "board squares" for the TOP player's side
only: x = columns from the left (0 to 16), y = rows from the top (0 to 16).
The other three sides are exactly the same picture rotated a quarter turn,
a half turn and three quarters of a turn around the center of the board.
A rotation is done by multiplying the point by a "rotation matrix": a 2 x 2
table of numbers that turns any point around the origin.

A point is stored as a NumPy array [x, y].
=============================================================================
"""

import numpy as np

import game_engine as engine

BOARD_SIZE_IN_SQUARES = 16
BOARD_CENTER_IN_SQUARES = np.array([8.0, 8.0])

# Rotating a point a quarter turn CLOCKWISE on screen (where y grows downward)
# turns the offset (dx, dy) from the center into (-dy, dx). As a matrix:
QUARTER_TURN_CLOCKWISE = np.array([[0.0, -1.0],
                                   [1.0, 0.0]])

# Sizes of the round areas, in squares.
HOME_CIRCLE_RADIUS_IN_SQUARES = 1.15
START_CIRCLE_RADIUS_IN_SQUARES = 1.2
CENTRAL_HUB_RADIUS_IN_SQUARES = 2.95

# Where things are for the TOP player (seat 0), before any rotation.
SAFETY_LANE_FIRST_SQUARE_FOR_TOP_SEAT = np.array([2.5, 1.5])   # lane runs downward from here
HOME_CENTER_FOR_TOP_SEAT = np.array([2.5, 7.05])
START_CENTER_FOR_TOP_SEAT = np.array([5.6, 2.65])

# Four parking spots inside a Start or Home circle (offsets in squares).
PARKING_SPOT_OFFSETS = np.array([[-0.42, -0.42], [0.42, -0.42],
                                 [-0.42, 0.42], [0.42, 0.42]])


def rotate_point_clockwise(point_in_squares: np.ndarray, number_of_quarter_turns: int) -> np.ndarray:
    """Turns a point around the center of the board by a number of quarter turns."""
    rotation = np.linalg.matrix_power(QUARTER_TURN_CLOCKWISE, number_of_quarter_turns % 4)
    offset_from_center = point_in_squares - BOARD_CENTER_IN_SQUARES
    return BOARD_CENTER_IN_SQUARES + rotation @ offset_from_center   # "@" means matrix multiplication


def get_center_of_track_square(track_space_number: int) -> np.ndarray:
    """Center of track square 0-59, in squares."""
    side_number, position_on_side = divmod(track_space_number, engine.NUMBER_OF_TRACK_SPACES_PER_SIDE)
    center_on_top_side = np.array([position_on_side + 0.5, 0.5])
    return rotate_point_clockwise(center_on_top_side, side_number)


def get_center_of_safety_square(seat_number: int, safety_zone_step: int) -> np.ndarray:
    """Center of a Safety Zone square (step 0-4); the lane runs inward."""
    center_for_top_seat = SAFETY_LANE_FIRST_SQUARE_FOR_TOP_SEAT + np.array([0.0, safety_zone_step])
    return rotate_point_clockwise(center_for_top_seat, seat_number)


def get_center_of_home_circle(seat_number: int) -> np.ndarray:
    return rotate_point_clockwise(HOME_CENTER_FOR_TOP_SEAT, seat_number)


def get_center_of_start_circle(seat_number: int) -> np.ndarray:
    return rotate_point_clockwise(START_CENTER_FOR_TOP_SEAT, seat_number)


def calculate_position_of_every_pawn(game_state: engine.GameState) -> dict:
    """Where every pawn should be drawn, in squares.
    Returns a dictionary: pawn_id -> np.array([x, y])."""
    positions = {}
    for pawn in game_state.pawns:
        zone = pawn.location.zone
        if zone in ("start", "home"):
            # Pawns of one owner share a circle, one parking spot each.
            pawns_in_same_circle = sorted(
                (other for other in game_state.pawns if other.owner_seat == pawn.owner_seat and other.location.zone == zone),
                key=lambda other: other.pawn_number,
            )
            spot_number = pawns_in_same_circle.index(pawn) % 4
            circle_center = get_center_of_start_circle(pawn.owner_seat) if zone == "start" else get_center_of_home_circle(pawn.owner_seat)
            positions[pawn.pawn_id] = circle_center + PARKING_SPOT_OFFSETS[spot_number]
            continue

        if zone == "track":
            center = get_center_of_track_square(pawn.location.track_space_number)
        else:
            center = get_center_of_safety_square(pawn.owner_seat, pawn.location.safety_zone_step)
        # Stacked pawns are drawn slightly apart so both stay visible.
        if pawn.quantum_state == "stacked_on_top":
            center = center + np.array([-0.16, -0.16])
        elif engine.is_pawn_covered_at_bottom_of_stack(pawn):
            center = center + np.array([0.12, 0.12])
        positions[pawn.pawn_id] = center
    return positions


def make_dashed_line_segments(start_point: np.ndarray, end_point: np.ndarray, dash_length: float, gap_length: float, phase_shift: float = 0.0) -> list:
    """Splits a straight line into short dashes. Returns a list of
    (dash_start, dash_end) point pairs. phase_shift slides the dashes along the
    line, which makes them look like they are flowing when it changes over time."""
    line_vector = end_point - start_point
    line_length = float(np.hypot(*line_vector))
    if line_length < 1e-6:
        return []
    unit_direction = line_vector / line_length
    pattern_length = dash_length + gap_length
    dash_starts = np.arange(-pattern_length + (phase_shift % pattern_length), line_length, pattern_length)
    segments = []
    for dash_start in dash_starts:
        clipped_start = max(dash_start, 0.0)
        clipped_end = min(dash_start + dash_length, line_length)
        if clipped_end > clipped_start:
            segments.append((start_point + unit_direction * clipped_start, start_point + unit_direction * clipped_end))
    return segments


def make_arrowhead_triangle(tip_point: np.ndarray, pointing_direction: np.ndarray, length: float, half_width: float) -> list:
    """Three corner points of a triangle whose tip is at tip_point, pointing in
    pointing_direction (used for the slide arrows)."""
    unit_direction = pointing_direction / np.hypot(*pointing_direction)
    perpendicular = np.array([-unit_direction[1], unit_direction[0]])   # a quarter turn of the direction
    back_center = tip_point - unit_direction * length
    return [tip_point, back_center + perpendicular * half_width, back_center - perpendicular * half_width]


def move_points_smoothly_toward_targets(current_points: dict, target_points: dict, fraction_of_distance: float) -> dict:
    """Animation helper: moves every pawn a fraction of the remaining way toward
    where it should be. Called every frame, this makes pawns glide instead of
    jumping. Returns the updated positions."""
    updated_points = {}
    for pawn_id, target in target_points.items():
        current = current_points.get(pawn_id, target)
        updated_points[pawn_id] = current + (target - current) * fraction_of_distance
    return updated_points
