from pathlib import Path

from unbolt.overrides import Overrides, apply_override, load_overrides, save_overrides


def test_loading_a_missing_file_returns_empty_overrides(tmp_path: Path) -> None:
    result = load_overrides(tmp_path / "does-not-exist.json")
    assert result == Overrides()


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    overrides = apply_override(
        Overrides(), "REC.AGE", "uint16", "fits and matches semantics", valid_choices=["uint16"]
    )

    save_overrides(overrides, path)
    restored = load_overrides(path)

    assert restored == overrides


def test_saved_file_is_stable_sorted_json(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    overrides = apply_override(Overrides(), "REC.A", "int16", "x", valid_choices=["int16"])

    save_overrides(overrides, path)
    first = path.read_text()
    save_overrides(overrides, path)
    second = path.read_text()

    assert first == second
