# config.py

import os
from dotenv import load_dotenv

# Load environment variables from the .env file into the system environment
load_dotenv()

class Config:
    """
    Configuration class for the Flask application.
    Manages application settings, including security keys and database connections.
    """

    # Secret key used by Flask to secure sessions and other security-related needs.
    # Initially set to a hard-coded string, then overridden by an environment variable if available.
    SECRET_KEY = "some_super_secret_string"
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key')

    # SQLAlchemy Database URI for connecting to the MySQL database.
    # Constructs the URI using environment variables for flexibility and security.
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )

    # Disables the SQLAlchemy event system to save resources.
    # Setting to True to suppress modification tracking, which is unnecessary in this context.
    SQLALCHEMY_TRACK_MODIFICATIONS = True
