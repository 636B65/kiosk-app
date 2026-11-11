from kiosk_common.config import ServiceConfig


class Config(ServiceConfig):
    service_name: str = "auth-service"
    # Seed password for the first "admin" user (min 8 chars, else a random one is printed).
    admin_password: str = ""
