import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock

from fastapi import HTTPException
from pydantic import ValidationError

from src.main import add_months, create_payment, list_payments
from src.models import PaymentMethod, Role, User, UserStatus
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
    def test_client_payment_query_is_restricted_to_authenticated_user(self):
        db = Mock()
        db.scalars.return_value.all.return_value = []
        client = make_client()

        self.assertEqual(list_payments(db, client), [])

        query = db.scalars.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("pagos_mensualidad.id_usuario = 12", sql)
        self.assertIn("LIMIT 100", sql)

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


if __name__ == "__main__":
    unittest.main()
