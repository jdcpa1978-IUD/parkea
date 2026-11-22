import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from src.main import update_cell
from src.models import AccessRecord, AccessStatus, Cell, CellStatus, Role
from src.schemas import CellStatusUpdate
from src.services.access import _cell_status_after_exit, register_exit


class CellAvailabilityAfterExitTests(unittest.TestCase):
    def test_occupied_cell_becomes_available_after_exit(self):
        self.assertEqual(
            _cell_status_after_exit(CellStatus.OCUPADA),
            CellStatus.DISPONIBLE,
        )

    def test_maintenance_cell_remains_unavailable_after_exit(self):
        self.assertEqual(
            _cell_status_after_exit(CellStatus.MANTENIMIENTO),
            CellStatus.MANTENIMIENTO,
        )

    def test_cell_marked_for_maintenance_stays_unavailable_after_exit(self):
        cell = SimpleNamespace(id_celda=7, estado=CellStatus.OCUPADA)
        entered_at = datetime(2026, 11, 8, 14, 0, tzinfo=timezone.utc)
        now = datetime(2026, 11, 8, 15, 30, tzinfo=timezone.utc)
        record = SimpleNamespace(
            id_celda=cell.id_celda,
            fecha_hora_ingreso=entered_at,
            estado_registro=AccessStatus.INGRESO_ACTIVO,
            celda=cell,
            vehiculo=SimpleNamespace(placa="ABC123"),
        )
        db = Mock()

        def scalar(statement):
            entity = statement.column_descriptions[0].get("entity")
            if entity is Cell:
                return cell
            if entity is AccessRecord:
                return record
            return now

        db.scalar.side_effect = scalar

        update_cell(cell.id_celda, CellStatusUpdate(estado=CellStatus.MANTENIMIENTO), db, SimpleNamespace(rol=Role.OPERADOR))
        finalized, minutes = register_exit(db, "ABC123", operator_id=3)

        self.assertEqual(minutes, 90)
        self.assertEqual(finalized.estado_registro, AccessStatus.FINALIZADO)
        self.assertEqual(finalized.fecha_hora_salida, now)
        self.assertEqual(finalized.id_operador_salida, 3)
        self.assertEqual(cell.estado, CellStatus.MANTENIMIENTO)


if __name__ == "__main__":
    unittest.main()
