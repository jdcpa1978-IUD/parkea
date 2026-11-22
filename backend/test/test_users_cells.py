import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.auth import UNUSABLE_PASSWORD, hash_password, verify_password
from src.main import (
    create_cell,
    create_user,
    create_vehicle_with_new_client,
    dashboard,
    deactivate_user,
    login,
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
from src.schemas import CellCreate, CellStatusUpdate, LoginInput, UserCreate, UserUpdate, VehicleWithNewClientCreate


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
    def test_staff_login_remains_available(self):
        db = Mock()
        operator = make_user(2, role=Role.OPERADOR)
        operator.password_hash = hash_password("password-123")
        db.scalar.return_value = operator
        self.assertEqual(login(LoginInput(documento=operator.documento, password="password-123"), db)["user"].rol, Role.OPERADOR)

    def test_vehicle_registration_creates_client_without_login_credentials(self):
        db = Mock()
        payload = VehicleWithNewClientCreate(
            placa="ABC123",
            tipo_vehiculo=VehicleType.AUTOMOVIL,
            cliente={"documento": "123", "nombre_completo": "Ana Pérez"},
        )
        result = create_vehicle_with_new_client(payload, db, make_user(1))
        self.assertEqual(result["cliente"].password_hash, UNUSABLE_PASSWORD)
        self.assertNotIn("clave_temporal", result)

    def test_client_cannot_log_in_or_be_assigned_password(self):
        db = Mock()
        admin = make_user(1)
        client = create_user(
            UserCreate(documento="123", nombre="Ana", apellido="Pérez", rol=Role.CLIENTE),
            db,
            admin,
        )
        client.id_usuario = 2
        client.estado = UserStatus.ACTIVO
        self.assertEqual(client.password_hash, UNUSABLE_PASSWORD)
        db.scalar.return_value = client
        with self.assertRaises(HTTPException) as raised:
            login(LoginInput(documento="123", password="any-password"), db)
        self.assertEqual(raised.exception.status_code, 401)

        db.get.return_value = client
        with self.assertRaises(HTTPException) as raised:
            update_user(2, UserUpdate(password="password-123"), db, admin)
        self.assertEqual(raised.exception.status_code, 422)
        client.password_hash = hash_password("password-123")
        with self.assertRaises(HTTPException) as raised:
            login(LoginInput(documento="123", password="password-123"), db)
        self.assertEqual(raised.exception.status_code, 401)
        with self.assertRaises(ValidationError):
            UserCreate(documento="123", nombre="Ana", apellido="Pérez", rol=Role.CLIENTE, password="password-123")

    def test_staff_creation_requires_valid_password(self):
        for role in (Role.ADMINISTRADOR, Role.OPERADOR):
            for password in (None, "", "short", "á" * 37):
                with self.subTest(role=role, password=password), self.assertRaises(ValidationError):
                    UserCreate(documento="123", nombre="Ana", apellido="Pérez", rol=role, password=password)

    def test_promoting_client_without_password_requires_password(self):
        db = Mock()
        client = make_user(2, role=Role.CLIENTE)
        client.password_hash = UNUSABLE_PASSWORD
        db.get.return_value = client
        with self.assertRaises(HTTPException) as raised:
            update_user(2, UserUpdate(rol=Role.OPERADOR), db, make_user(1))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(client.rol, Role.CLIENTE)
        db.rollback.assert_called_once()
        db.commit.assert_not_called()

        update_user(2, UserUpdate(rol=Role.OPERADOR, password="password-123"), db, make_user(1))
        self.assertEqual(client.rol, Role.OPERADOR)
        self.assertTrue(verify_password("password-123", client.password_hash))

    def test_reactivating_client_does_not_restore_login(self):
        db = Mock()
        admin = make_user(1)
        client = make_user(2, role=Role.CLIENTE, status=UserStatus.INACTIVO)
        client.password_hash = UNUSABLE_PASSWORD
        db.get.return_value = client
        db.scalar.return_value = client
        update_user(2, UserUpdate(estado=UserStatus.ACTIVO), db, admin)
        self.assertEqual(client.estado, UserStatus.ACTIVO)
        with self.assertRaises(HTTPException):
            login(LoginInput(documento=client.documento, password="password-123"), db)
        client.password_hash = hash_password("password-123")
        deactivate_user(2, db, admin)
        with self.assertRaises(HTTPException):
            login(LoginInput(documento=client.documento, password="password-123"), db)
        update_user(2, UserUpdate(estado=UserStatus.ACTIVO), db, admin)
        with self.assertRaises(HTTPException):
            login(LoginInput(documento=client.documento, password="password-123"), db)

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
            rol=Role.OPERADOR,
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
        db.rollback.assert_called_once()

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
        db.rollback.assert_called_once()


class CellAdministrationTests(unittest.TestCase):
    def test_operator_can_send_available_and_occupied_cells_to_maintenance(self):
        for state in (CellStatus.DISPONIBLE, CellStatus.OCUPADA):
            with self.subTest(state=state):
                db = Mock()
                cell = Cell(id_celda=7, codigo_celda="A-07", tipo_celda=VehicleType.AUTOMOVIL, estado=state)
                db.scalar.return_value = cell
                update_cell(7, CellStatusUpdate(estado=CellStatus.MANTENIMIENTO), db, make_user(2, Role.OPERADOR))
                self.assertEqual(cell.estado, CellStatus.MANTENIMIENTO)
                db.commit.assert_called_once()

    def test_operator_cannot_reenable_cell_or_mark_it_occupied(self):
        for state in (CellStatus.DISPONIBLE, CellStatus.OCUPADA):
            with self.subTest(state=state):
                db = Mock()
                with self.assertRaises(HTTPException) as raised:
                    update_cell(7, CellStatusUpdate(estado=state), db, make_user(2, Role.OPERADOR))
                self.assertEqual(raised.exception.status_code, 403)
                db.commit.assert_not_called()
                db.rollback.assert_called_once()

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
        db.rollback.assert_called_once()

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
