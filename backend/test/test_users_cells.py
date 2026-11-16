import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.main import (
    create_cell,
    create_user,
    dashboard,
    deactivate_user,
    update_cell,
    update_user,
)
from src.models import (
    AccessRecord,
    AccessStatus,
    Cell,
    CellStatus,
    Role,
    User,
    UserStatus,
    VehicleType,
)
from src.schemas import CellCreate, CellStatusUpdate, UserCreate, UserUpdate


def integrity_error():
    return IntegrityError("statement", {}, Exception("unique constraint"))


def make_user(user_id, role=Role.ADMINISTRADOR, status=UserStatus.ACTIVO):
    return User(
        id_usuario=user_id,
        documento=f"doc-{user_id}",
        nombre="Ana",
        apellido="Pérez",
        password_hash="existing-hash",
        rol=role,
        estado=status,
    )


class UserAdministrationTests(unittest.TestCase):
    def test_create_user_hashes_password_and_trims_names(self):
        db = Mock()
        admin = make_user(1)
        payload = UserCreate(
            documento=" 123456 ",
            nombre=" Ana ",
            apellido=" Pérez ",
            password="password-123",
            rol=Role.OPERADOR,
        )

        with patch("src.main.hash_password", return_value="bcrypt-hash") as hash_password:
            user = create_user(payload, db, admin)

        self.assertEqual(user.documento, "123456")
        self.assertEqual(user.nombre, "Ana")
        self.assertEqual(user.apellido, "Pérez")
        self.assertEqual(user.password_hash, "bcrypt-hash")
        self.assertEqual(user.rol, Role.OPERADOR)
        hash_password.assert_called_once_with("password-123")
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(user)

    def test_create_user_rolls_back_and_returns_conflict_on_duplicate(self):
        db = Mock()
        db.commit.side_effect = integrity_error()
        payload = UserCreate(
            documento="123456",
            nombre="Ana",
            apellido="Pérez",
            password="password-123",
            rol=Role.CLIENTE,
        )

        with patch("src.main.hash_password", return_value="bcrypt-hash"):
            with self.assertRaises(HTTPException) as raised:
                create_user(payload, db, make_user(1))

        self.assertEqual(raised.exception.status_code, 409)
        db.rollback.assert_called_once()
        db.refresh.assert_not_called()

    def test_update_without_password_preserves_hash(self):
        db = Mock()
        user = make_user(2, role=Role.CLIENTE)
        db.get.return_value = user

        result = update_user(
            user.id_usuario,
            UserUpdate(nombre="  Ana María  "),
            db,
            make_user(1),
        )

        self.assertIs(result, user)
        self.assertEqual(user.nombre, "Ana María")
        self.assertEqual(user.password_hash, "existing-hash")
        db.commit.assert_called_once()

    def test_admin_cannot_change_own_role(self):
        db = Mock()
        admin = make_user(1)
        db.get.return_value = admin

        with self.assertRaises(HTTPException) as raised:
            update_user(
                admin.id_usuario,
                UserUpdate(rol=Role.OPERADOR),
                db,
                admin,
            )

        self.assertEqual(raised.exception.status_code, 409)
        db.commit.assert_not_called()

    def test_deactivate_user_is_logical_and_cannot_deactivate_self(self):
        db = Mock()
        admin = make_user(1)
        other_user = make_user(2, role=Role.CLIENTE)
        db.get.return_value = other_user

        deactivate_user(other_user.id_usuario, db, admin)

        self.assertEqual(other_user.estado, UserStatus.INACTIVO)
        db.commit.assert_called_once()

        db.reset_mock()
        db.get.return_value = admin
        with self.assertRaises(HTTPException) as raised:
            deactivate_user(admin.id_usuario, db, admin)

        self.assertEqual(raised.exception.status_code, 409)
        db.commit.assert_not_called()


class CellAdministrationTests(unittest.TestCase):
    def test_dashboard_counts_active_accesses_as_occupied_cells(self):
        db = Mock()
        db.scalar.side_effect = [8, 2, 2, 4]

        result = dashboard(db, make_user(1))

        self.assertEqual(result["celdas_totales"], 8)
        self.assertEqual(result["celdas_ocupadas"], 2)
        occupied_query = db.scalar.call_args_list[1].args[0]
        condition = occupied_query.whereclause
        self.assertIs(condition.left.table, AccessRecord.__table__)
        self.assertEqual(condition.left.key, "estado_registro")
        self.assertEqual(condition.right.value, AccessStatus.INGRESO_ACTIVO)

    def test_create_cell_normalizes_code(self):
        db = Mock()
        payload = CellCreate(
            codigo_celda=" a-07 ",
            tipo_celda=VehicleType.AUTOMOVIL,
        )

        cell = create_cell(payload, db, make_user(1))

        self.assertEqual(cell.codigo_celda, "A-07")
        self.assertEqual(cell.tipo_celda, VehicleType.AUTOMOVIL)
        db.commit.assert_called_once()

    def test_create_cell_rolls_back_and_returns_conflict_on_duplicate(self):
        db = Mock()
        db.commit.side_effect = integrity_error()
        payload = CellCreate(
            codigo_celda="A-07",
            tipo_celda=VehicleType.AUTOMOVIL,
        )

        with self.assertRaises(HTTPException) as raised:
            create_cell(payload, db, make_user(1))

        self.assertEqual(raised.exception.status_code, 409)
        db.rollback.assert_called_once()

    def test_active_cell_cannot_be_released_manually(self):
        db = Mock()
        cell = Cell(
            id_celda=7,
            codigo_celda="A-07",
            tipo_celda=VehicleType.AUTOMOVIL,
            estado=CellStatus.OCUPADA,
        )
        db.scalar.side_effect = [cell, 123]

        with self.assertRaises(HTTPException) as raised:
            update_cell(
                cell.id_celda,
                CellStatusUpdate(estado=CellStatus.DISPONIBLE),
                db,
                make_user(1),
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(cell.estado, CellStatus.OCUPADA)
        db.commit.assert_not_called()

    def test_occupied_cell_can_be_marked_for_maintenance(self):
        db = Mock()
        cell = Cell(
            id_celda=7,
            codigo_celda="A-07",
            tipo_celda=VehicleType.AUTOMOVIL,
            estado=CellStatus.OCUPADA,
        )
        db.scalar.return_value = cell

        result = update_cell(
            cell.id_celda,
            CellStatusUpdate(estado=CellStatus.MANTENIMIENTO),
            db,
            make_user(1),
        )

        self.assertIs(result, cell)
        self.assertEqual(cell.estado, CellStatus.MANTENIMIENTO)
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
