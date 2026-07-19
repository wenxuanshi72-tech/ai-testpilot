from __future__ import annotations

from plugin.backend.app.config import PluginConfig
from plugin.backend.app.database import PluginDatabase


def main() -> None:
    database = PluginDatabase(str(PluginConfig.as_mapping()["PLUGIN_DATABASE_URL"]))
    database.migrate()
    print("Plugin database migrations applied.")


if __name__ == "__main__":
    main()
