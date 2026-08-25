"""Working storage.

The keys are ours today. The moment one is echoed back from a client, the
validation in ``LocalTempStorage`` is the only thing standing between a
storage key and an arbitrary file write — so it is tested as if that day has
already arrived.
"""
from __future__ import annotations

import pytest

from app.storage import export_key, prompt_key, recording_key
from app.storage.local import LocalTempStorage


@pytest.fixture
def storage(tmp_path):
    return LocalTempStorage(root=tmp_path)


def test_a_recording_round_trips(storage):
    key = recording_key("stmarys", "attempt-1", "response-1")
    stored = storage.put(key, b"fake-audio-bytes", "audio/webm")

    assert stored.bytes == 16
    assert storage.exists(key)
    assert storage.get(key) == b"fake-audio-bytes"
    assert storage.size(key) == 16

    assert storage.delete(key) is True
    assert storage.delete(key) is False
    assert not storage.exists(key)


def test_keys_are_namespaced_by_institution(storage):
    a = recording_key("stmarys", "att", "res")
    b = recording_key("vignan", "att", "res")
    assert a != b
    assert a.startswith("recordings/stmarys/")
    assert b.startswith("recordings/vignan/")


@pytest.mark.parametrize("key", [
    "../secrets.env",
    "recordings/../../etc/passwd",
    "/absolute/path.webm",
    "C:/Windows/System32/config",
    "",
    "recordings/stmarys/../../../escape.webm",
])
def test_a_key_cannot_escape_the_media_root(storage, key):
    with pytest.raises(ValueError):
        storage.put(key, b"x")
    with pytest.raises(ValueError):
        storage.get(key)


def test_writing_creates_the_folder_tree(storage, tmp_path):
    storage.put(prompt_key("item-9"), b"mp3")
    assert (tmp_path / "prompts" / "item-9.mp3").exists()

    storage.put(export_key("stmarys", "cohort.csv"), b"a,b\n")
    assert (tmp_path / "exports" / "stmarys" / "cohort.csv").exists()


def test_the_provider_satisfies_the_storage_contract(storage):
    from app.storage.base import StorageProvider
    assert isinstance(storage, StorageProvider)
    assert storage.provider_key == "local_tmp"
    assert storage.version


def test_purging_a_prefix_removes_an_institutions_recordings(storage, tmp_path):
    """Offboarding has to take the audio with it (PLAT-01).

    Dropping the schema alone leaves every recording on disk with no row
    pointing at it — unreachable through the product and entirely present on
    the filesystem. That is not what "we deleted your data" means.
    """
    for i in range(3):
        storage.put(recording_key("leaving", f"attempt-{i}", "r1"), b"audio")
    storage.put(export_key("leaving", "cohort.csv"), b"a,b\n")
    keeper = recording_key("staying", "attempt-1", "r1")
    storage.put(keeper, b"audio")

    removed = storage.purge_prefix("recordings/leaving")

    assert removed == 3
    assert not (tmp_path / "recordings" / "leaving").exists()
    assert storage.exists(keeper), "the other institution must be untouched"
    assert storage.exists(export_key("leaving", "cohort.csv")), "exports are a separate prefix"


def test_purging_a_prefix_that_does_not_exist_is_not_an_error(storage):
    assert storage.purge_prefix("recordings/never-existed") == 0


@pytest.mark.parametrize("prefix", ["..", "recordings/../..", "/", "C:/Windows"])
def test_a_prefix_cannot_escape_the_media_root(storage, prefix):
    """A purge that could climb out would empty the media root."""
    with pytest.raises(ValueError):
        storage.purge_prefix(prefix)
