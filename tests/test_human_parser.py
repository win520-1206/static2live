"""Explicit synthetic labels test mask algebra, not real-model accuracy."""
import numpy as np
import pytest
from static2live.human_parser import LABELS, ModelHumanParsing, human_regions, prepare_human_parser
from static2live.storage import write_json
from static2live.segmentation import MODEL_FILES


def test_missing_parser_never_downloads(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('inference must not download')
    monkeypatch.setattr('static2live.human_parser.download_snapshot', forbidden)
    with pytest.raises(ValueError, match='human-parsing'):
        ModelHumanParsing(tmp_path).predict(None)


def test_wrong_model_identity_rejected_before_inference(tmp_path):
    folder = tmp_path / 'fashn-human-parser'
    folder.mkdir()
    write_json(folder / 'static2live-model.json', {'model_id': 'nvidia/segformer-b0-finetuned-ade-512-512',
                                                'files': {n: 'bad' for n in [*MODEL_FILES, 'LICENSE.txt']}})
    with pytest.raises(ValueError, match='身份'):
        ModelHumanParsing(tmp_path).predict(None)


def test_tampered_model_rejected_before_inference(tmp_path):
    folder = tmp_path / 'fashn-human-parser'
    folder.mkdir()
    (folder / 'config.json').write_text('{}', encoding='utf8')
    write_json(folder / 'static2live-model.json', {'model_id': 'fashn-ai/fashn-human-parser',
                                                'files': {n: '0' * 64 for n in [*MODEL_FILES, 'LICENSE.txt']}})
    with pytest.raises(ValueError, match='哈希'):
        ModelHumanParsing(tmp_path).predict(None)


def test_prepare_requires_explicit_license(tmp_path, monkeypatch):
    monkeypatch.setattr('static2live.human_parser.download_snapshot', lambda *a, **k: pytest.fail('download before consent'))
    with pytest.raises(ValueError, match='accept-model-license'):
        prepare_human_parser(tmp_path)


def test_protected_union_and_no_overlap():
    labels = np.full((32, 48), 2, dtype=np.uint8)
    labels[8:16, 18:26] = 1
    labels[18:22, 18:22] = 13
    labels[23:25, 30:32] = 17
    labels[26:] = 3
    original = labels.copy()
    masks, records = human_regions(labels, dict(enumerate(LABELS)), 2)
    assert np.array_equal(labels, original)
    protected = np.asarray(masks['protected'])
    assert protected[7, 17] == 255
    assert protected[18, 18] == 255 and protected[23, 30] == 255
    assert not np.any(np.asarray(masks['hair']) & protected)
    assert not np.any(np.asarray(masks['cloth']) & protected)
    assert records['protected']['guard_px'] == 2
    assert np.asarray(masks['cloth'])[31, 0] == 255
    assert all(m.size == (48, 32) for m in masks.values())


def test_no_person_does_not_fabricate_masks():
    masks, _ = human_regions(np.zeros((8, 12), dtype='uint8'), dict(enumerate(LABELS)))
    assert all(not np.asarray(mask).any() for mask in masks.values())


def test_enclosed_background_guard_keeps_exterior_and_raw_labels():
    labels = np.zeros((16, 20), dtype='uint8')
    labels[2:14, 4:16] = 2
    labels[6:9, 8:11] = 0  # enclosed false-background island
    labels[3:5, 4:7] = 0  # connected to exterior, must remain background
    original = labels.copy()
    masks, records = human_regions(labels, dict(enumerate(LABELS)), 0)
    assert np.array_equal(labels, original)
    assert np.asarray(masks['person'])[7, 9] == 255
    assert np.asarray(masks['protected'])[7, 9] == 255
    assert np.asarray(masks['person'])[3, 4] == 0
    assert np.asarray(masks['protected'])[3, 4] == 0
    assert records['protected']['enclosed_background_guard_px'] == 9


@pytest.mark.parametrize('bad', [np.zeros((8, 8), dtype='float32'), np.zeros(8, dtype='uint8'), np.zeros((0, 0), dtype='uint8'), np.full((8, 8), 99)])
def test_invalid_labels_rejected(bad):
    with pytest.raises(ValueError):
        human_regions(bad, dict(enumerate(LABELS)))


def test_missing_semantic_classes_rejected():
    with pytest.raises(ValueError, match='类别表'):
        human_regions(np.zeros((4, 4), dtype='uint8'), {0: 'background'})


@pytest.mark.parametrize('margin', [-1, 33, 1.5, True])
def test_invalid_guard_rejected(margin):
    with pytest.raises(ValueError, match='保护区'):
        human_regions(np.zeros((4, 4), dtype='uint8'), dict(enumerate(LABELS)), margin)
