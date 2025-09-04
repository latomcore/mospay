from setuptools import setup, find_packages

setup(
    name="mospay",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "Flask==3.0.0",
        "psycopg2-binary==2.8.6",
        "Flask-SQLAlchemy==3.1.1",
        "Flask-JWT-Extended==4.6.0",
        "Flask-Bcrypt==1.0.1",
        "Flask-CORS==4.0.0",
        "python-dotenv==1.0.0",
        "cryptography==42.0.5",
        "requests==2.31.0",
        "gunicorn==21.2.0",
        "Werkzeug==3.0.1",
    ],
    python_requires=">=3.11,<3.12",
)
