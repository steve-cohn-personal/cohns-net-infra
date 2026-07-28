from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

_settings = get_settings()

# Keyed by client IP. Behind CloudFront/ALB the real client is in X-Forwarded-For;
# get_remote_address reads it when the app trusts the proxy (uvicorn --proxy-headers).
limiter = Limiter(key_func=get_remote_address, storage_uri=_settings.rate_limit_storage)
