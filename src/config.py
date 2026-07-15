from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Ozon
    ozon_category_url: str = "https://www.ozon.ru/category/smartfony-15502/"
    target_product_count: int = 10_000
    demo_mode: bool = False
    demo_target_count: int = 100
    request_delay_ms: int = 800
    parser_mock: bool = False

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    llm_batch_size: int = 50
    llm_mock: bool = False

    # AmoCRM
    amocrm_subdomain: str = ""
    amocrm_access_token: str = ""
    amocrm_refresh_token: str = ""
    amocrm_client_id: str = ""
    amocrm_client_secret: str = ""
    amocrm_redirect_uri: str = "https://example.com"
    crm_mock: bool = False
    crm_task_limit: int = 10

    # Storage
    data_dir: Path = Field(default=Path("data"))
    checkpoint_dir: Path = Field(default=Path("data/checkpoints"))

    @property
    def effective_target_count(self) -> int:
        return self.demo_target_count if self.demo_mode else self.target_product_count

    @property
    def ozon_api_base(self) -> str:
        return "https://www.ozon.ru/api/composer-api.bx/page/json/v2"

    @property
    def amocrm_base_url(self) -> str:
        return f"https://{self.amocrm_subdomain}.amocrm.ru"


def get_settings() -> Settings:
    return Settings()
