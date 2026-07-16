"""Keep local secrets and developer settings out of the test environment."""

import os

os.environ["APP_ENV"] = "test"
os.environ["API_AUTH_TOKEN"] = ""
os.environ["ALLOWED_HOSTS"] = "*"
