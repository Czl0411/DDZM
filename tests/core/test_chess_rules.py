import pytest

from dzmm_bot.core.chess_rules import (
    ChessMove, ChessPosition, IllegalChessMove, basic_outcome, initial_position,
    legal_moves, play_move,
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
    p = position([(4, 9, "K"), (4, 0, "k"), (3, 1, "R"), (5, 1, "R"), (4, 5, "P")], "black")
    outcome = basic_outcome(p)
    assert outcome is not None and outcome.winner == "red"
