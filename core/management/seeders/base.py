# seeders/base.py

class BaseSeeder:
    def run(self):
        raise NotImplementedError("Seeder must implement run()")