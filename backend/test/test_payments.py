import asyncio
import json
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, MetaData, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.auth import create_access_token
from src.database import get_db
from src.main import add_months, app, create_payment, list_payments
from src.models import (
    AccessRecord, AccessStatus, Cell, CellStatus, MonthlyPayment, PaymentMethod,
    Role, User, UserStatus, Vehicle, VehicleType,
)
from src.schemas import PaymentCreate


def make_client(status=UserStatus.ACTIVO):
    return User(
        id_usuario=12,
        documento="123456",
        nombre="Ana",
        apellido="Pérez",
        password_hash="hash",
        rol=Role.CLIENTE,
        estado=status,
    )


class PaymentValidationTests(unittest.TestCase):
    def test_payment_rejects_non_positive_amount_and_invalid_month_range(self):
        base = {
            "id_usuario": 12,
            "monto": "120000.00",
            "meses": 1,
            "metodo_pago": "EFECTIVO",
        }

        for invalid in (
            {**base, "monto": "0"},
            {**base, "monto": "-5"},
            {**base, "monto": "1.001"},
            {**base, "meses": 0},
            {**base, "meses": 25},
            {**base, "metodo_pago": "CHEQUE"},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    PaymentCreate.model_validate(invalid)

    def test_add_months_handles_year_boundary_and_short_month(self):
        self.assertEqual(add_months(date(2026, 12, 31), 1), date(2027, 1, 31))
        self.assertEqual(add_months(date(2027, 1, 31), 1), date(2027, 2, 28))


class PaymentRegistrationTests(unittest.TestCase):
    def test_registration_without_previous_payment_starts_today(self):
        db = Mock()
        client = make_client()
        db.scalar.side_effect = [client, None]
        payload = PaymentCreate(
            id_usuario=client.id_usuario,
            monto=Decimal("120000.00"),
            meses=1,
            metodo_pago=PaymentMethod.EFECTIVO,
        )

        payment = create_payment(payload, db, Mock())

        self.assertEqual(payment.fecha_inicio_vencimiento, date.today())
        self.assertEqual(
            payment.fecha_fin_vencimiento,
            add_months(date.today(), 1) - timedelta(days=1),
        )
        db.commit.assert_called_once()

    def test_registration_chains_new_period_after_existing_vigency(self):
        db = Mock()
        client = make_client()
        latest_end = date.today() + timedelta(days=10)
        db.scalar.side_effect = [client, latest_end]
        payload = PaymentCreate(
            id_usuario=client.id_usuario,
            monto=Decimal("120000.00"),
            meses=2,
            metodo_pago=PaymentMethod.TRANSFERENCIA,
        )

        payment = create_payment(payload, db, Mock())

        self.assertEqual(payment.id_usuario, client.id_usuario)
        self.assertEqual(payment.monto, Decimal("120000.00"))
        self.assertEqual(payment.fecha_inicio_vencimiento, latest_end + timedelta(days=1))
        self.assertEqual(
            payment.fecha_fin_vencimiento,
            add_months(latest_end + timedelta(days=1), 2) - timedelta(days=1),
        )
        self.assertEqual(payment.metodo_pago, PaymentMethod.TRANSFERENCIA)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(payment)

    def test_registration_starts_today_when_previous_period_expired(self):
        db = Mock()
        client = make_client()
        db.scalar.side_effect = [client, date.today() - timedelta(days=1)]
        payload = PaymentCreate(
            id_usuario=client.id_usuario,
            monto=Decimal("95000.00"),
            meses=1,
            metodo_pago=PaymentMethod.EFECTIVO,
        )

        payment = create_payment(payload, db, Mock())

        self.assertEqual(payment.fecha_inicio_vencimiento, date.today())
        self.assertEqual(payment.fecha_fin_vencimiento, add_months(date.today(), 1) - timedelta(days=1))
        db.commit.assert_called_once()

    def test_registration_rejects_missing_or_inactive_client_without_commit(self):
        payload = PaymentCreate(
            id_usuario=12,
            monto=Decimal("120000.00"),
            meses=1,
            metodo_pago=PaymentMethod.EFECTIVO,
        )
        for client in (None, make_client(UserStatus.INACTIVO)):
            with self.subTest(client=client):
                db = Mock()
                db.scalar.return_value = client

                with self.assertRaises(HTTPException) as raised:
                    create_payment(payload, db, Mock())

                self.assertEqual(raised.exception.status_code, 404)
                db.commit.assert_not_called()
                db.add.assert_not_called()


class PaymentHistoryTests(unittest.TestCase):
    def test_staff_history_is_not_filtered_to_a_single_client(self):
        db = Mock()
        db.scalars.return_value.all.return_value = []
        operator = User(
            id_usuario=7,
            documento="op-7",
            nombre="Luis",
            apellido="Díaz",
            password_hash="hash",
            rol=Role.OPERADOR,
            estado=UserStatus.ACTIVO,
        )

        self.assertEqual(list_payments(db, operator), [])

        query = db.scalars.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        self.assertNotIn("WHERE", sql)
        self.assertIn("LIMIT 100", sql)


class ClientConsultationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        metadata = MetaData()
        for model in (User, Vehicle, Cell, AccessRecord, MonthlyPayment):
            model.__table__.to_metadata(metadata)
        vehicle_table = metadata.tables["vehiculos"]
        for constraint in list(vehicle_table.constraints):
            if isinstance(constraint, CheckConstraint):
                vehicle_table.constraints.remove(constraint)
        # PostgreSQL partial indexes cannot be represented by these SQLite table copies.
        metadata.tables["registros_acceso"].indexes.clear()
        metadata.create_all(self.engine)
        today = date.today()
        with Session(self.engine) as db:
            clients = [
                User(
                    id_usuario=i,
                    documento=f"client-{i}",
                    nombre=f"Cliente {i}",
                    apellido="Prueba",
                    password_hash="hash",
                    rol=Role.CLIENTE,
                    estado=UserStatus.INACTIVO if i == 7 else UserStatus.ACTIVO,
                )
                for i in range(1, 9)
            ]
            staff = [
                User(
                    id_usuario=ident,
                    documento=f"staff-{ident}",
                    nombre="Personal",
                    apellido="Prueba",
                    password_hash="hash",
                    rol=role,
                    estado=UserStatus.ACTIVO,
                )
                for ident, role in ((90, Role.ADMINISTRADOR), (91, Role.OPERADOR))
            ]
            db.add_all(clients + staff)
            db.flush()
            self.tokens = {user.id_usuario: create_access_token(user) for user in clients + staff}
            ranges = [
                (2, today - timedelta(days=30), today - timedelta(days=1)),
                (3, today + timedelta(days=1), today + timedelta(days=30)),
                (4, today, today + timedelta(days=30)),
                (5, today - timedelta(days=30), today),
                (6, today - timedelta(days=30), today - timedelta(days=1)),
                (6, today + timedelta(days=1), today + timedelta(days=30)),
            ]
            ranges.extend((2, today - timedelta(days=100), today - timedelta(days=99)) for _ in range(100))
            db.add_all([
                MonthlyPayment(
                    id_usuario=client_id,
                    monto=Decimal("1000.00"),
                    fecha_inicio_vencimiento=start,
                    fecha_fin_vencimiento=end,
                    metodo_pago=PaymentMethod.EFECTIVO,
                )
                for client_id, start, end in ranges
            ])
            db.add_all([
                Vehicle(id_vehiculo=i, placa=plate, tipo_vehiculo=VehicleType.AUTOMOVIL, id_usuario=owner)
                for i, plate, owner in ((1, "ABC123", 2), (2, "DEF456", 2), (3, "GHI789", 3))
            ])
            db.add_all([
                Cell(id_celda=i, codigo_celda=f"A-{i}", tipo_celda=VehicleType.AUTOMOVIL, estado=CellStatus.DISPONIBLE)
                for i in range(1, 4)
            ])
            db.flush()
            now = datetime.now()
            db.add_all([
                AccessRecord(
                    id_vehiculo=vehicle_id, id_celda=cell_id, id_operador_ingreso=91,
                    fecha_hora_ingreso=now, fecha_hora_salida=now if ended else None,
                    estado_registro=AccessStatus.FINALIZADO if ended else AccessStatus.INGRESO_ACTIVO,
                )
                for vehicle_id, cell_id, ended in ((1, 1, True), (2, 2, False), (3, 3, False))
            ])
            db.commit()

        def isolated_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = isolated_db
        self.addCleanup(app.dependency_overrides.pop, get_db, None)
        self.addCleanup(self.engine.dispose)

    def request(self, method, path, user_id, payload=None):
        async def request():
            messages = []
            received = False
            request_body = json.dumps(payload).encode() if payload is not None else b""

            async def receive():
                nonlocal received
                if not received:
                    received = True
                    return {"type": "http.request", "body": request_body, "more_body": False}
                await asyncio.Event().wait()

            async def send(message):
                messages.append(message)

            await app({
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                "query_string": b"", "root_path": "",
                "headers": [
                    (b"authorization", f"Bearer {self.tokens[user_id]}".encode()),
                    (b"content-type", b"application/json"),
                ],
                "client": ("127.0.0.1", 12345), "server": ("test", 80),
            }, receive, send)
            status = next(message["status"] for message in messages if message["type"] == "http.response.start")
            body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
            return status, json.loads(body)

        return asyncio.run(request())

    def get(self, path, user_id):
        return self.request("GET", path, user_id)

    def test_staff_registers_payment_and_it_appears_in_coverage_and_histories(self):
        today = date.today()
        payload = {"id_usuario": 1, "monto": "120000.00", "meses": 1, "metodo_pago": "EFECTIVO"}
        status, payment = self.request("POST", "/api/pagos", 91, payload)
        self.assertEqual(status, 201)
        self.assertEqual(payment["fecha_inicio_vencimiento"], today.isoformat())
        first_end = add_months(today, 1) - timedelta(days=1)
        self.assertEqual(payment["fecha_fin_vencimiento"], first_end.isoformat())

        status, coverage = self.get("/api/clientes/vigencias", 90)
        self.assertEqual(status, 200)
        self.assertTrue(next(client for client in coverage if client["id_usuario"] == 1)["vigente"])
        status, history = self.get("/api/clientes/1/historial", 91)
        self.assertEqual(status, 200)
        self.assertEqual([item["id_pago"] for item in history["pagos"]], [payment["id_pago"]])
        self.assertEqual(self.get("/api/pagos", 1)[0], 401)

        status, second_payment = self.request("POST", "/api/pagos", 90, payload)
        self.assertEqual(status, 201)
        self.assertEqual(second_payment["fecha_inicio_vencimiento"], (first_end + timedelta(days=1)).isoformat())
        with Session(self.engine) as db:
            count = db.scalar(select(func.count()).select_from(MonthlyPayment).where(MonthlyPayment.id_usuario == 1))
            self.assertEqual(count, 2)

    def test_registration_chains_after_future_period_without_marking_it_current(self):
        payload = {"id_usuario": 3, "monto": "95000.00", "meses": 1, "metodo_pago": "TRANSFERENCIA"}
        status, payment = self.request("POST", "/api/pagos", 90, payload)
        self.assertEqual(status, 201)
        self.assertEqual(payment["fecha_inicio_vencimiento"], (date.today() + timedelta(days=31)).isoformat())
        _, coverage = self.get("/api/clientes/vigencias", 91)
        self.assertFalse(next(client for client in coverage if client["id_usuario"] == 3)["vigente"])

    def test_registration_rejects_invalid_requests_without_creating_payment(self):
        payload = {"id_usuario": 1, "monto": "120000.00", "meses": 1, "metodo_pago": "EFECTIVO"}
        with Session(self.engine) as db:
            before = db.scalar(select(func.count()).select_from(MonthlyPayment))
        cases = (
            (1, payload, 401),
            (91, {**payload, "monto": "0"}, 422),
            (91, {**payload, "meses": 25}, 422),
            (91, {**payload, "metodo_pago": "CHEQUE"}, 422),
            (91, {**payload, "id_usuario": 7}, 404),
            (91, {**payload, "id_usuario": 999}, 404),
        )
        for user_id, data, expected in cases:
            with self.subTest(user_id=user_id, data=data):
                self.assertEqual(self.request("POST", "/api/pagos", user_id, data)[0], expected)
        with Session(self.engine) as db:
            after = db.scalar(select(func.count()).select_from(MonthlyPayment))
        self.assertEqual(after, before)

    def test_recent_history_limits_results_and_denies_client(self):
        status, staff_payments = self.get("/api/pagos", 91)
        self.assertEqual(status, 200)
        self.assertEqual(len(staff_payments), 100)
        self.assertEqual(
            [payment["fecha_pago"] for payment in staff_payments],
            sorted((payment["fecha_pago"] for payment in staff_payments), reverse=True),
        )
        self.assertEqual(self.get("/api/pagos", 2)[0], 401)

    def test_coverage_includes_boundaries_future_expired_and_inactive_accounts(self):
        status, response = self.get("/api/clientes/vigencias", 91)
        self.assertEqual(status, 200)
        clients = {item["id_usuario"]: item for item in response}
        self.assertEqual(set(clients), set(range(1, 9)))
        self.assertEqual({i for i, item in clients.items() if item["vigente"]}, {4, 5})
        self.assertEqual(clients[7]["estado"], "INACTIVO")

    def test_history_contains_all_payments_and_only_own_active_and_finished_accesses(self):
        status, response = self.get("/api/clientes/2/historial", 90)
        self.assertEqual(status, 200)
        self.assertEqual(len(response["pagos"]), 101)
        self.assertTrue(all(payment["id_usuario"] == 2 for payment in response["pagos"]))
        self.assertEqual({record["placa"] for record in response["accesos"]}, {"ABC123", "DEF456"})
        self.assertEqual({record["estado_registro"] for record in response["accesos"]}, {"FINALIZADO", "INGRESO_ACTIVO"})
        self.assertEqual({record["codigo_celda"] for record in response["accesos"]}, {"A-1", "A-2"})
        self.assertEqual(self.get("/api/clientes/1/historial", 91), (200, {"pagos": [], "accesos": []}))
        self.assertEqual(self.get("/api/clientes/90/historial", 91)[0], 404)
        self.assertEqual(self.get("/api/clientes/999/historial", 91)[0], 404)

    def test_consultations_are_denied_to_client(self):
        for path in ("/api/clientes/vigencias", "/api/clientes/2/historial"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path, 1)[0], 401)

    def test_existing_staff_token_is_rejected_after_role_changes_to_client(self):
        self.assertEqual(self.get("/api/pagos", 91)[0], 200)
        with Session(self.engine) as db:
            db.get(User, 91).rol = Role.CLIENTE
            db.commit()
        self.assertEqual(self.get("/api/pagos", 91)[0], 401)


if __name__ == "__main__":
    unittest.main()
