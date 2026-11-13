# seeders/base.py
from django.db import connection


class BaseSeeder:
    def run(self):
        raise NotImplementedError("Seeder must implement run()")

    @staticmethod
    def sync_sequence(model):
        """Synchronize postgres auto-increment sequence with MAX(id) if needed."""
        if connection.vendor != "postgresql":
            return
        table_name = model._meta.db_table
        pk_name = model._meta.pk.column
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                DO $$
                DECLARE
                    seq text;
                BEGIN
                    seq := pg_get_serial_sequence('{table_name}', '{pk_name}');
                    IF seq IS NOT NULL THEN
                        EXECUTE format('SELECT setval(%L, COALESCE(MAX(%I), 1)) FROM %I', seq, '{pk_name}', '{table_name}');
                    END IF;
                END $$;
                """
            )

    @classmethod
    def sync_sequences(cls, *models):
        """Synchronize sequences for multiple models."""
        for model in models:
            cls.sync_sequence(model)
