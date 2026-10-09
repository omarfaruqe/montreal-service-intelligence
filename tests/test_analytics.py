import pytest


def test_borough_counts_default_to_requests(client):
    response = client.get("/api/analytics/boroughs")

    assert response.status_code == 200
    assert response.json() == [
        {"borough": "Ville-Marie", "records": 2},
        {"borough": None, "records": 1},
    ]


def test_top_categories(client):
    response = client.get(
        "/api/analytics/categories",
        params={"limit": 1},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"category": "Nid-de-poule", "records": 2},
    ]


def test_monthly_counts_default_to_requests(client):
    response = client.get("/api/analytics/monthly")

    assert response.status_code == 200
    assert response.json() == [
        {"month": "2024-01-01", "records": 1},
        {"month": "2024-02-01", "records": 2},
    ]


def test_monthly_counts_include_all_natures(client):
    response = client.get(
        "/api/analytics/monthly",
        params={"nature": "all"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"month": "2024-01-01", "records": 2},
        {"month": "2024-02-01", "records": 2},
        {"month": "2024-03-01", "records": 1},
    ]


def test_monthly_combined_filters(client):
    response = client.get(
        "/api/analytics/monthly",
        params={
            "category": "Nid-de-poule",
            "borough": "Ville-Marie",
            "created_from": "2024-02-01T00:00:00",
            "created_before": "2024-03-01T00:00:00",
        },
    )

    assert response.status_code == 200
    assert response.json() == [
        {"month": "2024-02-01", "records": 1},
    ]


def test_information_borough_count_keeps_null(client):
    response = client.get(
        "/api/analytics/boroughs",
        params={"nature": "Information"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"borough": None, "records": 1},
    ]


def test_monthly_no_matches(client):
    response = client.get(
        "/api/analytics/monthly",
        params={"category": "Category that does not exist"},
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "path, params",
    [
        (
            "/api/analytics/categories",
            {"limit": 101},
        ),
        (
            "/api/analytics/categories",
            {"limit": 0},
        ),
        (
            "/api/analytics/boroughs",
            {"nature": "Unknown"},
        ),
        (
            "/api/analytics/monthly",
            {"created_from": "2024-01-01T00:00:00Z"},
        ),
        (
            "/api/analytics/monthly",
            {
                "created_from": "2024-03-01T00:00:00",
                "created_before": "2024-02-01T00:00:00",
            },
        ),
    ],
)
def test_analytics_validation(client, path, params):
    response = client.get(path, params=params)

    assert response.status_code == 422