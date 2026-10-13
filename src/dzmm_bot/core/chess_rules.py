"""Pure, server-side Chinese chess move validation."""

from dataclasses import dataclass


class IllegalChessMove(ValueError):
    pass


@dataclass(frozen=True)
class ChessMove:
    from_x: int
    from_y: int
    to_x: int
    to_y: int


@dataclass(frozen=True)
class ChessPosition:
    board: tuple[str, ...]
    turn: str

    def __post_init__(self):
        if len(self.board) != 10 or any(len(row) != 9 for row in self.board):
            raise ValueError("棋盘必须为 9×10")
        if self.turn not in {"red", "black"}:
            raise ValueError("无效的行棋方")


@dataclass(frozen=True)
class ChessOutcome:
    winner: str | None
    reason: str


@dataclass(frozen=True)
class ChessViolation:
    side: str
    reason: str


def initial_position() -> ChessPosition:
    return ChessPosition((
        "rheakaehr", ".........", ".c.....c.", "p.p.p.p.p", ".........",
        ".........", "P.P.P.P.P", ".C.....C.", ".........", "RHEAKAEHR",
    ), "red")


def _color(piece: str) -> str | None:
    if piece == ".":
        return None
    return "red" if piece.isupper() else "black"


def _inside(x: int, y: int) -> bool:
    return 0 <= x < 9 and 0 <= y < 10


def _palace(color: str, x: int, y: int) -> bool:
    return 3 <= x <= 5 and (7 <= y <= 9 if color == "red" else 0 <= y <= 2)


def _piece_targets(board: tuple[str, ...], x: int, y: int):
    piece = board[y][x]
    color = _color(piece)
    if color is None:
        return
    kind = piece.upper()

    def usable(tx, ty):
        return _inside(tx, ty) and _color(board[ty][tx]) != color

    if kind in {"R", "C"}:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tx, ty = x + dx, y + dy
            screened = False
            while _inside(tx, ty):
                target = board[ty][tx]
                if kind == "R":
                    if target == ".":
                        yield tx, ty
                    else:
                        if usable(tx, ty):
                            yield tx, ty
                        break
                elif not screened:
                    if target == ".":
                        yield tx, ty
                    else:
                        screened = True
                elif target != ".":
                    if usable(tx, ty):
                        yield tx, ty
                    break
                tx, ty = tx + dx, ty + dy
    elif kind == "H":
        for leg_x, leg_y, dests in (
            (1, 0, ((2, 1), (2, -1))), (-1, 0, ((-2, 1), (-2, -1))),
            (0, 1, ((1, 2), (-1, 2))), (0, -1, ((1, -2), (-1, -2))),
        ):
            if _inside(x + leg_x, y + leg_y) and board[y + leg_y][x + leg_x] == ".":
                for dx, dy in dests:
                    if usable(x + dx, y + dy):
                        yield x + dx, y + dy
    elif kind == "E":
        for dx, dy in ((2, 2), (-2, 2), (2, -2), (-2, -2)):
            tx, ty = x + dx, y + dy
            if (0 <= ty <= 4 if color == "black" else 5 <= ty <= 9) and usable(tx, ty) and board[y + dy // 2][x + dx // 2] == ".":
                yield tx, ty
    elif kind == "A":
        for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            tx, ty = x + dx, y + dy
            if _palace(color, tx, ty) and usable(tx, ty):
                yield tx, ty
    elif kind == "K":
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tx, ty = x + dx, y + dy
            if _palace(color, tx, ty) and usable(tx, ty):
                yield tx, ty
    elif kind == "P":
        forward = -1 if color == "red" else 1
        options = [(x, y + forward)]
        if (y <= 4 if color == "red" else y >= 5):
            options.extend(((x - 1, y), (x + 1, y)))
        for tx, ty in options:
            if usable(tx, ty):
                yield tx, ty


def _moved(board: tuple[str, ...], move: ChessMove) -> tuple[str, ...]:
    rows = [list(row) for row in board]
    rows[move.to_y][move.to_x] = rows[move.from_y][move.from_x]
    rows[move.from_y][move.from_x] = "."
    return tuple("".join(row) for row in rows)


def _in_check(board: tuple[str, ...], color: str) -> bool:
    king = "K" if color == "red" else "k"
    try:
        kx, ky = next((x, y) for y, row in enumerate(board) for x, p in enumerate(row) if p == king)
    except StopIteration:
        return True
    enemy_king = "k" if color == "red" else "K"
    for y, row in enumerate(board):
        for x, piece in enumerate(row):
            if piece != enemy_king or x != kx:
                continue
            if all(board[step][x] == "." for step in range(min(y, ky) + 1, max(y, ky))):
                return True
    for y, row in enumerate(board):
        for x, piece in enumerate(row):
            if _color(piece) != color and piece != ".":
                if (kx, ky) in _piece_targets(board, x, y):
                    return True
    return False


def legal_moves(position: ChessPosition) -> tuple[ChessMove, ...]:
    moves = []
    for y, row in enumerate(position.board):
        for x, piece in enumerate(row):
            if _color(piece) != position.turn:
                continue
            for tx, ty in _piece_targets(position.board, x, y):
                if position.board[ty][tx].upper() == "K":
                    continue
                move = ChessMove(x, y, tx, ty)
                if not _in_check(_moved(position.board, move), position.turn):
                    moves.append(move)
    return tuple(moves)


def play_move(position: ChessPosition, move: ChessMove) -> ChessPosition:
    if move not in legal_moves(position):
        raise IllegalChessMove("非法着法")
    return ChessPosition(_moved(position.board, move), "black" if position.turn == "red" else "red")


def basic_outcome(position: ChessPosition) -> ChessOutcome | None:
    if legal_moves(position):
        return None
    return ChessOutcome("black" if position.turn == "red" else "red", "checkmate" if _in_check(position.board, position.turn) else "stalemate")


def _unprotected_target(board: tuple[str, ...], x: int, y: int, attacker: str) -> bool:
    """Whether the threatened piece can be immediately recaptured if taken."""
    victim = board[y][x]
    if victim == "." or victim.upper() == "K":
        return False
    if victim.upper() == "P" and (y >= 5 if victim.isupper() else y <= 4):
        return False
    rows = [list(row) for row in board]
    rows[y][x] = "R" if attacker == "red" else "r"
    hypothetical = tuple("".join(row) for row in rows)
    for sy, row in enumerate(board):
        for sx, defender in enumerate(row):
            if (sx, sy) != (x, y) and _color(defender) == _color(victim):
                if (x, y) in _piece_targets(hypothetical, sx, sy):
                    return False
    return True


def _repetition_attack(before: ChessPosition, after: ChessPosition, move: ChessMove) -> str | None:
    if _in_check(after.board, after.turn):
        return "check"
    piece = after.board[move.to_y][move.to_x]
    if piece.upper() in {"K", "P"}:
        return None
    for x, y in _piece_targets(after.board, move.to_x, move.to_y):
        if _unprotected_target(after.board, x, y, before.turn):
            return "chase"
    return None


def adjudicate_repetition(
    history: tuple[ChessPosition, ...], moves: tuple[ChessMove, ...]
) -> ChessOutcome | ChessViolation | None:
    """Flag clear single-sided long check/chase; quiet repetitions never auto-draw.

    Complex 2020-rule exchanges and simultaneous threats require a human ruling;
    this function deliberately returns ``None`` instead of inventing one.
    """
    if len(history) != len(moves) + 1 or len(history) < 7:
        return None
    current = history[-1]
    occurrences = [i for i, position in enumerate(history) if position == current]
    if len(occurrences) < 3:
        return None
    first, second, third = occurrences[-3:]
    cycle_len = third - second
    if cycle_len == 0 or second - first != cycle_len:
        return None
    if history[first:second + 1] != history[second:third + 1]:
        return None
    attacks = {"red": [], "black": []}
    for index in range(second, third):
        attacks[history[index].turn].append(_repetition_attack(history[index], history[index + 1], moves[index]))
    offenders = {
        side: kinds for side, kinds in attacks.items()
        if kinds and all(kind is not None for kind in kinds)
    }
    if len(offenders) == 1:
        side, kinds = next(iter(offenders.items()))
        return ChessViolation(side, "long_check" if all(kind == "check" for kind in kinds) else "long_chase")
    return None
