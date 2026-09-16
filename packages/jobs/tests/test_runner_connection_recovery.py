from threading import Event
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import InterfaceError, OperationalError

from zhixing_jobs.runner import WorkerRunner


@pytest.mark.parametrize("error_type", [OperationalError, InterfaceError])
def test_connection_recovery_is_bounded_resets_and_redacts(error_type, caplog):
    stop = Mock()
    stop.is_set.side_effect = [False] * 9 + [True]
    runner = WorkerRunner(Mock(), {}, worker_id="synthetic", poll_seconds=0.5)
    error = error_type("synthetic-private-sql", {}, Exception("synthetic-private-credential"))
    runner.run_once = Mock(side_effect=[error] * 6 + [None, error, None])
    runner.run_forever(stop)
    assert [call.args[0] for call in stop.wait.call_args_list] == [
        1, 2, 4, 8, 16, 30, 0.5, 1, 0.5,
    ]
    assert "synthetic-private" not in caplog.text


def test_programming_error_is_not_hidden():
    runner = WorkerRunner(Mock(), {}, worker_id="synthetic")
    runner.run_once = Mock(side_effect=ValueError("invalid configuration"))
    stop = Mock()
    stop.is_set.return_value = False
    with pytest.raises(ValueError):
        runner.run_forever(stop)
    stop.wait.assert_not_called()


def test_shutdown_during_reconnect_does_not_poll_again():
    stop = Event()
    runner = WorkerRunner(Mock(), {}, worker_id="synthetic")
    runner.run_once = Mock(side_effect=OperationalError("", {}, Exception()))
    wait = Mock(side_effect=lambda _: stop.set())
    stop.wait = wait
    runner.run_forever(stop)
    runner.run_once.assert_called_once()
    wait.assert_called_once_with(1)
