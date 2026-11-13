"""Private-hand guidance using only the viewer's hand and public information."""
from dataclasses import replace

from .mahjong_rules import HandContext, hand_value, is_closed, tile_type, waits


def hand_hints(state: dict, seat: int | None, actions: dict) -> dict:
    if seat not in range(4) or state["phase"] not in {"playing", "reaction"}:
        return {}
    hand = state["hands"][seat]
    melds = state["melds"][seat]
    known = set(hand)
    for row in state["discards"]:
        known.update(item["tile"] for item in row)
    for row in state["melds"]:
        for meld in row:
            known.update(meld["tiles"])
    known.update(state["dead_wall"][i] for i in (4, 6, 8, 10, 12)[:state["kan_count"] + 1])
    own_discards = {tile_type(item["tile"]) for item in state["discards"][seat]}
    context = HandContext(
        riichi=state["riichi"][seat],
        player_wind=27 + (seat - state["dealer"]) % 4,
        round_wind=state["round_wind"],
    )

    def summary(tiles, discarded=None):
        wanted = waits(tiles, melds)
        discarded_types = own_discards | ({tile_type(discarded)} if discarded is not None else set())
        furiten = "discard" if wanted & discarded_types else None
        # A non-riichi temporary furiten clears on the next draw, not on discard.
        if not furiten and state["temporary_furiten"][seat]:
            furiten = "riichi_pass" if context.riichi else "temporary"
        used = {*tiles, *(tile for meld in melds for tile in meld["tiles"])}
        entries = []
        for kind in sorted(wanted):
            candidate = next(tile for tile in range(kind * 4, kind * 4 + 4) if tile not in used)
            completed = [*tiles, candidate]
            ron = hand_value(completed, candidate, melds, context)
            tsumo = hand_value(completed, candidate, melds, replace(context, tsumo=True))
            entries.append({
                "type": kind,
                "unseen": sum(tile not in known for tile in range(kind * 4, kind * 4 + 4)),
                "ron_reason": furiten or ron.error,
                "tsumo_reason": tsumo.error,
            })
            # The ordinary-hand preview must not override a legal houtei/chankan response.
            if discarded is None and actions.get("ron") and kind == tile_type(state["pending"]["tile"]):
                entries[-1]["ron_now"] = True
        return {"waits": entries, "furiten": furiten, "closed": is_closed(melds)}

    discards = {}
    for tile in actions.get("discard", []):
        reduced = list(hand)
        reduced.remove(tile)
        value = summary(reduced, tile)
        if value["waits"]:
            discards[str(tile)] = value
    return {"current": summary(hand) if len(hand) % 3 == 1 else None, "discards": discards}
