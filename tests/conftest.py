import os

os.environ.setdefault("CONSTRUCTION_OS_SECRET_KEY", "test-secret-key-that-is-at-least-32-chars")
os.environ.setdefault(
    "CONSTRUCTION_OS_DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test"
)
os.environ.setdefault("CONSTRUCTION_OS_REDIS_URL", "redis://localhost:6379/15")
