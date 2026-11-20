from __future__ import annotations

import unittest

from schemaorg import constants
from schemaorg.layout import InputLayout, StatsLayout


class PublicStatsDataTests(unittest.TestCase):
    """Public statistics data files must use https:// URLs."""

    layout: StatsLayout

    @classmethod
    def setUpClass(cls) -> None:
        cls.layout = StatsLayout(InputLayout(constants.PROJECT_ROOT))

    def test_stats_csv_use_https(self) -> None:
        failures: list[str] = []
        for provider in self.layout.providers():
            for epoch, file_path in self.layout.epochs(provider, ext="csv").items():
                for row in self.layout._read_csv(file_path):
                    name = row.get("Name", "")
                    if not name.startswith("https://"):
                        failures.append(
                            f" - Provider: {provider}, Epoch: {epoch.strftime('%Y_%m')}"
                        )
                        break

        if failures:
            joined = "\n".join(failures)
            self.fail(f"Statistics CSV data contains non-https URLs in:\n{joined}")

    def test_stats_json_use_https(self) -> None:
        failures: list[str] = []
        for provider in self.layout.providers():
            for epoch, file_path in self.layout.epochs(provider, ext="json").items():
                for entry in self.layout._read_json(file_path):
                    name = entry.get("Name", "")
                    if not name.startswith("https://"):
                        failures.append(
                            f" - Provider: {provider}, Epoch: {epoch.strftime('%Y_%m')}"
                        )
                        break

        if failures:
            joined = "\n".join(failures)
            self.fail(f"Statistics JSON data contains non-https URLs in:\n{joined}")


if __name__ == "__main__":
    unittest.main()
