import numpy as np
import pytest
from PIL import Image, ImageDraw
from static2live.sway import build_sway_weight, sway_displacement, validate_sway


def fixture_masks():
    hair = Image.new('L', (512, 512))
    ImageDraw.Draw(hair).rectangle((100, 50, 350, 430), fill=255)
    protected = Image.new('L', hair.size)
    ImageDraw.Draw(protected).rectangle((240, 100, 360, 300), fill=255)
    return hair, protected


def test_local_tip_weights_protect_and_anchor():
    hair, protected = fixture_masks()
    before = hair.tobytes(), protected.tobytes()
    weight = build_sway_weight(hair, protected, 3)
    w = np.asarray(weight)
    assert w[420, 102] > 150
    assert w[60, 102] == 0
    assert w[400, 200] == 0  # dense hair interior does not move as one slab
    assert not np.any(w[np.asarray(protected) > 0])
    assert w[420, 97] > 0  # bounded inverse-sampling halo outside silhouette
    assert w[420, 70] == 0
    assert before == (hair.tobytes(), protected.tobytes())


def test_displacement_bound_period_and_zero():
    hair, protected = fixture_masks()
    weight = build_sway_weight(hair, protected, 3)
    p = dict(enabled=True, amplitude_px=3, period_seconds=5, phase=.3)
    a = sway_displacement(weight, .7, p)
    b = sway_displacement(weight, 5.7, p)
    assert np.allclose(a, b)
    assert np.max(np.abs(a)) <= 3
    assert not np.any(a[np.asarray(protected) > 0])
    assert not np.array_equal(a, sway_displacement(weight, 2, p))
    for update in ({'enabled': False}, {'amplitude_px': 0}):
        assert not sway_displacement(weight, 2, {**p, **update}).any()


def test_empty_and_zero_masks():
    hair, protected = fixture_masks()
    assert not np.asarray(build_sway_weight(hair, protected, 0)).any()
    assert not np.asarray(build_sway_weight(Image.new('L', hair.size), protected, 2)).any()


def test_upper_side_tips_have_gradual_weight_without_moving_roots_or_mass():
    hair, _ = fixture_masks()
    protected = Image.new('L', hair.size)
    w = np.asarray(build_sway_weight(hair, protected, 2))
    # 35% down the selected mask: visible contribution instead of a nearly
    # zero squared ramp, without changing amplitude or moving the whole image.
    assert 40 <= w[183, 102] <= 70
    assert w[183, 102] < w[300, 102] < w[420, 102]
    assert not w[50:100].any()
    assert w[183, 200] == 0
    assert w[183, 70] == 0


def test_tip_edge_v2_promotes_side_tips_not_roots_face_or_interior():
    hair, protected = fixture_masks()
    old=np.asarray(build_sway_weight(hair,protected,2.5))
    new=np.asarray(build_sway_weight(hair,protected,2.5,policy='tip-edge-v2'))
    assert new[183,102] > old[183,102]*2
    assert new[260,102] >= 250
    assert not new[50:100].any()
    assert new[183,200] == 0
    assert not new[np.asarray(protected)>0].any()
    assert new[183,70] == 0
    p=dict(enabled=True,amplitude_px=2.5,period_seconds=5.5,phase=.3)
    assert np.max(np.abs(sway_displacement(Image.fromarray(new),1,p)))<=2.5
    with pytest.raises(ValueError):
        build_sway_weight(hair,protected,2.5,policy='unknown')


@pytest.mark.parametrize('update', [{'amplitude_px': 5}, {'amplitude_px': float('nan')},
                                  {'period_seconds': 0}, {'phase': -1}, {'enabled': 1}])
def test_invalid_sway_rejected(update):
    with pytest.raises(ValueError):
        validate_sway(dict(enabled=True, amplitude_px=3, period_seconds=5, phase=.3, **{}) | update, (512, 512))
