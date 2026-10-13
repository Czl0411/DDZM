import pytest

from dzmm_bot.core.chess_rules import (
    ChessMove, ChessPosition, ChessViolation, IllegalChessMove, adjudicate_repetition,
    basic_outcome, initial_position, legal_moves, play_move,
)


def position(pieces, turn="red"):
    rows = [["."] * 9 for _ in range(10)]
    for x, y, piece in pieces:
        rows[y][x] = piece
    return ChessPosition(tuple("".join(row) for row in rows), turn)


def try_move(pos, a, b):
    return play_move(pos, ChessMove(*a, *b))


def test_starting_board_is_symmetric_and_red_starts():
    pos = initial_position()
    assert pos.turn == "red"
    assert pos.board[0] == "rheakaehr"
    assert pos.board[9] == "RHEAKAEHR"
    assert len(legal_moves(pos)) > 0


def test_rook_horse_and_cannon_blocking():
    p = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (0, 9, "R"), (0, 7, "P")])
    with pytest.raises(IllegalChessMove):
        try_move(p, (0, 9), (0, 6))
    assert try_move(p, (0, 9), (0, 8)).board[8][0] == "R"
    p = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (1, 9, "H"), (1, 8, "P")])
    with pytest.raises(IllegalChessMove):
        try_move(p, (1, 9), (2, 7))
    p = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (0, 7, "C"), (0, 5, "P"), (0, 3, "p")])
    assert try_move(p, (0, 7), (0, 3)).board[3][0] == "C"
    with pytest.raises(IllegalChessMove):
        try_move(p, (0, 7), (0, 4))


def test_elephant_advisor_king_and_pawn():
    p = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (2, 9, "E"), (3, 8, "P")])
    with pytest.raises(IllegalChessMove):
        try_move(p, (2, 9), (4, 7))
    p = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (2, 9, "E")])
    assert try_move(p, (2, 9), (4, 7)).board[7][4] == "E"
    p = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (4, 8, "A")])
    assert try_move(p, (4, 8), (3, 9)).board[9][3] == "A"
    with pytest.raises(IllegalChessMove):
        try_move(p, (4, 8), (2, 6))
    with pytest.raises(IllegalChessMove):
        try_move(p, (4, 9), (4, 7))
    p = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (0, 6, "P")])
    with pytest.raises(IllegalChessMove):
        try_move(p, (0, 6), (1, 6))
    p = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (0, 4, "P")])
    assert try_move(p, (0, 4), (1, 4)).board[4][1] == "P"


def test_facing_generals_and_check_response():
    p = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "R")])
    with pytest.raises(IllegalChessMove):
        try_move(p, (4, 5), (5, 5))
    p = position([(4, 9, "K"), (3, 0, "k"), (4, 5, "r"), (0, 9, "R")])
    with pytest.raises(IllegalChessMove):
        try_move(p, (0, 9), (0, 8))
    assert try_move(p, (4, 9), (5, 9)).board[9][5] == "K"


def test_checkmate_or_stalemate_loses_for_side_to_move():
    p = position([(4, 9, "K"), (4, 0, "k"), (3, 1, "R"), (5, 1, "R"), (4, 2, "R")], "black")
    outcome = basic_outcome(p)
    assert outcome is not None and outcome.winner == "red"


def cycle(start, sequence, rounds=2):
    history = [start]
    moves = []
    for _ in range(rounds):
        for move in sequence:
            history.append(play_move(history[-1], move))
            moves.append(move)
    return tuple(history), tuple(moves)


def test_threefold_quiet_repetition_is_not_automatic_draw():
    start = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (0, 9, "R"), (8, 0, "r")])
    sequence = (ChessMove(0, 9, 0, 8), ChessMove(8, 0, 8, 1), ChessMove(0, 8, 0, 9), ChessMove(8, 1, 8, 0))
    history, moves = cycle(start, sequence)
    assert history[0] == history[4] == history[8]
    assert adjudicate_repetition(history[:5], moves[:4]) is None
    assert adjudicate_repetition(history, moves) is None


def test_single_side_perpetual_check_must_change():
    start = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (3, 3, "R")])
    sequence = (ChessMove(3, 3, 4, 3), ChessMove(4, 0, 3, 0), ChessMove(4, 3, 3, 3), ChessMove(3, 0, 4, 0))
    history, moves = cycle(start, sequence)
    ruling = adjudicate_repetition(history, moves)
    assert isinstance(ruling, ChessViolation)
    assert ruling.side == "red" and ruling.reason == "long_check"


def test_single_side_perpetual_chase_must_change():
    start = position([(4, 9, "K"), (4, 0, "k"), (4, 5, "P"), (2, 6, "R"), (1, 3, "h")])
    sequence = (ChessMove(2, 6, 1, 6), ChessMove(1, 3, 2, 5), ChessMove(1, 6, 2, 6), ChessMove(2, 5, 1, 3))
    history, moves = cycle(start, sequence)
    ruling = adjudicate_repetition(history, moves)
    assert isinstance(ruling, ChessViolation)
    assert ruling.side == "red" and ruling.reason == "long_chase"
    p = position([(4, 9, "K"), (4, 0, "k"), (3, 1, "R"), (5, 1, "R"), (4, 5, "P")], "black")
    outcome = basic_outcome(p)
    assert outcome is not None and outcome.winner == "red"
