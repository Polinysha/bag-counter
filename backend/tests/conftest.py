"""
Runs before any test module is collected (pytest always imports
conftest.py first). Points BC_DATA_DIR at a throwaway temp directory
*before* anything imports app.config, so `settings.data_dir` never
resolves to the real "/data" (the production/Docker mount path) - on
a Linux CI runner (or any non-root Linux/Mac user), creating a folder
at the filesystem root raises PermissionError; the same code happens
to "work" on Windows only because "/data" there resolves to a
writable drive-relative path, which masked this in local testing.
"""

import os
import tempfile

os.environ.setdefault("BC_DATA_DIR", tempfile.mkdtemp(prefix="bag-counter-tests-"))
