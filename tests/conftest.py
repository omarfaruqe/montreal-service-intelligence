from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import engine, get_db
from app.main import app
from app.models.service_request import ServiceRequest


@pytest.fixture
def client():
    schema = f"test_{uuid4().hex}"

    with engine.connect() as connection:
        transaction = connection.begin()
        session = None
        previous_overrides = app.dependency_overrides.copy()

        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(
                f'SET LOCAL search_path TO "{schema}"'
            )

            ServiceRequest.__table__.create(
                bind=connection,
                checkfirst=False,
            )

            session = Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )

            sample_rows = [
                (
                    1,
                    "Requete",
                    "Nid-de-poule",
                    "Ville-Marie",
                    datetime(2024, 1, 10, 9),
                ),
                (
                    2,
                    "Requete",
                    "Nid-de-poule",
                    "Ville-Marie",
                    datetime(2024, 2, 10, 9),
                ),
                (
                    3,
                    "Requete",
                    "Collecte de déchets",
                    None,
                    datetime(2024, 2, 20, 9),
                ),
                (
                    4,
                    "Information",
                    "Taxes foncières",
                    None,
                    datetime(2024, 1, 15, 9),
                ),
                (
                    5,
                    "Plainte",
                    "Nid-de-poule",
                    "Verdun",
                    datetime(2024, 3, 10, 9),
                ),
            ]

            for (
                record_id,
                nature,
                category,
                borough,
                created_at,
            ) in sample_rows:
                session.add(
                    ServiceRequest(
                        id=record_id,
                        source_id=(
                            None
                            if nature == "Information"
                            else f"TEST-{record_id}"
                        ),
                        nature=nature,
                        category=category,
                        borough=borough,
                        created_at=created_at,
                        source_file_sha256="a" * 64,
                        source_row_number=record_id,
                    )
                )

            session.flush()

            def override_get_db():
                yield session

            app.dependency_overrides[get_db] = override_get_db

            with TestClient(app) as test_client:
                yield test_client

        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)

            if session is not None:
                session.close()

            # Roll back the temporary schema and its sample data.
            transaction.rollback()