"""Tests for the locale-independent ``winget upgrade`` table parser.

The parser is the riskiest code in the package (it must survive winget's
locale-varying human table), so the fixtures below pin down the observed
variants: spaced dash runs (English default), a single continuous dash run
(French), and the trailing summary line that must be dropped.
"""

from __future__ import annotations

import unittest

from winget_tui.winget import parse_upgrade_output


# Real winget sizes each column to fit its longest value (header included),
# so header word positions always align with data column starts. The fixtures
# below reproduce that: values are left-padded to width-derived starts.
COLUMN_WIDTHS = (60, 40, 12, 12, 10)


def _line(name: str, id_: str, version: str, available: str, source: str) -> str:
    parts = [
        name.ljust(COLUMN_WIDTHS[0]),
        id_.ljust(COLUMN_WIDTHS[1]),
        version.ljust(COLUMN_WIDTHS[2]),
        available.ljust(COLUMN_WIDTHS[3]),
        source.ljust(COLUMN_WIDTHS[4]),
    ]
    return "".join(parts).rstrip()


def _spaced_separator() -> str:
    """English-style separator: dash runs aligned per column, spaces between."""
    return " ".join("-" * width for width in COLUMN_WIDTHS)


ENGLISH_HEADER = _line("Name", "Id", "Version", "Available", "Source")


class EnglishTableTest(unittest.TestCase):
    def test_parses_rows_and_drops_summary_line(self) -> None:
        stdout = "\n".join(
            [
                ENGLISH_HEADER,
                _spaced_separator(),
                _line(
                    "Eclipse Temurin JDK avec Hotspot 21.0.11 (x64)",
                    "EclipseAdoptium.Temurin.21.JDK",
                    "21.0.11",
                    "21.0.12",
                    "winget",
                ),
                _line("uv", "astral-sh.uv", "0.12.0", "0.12.1", "winget"),
                "Found 2 packages with an update available.",
            ]
        )
        packages = parse_upgrade_output(stdout)
        self.assertEqual(len(packages), 2)
        self.assertEqual(packages[0].name, "Eclipse Temurin JDK avec Hotspot 21.0.11 (x64)")
        self.assertEqual(packages[0].id, "EclipseAdoptium.Temurin.21.JDK")
        self.assertEqual(packages[0].version, "21.0.11")
        self.assertEqual(packages[0].available, "21.0.12")
        self.assertEqual(packages[0].source, "winget")
        self.assertEqual(packages[1].id, "astral-sh.uv")

    def test_spaced_separator_is_detected(self) -> None:
        """Regression: the English separator has spaces between dash runs; it
        must still be recognized as the separator row."""
        stdout = "\n".join(
            [
                ENGLISH_HEADER,
                _spaced_separator(),
                _line("7-Zip 24.09 (x64)", "7-Zip.7-Zip", "24.09", "24.10", "winget"),
            ]
        )
        self.assertEqual(len(parse_upgrade_output(stdout)), 1)

    def test_no_separator_means_no_updates(self) -> None:
        stdout = "No package has an available update.\n"
        self.assertEqual(parse_upgrade_output(stdout), [])

    def test_empty_output(self) -> None:
        self.assertEqual(parse_upgrade_output(""), [])


class FrenchTableTest(unittest.TestCase):
    def test_parses_continuous_dash_run_separator(self) -> None:
        header = _line("Nom", "ID", "Version", "Disponible", "Source")
        separator = "-" * 100  # French winget prints one continuous dash run
        stdout = "\n".join(
            [
                header,
                separator,
                _line(
                    "Eclipse Temurin JDK avec Hotspot 21.0.11 (x64)",
                    "EclipseAdoptium.Temurin.21.JDK",
                    "21.0.11",
                    "21.0.12",
                    "winget",
                ),
                "18 mises a niveau disponibles.",
            ]
        )
        packages = parse_upgrade_output(stdout)
        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0].id, "EclipseAdoptium.Temurin.21.JDK")

    def test_degenerate_header_is_safe(self) -> None:
        # A header whose whitespace-delimited words number < 5 (e.g. a
        # single-word title) falls back to dash-run boundaries; either way the
        # parse must not crash.
        header = _line("Colonne unique", "", "", "", "")
        separator = "-" * 100
        stdout = "\n".join(
            [
                header,
                separator,
                _line("alpha", "alpha.pkg", "1.0", "2.0", "winget"),
            ]
        )
        self.assertIsInstance(parse_upgrade_output(stdout), list)


class IdSanityTest(unittest.TestCase):
    def test_whitespace_in_id_field_is_dropped(self) -> None:
        """Summary/title lines whose ID slice is blank or whitespace are not
        packages."""
        stdout = "\n".join(
            [
                ENGLISH_HEADER,
                _spaced_separator(),
                _line("real", "real.pkg", "1.0", "2.0", "winget"),
                "   ",
                "Some trailer line",
            ]
        )
        packages = parse_upgrade_output(stdout)
        self.assertEqual([p.id for p in packages], ["real.pkg"])


if __name__ == "__main__":
    unittest.main()
