from importlib.metadata import version

import yoriqnoma_scanner


def test_package_imports_and_version_matches_metadata() -> None:
    assert yoriqnoma_scanner.__version__ == version("yoriqnoma-scanner")
