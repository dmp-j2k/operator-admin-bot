from dotenv import load_dotenv

from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    ADMIN_TOKEN: str
    OPERATOR_TOKEN: str
    ADMINS: str
    ADMINS_1: str
    SERVICE_PORT: int
    SERVICE_TOKEN: str
    WEB_APP_URL: str
    REDIS_URL: str
    S3_ACCESS_KEY_ID: str
    S3_SECRET_ACCESS_KEY: str
    S3_BUCKET_NAME: str
    S3_ENDPOINT_URL: str


settings = Settings() # type: ignore
