import psycopg

from config import get_db_config


def main() -> None:
    db_config = get_db_config()

    with psycopg.connect(**db_config) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_database() AS database_name,
                    current_user AS database_user,
                    version() AS postgresql_version;
                """
            )
            database_name, database_user, postgresql_version = cursor.fetchone()

    print(f"Connected to database: {database_name}")
    print(f"Connected as user: {database_user}")
    print(postgresql_version)


if __name__ == "__main__":
    main()