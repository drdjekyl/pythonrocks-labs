# Mêmes commandes que le gabarit python-starter, pour ne pas dépayser.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

default:
    @just --list

# Crée l'environnement, installe tout, et branche le hook de pre-commit
install:
    uv sync
    uv run pre-commit install

# Vérifie le style et cherche les erreurs
lint:
    uv run ruff check .
    uv run ruff format --check .

# Corrige et reformate
format:
    uv run ruff check --fix .
    uv run ruff format .

# Régénère l'instantané Parquet depuis l'API publique (~2 min, throttlé)
donnees:
    uv run python src/labs/yachts.py

# Ouvre les notebooks
lab:
    uv run jupyter lab

# Lance les tests (pas de `--cov` ici : pas de pytest-cov dans ce dépôt)
test:
    uv run pytest

# Tout vérifier — exactement ce que fait la CI
check: lint test
