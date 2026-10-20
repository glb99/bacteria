import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("PROJECT_NAME", "bacteria")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/bacteria")
os.environ.setdefault("FIRST_SUPERUSER", "admin@example.com")
os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "password")
