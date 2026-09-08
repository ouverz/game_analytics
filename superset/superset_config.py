"""Local-only Superset configuration for the assignment dashboard."""

import os


SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = "sqlite:////app/superset_home/superset.db"

# This deployment is bound to localhost and is not intended for production.
TALISMAN_ENABLED = False
CONTENT_SECURITY_POLICY_WARNING = False
WTF_CSRF_ENABLED = True
PREVENT_UNSAFE_DB_CONNECTIONS = False

# Keep local dashboard queries responsive without adding Redis or workers.
CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300}
DATA_CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300}

# One restrained, accessible palette shared by the loading and FTUE dashboards.
# Sequential blues/teals describe the player journey; amber and coral are kept
# available for friction and failure rather than used as decorative categories.
EXTRA_CATEGORICAL_COLOR_SCHEMES = [
    {
        "id": "technicalLaunch",
        "label": "Technical launch",
        "description": "Launch-health dashboard palette",
        "colors": [
            "#176B87",
            "#18A7A0",
            "#5BC0BE",
            "#8FD3CF",
            "#F2B134",
            "#D95D5D",
        ],
    }
]
