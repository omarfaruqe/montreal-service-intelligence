import pytest


def test_pagination_returns_every_record_once(client):
    ids = []
    after_id = 0

    for _ in range(5):
        response = client.get(
            "/api/service-requests",
            params={"limit": 2, "after_id": after_id},
        )

        assert response.status_code == 200
        page = response.json()
        ids.extend(item["id"] for item in page["items"])

        if not page["has_more"]:
            assert page["next_after_id"] is None
            break

        assert page["next_after_id"] > after_id
        after_id = page["next_after_id"]
    else:
        pytest.fail("Pagination did not terminate.")

    assert ids == [1, 2, 3, 4, 5]


def test_combined_filters(client):
    response = client.get(
        "/api/service-requests",
        params={
            "nature": "Requete",
            "category": "Nid-de-poule",
            "borough": "Ville-Marie",
        },
    )

    assert response.status_code == 200
    assert [
        row["id"] for row in response.json()["items"]
    ] == [1, 2]


def test_date_range_has_exclusive_end(client):
    response = client.get(
        "/api/service-requests",
        params={
            "created_from": "2024-01-10T09:00:00",
            "created_before": "2024-02-10T09:00:00",
        },
    )

    assert response.status_code == 200
    assert [
        row["id"] for row in response.json()["items"]
    ] == [1, 4]


def test_information_preserves_missing_fields(client):
    response = client.get("/api/service-requests/4")

    assert response.status_code == 200
    record = response.json()

    assert record["nature"] == "Information"
    assert record["source_id"] is None
    assert record["borough"] is None
    assert record["last_status"] is None


def test_missing_record_returns_404(client):
    response = client.get("/api/service-requests/999")

    assert response.status_code == 404


def test_no_matches_returns_empty_page(client):
    response = client.get(
        "/api/service-requests",
        params={"category": "Category that does not exist"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "next_after_id": None,
        "has_more": False,
    }


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"after_id": -1},
        {"nature": "Unknown"},
        {"created_from": "not-a-date"},
        {"created_from": "2024-01-01T00:00:00Z"},
        {
            "created_from": "2024-03-01T00:00:00",
            "created_before": "2024-02-01T00:00:00",
        },
    ],
)
def test_invalid_parameters_return_422(client, params):
    response = client.get(
        "/api/service-requests",
        params=params,
    )

    assert response.status_code == 422