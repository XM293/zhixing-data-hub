import gzip

import pytest

from zhixing_worker.archive import RawArchive


def test_archive_hash_integrity_and_content_addressed_rewrite(tmp_path):
    archive = RawArchive(tmp_path)
    payload = {"code": 0, "data": [{"id": "synthetic", "name": "合成"}]}
    first = archive.write(payload)
    assert first == archive.write(payload)
    assert archive.read(first.storage_key, first.content_hash) == payload
    (tmp_path / first.storage_key).write_bytes(gzip.compress(b'{}'))
    with pytest.raises(ValueError, match="hash"):
        archive.read(first.storage_key, first.content_hash)


@pytest.mark.parametrize("key", ["../outside.json.gz", "/tmp/raw.json.gz",
                                "C:/outside.json.gz", "ab/../../raw.json.gz",
                                "ab\\raw.json.gz"])
def test_archive_rejects_unsafe_manifest_paths(tmp_path, key):
    with pytest.raises(ValueError, match="path"):
        RawArchive(tmp_path).read(key, "a" * 64)


def test_report_binary_archive_preserves_exact_bytes_and_enforces_limits(tmp_path):
    archive = RawArchive(tmp_path, max_page_bytes=32)
    report = b"synthetic\x00report\xffbytes"
    blob = archive.write_bytes(report)
    assert blob.storage_key.endswith(".bin.gz")
    assert archive.read_bytes(blob.storage_key, blob.content_hash) == report
    assert archive.write_bytes(report) == blob
    with pytest.raises(ValueError, match="too_large"):
        archive.write_bytes(b"x" * 33)
