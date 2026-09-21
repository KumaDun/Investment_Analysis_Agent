from directories import get_root_directory
from ingest.database import get_connection

def initialize_database():
    schema_path = get_root_directory() / "ingest" / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(schema_sql)

if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully.")