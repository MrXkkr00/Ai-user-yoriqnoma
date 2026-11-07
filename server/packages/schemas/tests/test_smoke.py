from importlib.metadata import version

import yoriqnoma_schemas


def test_package_imports_and_version_matches_metadata() -> None:
    assert yoriqnoma_schemas.__version__ == version("yoriqnoma-schemas")
