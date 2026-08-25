"""Le cas qui fait la valeur de ce module : une variation brute identique peut cacher une
variation normalisée nulle. Aucune donnée ici n'est réelle -- les chiffres exacts de la
collecte réelle vivent dans la docstring de `pypi_features.py`, ces tests couvrent la logique.
"""

from datetime import date

import pandas as pd
import pytest

from labs.pypi_features import COLONNES_FUITE, construire_features


def _telechargements(paquet: str, valeurs: list[int]) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=len(valeurs)).date
    return pd.DataFrame({"package": paquet, "date": dates, "downloads": valeurs})


def _releases(
    paquet: str, premiere: date, derniere: date, n: int, reference: date
) -> dict:
    return {
        "package": paquet,
        "first_release": premiere,
        "last_release": derniere,
        "n_releases": n,
        "reference_date": reference,
    }


def test_variation_brute_identique_mais_normalisee_nulle():
    """`certifi` double sur la période (baseline) ; `requests` double aussi : la variation
    brute de `requests` affiche +100 %, mais sa part relative à `certifi` n'a pas bougé -- la
    variation normalisée doit être nulle. C'est exactement le piège que ce module corrige."""
    telechargements = pd.concat(
        [
            _telechargements("certifi", [100] * 7 + [200] * 7),
            _telechargements("requests", [50] * 7 + [100] * 7),
        ],
        ignore_index=True,
    )
    reference = date(2026, 6, 1)
    releases = pd.DataFrame(
        [
            _releases("certifi", date(2020, 1, 1), date(2021, 1, 1), 10, reference),
            _releases("requests", date(2020, 1, 1), date(2021, 1, 1), 10, reference),
        ]
    )

    df = construire_features(telechargements, releases).set_index("package")

    assert df.loc["certifi", "variation_brute_pct"] == pytest.approx(100.0)
    assert df.loc["requests", "variation_brute_pct"] == pytest.approx(100.0)
    assert df.loc["certifi", "variation_normalisee_pct"] == pytest.approx(0.0)
    assert df.loc["requests", "variation_normalisee_pct"] == pytest.approx(0.0)


def test_variation_normalisee_capture_le_mouvement_relatif():
    """`requests` double pendant que `certifi` reste stable : la variation normalisée doit
    refléter la vraie hausse relative, pas être écrasée par le baseline."""
    telechargements = pd.concat(
        [
            _telechargements("certifi", [100] * 14),
            _telechargements("requests", [50] * 7 + [100] * 7),
        ],
        ignore_index=True,
    )
    reference = date(2026, 6, 1)
    releases = pd.DataFrame(
        [
            _releases("certifi", date(2020, 1, 1), date(2021, 1, 1), 10, reference),
            _releases("requests", date(2020, 1, 1), date(2021, 1, 1), 10, reference),
        ]
    )

    df = construire_features(telechargements, releases).set_index("package")
    assert df.loc["certifi", "variation_normalisee_pct"] == pytest.approx(0.0)
    assert df.loc["requests", "variation_normalisee_pct"] == pytest.approx(100.0)


def test_age_recence_et_cadence():
    telechargements = pd.concat(
        [
            _telechargements("certifi", [100] * 14),
            _telechargements("requests", [100] * 14),
        ],
        ignore_index=True,
    )
    reference = date(2022, 1, 1)
    releases = pd.DataFrame(
        [
            _releases("certifi", date(2020, 1, 1), date(2021, 1, 1), 10, reference),
            _releases("requests", date(2020, 1, 1), date(2021, 1, 1), 10, reference),
        ]
    )
    df = construire_features(telechargements, releases).set_index("package")

    assert df.loc["certifi", "age_jours"] == 731  # 2020 bissextile + 2021 -> 366 + 365
    assert df.loc["certifi", "recence_jours"] == 365
    # 10 releases sur 366 jours (2020 bissextile) -> 10 / (366 / 365.25)
    assert df.loc["certifi", "cadence_releases_an"] == pytest.approx(
        10 / (366 / 365.25)
    )


def test_cadence_indeterminee_si_une_seule_journee_de_publication():
    """Première et dernière release le même jour (une seule release, ou plusieurs le même
    jour) : la cadence n'a pas de sens, ce doit être `None`, jamais une division par zéro ni un
    0 silencieux."""
    telechargements = pd.concat(
        [
            _telechargements("certifi", [100] * 14),
            _telechargements("anthropic", [100] * 14),
        ],
        ignore_index=True,
    )
    reference = date(2026, 1, 1)
    releases = pd.DataFrame(
        [
            _releases("certifi", date(2020, 1, 1), date(2021, 1, 1), 10, reference),
            _releases("anthropic", date(2024, 1, 1), date(2024, 1, 1), 1, reference),
        ]
    )
    df = construire_features(telechargements, releases).set_index("package")
    assert pd.isna(df.loc["anthropic", "cadence_releases_an"])


def test_desaccord_entre_les_deux_sources_leve():
    telechargements = _telechargements("certifi", [100] * 14)
    releases = pd.DataFrame(
        [
            _releases(
                "requests", date(2020, 1, 1), date(2021, 1, 1), 10, date(2026, 1, 1)
            )
        ]
    )
    with pytest.raises(ValueError, match="désaccord"):
        construire_features(telechargements, releases)


def test_baseline_absente_leve():
    telechargements = _telechargements("requests", [100] * 14)
    releases = pd.DataFrame(
        [
            _releases(
                "requests", date(2020, 1, 1), date(2021, 1, 1), 10, date(2026, 1, 1)
            )
        ]
    )
    with pytest.raises(ValueError, match="certifi"):
        construire_features(telechargements, releases)


def test_colonnes_fuite_sont_bien_des_colonnes_reelles_du_resultat():
    """Garde-fou croisé avec `pypi_classification.py` : si une des trois colonnes de fuite
    disparaissait ou changeait de nom ici, l'exclusion côté classification deviendrait un
    no-op silencieux plutôt qu'une vraie protection."""
    telechargements = pd.concat(
        [
            _telechargements("certifi", [100] * 14),
            _telechargements("requests", [100] * 14),
        ],
        ignore_index=True,
    )
    releases = pd.DataFrame(
        [
            _releases(
                "certifi", date(2020, 1, 1), date(2021, 1, 1), 10, date(2026, 1, 1)
            ),
            _releases(
                "requests", date(2020, 1, 1), date(2021, 1, 1), 10, date(2026, 1, 1)
            ),
        ]
    )
    df = construire_features(telechargements, releases)
    assert set(COLONNES_FUITE) <= set(df.columns)
