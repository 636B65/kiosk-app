from kiosk_common.config import ServiceConfig


class Config(ServiceConfig):
    service_name: str = "catalog-service"
    # Product images (a persistent volume in Kubernetes).
    images_dir: str = ""
    seed_demo_data: bool = True

    @property
    def images_path(self) -> str:
        return self.images_dir or f"{self.data_dir}/product_images"
