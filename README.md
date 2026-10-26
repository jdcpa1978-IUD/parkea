# PARKEA

Aplicación inicial de gestión de parqueadero con **Angular**, **FastAPI (Python)** y **PostgreSQL**. Incluye control de accesos con mensualidad vigente, mapa de celdas, usuarios y roles, vehículos, pagos e incidentes.

## Estructura

```text
parkea_app/
├── backend/                 # API FastAPI, modelos y autenticación
│   ├── scripts/              # Alta segura del primer administrador
│   ├── src/main.py           # Endpoints REST
│   ├── src/services/         # Reglas transaccionales de negocio
│   └── test/
├── database/schema.sql       # Esquema PostgreSQL e inicialización de celdas
├── frontend/                 # Aplicación Angular
└── docker-compose.yml        # PostgreSQL 16 para desarrollo local
```

## Requisitos

- Python 3.11 o superior.
- Node.js 24.15 o superior (o 22.22.3 o superior) y npm.
- Docker Desktop con Docker Compose, o una instancia PostgreSQL 14 o superior.

## Arranque en Windows

Abre PowerShell en `Documentos\parkea_app`.

### 1. Inicializar PostgreSQL

```powershell
docker compose up -d postgres
```

En una base nueva, Docker aplica `database\schema.sql` y crea celdas de ejemplo. El usuario, contraseña y base `parkea` del Compose son solamente para desarrollo local.

Si usas PostgreSQL externo, ejecuta `database\schema.sql` con `psql` y configura su cadena de conexión en `backend\.env`. Para la instancia de pgAdmin de la captura, usa tu usuario PostgreSQL, la base existente `Datasistempark` y la contraseña que configuraste localmente; no compartas esa contraseña. Si contiene caracteres especiales, codifícalos para una URL.

Para alinear una base `Datasistempark` ya existente sin recrearla, primero detén el backend y crea una copia de seguridad. En pgAdmin, selecciona esa base, abre **Query Tool**, carga `database\migrations\001_align_existing_schema.sql` y ejecútalo una sola vez. La migración conserva los datos, interpreta las fechas existentes como hora local de Bogotá, limita las placas a seis caracteres alfanuméricos y añade las restricciones e índices que faltaban. Los clientes continúan almacenándose en `usuarios` con rol `CLIENTE`; esta migración no crea una tabla `clientes`.

### 2. Configurar y arrancar el backend

```powershell
Copy-Item backend\.env.example backend\.env
$jwtKey = python -c "import secrets; print(secrets.token_urlsafe(48))"
(Get-Content backend\.env) -replace '^JWT_SECRET_KEY=.*$', "JWT_SECRET_KEY=$jwtKey" | Set-Content backend\.env
Set-Location backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn src.main:app --reload
```

La API se sirve en `http://localhost:8000`; la documentación interactiva está en `http://localhost:8000/docs`. El esquema se instala desde el script SQL antes de arrancar la API.

### 3. Crear el administrador inicial

En otra terminal, desde `Documentos\parkea_app`:

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
python scripts\create_admin.py
```

El comando solicita documento, nombre y contraseña sin mostrarla. Solo permite crear el primer administrador.

### 4. Arrancar Angular

En otra terminal:

```powershell
Set-Location frontend
npm install
npm start
```

Abre `http://localhost:4200` e inicia sesión con el administrador creado. Desde la aplicación puedes registrar operadores, clientes, sus vehículos, celdas, mensualidades e incidentes. En **Vehículos**, el formulario permite asociar un cliente existente o registrar en una sola transacción un cliente nuevo junto con su vehículo. El alta conjunta solo solicita documento y nombre completo; genera una clave inicial aleatoria, la guarda con BCrypt y se la muestra al administrador una sola vez para compartirla con el cliente.

## Roles y operaciones

- **Administrador:** administra usuarios, vehículos y celdas; consulta y opera todas las funciones.
- **Operador:** registra entradas y salidas, consulta celdas, registra pagos y novedades.
- **Cliente:** consulta sus vehículos, sus pagos y sus accesos; el resto de clientes y las operaciones internas quedan restringidos.

Para una entrada, la API valida cliente activo y mensualidad vigente, bloquea el vehículo y la plaza durante la transacción y registra el ingreso. La salida finaliza la estancia y libera la plaza en la misma transacción. Las mensualidades se encadenan desde el vencimiento vigente y ajustan el último día a la longitud real del mes. Índices únicos parciales impiden más de un ingreso activo por vehículo o celda.

## API principal

| Método | Ruta | Acceso |
|---|---|---|
| POST | `/api/auth/login` | Público |
| GET | `/api/auth/me` | Autenticado |
| GET | `/api/dashboard` | Autenticado |
| GET / POST / PATCH / DELETE | `/api/usuarios` | Administrador |
| GET | `/api/clientes` | Administrador u operador |
| GET / POST | `/api/vehiculos` | Lectura según rol; alta administrador |
| GET / POST / PATCH | `/api/celdas` | Lectura autenticada; cambios administrador |
| POST | `/api/accesos/entrada` | Administrador u operador |
| POST | `/api/accesos/salida` | Administrador u operador |
| GET | `/api/accesos/activos` | Consulta autenticada, limitada al propio cliente |
| GET / POST | `/api/pagos` | Lectura propia o de operación; alta administrador u operador |
| GET / POST | `/api/novedades` | Administrador u operador |

Las búsquedas exactas por placa usan un índice. La placa acepta únicamente de 1 a 6 caracteres alfanuméricos y se normaliza a mayúsculas tanto en la interfaz como en la API. La API devuelve errores de validación y conflictos con códigos HTTP explícitos.

## Pruebas

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s test -v
```

## Notas antes de producción

Configura `DATABASE_URL`, `JWT_SECRET_KEY` (mínimo 32 bytes) y `CORS_ORIGINS` según el entorno. No publiques el `.env` ni uses las credenciales de desarrollo de Docker en producción. Despliega detrás de HTTPS, añade migraciones versionadas, copias de seguridad y auditoría, y mueve la sesión del navegador a cookies `HttpOnly`, `Secure` y `SameSite` antes de manejar información real de clientes.
