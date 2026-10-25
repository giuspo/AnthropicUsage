"""Test application versioning and format."""

import re
from claude_usage import __version__, __version_info__


def test_version_format():
    """Validates major.minor.compilation format."""
    assert len(__version_info__) == 3
    major, minor, compilation = __version_info__
    assert isinstance(major, int) and major >= 1
    assert isinstance(minor, int) and minor >= 0
    assert isinstance(compilation, int) and compilation >= 0

    assert __version__ == f"{major}.{minor}.{compilation}"
    assert re.match(r"^\d+\.\d+\.\d+$", __version__)
