from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    with engine.connect() as connection:
        result = connection.execute(
            text(
                "SELECT current_database() AS database_name, "
                "current_user AS database_user, "
                "version() AS database_version"
            )
        ).mappings().one()

        print("Database connection successful.")
        print(f"Database: {result['database_name']}")
        print(f"User: {result['database_user']}")
        print(f"Version: {result['database_version']}")


if __name__ == "__main__":
    main()