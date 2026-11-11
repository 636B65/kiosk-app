from kiosk_common.config import ServiceConfig


class Config(ServiceConfig):
    service_name: str = "system-service"
    # Databases to back up: "name=url,name=url" (postgresql:// or sqlite:///).
    backup_database_urls: str = ""
    backup_dir: str = ""

    @property
    def backup_path(self) -> str:
        return self.backup_dir or f"{self.data_dir}/backups"

    @property
    def databases(self) -> dict[str, str]:
        result = {}
        for entry in self.backup_database_urls.split(","):
            if "=" in entry:
                name, url = entry.split("=", 1)
                result[name.strip()] = url.strip()
        return result
