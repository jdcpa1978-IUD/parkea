import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException
from pydantic import ValidationError

from src.main import create_incident
from src.models import AccessStatus
from src.schemas import IncidentCreate


class IncidentValidationTests(unittest.TestCase):
    def test_description_is_trimmed(self):
        payload = IncidentCreate(id_registro=1, descripcion="  Daño observado  ")

        self.assertEqual(payload.descripcion, "Daño observado")

    def test_whitespace_only_description_is_rejected(self):
        with self.assertRaises(ValidationError):
            IncidentCreate(id_registro=1, descripcion="   ")

    def test_incident_can_be_created_for_active_access(self):
        record = SimpleNamespace(estado_registro=AccessStatus.INGRESO_ACTIVO)
        db = Mock()
        db.get.return_value = record

        create_incident(IncidentCreate(id_registro=1, descripcion="Daño"), db, SimpleNamespace(id_usuario=2))

        incident = db.add.call_args.args[0]
        self.assertEqual(incident.id_registro, 1)
        self.assertEqual(incident.id_operador, 2)
        self.assertEqual(incident.descripcion, "Daño")
        db.commit.assert_called_once()

    def test_incident_for_finalized_access_is_rejected(self):
        db = Mock()
        db.get.return_value = SimpleNamespace(estado_registro=AccessStatus.FINALIZADO)

        with self.assertRaises(HTTPException) as error:
            create_incident(IncidentCreate(id_registro=1, descripcion="Daño"), db, SimpleNamespace(id_usuario=2))

        self.assertEqual(error.exception.status_code, 409)
        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_incident_for_missing_access_is_rejected(self):
        db = Mock()
        db.get.return_value = None

        with self.assertRaises(HTTPException) as error:
            create_incident(IncidentCreate(id_registro=1, descripcion="Daño"), db, SimpleNamespace(id_usuario=2))

        self.assertEqual(error.exception.status_code, 404)
        db.add.assert_not_called()
        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
