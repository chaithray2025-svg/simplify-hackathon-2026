"""
tests/conftest.py

Pytest auto-discovers and runs this before collecting tests in this folder.

test_trend_detection.py does `from trend_detection import ...` with no
package prefix, which only works if trend_detection.py's folder is on
sys.path. Since trend_detection.py lives in person2_trend_advice/ (a
sibling folder to tests/, not inside it), this file adds that folder to
sys.path so the import resolves — without moving any source files or
turning person2_trend_advice/ into a package.
"""

import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TESTS_DIR)
_PERSON2_DIR = os.path.join(_REPO_ROOT, "person2_trend_advice")

if os.path.isdir(_PERSON2_DIR) and _PERSON2_DIR not in sys.path:
    sys.path.insert(0, _PERSON2_DIR)