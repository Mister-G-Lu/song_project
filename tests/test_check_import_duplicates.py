import pytest
from scripts.check_import_duplicates import check, key


def row(artist, song, rating='70'):
    return dict(artist=artist, song=song, title=f'{song} ({artist})', rating=rating)


def test_original_lower_rating_wins():
    old = row('Chain smokers', 'SELFIE', '1')
    new = row('The Chainsmokers', '#SELFIE', '10')
    removals, _ = check([old], [old, new])
    assert removals[0]['remove_index'] == 1
    assert removals[0]['kept']['rating'] == '1'


def test_accents_and_spaces():
    assert key(row('Beyoncé', 'Crazy in Love')) == key(row('Beyonce', 'Crazy in Love'))
    assert key(row('One Republic', 'If I Lose Myself')) == key(row('OneRepublic', 'If I Lose Myself'))


def test_versions_numbers_and_unicode_not_discarded():
    old = row('Artist', 'Song')
    for title in ['Song (Live)', 'Song (Remix)', 'Song / B-side', 'Song 1979']:
        assert check([old], [old, row('Artist', title)])[0] == []
    assert key(row('TUYU', 'やっぱり雨は降るんだね')) != key(row('TUYU', 'アサガオの散る頃に'))
    assert key(row('', 'Song')) is None


def test_split_single_review_only():
    old = row('Artist', 'Song')
    removals, review = check([old], [old, row('Artist', 'Song / B-side')])
    assert not removals
    assert review == [[0, 1]]


def test_original_duplicates_and_new_only_groups_not_removed():
    old = row('Artist', 'Song')
    assert not check([old, old], [old, old])[0]
    assert not check([], [old, old])[0]


def test_changed_baseline_rejected():
    with pytest.raises(ValueError):
        check([row('Artist', 'Song', '80')], [row('Artist', 'Song', '70')])
