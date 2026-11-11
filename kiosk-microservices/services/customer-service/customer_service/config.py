from kiosk_common.config import ServiceConfig


class Config(ServiceConfig):
    service_name: str = "customer-service"
    # Secret (>= 32 chars) for customer PIN hashes; else pin_pepper.key next to the data dir.
    pin_pepper: str = ""
