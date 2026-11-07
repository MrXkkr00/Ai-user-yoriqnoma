from importlib.metadata import version

import yoriqnoma_core


def test_package_imports_and_version_matches_metadata() -> None:
    assert yoriqnoma_core.__version__ == version("yoriqnoma-core")
