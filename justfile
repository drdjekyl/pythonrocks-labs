# Mêmes commandes que le gabarit python-starter, pour ne pas dépayser.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

default:
    @just --list

# Crée l'environnement et installe tout
install:
    uv sync

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
