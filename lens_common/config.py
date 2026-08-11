from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gateway_url: str = "https://aws-us-east-1.hevlayer.com"
    gateway_api_key: str = ""
    namespace: str = "lens-commons-quality"
    timeout_seconds: float = 180.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_prefix="LAYER_",
    )
