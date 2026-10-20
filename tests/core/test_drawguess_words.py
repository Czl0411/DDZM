import pytest

from dzmm_bot.core.drawguess_words import WORDS, normalize_guess, validate_candidates, word_matches


def test_words_are_unique_and_normalized():
    assert len(WORDS) >= 100
    ids = [word.id for word in WORDS]
    answers = [normalize_guess(word.answer) for word in WORDS]
    assert len(ids) == len(set(ids))
    assert len(answers) == len(set(answers))
    assert all(answer and answer == normalize_guess(answer) for answer in answers)


def test_normalization_and_explicit_aliases_only():
    assert normalize_guess("  ＡＢＣ  ") == "abc"
    word = next(word for word in WORDS if word.answer == "自行车")
    assert word_matches(word.id, " 自行车 ")
    assert word_matches(word.id, "脚踏车")
    assert not word_matches(word.id, "我画的是自行车")
    assert not word_matches(word.id, "单车")


def test_candidate_sets_reject_duplicates_and_used_words():
    ids = [word.id for word in WORDS]
    assert validate_candidates(ids[:3], set()) == ids[:3]
    with pytest.raises(ValueError, match="三个"):
        validate_candidates(ids[:2], set())
    with pytest.raises(ValueError, match="重复"):
        validate_candidates([ids[0], ids[0], ids[1]], set())
    with pytest.raises(ValueError, match="使用"):
        validate_candidates(ids[:3], {ids[1]})
    used = set()
    for offset in range(0, 48, 3):
        chosen = validate_candidates(ids[offset:offset + 3], used)
        used.add(chosen[0])
    assert len(used) == 16
