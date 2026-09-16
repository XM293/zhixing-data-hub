import gzip
import json

from zhixing_api.connectors.lingxing.raw_archive import RawArchive


def test_raw_archive_content_addressed(tmp_path):
    result = RawArchive(tmp_path).put({"店铺": "合成", "items": [1]})
    path = tmp_path / result["storage_key"]
    assert path.exists()
    assert json.loads(gzip.open(path, "rb").read()) == {"店铺": "合成", "items": [1]}
