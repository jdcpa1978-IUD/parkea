import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.auth import hash_password
from src.database import SessionLocal
from src.models import Role, User, UserStatus


def prompt(label: str, max_length: int) -> str:
    value = input(label).strip()
    if not value or len(value) > max_length:
        raise ValueError(f"El valor debe tener entre 1 y {max_length} caracteres")
    return value


def main():
    documento = prompt("Documento del administrador: ", 20)
    nombre = prompt("Nombre: ", 50)
    apellido = prompt("Apellido: ", 50)
    email = input("Correo (opcional): ").strip().lower() or None
    if email and (len(email) > 100 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)):
        raise ValueError("El correo no es válido")
    password = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
    if len(password) < 12 or len(password.encode()) > 72:
        raise ValueError("La contraseña debe tener entre 12 y 72 bytes")

    with SessionLocal.begin() as db:
        if db.scalar(select(User.id_usuario).where(User.rol == Role.ADMINISTRADOR)):
            raise ValueError("Ya existe un administrador; no se creó otro")
        db.add(
            User(
                documento=documento,
                nombre=nombre,
                apellido=apellido,
                email=email,
                password_hash=hash_password(password),
                rol=Role.ADMINISTRADOR,
                estado=UserStatus.ACTIVO,
            )
        )
    print("Administrador creado correctamente.")


if __name__ == "__main__":
    main()
