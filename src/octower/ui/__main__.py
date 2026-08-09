"""Run the offline Phase 7 terminal demonstration with ``python -m octower.ui``."""

from octower.ui.app import ControlTowerApp
from octower.ui.demo import DemoBoardDataSource


def main() -> None:
    ControlTowerApp(DemoBoardDataSource()).run()


if __name__ == "__main__":
    main()
