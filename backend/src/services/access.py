from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from src.models import (
    AccessRecord,
    AccessStatus,
    Cell,
    CellStatus,
    MonthlyPayment,
    Role,
    User,
    UserStatus,
    Vehicle,
)


def _exit_time_and_minutes(entered_at: datetime, now: datetime) -> tuple[datetime, int]:
    if entered_at.tzinfo is None:
        entered_at = entered_at.replace(tzinfo=now.tzinfo)
        exit_at = now.replace(tzinfo=None)
    else:
        exit_at = now

    elapsed = max(0, int((now - entered_at).total_seconds() // 60))
    return exit_at, elapsed


def register_entry(db: Session, plate: str, operator_id: int) -> AccessRecord:
    vehicle = db.scalar(
        select(Vehicle).where(Vehicle.placa == plate).with_for_update()
    )
    if vehicle is None:
        raise HTTPException(status_code=404, detail="No existe un vehículo con esa placa")

    owner = db.get(User, vehicle.id_usuario)
    if owner is None or owner.estado != UserStatus.ACTIVO or owner.rol != Role.CLIENTE:
        raise HTTPException(status_code=409, detail="El cliente está inactivo")

    today = datetime.now(timezone.utc).date()
    active_payment = db.scalar(
        select(MonthlyPayment.id_pago)
        .where(
            MonthlyPayment.id_usuario == vehicle.id_usuario,
            MonthlyPayment.fecha_inicio_vencimiento <= today,
            MonthlyPayment.fecha_fin_vencimiento >= today,
        )
        .limit(1)
    )
    if active_payment is None:
        raise HTTPException(status_code=403, detail="El cliente no tiene mensualidad vigente")

    if db.scalar(
        select(AccessRecord.id_registro).where(
            AccessRecord.id_vehiculo == vehicle.id_vehiculo,
            AccessRecord.estado_registro == AccessStatus.INGRESO_ACTIVO,
        )
    ):
        raise HTTPException(status_code=409, detail="El vehículo ya se encuentra dentro")

    cell = db.scalar(
        select(Cell)
        .where(
            Cell.tipo_celda == vehicle.tipo_vehiculo,
            Cell.estado == CellStatus.DISPONIBLE,
        )
        .order_by(Cell.codigo_celda)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if cell is None:
        raise HTTPException(status_code=409, detail="No hay celdas disponibles para este vehículo")

    cell.estado = CellStatus.OCUPADA
    record = AccessRecord(
        vehiculo=vehicle,
        celda=cell,
        id_operador_ingreso=operator_id,
        estado_registro=AccessStatus.INGRESO_ACTIVO,
    )
    db.add(record)
    db.flush()
    return record


def register_exit(db: Session, plate: str, operator_id: int) -> tuple[AccessRecord, int]:
    record = db.scalar(
        select(AccessRecord)
        .join(Vehicle)
        .options(joinedload(AccessRecord.celda), joinedload(AccessRecord.vehiculo))
        .where(
            Vehicle.placa == plate,
            AccessRecord.estado_registro == AccessStatus.INGRESO_ACTIVO,
        )
        .with_for_update(of=AccessRecord)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="No se encontró un ingreso activo para esa placa")

    cell = db.scalar(select(Cell).where(Cell.id_celda == record.id_celda).with_for_update())
    now = db.scalar(select(func.now()))
    if now is None:
        raise RuntimeError("No fue posible obtener la hora actual de la base de datos")
    exit_at, elapsed = _exit_time_and_minutes(record.fecha_hora_ingreso, now)
    record.fecha_hora_salida = exit_at
    record.id_operador_salida = operator_id
    record.estado_registro = AccessStatus.FINALIZADO
    cell.estado = CellStatus.DISPONIBLE
    return record, elapsed
