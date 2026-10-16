from importlib.metadata import version

import unbolt


def test_version_matches_installed_metadata():
    assert unbolt.__version__ == version("unbolt")
