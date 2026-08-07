"""Tests for the persistent blacklist file handling."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from winget_tui import blacklist


class BlacklistFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._path = Path(self._tmp.name) / "blacklist.txt"
        patcher = mock.patch.object(blacklist, "blacklist_path", return_value=self._path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_add_and_load(self) -> None:
        self.assertTrue(blacklist.add("alpha.pkg"))
        self.assertFalse(blacklist.add("alpha.pkg"))  # already present
        self.assertEqual(blacklist.load_blacklist(), {"alpha.pkg"})

    def test_add_after_no_trailing_newline_does_not_glue(self) -> None:
        """Regression: appending to a file lacking a trailing newline must not
        glue the new ID onto the last line."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("alpha.pkg", encoding="utf-8")  # no trailing \n
        blacklist.add("beta.pkg")
        self.assertEqual(
            blacklist.load_blacklist(), {"alpha.pkg", "beta.pkg"}
        )

    def test_remove_preserves_comments_and_order(self) -> None:
        """Regression: rewriting on remove must keep user comments, blank
        lines, and ordering — only the removed ID's line disappears."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            "# never touch this\n\nalpha.pkg\nbeta.pkg\n# keep me\n",
            encoding="utf-8",
        )
        self.assertTrue(blacklist.remove("alpha.pkg"))
        self.assertEqual(blacklist.load_blacklist(), {"beta.pkg"})
        content = self._path.read_text(encoding="utf-8")
        self.assertIn("# never touch this", content)
        self.assertIn("# keep me", content)
        self.assertNotIn("alpha.pkg", content)
        self.assertLess(content.index("# never touch this"), content.index("beta.pkg"))
        self.assertLess(content.index("beta.pkg"), content.index("# keep me"))

    def test_remove_absent_id_is_noop(self) -> None:
        self.assertFalse(blacklist.remove("nope.pkg"))
        self.assertFalse(self._path.exists())

    def test_load_tolerates_missing_file(self) -> None:
        self.assertEqual(blacklist.load_blacklist(), set())


if __name__ == "__main__":
    unittest.main()
