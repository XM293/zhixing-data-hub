import pytest

from zhixing_worker.lingxing_sync import Lease


def test_lease_acquire_and_expire():
    lease = Lease(60)
    assert lease.is_expired
    lease.acquire()
    assert not lease.is_expired
    lease.expires_at = lease.expires_at.replace(year=2000)
    with pytest.raises(RuntimeError, match="lease_expired"):
        lease.renew()
