import unittest

from pydantic import ValidationError

from src.models import VehicleType
from src.schemas import EntryInput, VehicleCreate, VehicleWithNewClientCreate


class PlateValidationTests(unittest.TestCase):
    def test_vehicle_plate_is_normalized_and_accepts_six_alphanumeric_characters(self):
        vehicle = VehicleCreate(
            placa="ab123c",
            tipo_vehiculo=VehicleType.AUTOMOVIL,
            id_usuario=1,
        )
        self.assertEqual(vehicle.placa, "AB123C")

    def test_vehicle_plate_rejects_more_than_six_characters(self):
        with self.assertRaises(ValidationError):
            VehicleCreate(placa="ABC1234", tipo_vehiculo="AUTOMOVIL", id_usuario=1)

    def test_vehicle_plate_rejects_non_alphanumeric_characters(self):
        for plate in ("ABC-12", "ABC 12", "ÁBC123"):
            with self.subTest(plate=plate), self.assertRaises(ValidationError):
                VehicleCreate(placa=plate, tipo_vehiculo="AUTOMOVIL", id_usuario=1)

    def test_access_plate_uses_the_same_validation(self):
        self.assertEqual(EntryInput(placa="abc123").placa, "ABC123")
        with self.assertRaises(ValidationError):
            EntryInput(placa="ABC-123")

    def test_combined_vehicle_and_new_client_registration(self):
        payload = VehicleWithNewClientCreate(
            placa="abc123",
            tipo_vehiculo="AUTOMOVIL",
            cliente={
                "documento": "123456",
                "nombre_completo": "Ana María Pérez",
            },
        )
        self.assertEqual(payload.placa, "ABC123")
        self.assertEqual(payload.cliente.documento, "123456")
        self.assertEqual(payload.cliente.nombre_completo, "Ana María Pérez")

    def test_combined_registration_requires_client_data(self):
        with self.assertRaises(ValidationError):
            VehicleWithNewClientCreate(placa="ABC123", tipo_vehiculo="AUTOMOVIL")

    def test_new_client_requires_full_name(self):
        with self.assertRaises(ValidationError):
            VehicleWithNewClientCreate(
                placa="ABC123",
                tipo_vehiculo="AUTOMOVIL",
                cliente={"documento": "123456", "nombre_completo": "Ana"},
            )

    def test_new_client_rejects_names_that_do_not_fit_database_columns(self):
        with self.assertRaises(ValidationError):
            VehicleWithNewClientCreate(
                placa="ABC123",
                tipo_vehiculo="AUTOMOVIL",
                cliente={
                    "documento": "123456",
                    "nombre_completo": f"{'A' * 51} Pérez",
                },
            )


if __name__ == "__main__":
    unittest.main()
