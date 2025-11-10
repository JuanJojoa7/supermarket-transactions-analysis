from app.analytics.ingestion import repo
from app.analytics.segmentation import kmeans_segments


def test_kmeans_default():
    repo.refresh()
    result = kmeans_segments(k=4)
    assert result['k'] == 4
    assert len(result['counts']) == 4
    assert len(result['centers']) == 4
    assert 'descriptions' in result


def test_kmeans_small_k():
    result = kmeans_segments(k=2)
    assert result['k'] == 2
    assert len(result['counts']) == 2
