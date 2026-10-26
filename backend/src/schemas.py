from datetime import date, datetime
from decimal import Decimal
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.models import CellStatus, PaymentMethod, Role, UserStatus, VehicleType


class LoginInput(BaseModel):
    documento: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=128)


class UserCreate(BaseModel):
    documento: str = Field(min_length=1, max_length=20)
    nombre: str = Field(min_length=1, max_length=50)
    apellido: str = Field(min_length=1, max_length=50)
    telefono: str | None = Field(default=None, max_length=15)
    email: EmailStr | None = None
    password: str = Field(min_length=8, max_length=72)
    rol: Role

    @field_validator("password")
    @classmethod
    def password_size(cls, value: str) -> str:
        if len(value.encode()) > 72:
            raise ValueError("La contraseña no puede superar 72 bytes")
        return value


class UserUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=50)
    apellido: str | None = Field(default=None, min_length=1, max_length=50)
    telefono: str | None = Field(default=None, max_length=15)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)
    rol: Role | None = None
    estado: UserStatus | None = None

    @field_validator("password")
    @classmethod
    def password_size(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode()) > 72:
            raise ValueError("La contraseña no puede superar 72 bytes")
        return value


class UserOut(BaseModel):
    id_usuario: int
    documento: str
    nombre: str
    apellido: str
    telefono: str | None
    email: str | None
    rol: Role
    estado: UserStatus
    model_config = ConfigDict(from_attributes=True)


class VehicleCreate(BaseModel):
    placa: str = Field(min_length=1, max_length=6)
    tipo_vehiculo: VehicleType
    id_usuario: int
    marca: str | None = Field(default=None, max_length=30)
    modelo: str | None = Field(default=None, max_length=30)
    color: str | None = Field(default=None, max_length=20)

    @field_validator("placa")
    @classmethod
    def normalize_plate(cls, value: str) -> str:
        plate = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,6}", plate):
            raise ValueError("La placa solo puede contener letras y números, máximo 6 caracteres")
        return plate


class NewVehicleClient(BaseModel):
    documento: str = Field(min_length=1, max_length=20)

    nombre_completo: str = Field(min_length=3, max_length=101)

    @field_validator("nombre_completo")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        parts = value.split()
        if len(parts) < 2:
            raise ValueError("Ingresa el nombre y apellido completos del cliente")
        first_name = parts[0]
        surname = " ".join(parts[1:])
        if len(first_name) > 50 or len(surname) > 50:
            raise ValueError("El nombre y apellido no pueden superar 50 caracteres cada uno")
        return " ".join(parts)


class VehicleWithNewClientCreate(BaseModel):
    placa: str = Field(min_length=1, max_length=6)
    tipo_vehiculo: VehicleType
    marca: str | None = Field(default=None, max_length=30)
    modelo: str | None = Field(default=None, max_length=30)
    color: str | None = Field(default=None, max_length=20)
    cliente: NewVehicleClient

    @field_validator("placa")
    @classmethod
    def normalize_plate(cls, value: str) -> str:
        plate = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,6}", plate):
            raise ValueError("La placa solo puede contener letras y números, máximo 6 caracteres")
        return plate


class VehicleOut(BaseModel):
    id_vehiculo: int
    placa: str
    tipo_vehiculo: VehicleType
    marca: str | None
    modelo: str | None
    color: str | None
    id_usuario: int
    model_config = ConfigDict(from_attributes=True)


class VehicleWithNewClientOut(BaseModel):
    vehiculo: VehicleOut
    cliente: UserOut
    clave_temporal: str


class CellCreate(BaseModel):
    codigo_celda: str = Field(min_length=1, max_length=10)
    tipo_celda: VehicleType


class CellStatusUpdate(BaseModel):
    estado: CellStatus


class CellOut(BaseModel):
    id_celda: int
    codigo_celda: str
    tipo_celda: VehicleType
    estado: CellStatus
    model_config = ConfigDict(from_attributes=True)


class EntryInput(BaseModel):
    placa: str = Field(min_length=1, max_length=6)

    @field_validator("placa")
    @classmethod
    def normalize_plate(cls, value: str) -> str:
        plate = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,6}", plate):
            raise ValueError("La placa solo puede contener letras y números, máximo 6 caracteres")
        return plate


class ExitInput(EntryInput):
    pass


class PaymentCreate(BaseModel):
    id_usuario: int
    monto: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    meses: int = Field(default=1, ge=1, le=24)
    metodo_pago: PaymentMethod


class PaymentOut(BaseModel):
    id_pago: int
    id_usuario: int
    monto: Decimal
    fecha_pago: datetime
    fecha_inicio_vencimiento: date
    fecha_fin_vencimiento: date
    metodo_pago: PaymentMethod
    model_config = ConfigDict(from_attributes=True)


class IncidentCreate(BaseModel):
    id_registro: int
    descripcion: str = Field(min_length=1, max_length=5000)


class IncidentOut(BaseModel):
    id_novedad: int
    id_registro: int
    id_operador: int
    descripcion: str
    fecha_hora: datetime
    model_config = ConfigDict(from_attributes=True)


class AccessOut(BaseModel):
    id_registro: int
    id_vehiculo: int
    placa: str
    id_celda: int
    codigo_celda: str
    fecha_hora_ingreso: datetime
    fecha_hora_salida: datetime | None
    estado_registro: str
    model_config = ConfigDict(from_attributes=True)
