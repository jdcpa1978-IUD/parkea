import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Role(str, enum.Enum):
    ADMINISTRADOR = "ADMINISTRADOR"
    OPERADOR = "OPERADOR"
    CLIENTE = "CLIENTE"


class UserStatus(str, enum.Enum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"


class VehicleType(str, enum.Enum):
    AUTOMOVIL = "AUTOMOVIL"
    MOTOCICLETA = "MOTOCICLETA"


class CellStatus(str, enum.Enum):
    DISPONIBLE = "DISPONIBLE"
    OCUPADA = "OCUPADA"
    MANTENIMIENTO = "MANTENIMIENTO"


class AccessStatus(str, enum.Enum):
    INGRESO_ACTIVO = "INGRESO_ACTIVO"
    FINALIZADO = "FINALIZADO"


class PaymentMethod(str, enum.Enum):
    EFECTIVO = "EFECTIVO"
    TRANSFERENCIA = "TRANSFERENCIA"
    TARJETA = "TARJETA"


class User(Base):
    __tablename__ = "usuarios"

    id_usuario: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False)
    apellido: Mapped[str] = mapped_column(String(50), nullable=False)
    telefono: Mapped[str | None] = mapped_column(String(15))
    email: Mapped[str | None] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[Role] = mapped_column(Enum(Role, name="rol_usuario"), nullable=False)
    estado: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="estado_usuario"), nullable=False, default=UserStatus.ACTIVO
    )
    vehiculos: Mapped[list["Vehicle"]] = relationship(back_populates="usuario")


class Vehicle(Base):
    __tablename__ = "vehiculos"
    __table_args__ = (
        CheckConstraint(
            "placa ~ '^[A-Z0-9]{1,6}$'",
            name="ck_vehiculo_placa_alfanumerica",
        ),
    )

    id_vehiculo: Mapped[int] = mapped_column(Integer, primary_key=True)
    placa: Mapped[str] = mapped_column(String(6), unique=True, nullable=False)
    tipo_vehiculo: Mapped[VehicleType] = mapped_column(
        Enum(VehicleType, name="tipo_vehiculo_enum"), nullable=False
    )
    marca: Mapped[str | None] = mapped_column(String(30))
    modelo: Mapped[str | None] = mapped_column(String(30))
    color: Mapped[str | None] = mapped_column(String(20))
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"), nullable=False
    )
    usuario: Mapped[User] = relationship(back_populates="vehiculos")


class Cell(Base):
    __tablename__ = "celdas"

    id_celda: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_celda: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    tipo_celda: Mapped[VehicleType] = mapped_column(
        Enum(VehicleType, name="tipo_vehiculo_enum"), nullable=False
    )
    estado: Mapped[CellStatus] = mapped_column(
        Enum(CellStatus, name="estado_celda_enum"),
        nullable=False,
        default=CellStatus.DISPONIBLE,
    )
    registros: Mapped[list["AccessRecord"]] = relationship(back_populates="celda")


class AccessRecord(Base):
    __tablename__ = "registros_acceso"
    __table_args__ = (
        CheckConstraint(
            "(estado_registro = 'INGRESO_ACTIVO' AND fecha_hora_salida IS NULL) OR "
            "(estado_registro = 'FINALIZADO' AND fecha_hora_salida IS NOT NULL)",
            name="ck_registro_estado_salida",
        ),
        Index(
            "uq_registro_celda_activa",
            "id_celda",
            unique=True,
            postgresql_where=text("estado_registro = 'INGRESO_ACTIVO'"),
        ),
        Index(
            "uq_registro_vehiculo_activo",
            "id_vehiculo",
            unique=True,
            postgresql_where=text("estado_registro = 'INGRESO_ACTIVO'"),
        ),
    )

    id_registro: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_vehiculo: Mapped[int] = mapped_column(
        ForeignKey("vehiculos.id_vehiculo", ondelete="RESTRICT"), nullable=False
    )
    id_celda: Mapped[int] = mapped_column(
        ForeignKey("celdas.id_celda", ondelete="RESTRICT"), nullable=False
    )
    id_operador_ingreso: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"), nullable=False
    )
    id_operador_salida: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="RESTRICT")
    )
    fecha_hora_ingreso: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fecha_hora_salida: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado_registro: Mapped[AccessStatus] = mapped_column(
        Enum(AccessStatus, name="estado_registro_enum"),
        nullable=False,
        default=AccessStatus.INGRESO_ACTIVO,
    )
    vehiculo: Mapped[Vehicle] = relationship()
    celda: Mapped[Cell] = relationship(back_populates="registros")
    novedades: Mapped[list["Incident"]] = relationship(back_populates="registro")


class MonthlyPayment(Base):
    __tablename__ = "pagos_mensualidad"
    __table_args__ = (
        CheckConstraint("monto > 0", name="ck_pago_monto_positivo"),
        CheckConstraint(
            "fecha_fin_vencimiento >= fecha_inicio_vencimiento",
            name="ck_pago_rango_fechas",
        ),
    )

    id_pago: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"), nullable=False
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    fecha_pago: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fecha_inicio_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    metodo_pago: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="metodo_pago_enum"), nullable=False
    )
    usuario: Mapped[User] = relationship()


class Incident(Base):
    __tablename__ = "novedades"
    __table_args__ = (
        CheckConstraint("length(trim(descripcion)) > 0", name="ck_novedad_descripcion"),
    )

    id_novedad: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_registro: Mapped[int] = mapped_column(
        ForeignKey("registros_acceso.id_registro", ondelete="RESTRICT"), nullable=False
    )
    id_operador: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="RESTRICT"), nullable=False
    )
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    registro: Mapped[AccessRecord] = relationship(back_populates="novedades")
    operador: Mapped[User] = relationship()
