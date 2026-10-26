import calendar
import secrets
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from src.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)
from src.config import settings
from src.database import get_db
from src.models import (
    AccessRecord,
    AccessStatus,
    Cell,
    CellStatus,
    Incident,
    MonthlyPayment,
    PaymentMethod,
    Role,
    User,
    UserStatus,
    Vehicle,
)
from src.schemas import (
    AccessOut,
    CellCreate,
    CellOut,
    CellStatusUpdate,
    EntryInput,
    ExitInput,
    IncidentCreate,
    IncidentOut,
    LoginInput,
    PaymentCreate,
    PaymentOut,
    UserCreate,
    UserOut,
    UserUpdate,
    VehicleCreate,
    VehicleOut,
    VehicleWithNewClientCreate,
    VehicleWithNewClientOut,
)
from src.services.access import register_entry, register_exit

app = FastAPI(
    title="PARKEA API",
    description="API de gestión de parqueadero, accesos, mensualidades y novedades.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[User, Depends(require_roles(Role.ADMINISTRADOR))]
Staff = Annotated[User, Depends(require_roles(Role.ADMINISTRADOR, Role.OPERADOR))]
Authenticated = Annotated[User, Depends(get_current_user)]


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def translate_integrity_error(exc: IntegrityError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="El documento, correo, placa o código de celda ya está registrado",
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "PARKEA"}


@app.post("/api/auth/login")
def login(payload: LoginInput, db: Db):
    user = db.scalar(select(User).where(User.documento == payload.documento.strip()))
    if (
        user is None
        or user.estado != UserStatus.ACTIVO
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Documento o contraseña incorrectos")
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": UserOut.model_validate(user),
    }


@app.get("/api/auth/me", response_model=UserOut)
def me(current_user: Authenticated):
    return current_user


@app.get("/api/dashboard")
def dashboard(db: Db, current_user: Authenticated):
    today = date.today()
    if current_user.rol == Role.CLIENTE:
        return {
            "celdas_totales": 0,
            "celdas_ocupadas": 0,
            "ingresos_activos": db.scalar(
                select(func.count())
                .select_from(AccessRecord)
                .join(Vehicle)
                .where(
                    Vehicle.id_usuario == current_user.id_usuario,
                    AccessRecord.estado_registro == AccessStatus.INGRESO_ACTIVO,
                )
            )
            or 0,
            "mensualidades_vigentes": db.scalar(
                select(func.count())
                .select_from(MonthlyPayment)
                .where(
                    MonthlyPayment.id_usuario == current_user.id_usuario,
                    MonthlyPayment.fecha_inicio_vencimiento <= today,
                    MonthlyPayment.fecha_fin_vencimiento >= today,
                )
            )
            or 0,
        }
    return {
        "celdas_totales": db.scalar(select(func.count()).select_from(Cell)) or 0,
        "celdas_ocupadas": db.scalar(
            select(func.count()).select_from(Cell).where(Cell.estado == CellStatus.OCUPADA)
        )
        or 0,
        "ingresos_activos": db.scalar(
            select(func.count())
            .select_from(AccessRecord)
            .where(AccessRecord.estado_registro == AccessStatus.INGRESO_ACTIVO)
        )
        or 0,
        "mensualidades_vigentes": db.scalar(
            select(func.count())
            .select_from(MonthlyPayment)
            .where(
                MonthlyPayment.fecha_inicio_vencimiento <= today,
                MonthlyPayment.fecha_fin_vencimiento >= today,
            )
        )
        or 0,
    }


@app.get("/api/usuarios", response_model=list[UserOut])
def list_users(db: Db, _: Admin):
    return db.scalars(select(User).order_by(User.apellido, User.nombre)).all()


@app.get("/api/clientes", response_model=list[UserOut])
def list_clients(db: Db, _: Staff):
    return db.scalars(
        select(User)
        .where(User.rol == Role.CLIENTE, User.estado == UserStatus.ACTIVO)
        .order_by(User.apellido, User.nombre)
    ).all()


@app.post("/api/usuarios", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Db, _: Admin):
    user = User(
        documento=payload.documento.strip(),
        nombre=payload.nombre.strip(),
        apellido=payload.apellido.strip(),
        telefono=payload.telefono,
        email=str(payload.email).lower() if payload.email else None,
        password_hash=hash_password(payload.password),
        rol=payload.rol,
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise translate_integrity_error(exc) from exc
    return user


@app.patch("/api/usuarios/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Db, current_user: Admin):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    changes = payload.model_dump(exclude_unset=True)
    if user.id_usuario == current_user.id_usuario and (
        changes.get("estado") == UserStatus.INACTIVO
        or changes.get("rol") not in (None, Role.ADMINISTRADOR)
    ):
        raise HTTPException(status_code=409, detail="No puede desactivar ni cambiar su propio rol")
    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    if "email" in changes and changes["email"] is not None:
        changes["email"] = str(changes["email"]).lower()
    for field, value in changes.items():
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise translate_integrity_error(exc) from exc
    return user


@app.delete("/api/usuarios/{user_id}", status_code=204)
def deactivate_user(user_id: int, db: Db, current_user: Admin):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.id_usuario == current_user.id_usuario:
        raise HTTPException(status_code=409, detail="No puede desactivar su propio usuario")
    user.estado = UserStatus.INACTIVO
    db.commit()


@app.get("/api/vehiculos", response_model=list[VehicleOut])
def list_vehicles(db: Db, current_user: Authenticated, placa: str | None = None):
    query = select(Vehicle).order_by(Vehicle.placa)
    if current_user.rol == Role.CLIENTE:
        query = query.where(Vehicle.id_usuario == current_user.id_usuario)
    if placa:
        query = query.where(Vehicle.placa == placa.strip().upper())
    return db.scalars(query.limit(100)).all()


@app.post("/api/vehiculos", response_model=VehicleOut, status_code=201)
def create_vehicle(payload: VehicleCreate, db: Db, _: Admin):
    owner = db.get(User, payload.id_usuario)
    if owner is None or owner.rol != Role.CLIENTE:
        raise HTTPException(status_code=422, detail="El vehículo debe pertenecer a un cliente existente")
    vehicle = Vehicle(**payload.model_dump())
    try:
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
    except IntegrityError as exc:
        db.rollback()
        raise translate_integrity_error(exc) from exc
    return vehicle


@app.post(
    "/api/vehiculos/registro-completo",
    response_model=VehicleWithNewClientOut,
    status_code=201,
)
def create_vehicle_with_new_client(
    payload: VehicleWithNewClientCreate,
    db: Db,
    _: Admin,
):
    first_name, surname = payload.cliente.nombre_completo.split(maxsplit=1)
    temporary_password = secrets.token_urlsafe(18)
    client = User(
        documento=payload.cliente.documento.strip(),
        nombre=first_name,
        apellido=surname,
        password_hash=hash_password(temporary_password),
        rol=Role.CLIENTE,
        estado=UserStatus.ACTIVO,
    )
    vehicle_data = payload.model_dump(exclude={"cliente"})
    vehicle = Vehicle(**vehicle_data, usuario=client)
    try:
        db.add(vehicle)
        db.commit()
        db.refresh(client)
        db.refresh(vehicle)
    except IntegrityError as exc:
        db.rollback()
        raise translate_integrity_error(exc) from exc
    return {
        "vehiculo": vehicle,
        "cliente": client,
        "clave_temporal": temporary_password,
    }


@app.get("/api/celdas", response_model=list[CellOut])
def list_cells(db: Db, _: Authenticated):
    return db.scalars(select(Cell).order_by(Cell.codigo_celda)).all()


@app.post("/api/celdas", response_model=CellOut, status_code=201)
def create_cell(payload: CellCreate, db: Db, _: Admin):
    cell = Cell(
        codigo_celda=payload.codigo_celda.strip().upper(),
        tipo_celda=payload.tipo_celda,
    )
    try:
        db.add(cell)
        db.commit()
        db.refresh(cell)
    except IntegrityError as exc:
        db.rollback()
        raise translate_integrity_error(exc) from exc
    return cell


@app.patch("/api/celdas/{cell_id}", response_model=CellOut)
def update_cell(cell_id: int, payload: CellStatusUpdate, db: Db, _: Admin):
    cell = db.scalar(select(Cell).where(Cell.id_celda == cell_id).with_for_update())
    if cell is None:
        raise HTTPException(status_code=404, detail="Celda no encontrada")
    if payload.estado == CellStatus.OCUPADA:
        raise HTTPException(status_code=409, detail="Las celdas se ocupan únicamente al registrar un ingreso")
    if payload.estado == CellStatus.DISPONIBLE and db.scalar(
        select(AccessRecord.id_registro).where(
            AccessRecord.id_celda == cell_id,
            AccessRecord.estado_registro == AccessStatus.INGRESO_ACTIVO,
        )
    ):
        raise HTTPException(status_code=409, detail="No se puede liberar una celda con un ingreso activo")
    cell.estado = payload.estado
    db.commit()
    db.refresh(cell)
    return cell


@app.post("/api/accesos/entrada", response_model=AccessOut, status_code=201)
def entry(payload: EntryInput, db: Db, operator: Staff):
    try:
        record = register_entry(db, payload.placa, operator.id_usuario)
        db.commit()
        db.refresh(record)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="El vehículo ya tiene un ingreso activo") from exc
    return {
        "id_registro": record.id_registro,
        "id_vehiculo": record.id_vehiculo,
        "placa": payload.placa,
        "id_celda": record.id_celda,
        "codigo_celda": record.celda.codigo_celda,
        "fecha_hora_ingreso": record.fecha_hora_ingreso,
        "fecha_hora_salida": None,
        "estado_registro": record.estado_registro.value,
    }


@app.post("/api/accesos/salida")
def exit_access(payload: ExitInput, db: Db, operator: Staff):
    record, minutes = register_exit(db, payload.placa, operator.id_usuario)
    db.commit()
    db.refresh(record)
    return {
        "id_registro": record.id_registro,
        "placa": record.vehiculo.placa,
        "codigo_celda": record.celda.codigo_celda,
        "fecha_hora_salida": record.fecha_hora_salida,
        "minutos_permanencia": minutes,
        "horas_permanencia": round(minutes / 60, 2),
        "estado_registro": record.estado_registro.value,
    }


@app.get("/api/accesos/activos", response_model=list[AccessOut])
def active_accesses(db: Db, current_user: Authenticated):
    query = (
        select(AccessRecord)
        .options(joinedload(AccessRecord.vehiculo), joinedload(AccessRecord.celda))
        .where(AccessRecord.estado_registro == AccessStatus.INGRESO_ACTIVO)
        .order_by(AccessRecord.fecha_hora_ingreso.desc())
    )
    if current_user.rol == Role.CLIENTE:
        query = query.join(Vehicle).where(Vehicle.id_usuario == current_user.id_usuario)
    records = db.scalars(query).all()
    return [
        {
            "id_registro": record.id_registro,
            "id_vehiculo": record.id_vehiculo,
            "placa": record.vehiculo.placa,
            "id_celda": record.id_celda,
            "codigo_celda": record.celda.codigo_celda,
            "fecha_hora_ingreso": record.fecha_hora_ingreso,
            "fecha_hora_salida": record.fecha_hora_salida,
            "estado_registro": record.estado_registro.value,
        }
        for record in records
    ]


@app.get("/api/pagos", response_model=list[PaymentOut])
def list_payments(db: Db, current_user: Authenticated):
    query = select(MonthlyPayment).order_by(MonthlyPayment.fecha_pago.desc())
    if current_user.rol == Role.CLIENTE:
        query = query.where(MonthlyPayment.id_usuario == current_user.id_usuario)
    return db.scalars(query.limit(100)).all()


@app.post("/api/pagos", response_model=PaymentOut, status_code=201)
def create_payment(payload: PaymentCreate, db: Db, _: Staff):
    try:
        user = db.scalar(
            select(User).where(User.id_usuario == payload.id_usuario).with_for_update()
        )
        if user is None or user.rol != Role.CLIENTE or user.estado != UserStatus.ACTIVO:
            raise HTTPException(status_code=404, detail="No se encontró un cliente activo")
        today = date.today()
        latest_end = db.scalar(
            select(func.max(MonthlyPayment.fecha_fin_vencimiento)).where(
                MonthlyPayment.id_usuario == user.id_usuario
            )
        )
        start = max(today, latest_end + timedelta(days=1)) if latest_end and latest_end >= today else today
        payment = MonthlyPayment(
            id_usuario=user.id_usuario,
            monto=payload.monto,
            fecha_inicio_vencimiento=start,
            fecha_fin_vencimiento=add_months(start, payload.meses) - timedelta(days=1),
            metodo_pago=payload.metodo_pago,
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo guardar el pago") from exc
    return payment


@app.get("/api/novedades", response_model=list[IncidentOut])
def list_incidents(db: Db, _: Staff):
    return db.scalars(select(Incident).order_by(Incident.fecha_hora.desc()).limit(100)).all()


@app.post("/api/novedades", response_model=IncidentOut, status_code=201)
def create_incident(payload: IncidentCreate, db: Db, operator: Staff):
    record = db.get(AccessRecord, payload.id_registro)
    if record is None:
        raise HTTPException(status_code=404, detail="No se encontró el registro de acceso")
    incident = Incident(
        id_registro=payload.id_registro,
        id_operador=operator.id_usuario,
        descripcion=payload.descripcion.strip(),
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident
