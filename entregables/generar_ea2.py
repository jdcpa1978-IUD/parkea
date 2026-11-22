from pathlib import Path
import tempfile

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as PdfImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent
DOCX_PATH = ROOT / "Pineda_Jose_EA2.docx"
PDF_PATH = ROOT / "Pineda_Jose_EA2.pdf"
IMAGE_DIR = None

NAVY = "#172554"
BLUE = "#2563eb"
INK = "#0f172a"
MUTED = "#64748b"
PALE = "#f3f5f9"

USERS_REQUIREMENTS = [
    ["ID", "Requerimiento funcional", "Aceptación / evidencia"],
    ["RF-U01", "El administrador inicia sesión y gestiona las cuentas. Solo el administrador puede consultar el directorio, crear, editar o desactivar usuarios.", "Rutas protegidas por JWT y rol ADMINISTRADOR; operador/cliente rechazados."],
    ["RF-U02", "Consultar directorio con documento, nombre, correo, rol y estado.", "Ordenado por apellido/nombre; respuesta sin password_hash."],
    ["RF-U03", "Crear usuario con documento, nombre, apellido, contraseña y rol; correo/teléfono opcionales.", "Cuenta activa creada; contraseña guardada como hash BCrypt."],
    ["RF-U04", "Documento y correo (si se suministra) son únicos.", "Duplicado devuelve conflicto; transacción revertida."],
    ["RF-U05", "Actualizar datos permitidos y, opcionalmente, contraseña.", "Campo de contraseña vacío/omitido conserva la contraseña actual; nueva contraseña se procesa con BCrypt."],
    ["RF-U06", "Desactivar usuario sin borrado físico.", "Cuenta pasa a INACTIVO; el administrador no puede desactivarse ni cambiar su propio rol."],
]

CELL_REQUIREMENTS = [
    ["ID", "Requerimiento funcional", "Aceptación / evidencia"],
    ["RF-C01", "Usuarios autenticados consultan mapa ordenado por código con tipo y estado de celda.", "La lectura del mapa es independiente de las operaciones de asignación y liberación."],
    ["RF-C02", "El administrador registra celdas con código y tipo.", "Código único; duplicado se rechaza sin crear otra fila."],
    ["RF-C03", "El mapa muestra leyenda, detalle y actualización automática en un máximo de 15 segundos.", "Tipo/estado textual además del color; prueba visual de 15 s pendiente."],
    ["RF-C04", "El administrador programa mantenimiento y habilita celdas.", "Una celda ocupada puede programarse para mantenimiento; permanece fuera de servicio tras la salida."],
    ["RF-C05", "Entrada y salida controlan la ocupación.", "Solo la entrada asigna celda disponible compatible; solo la salida libera. No se libera manualmente una celda con acceso activo."],
]

NFR = [
    ["ID", "Requerimiento no funcional"],
    ["RNF-01 Seguridad", "Token JWT vigente para operaciones privadas; administrador requerido para gestión de cuentas y cambios de celdas; operadores/clientes no ejecutan cambios no autorizados."],
    ["RNF-02 Credenciales", "Contraseñas guardadas con BCrypt; hashes y contraseñas no aparecen en respuestas."],
    ["RNF-03 Integridad", "Restricciones únicas y transacciones evitan duplicados y cambios parciales; rechazos cierran con ROLLBACK."],
    ["RNF-04 Usabilidad", "Interfaz en español, estados etiquetados con texto/color y errores explícitos."],
    ["RNF-05 Actualización", "El mapa debe reflejar estado actualizado en un ciclo de hasta 15 segundos (pendiente de medir en navegador)."],
    ["RNF-06 Rendimiento", "Meta propuesta, pendiente de medir: percentil 95 menor a 2 segundos con hasta 500 registros."],
    ["RNF-07 Compatibilidad", "Meta por validar: Chrome/Edge vigentes y ancho entre 360–1920 px."],
    ["RNF-08 Errores", "Validación, autorización, ausencia y unicidad presentan HTTP apropiado y mensaje comprensible; un rechazo no confirma cambios."],
]

TESTS = [
    ["ID", "Ejecución / datos", "Resultado esperado", "Resultado obtenido"],
    ["PT-U01", "Crear usuario con documento nuevo y rol OPERADOR.", "Usuario activo; hash BCrypt; no se expone el hash.", "PASA — unit test con sesión simulada; usuario/hash/rol y commit verificados."],
    ["PT-U02", "Crear usuario con documento duplicado.", "Conflicto y rollback; sin cuenta parcial.", "PASA — IntegrityError simulado; rollback verificado. Unicidad con PostgreSQL pendiente."],
    ["PT-U03", "Correo duplicado al crear/editar.", "Conflicto; datos originales intactos.", "PENDIENTE — requiere verificación funcional en PostgreSQL."],
    ["PT-U04", "Editar datos sin enviar contraseña.", "Campos cambian y hash actual se conserva.", "PASA — test_update_without_password_preserves_hash."],
    ["PT-U05", "Operador/cliente intenta administrar usuarios.", "HTTP 403; sin cambios.", "PENDIENTE — revisar con cuentas por rol en ejecución HTTP."],
    ["PT-U06", "Auto-cambio de rol/estado; desactivar otro; probar login inactivo.", "Autoprotección rechazada con rollback; otro usuario queda INACTIVO y no inicia sesión.", "PASA parcial — rechazo/desactivación en unit test; login inactivo con API real pendiente."],
    ["PT-C01", "Operador/cliente/admin consultan mapa.", "Lectura permitida; contenido, detalle y controles visuales según rol.", "PENDIENTE — verificación visual con API y base activas."],
    ["PT-C02", "Crear celda con código y tipo válidos.", "Código normalizado y celda creada.", "PASA — test_create_cell_normalizes_code (sesión simulada)."],
    ["PT-C03", "Crear celda con código existente.", "Conflicto y rollback, sin duplicado.", "PASA — IntegrityError simulado; PostgreSQL real pendiente."],
    ["PT-C04", "Intentar ocupar/liberar manualmente una celda con acceso activo.", "Rechazo; estado y acceso no cambian; rollback.", "PASA — test_active_cell_cannot_be_released_manually."],
    ["PT-C05", "Marcar celda ocupada para mantenimiento y registrar salida.", "La celda se mantiene en MANTENIMIENTO al salir.", "PASA — test_occupied_cell_can_be_marked_for_maintenance y prueba de salida."],
    ["PT-C06", "Registrar salida de celda normal y de celda en mantenimiento.", "Normal vuelve DISPONIBLE; mantenimiento permanece no disponible.", "PASA — pruebas de ciclo de disponibilidad de celdas."],
    ["PT-C07", "Consultar resumen con accesos activos.", "Ocupación del tablero corresponde a estancias activas.", "PASA — test_dashboard_counts_active_accesses_as_occupied_cells."],
    ["PT-C08", "Cambiar estado y observar mapa sin recargar.", "Cambio visible en máximo 15 segundos.", "PENDIENTE — requiere medir refresco en navegador conectado a API."],
]

PENDING = [
    ["Caso pendiente", "Evidencia necesaria", "Motivo / estado"],
    ["PT-U03: unicidad real de correo/documento", "Captura de respuesta 409 y directorio sin cambios en PostgreSQL.", "No se ejecutó contra base activa; no está disponible Docker en este entorno."],
    ["PT-U05/PT-U06: permisos y login de cuenta inactiva", "Capturas de 403, 409 y 401 usando administrador, operador y usuario inactivo.", "La autorización está en código; falta prueba HTTP funcional con cuentas de prueba."],
    ["PT-C01: roles y mapa gráfico", "Capturas del mapa por rol, leyenda, detalle y controles admin ocultos para operador/cliente.", "Mockup de diseño incluido; no es una captura de ejecución."],
    ["PT-C03: unicidad de celda en PostgreSQL", "Respuesta 409 más mapa mostrando una sola celda.", "La prueba automatizada usa IntegrityError simulado."],
    ["PT-C08: refresco de 15 segundos", "Video/captura con hora de cambio y actualización de mapa sin recargar.", "El build Angular pasa; falta medir contra API/base activa."],
]


def fnt(size, bold=False):
    p = Path("C:/Windows/Fonts") / ("arialbd.ttf" if bold else "arial.ttf")
    try:
        return ImageFont.truetype(str(p), size)
    except OSError:
        return ImageFont.load_default()


def text(draw, xy, value, size=15, color=INK, bold=False):
    draw.text(xy, value, fill=color, font=fnt(size, bold))


def new_image(width, height):
    image = Image.new("RGB", (width, height), PALE)
    return image, ImageDraw.Draw(image)


def label_box(d, x, y, w, h, title, body="", fill="#ffffff", stroke="#cbd5e1"):
    d.rounded_rectangle((x, y, x + w, y + h), 12, fill=fill, outline=stroke, width=2)
    text(d, (x + 14, y + 12), title, 15, NAVY, True)
    if body:
        text(d, (x + 14, y + 38), body, 11, MUTED)


def make_mockup_users():
    im, d = new_image(1200, 800)
    d.rectangle((0, 0, 1200, 68), fill=NAVY)
    text(d, (30, 20), "PARKEA", 24, "#fff", True)
    text(d, (130, 25), "Gestión de parqueadero", 14, "#cbd5e1")
    d.rectangle((0, 68, 220, 800), fill="#fff")
    for y, t in [(115, "MENÚ PRINCIPAL"), (165, "Resumen general"), (210, "Entradas y salidas"),
                 (255, "Usuarios"), (300, "Mapa de celdas")]:
        text(d, (28, y), t, 14, MUTED if y == 115 else "#475569", y == 115)
    d.rounded_rectangle((12, 237, 208, 279), 8, fill="#eff6ff")
    text(d, (28, 248), "Usuarios", 14, BLUE, True)
    text(d, (252, 100), "ADMINISTRACIÓN / CUENTAS", 12, MUTED, True)
    text(d, (252, 126), "Gestión de usuarios", 27, INK, True)
    label_box(d, 252, 182, 914, 235, "Directorio", "Documento · Nombre · Correo · Rol · Estado · Acciones")
    d.rectangle((278, 235, 1140, 273), fill="#f8fafc")
    for x, t in [(290, "DOC."), (410, "NOMBRE"), (605, "CORREO"), (790, "ROL"), (900, "ESTADO"), (1030, "ACCIÓN")]:
        text(d, (x, 247), t, 11, "#475569", True)
    d.line((278, 275, 1140, 275), fill="#e2e8f0", width=2)
    for row, y in [(["•••456", "Cliente de prueba", "c•••@ejemplo.test", "CLIENTE", "ACTIVO", "Editar"], 286),
                   (["•••982", "Operador de prueba", "—", "OPERADOR", "INACTIVO", "Editar"], 329)]:
        for (x, _), v in zip([(290, ""), (410, ""), (605, ""), (790, ""), (900, ""), (1030, "")], row):
            text(d, (x, y), v, 11, "#334155")
    label_box(d, 252, 435, 914, 315, "Editar usuario · •••456", "Datos de ejemplo, no pertenecen a una persona real.")
    for x, y, title, value in [(278, 495, "NOMBRE", "Cliente"), (713, 495, "APELLIDO", "De prueba"),
                               (278, 570, "ROL", "CLIENTE ▾"), (713, 570, "ESTADO", "ACTIVO ▾"),
                               (278, 645, "CONTRASEÑA NUEVA (OPCIONAL)", "Vacía = conservar contraseña actual")]:
        text(d, (x, y), title, 11, "#334155", True)
        d.rounded_rectangle((x, y + 18, x + 405, y + 57), 5, fill="#fff", outline="#cbd5e1", width=2)
        text(d, (x + 12, y + 29), value, 12, "#475569")
    d.rounded_rectangle((713, 681, 890, 723), 7, fill=BLUE)
    text(d, (733, 694), "Guardar cambios", 13, "#fff", True)
    text(d, (912, 694), "Desactivar: confirmar acción", 11, MUTED)
    path = IMAGE_DIR / "mockup_usuarios.png"
    im.save(path)
    return path


def make_mockup_cells():
    im, d = new_image(1200, 800)
    d.rectangle((0, 0, 1200, 68), fill=NAVY)
    text(d, (30, 20), "PARKEA", 24, "#fff", True)
    text(d, (130, 25), "Administrador · Mapa de celdas", 14, "#cbd5e1")
    d.rectangle((0, 68, 220, 800), fill="#fff")
    for y, t in [(115, "MENÚ PRINCIPAL"), (165, "Resumen"), (210, "Accesos"),
                 (255, "Mapa de celdas"), (300, "Usuarios")]:
        text(d, (28, y), t, 14, MUTED if y == 115 else "#475569", y == 115)
    d.rounded_rectangle((12, 237, 208, 279), 8, fill="#eff6ff")
    text(d, (28, 248), "Mapa de celdas", 14, BLUE, True)
    text(d, (252, 100), "OPERACIÓN / CONSULTA", 12, MUTED, True)
    text(d, (252, 126), "Mapa de celdas", 27, INK, True)
    text(d, (252, 158), "Consulta estado y detalle. El mapa no asigna ni libera espacios.", 13, MUTED)
    label_box(d, 252, 185, 914, 68, "Leyenda", "● Disponible     ● Ocupada     ● Mantenimiento")
    d.ellipse((278, 222, 296, 240), fill="#22c55e")
    d.ellipse((427, 222, 445, 240), fill="#f59e0b")
    d.ellipse((545, 222, 563, 240), fill="#ef4444")
    label_box(d, 252, 270, 585, 470, "Celdas · automóviles y motocicletas")
    label_box(d, 856, 270, 310, 470, "Detalle de celda", "El panel cambia al seleccionar una celda.")
    cells = [
        (278, 330, "A-01", "DISPONIBLE", "#f0fdf4", "#86efac"),
        (455, 330, "A-02", "OCUPADA", "#fffbeb", "#fcd34d"),
        (632, 330, "A-03", "OCUPADA · MANT. AL SALIR", "#fff7ed", "#fdba74"),
        (278, 490, "M-01", "DISPONIBLE", "#f0fdf4", "#86efac"),
        (455, 490, "M-02", "MANTENIMIENTO", "#fef2f2", "#fca5a5"),
    ]
    for x, y, code, status, fill, stroke in cells:
        d.rounded_rectangle((x, y, x + 160, y + 115), 9, fill=fill, outline=stroke, width=2)
        text(d, (x + 15, y + 18), code, 20, INK, True)
        text(d, (x + 13, y + 57), status[:19], 10, "#475569", True)
    text(d, (880, 348), "A-03 · Automóvil", 17, NAVY, True)
    text(d, (880, 390), "Placa de prueba · ingreso 08:32", 11, "#334155")
    text(d, (880, 437), "Programar mantenimiento al salir", 11, "#334155")
    text(d, (880, 475), "Solo administrador", 10, MUTED)
    text(d, (880, 535), "Operador/cliente: lectura y detalle.", 11, MUTED)
    text(d, (880, 570), "La entrada asigna celda compatible;", 11, MUTED)
    text(d, (880, 590), "la salida la libera o conserva", 11, MUTED)
    text(d, (880, 610), "MANTENIMIENTO programado.", 11, MUTED)
    text(d, (278, 710), "OCUPADA deriva de una estancia activa; no se cambia desde el mapa.", 12, MUTED)
    path = IMAGE_DIR / "mockup_celdas.png"
    im.save(path)
    return path


def make_use_case(kind):
    im, d = new_image(1100, 560)
    d.rounded_rectangle((255, 35, 1070, 520), 8, fill="#fff", outline="#334155", width=3)
    title = "PARKEA · GESTIÓN DE USUARIOS" if kind == "users" else "PARKEA · GESTIÓN DE CELDAS"
    text(d, (460, 48), title, 18, NAVY, True)
    actors = [("Administrador", 175), ("Operador", 310), ("Cliente", 425)]
    for label, y in actors:
        d.ellipse((40, y, 80, y + 40), outline="#334155", width=2)
        d.line((60, y + 40, 60, y + 90), fill="#334155", width=2)
        d.line((30, y + 57, 90, y + 57), fill="#334155", width=2)
        d.line((60, y + 90, 35, y + 125), fill="#334155", width=2)
        d.line((60, y + 90, 85, y + 125), fill="#334155", width=2)
        text(d, (15, y + 128), label, 12, INK, True)
    if kind == "users":
        nodes = [
            (340, 125, "Consultar directorio"),
            (680, 125, "Registrar usuario"),
            (340, 245, "Actualizar usuario"),
            (680, 245, "Cambiar contraseña (opcional)"),
            (340, 365, "Desactivar usuario"),
            (680, 365, "Validar rol / unicidad / BCrypt"),
        ]
    else:
        nodes = [
            (340, 125, "Consultar mapa (solo lectura)"),
            (680, 125, "Registrar celda"),
            (340, 245, "Ver detalle (extiende consulta)"),
            (680, 245, "Mantenimiento / habilitar"),
            (340, 365, "Registrar entrada"),
            (680, 365, "Asignar celda compatible"),
        ]
        d.rounded_rectangle((340, 435, 610, 485), 8, fill="#fef2f2", outline="#fca5a5")
        text(d, (360, 452), "Registrar salida → liberar", 12, INK, True)
        d.rounded_rectangle((680, 435, 980, 485), 8, fill="#fff7ed", outline="#fdba74")
        text(d, (695, 452), "O conservar MANTENIMIENTO", 12, INK, True)
    for x, y, label in nodes:
        d.ellipse((x, y, x + 290, y + 66), fill="#eff6ff", outline=BLUE, width=2)
        text(d, (x + 15, y + 24), label, 12, INK, True)
    d.line((90, 205, 340, 158), fill="#64748b", width=2)
    d.line((90, 205, 680, 158), fill="#64748b", width=2)
    if kind == "users":
        d.line((90, 330, 340, 278), fill="#64748b", width=2)
        d.line((90, 330, 340, 398), fill="#64748b", width=2)
        d.line((630, 278, 680, 158), fill=BLUE, width=2)
        d.line((680, 278, 825, 245), fill=BLUE, width=2)
        text(d, (696, 212), "<<extend>> si se proporciona contraseña nueva", 10, BLUE)
        text(d, (345, 485), "Solo administrador · cambio vacío conserva contraseña actual", 11, MUTED)
    else:
        d.line((90, 330, 340, 278), fill="#64748b", width=2)
        d.line((90, 330, 340, 398), fill="#64748b", width=2)
        d.line((90, 445, 340, 398), fill="#64748b", width=2)
        d.line((630, 398, 680, 278), fill=BLUE, width=2)
        text(d, (630, 320), "<<include>> desde Registrar entrada", 10, BLUE)
    path = IMAGE_DIR / f"casos_{kind}.png"
    im.save(path)
    return path


def make_sequence(kind):
    im, d = new_image(1200, 720)
    labels = ["Actor", "Angular", "FastAPI/Auth", "Servicio", "PostgreSQL"]
    xs = [100, 330, 565, 800, 1070]
    for x, label in zip(xs, labels):
        d.rounded_rectangle((x - 86, 20, x + 86, 68), 8, fill="#eff6ff", outline=BLUE, width=2)
        text(d, (x - 55, 37), label, 13, NAVY, True)
        d.line((x, 68, x, 690), fill="#94a3b8", width=2)
    if kind == "users":
        actions = [
            (100, 330, "POST /auth/login: documento + contraseña"),
            (330, 565, "ApiService envía solicitud"),
            (565, 1070, "Buscar cuenta + validar BCrypt"),
            (565, 330, "200 JWT o 401 sin token"),
            (100, 330, "GET /usuarios + Bearer token"),
            (330, 565, "Solicitud con sesión"),
            (565, 800, "Validar JWT y rol ADMIN"),
            (800, 1070, "BEGIN; validar / actualizar"),
            (800, 1070, "COMMIT éxito / ROLLBACK rechazo"),
            (565, 330, "201/200/204 o 403/409"),
            (330, 100, "Refrescar datos / mostrar error"),
        ]
    elif kind == "access":
        actions = [
            (100, 330, "POST /auth/login: documento + contraseña"),
            (330, 565, "ApiService envía solicitud"),
            (565, 1070, "Buscar cuenta + validar BCrypt"),
            (565, 330, "200 JWT o 401 sin token"),
            (100, 330, "POST /accesos/entrada + Bearer"),
            (330, 565, "Solicitud con sesión"),
            (565, 800, "Validar rol operativo"),
            (800, 1070, "BEGIN; validar placa, mensualidad y celda"),
            (800, 1070, "COMMIT entrada válida / ROLLBACK rechazo"),
            (100, 330, "POST /accesos/salida + Bearer"),
            (565, 800, "Validar rol; localizar acceso activo"),
            (800, 1070, "BEGIN; cerrar estancia y actualizar celda"),
            (800, 1070, "COMMIT salida / ROLLBACK si no hay acceso"),
            (565, 330, "201/200 o 401/403/409"),
            (330, 100, "Actualizar estancia/mapa o mostrar error"),
        ]
    else:
        actions = [
            (100, 330, "POST /auth/login"),
            (330, 565, "Documento + contraseña"),
            (565, 1070, "Consultar cuenta y validar BCrypt"),
            (565, 330, "200 JWT o 401"),
            (100, 330, "GET /celdas + Bearer"),
            (330, 565, "Consultar mapa (lectura)"),
            (565, 1070, "SELECT celdas; sin asignar/liberar"),
            (100, 330, "POST/PATCH celdas (admin)"),
            (565, 800, "Validar rol; 401/403 si no autorizado"),
            (800, 1070, "BEGIN; validar; cambiar"),
            (800, 1070, "COMMIT permitido / ROLLBACK rechazado"),
            (100, 330, "Entrada/salida (operador/admin)"),
            (565, 800, "Validar rol y reglas de acceso"),
            (800, 1070, "BEGIN; asignar al entrar/liberar al salir"),
            (800, 1070, "COMMIT válido / ROLLBACK inválido"),
        ]
    y = 95
    for x1, x2, caption in actions:
        d.line((x1, y, x2, y), fill=BLUE, width=2)
        tip = 8 if x2 >= x1 else -8
        d.polygon([(x2, y), (x2 - tip, y - 5), (x2 - tip, y + 5)], fill=BLUE)
        tx = min(x1, x2) + 10
        text(d, (tx, y - 17), caption[:44], 10, INK)
        y += 38
    path = IMAGE_DIR / f"secuencia_{kind}.png"
    im.save(path)
    return path


def make_components():
    im, d = new_image(1200, 480)
    nodes = [
        (35, 100, 220, 120, "Roles\nAdministrador / Operador / Cliente"),
        (300, 100, 240, 120, "Angular\nPantallas + ApiService"),
        (590, 60, 300, 190, "FastAPI\nJWT + reglas de negocio"),
        (590, 320, 300, 100, "SQLAlchemy\nModelos / sesión"),
        (950, 320, 220, 100, "PostgreSQL\nusuarios / celdas /\naccesos"),
    ]
    for x, y, w, h, title in nodes:
        d.rounded_rectangle((x, y, x + w, y + h), 12, fill="#eff6ff", outline=BLUE, width=3)
        lines = title.split("\n")
        for i, line in enumerate(lines):
            text(d, (x + 12, y + 15 + i * 27), line, 14 if i == 0 else 11, NAVY if i == 0 else INK, i == 0)
    for a, b in [((255, 160), (300, 160)), ((540, 160), (590, 160)),
                 ((740, 250), (740, 320)), ((890, 370), (950, 370))]:
        d.line((*a, *b), fill="#475569", width=3)
    text(d, (34, 300), "Secuencia de login y JWT", 14, INK, True)
    text(d, (34, 335), "Iteración 1: accesos entrada/salida", 14, INK, True)
    text(d, (34, 370), "Iteración 2: usuarios y celdas", 14, INK, True)
    path = IMAGE_DIR / "componentes_ea2.png"
    im.save(path)
    return path


def docx_table(doc, rows, font_size=8):
    table = doc.add_table(rows=0, cols=len(rows[0]))
    table.style = "Light Shading Accent 1"
    for ri, row in enumerate(rows):
        cells = table.add_row().cells
        for ci, value in enumerate(row):
            cells[ci].text = value
            cells[ci].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for para in cells[ci].paragraphs:
                for run in para.runs:
                    run.font.name = "Arial"
                    run.font.size = Pt(font_size if len(rows[0]) > 2 else 9)
                    if ri == 0:
                        run.bold = True
                        run.font.color.rgb = RGBColor(255, 255, 255)
                if ri == 0:
                    from docx.oxml import OxmlElement
                    from docx.oxml.ns import qn

                    shd = OxmlElement("w:shd")
                    shd.set(qn("w:fill"), "172554")
                    cells[ci]._tc.get_or_add_tcPr().append(shd)
    return table


def add_picture(doc, path, width=6.7):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Inches(width))


def build_docx(images):
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin, sec.bottom_margin = Inches(.65), Inches(.65)
    sec.left_margin, sec.right_margin = Inches(.7), Inches(.7)
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(9)
    for name, size, rgb in [("Title", 26, (23, 37, 84)), ("Heading 1", 18, (23, 37, 84)), ("Heading 2", 12, (37, 99, 235))]:
        st = doc.styles[name]
        st.font.name, st.font.size, st.font.bold = "Arial", Pt(size), True
        st.font.color.rgb = RGBColor(*rgb)
    foot = sec.footer.paragraphs[0]
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    foot.add_run("PARKEA · Evidencia de Aprendizaje 2 · Iteración 2")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(80)
    r = p.add_run("IU DIGITAL DE ANTIOQUIA\n")
    r.bold, r.font.size = True, Pt(16)
    r = p.add_run("EVIDENCIA DE APRENDIZAJE 2\n")
    r.bold, r.font.size = True, Pt(25)
    r.font.color.rgb = RGBColor(23, 37, 84)
    r = p.add_run("Diseño del Sistema de Información · Iteración 2\n")
    r.font.size = Pt(19)
    r.font.color.rgb = RGBColor(37, 99, 235)
    p.add_run("Gestión de usuarios y celdas\n\n")
    p.add_run("Proyecto: Parqueadero Autos Colombia · PARKEA\n")
    p.add_run("Estudiante: José del Carmen Pineda Alarcón\n")
    p.add_run("Asignatura: Ingeniería de Software - PREICA2602B020053\n")
    p.add_run("Docente: Reinaldo Rojas\n")
    p.add_run("22 de noviembre de 2026")
    doc.add_page_break()

    doc.add_heading("Introducción", 1)
    doc.add_paragraph(
        "Autos Colombia necesita controlar el acceso de vehículos, usuarios, celdas y pagos mensuales. "
        "Esta Iteración 2 detalla la gestión de usuarios y celdas y su integración con la entrada y salida "
        "de la Iteración 1. La aplicación PARKEA utiliza Angular, FastAPI y PostgreSQL."
    )
    doc.add_heading("1. Alcance y reglas de negocio", 1)
    doc.add_paragraph(
        "ADMINISTRADOR gestiona cuentas y configura celdas; ADMINISTRADOR, OPERADOR y CLIENTE autenticados "
        "pueden consultar el mapa. La consulta del mapa es de solo lectura y no asigna ni libera celdas. "
        "Una entrada válida, ejecutada por personal operativo, asigna una celda disponible compatible y "
        "la marca OCUPADA. La salida cierra la estancia y libera la celda, salvo que tenga mantenimiento "
        "programado. Una celda ocupada no se libera manualmente."
    )
    doc.add_heading("2. Requerimientos funcionales", 1)
    doc.add_heading("2.1 Gestión de usuarios", 2)
    docx_table(doc, USERS_REQUIREMENTS, 8)
    doc.add_heading("2.2 Gestión de celdas", 2)
    docx_table(doc, CELL_REQUIREMENTS, 8)
    doc.add_heading("3. Requerimientos no funcionales", 1)
    docx_table(doc, NFR, 8)

    doc.add_page_break()
    doc.add_heading("4. Historias de usuario", 1)
    doc.add_heading("HU-06 · Gestión de usuarios (RF-U01 a RF-U06)", 2)
    doc.add_paragraph(
        "Como administrador, quiero registrar, consultar, actualizar y desactivar usuarios con roles de "
        "administrador, operador y cliente, para mantener las cuentas y sus permisos actualizados."
    )
    for criterion in [
        "Dado un formulario válido, al crear una cuenta, se guarda activa con el rol indicado y contraseña BCrypt; el directorio nunca expone el hash.",
        "Dado un documento o correo duplicado, el sistema rechaza la operación y no altera datos previos.",
        "Al editar datos, una contraseña vacía u omitida conserva la actual; si se entrega una nueva, se valida y hashea.",
        "El administrador no puede cambiar su propio rol ni desactivarse. La desactivación de otra cuenta es lógica y evita nuevos inicios de sesión.",
        "Una acción sin rol autorizado devuelve 403; un token inválido/vencido devuelve 401. El rechazo no persiste cambios.",
    ]:
        doc.add_paragraph(criterion, style="List Bullet")
    doc.add_heading("HU-03 · Consulta y administración de celdas (RF-C01 a RF-C05)", 2)
    doc.add_paragraph(
        "Como usuario autenticado, quiero consultar el mapa y detalle de celdas para conocer espacios y "
        "estados; como administrador, quiero crear celdas y programar/habilitar mantenimiento; como "
        "operador, quiero que la entrada y salida actualicen ocupación sin asignaciones manuales."
    )
    for criterion in [
        "La consulta muestra código, tipo, estado, leyenda y detalle de celda; no modifica ocupación.",
        "Código duplicado se rechaza; solo el administrador crea celdas y cambia estados administrables.",
        "La entrada valida cliente/mensualidad, vehículo, compatibilidad y disponibilidad antes de asignar.",
        "La salida libera una celda normal y conserva MANTENIMIENTO si se programó mientras estaba ocupada.",
        "Todo rechazo de actualización devuelve un error explícito y cierra la transacción con ROLLBACK.",
    ]:
        doc.add_paragraph(criterion, style="List Bullet")
    doc.add_heading("5. Diagramas de casos de uso", 1)
    doc.add_paragraph(
        "Los diagramas editables PlantUML, compatibles con la notación UML, están anexos. El cambio de "
        "contraseña es una extensión opcional de Actualizar usuario y, solo si se suministra, incluye "
        "proteger la nueva contraseña con BCrypt. En celdas, consultar mapa queda separado de la "
        "asignación durante entrada y liberación durante salida."
    )
    add_picture(doc, images["case_users"], 6.6)
    doc.add_paragraph("Fuente editable: entregables/diagramas/01_casos_uso_usuarios.puml.")
    add_picture(doc, images["case_cells"], 6.6)
    doc.add_paragraph("Fuente editable: entregables/diagramas/02_casos_uso_celdas.puml.")

    doc.add_page_break()
    doc.add_heading("6. Mockups gráficos", 1)
    doc.add_paragraph(
        "Los siguientes mockups son diseños gráficos de referencia (no capturas de ejecución). "
        "Se incluyen también sus fuentes SVG editables en entregables/mockups/."
    )
    doc.add_heading("Directorio y edición de usuarios", 2)
    add_picture(doc, images["mockup_users"], 6.8)
    doc.add_paragraph("Fuente SVG: entregables/mockups/mockup_usuarios_ea2.svg.")
    doc.add_heading("Mapa, detalle y mantenimiento", 2)
    add_picture(doc, images["mockup_cells"], 6.8)
    doc.add_paragraph("Fuente SVG: entregables/mockups/mockup_celdas_ea2.svg.")

    doc.add_page_break()
    doc.add_heading("7. Diagramas de secuencia actualizados", 1)
    doc.add_paragraph(
        "Las secuencias incorporan inicio de sesión, validación de token/rol, rutas de acceso denegado "
        "(401/403), resultados de éxito y rechazo, y COMMIT/ROLLBACK explícitos. Las fuentes editables "
        "detallan los mensajes y alternativas."
    )
    doc.add_heading("7.1 Accesos · Iteración 1", 2)
    add_picture(doc, images["seq_access"], 6.8)
    doc.add_paragraph("Fuente: entregables/diagramas/03_secuencia_iteracion1_accesos.puml.")
    doc.add_heading("7.2 Gestión de usuarios", 2)
    add_picture(doc, images["seq_users"], 6.8)
    doc.add_paragraph("Fuente: entregables/diagramas/04_secuencia_iteracion2_usuarios.puml.")
    doc.add_heading("7.3 Mapa, mantenimiento y ciclo de acceso", 2)
    add_picture(doc, images["seq_cells"], 6.8)
    doc.add_paragraph("Fuente: entregables/diagramas/05_secuencia_iteracion2_celdas.puml.")
    doc.add_heading("7.4 Diagrama de componentes", 2)
    add_picture(doc, images["components"], 6.8)
    doc.add_paragraph("Fuente: entregables/diagramas/06_componentes_iteraciones1y2.puml.")

    doc.add_page_break()
    doc.add_heading("8. Plan resumido de pruebas y resultados", 1)
    doc.add_paragraph(
        "Ejecución automatizada realizada el 22/11/2026 en backend con "
        "`python -m unittest discover -s test -v`: 41 pruebas aprobadas; 13 enfocadas en usuarios/celdas "
        "(10 de test_users_cells.py y 3 de test_access_cells.py). Las pruebas de servicio usan sesiones "
        "simuladas; no se consideran una prueba integral contra PostgreSQL. Build Angular: "
        "`npm run build`, aprobado. Docker no está disponible en este entorno, por lo que las pruebas "
        "visuales/API con una base PostgreSQL activa quedan identificadas como pendientes."
    )
    docx_table(doc, TESTS, 7)
    doc.add_heading("Casos pendientes y evidencia requerida", 2)
    docx_table(doc, PENDING, 7)
    doc.add_paragraph(
        "Evidencias de ejecución: entregables/evidencias/ea2_pruebas_backend.txt y "
        "entregables/evidencias/ea2_build_angular.txt. Los mockups adjuntos evidencian el diseño, "
        "no reemplazan capturas de una prueba funcional."
    )
    doc.add_heading("9. Implementación, repositorio y conclusiones", 1)
    doc.add_paragraph(
        "La API implementa directorio de usuarios, creación/edición/desactivación, mapa y cambios "
        "administrables de celdas; las rutas se protegen por JWT y rol. Las pruebas revisan BCrypt, "
        "normalización, conflictos, autoprotección, rollback, disponibilidad y mantenimiento. Se "
        "incorporó rollback explícito antes de rechazar actualizaciones de usuario/celda."
    )
    doc.add_paragraph("Repositorio: https://github.com/jdcpa1978-IUD/parkea")
    doc.add_paragraph("Video previamente suministrado: https://youtube.com/live/CyCH0SRFZp0?feature=share")
    doc.add_paragraph(
        "Antes de entregar, confirmar que el video muestre login, gestión de usuarios, mapa, cambio "
        "de contraseña opcional, roles y ciclo de mantenimiento. Si alguno falta, grabar o anexar "
        "la evidencia funcional pendiente indicada en el plan."
    )
    doc.add_paragraph(
        "Conclusión: la gestión de cuentas y celdas se integra con los accesos sin confundir la consulta "
        "visual con la asignación transaccional. Los diagramas corregidos y mockups gráficos completan "
        "el diseño; las pruebas automatizadas pasan. La unicidad y autorización en ejecución PostgreSQL/"
        "navegador siguen pendientes por falta de un runtime Docker disponible y deben validarse antes "
        "de afirmar cobertura end-to-end."
    )
    doc.save(DOCX_PATH)


def pdf_table(rows, widths, font_size=6.8):
    data = []
    for ri, row in enumerate(rows):
        st = ParagraphStyle(
            name=f"Cell{ri}_{len(row)}",
            fontName="Arial-Bold" if ri == 0 else "Arial",
            fontSize=font_size,
            leading=font_size + 2,
            textColor=colors.white if ri == 0 else colors.HexColor(INK),
        )
        data.append([Paragraph(str(c).replace("&", "&amp;"), st) for c in row])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    return t


def pdf_img(path, width=6.8):
    with Image.open(path) as im:
        aspect = im.height / im.width
    return PdfImage(str(path), width=width * inch, height=width * aspect * inch)


def build_pdf(images):
    pdfmetrics.registerFont(TTFont("Arial", r"C:\Windows\Fonts\arial.ttf"))
    pdfmetrics.registerFont(TTFont("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf"))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleEA2", fontName="Arial-Bold", fontSize=24, leading=30,
                              textColor=colors.HexColor(NAVY), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="H1EA2", fontName="Arial-Bold", fontSize=17, leading=21,
                              textColor=colors.HexColor(NAVY), spaceAfter=7))
    styles.add(ParagraphStyle(name="H2EA2", fontName="Arial-Bold", fontSize=11, leading=14,
                              textColor=colors.HexColor(BLUE), spaceBefore=5, spaceAfter=4))
    styles.add(ParagraphStyle(name="BodyEA2", fontName="Arial", fontSize=8.5, leading=12, spaceAfter=5))
    story = [
        Spacer(1, .8 * inch), Paragraph("IU DIGITAL DE ANTIOQUIA", styles["TitleEA2"]),
        Spacer(1, .2 * inch), Paragraph("EVIDENCIA DE APRENDIZAJE 2", styles["TitleEA2"]),
        Paragraph("Diseño del Sistema de Información · Iteración 2", styles["TitleEA2"]),
        Spacer(1, .2 * inch), Paragraph("Gestión de usuarios y celdas", styles["H2EA2"]),
        Spacer(1, .6 * inch),
        Paragraph("Proyecto: Parqueadero Autos Colombia · PARKEA<br/>Estudiante: José del Carmen Pineda Alarcón<br/>"
                  "Asignatura: Ingeniería de Software - PREICA2602B020053<br/>Docente: Reinaldo Rojas<br/>"
                  "22 de noviembre de 2026", styles["BodyEA2"]),
        PageBreak(),
        Paragraph("Introducción y alcance", styles["H1EA2"]),
        Paragraph("Autos Colombia necesita controlar el acceso de vehículos, usuarios, celdas y pagos. "
                  "Esta Iteración 2 detalla gestión de usuarios/celdas y su integración con entradas y salidas. "
                  "ADMINISTRADOR administra; todos los roles autenticados consultan el mapa. La consulta no "
                  "asigna ni libera. La entrada asigna celda compatible disponible y la salida libera, "
                  "conservando mantenimiento cuando fue programado.", styles["BodyEA2"]),
        Paragraph("2. Requerimientos funcionales · usuarios", styles["H1EA2"]),
        pdf_table(USERS_REQUIREMENTS, [.8 * inch, 3.35 * inch, 2.7 * inch]),
        Paragraph("Requerimientos funcionales · celdas", styles["H2EA2"]),
        pdf_table(CELL_REQUIREMENTS, [.8 * inch, 3.35 * inch, 2.7 * inch]),
        Paragraph("3. Requerimientos no funcionales", styles["H1EA2"]),
        pdf_table(NFR, [1.35 * inch, 5.5 * inch], 7.3),
        PageBreak(),
        Paragraph("4. Historias de usuario", styles["H1EA2"]),
        Paragraph("<b>HU-06 · Gestión de usuarios.</b> Como administrador, quiero registrar, consultar, "
                  "actualizar y desactivar usuarios con roles de administrador, operador y cliente, para "
                  "mantener las cuentas y permisos actualizados.", styles["BodyEA2"]),
        Paragraph("Criterios: crear cuenta activa con BCrypt; rechazar documento/correo duplicado sin "
                  "cambios parciales; si la contraseña se omite o queda vacía, conservar la anterior; "
                  "proteger cambios con rol ADMINISTRADOR; rechazar autoprotección; impedir login de cuenta inactiva.", styles["BodyEA2"]),
        Paragraph("<b>HU-03 · Consulta y administración de celdas.</b> Como usuario autenticado, quiero "
                  "consultar mapa y detalle; como administrador, crear celdas y gestionar mantenimiento; "
                  "como operador, registrar entradas/salidas con ocupación confiable.", styles["BodyEA2"]),
        Paragraph("Criterios: mapa de solo lectura; código único; entrada asigna solo celda disponible "
                  "compatible; salida libera celda normal o conserva MANTENIMIENTO; rechazos transaccionales "
                  "devuelven error y rollback.", styles["BodyEA2"]),
        Paragraph("5. Casos de uso", styles["H1EA2"]),
        Paragraph("Cambiar contraseña es una extensión opcional de Actualizar usuario; la nueva clave "
                  "incluye protección BCrypt. Consultar mapa está separado de asignar al ingresar y liberar al salir.", styles["BodyEA2"]),
        PageBreak(),
        pdf_img(images["case_users"], 6.8),
        Paragraph("Fuente UML editable: 01_casos_uso_usuarios.puml.", styles["BodyEA2"]),
        PageBreak(),
        pdf_img(images["case_cells"], 6.8),
        Paragraph("Fuente UML editable: 02_casos_uso_celdas.puml.", styles["BodyEA2"]),
        PageBreak(),
        Paragraph("6. Mockups gráficos", styles["H1EA2"]),
        Paragraph("Diseños de referencia (no capturas de ejecución); se incluyen fuentes SVG editables.", styles["BodyEA2"]),
        Paragraph("Directorio y edición de usuarios — contraseña opcional; vacío conserva la actual.", styles["H2EA2"]),
        pdf_img(images["mockup_users"], 6.8),
        Paragraph("Fuente SVG: mockup_usuarios_ea2.svg.", styles["BodyEA2"]),
        PageBreak(),
        Paragraph("6. Mockup de mapa y detalle", styles["H1EA2"]),
        Paragraph("Mapa y detalle — lectura separada de operaciones de acceso.", styles["H2EA2"]),
        pdf_img(images["mockup_cells"], 6.8),
        Paragraph("Fuente SVG: mockup_celdas_ea2.svg.", styles["BodyEA2"]),
        PageBreak(),
        Paragraph("7. Secuencias y componentes actualizados", styles["H1EA2"]),
        Paragraph("Incluyen login JWT, alternativas 401/403, éxito/rechazo, COMMIT y ROLLBACK.", styles["BodyEA2"]),
        Paragraph("Accesos · Iteración 1", styles["H2EA2"]), pdf_img(images["seq_access"], 6.8),
        Paragraph("Secuencia editable: 03_secuencia_iteracion1_accesos.puml.", styles["BodyEA2"]),
        PageBreak(),
        Paragraph("7.2 Secuencia de usuarios", styles["H1EA2"]),
        Paragraph("Usuarios", styles["H2EA2"]), pdf_img(images["seq_users"], 6.8),
        Paragraph("Secuencia editable: 04_secuencia_iteracion2_usuarios.puml.", styles["BodyEA2"]),
        PageBreak(),
        Paragraph("7.3 Secuencia de celdas y accesos", styles["H1EA2"]),
        Paragraph("Celdas, mapa y ciclo de acceso", styles["H2EA2"]), pdf_img(images["seq_cells"], 6.8),
        Paragraph("Secuencia editable: 05_secuencia_iteracion2_celdas.puml.", styles["BodyEA2"]),
        PageBreak(),
        Paragraph("7.4 Diagrama de componentes · iteraciones 1 y 2", styles["H1EA2"]),
        pdf_img(images["components"], 6.8),
        Paragraph("Fuente UML editable: 06_componentes_iteraciones1y2.puml.", styles["BodyEA2"]),
        PageBreak(),
        Paragraph("8. Plan de pruebas y resultados", styles["H1EA2"]),
        Paragraph("Backend: `python -m unittest discover -s test -v` — 41 aprobadas; 13 son pruebas "
                  "enfocadas en usuarios/celdas. Frontend: `npm run build` — aprobado. Las pruebas de servicio "
                  "usan sesión simulada. Docker no está disponible, así que los casos de PostgreSQL, permisos "
                  "HTTP y navegador quedan pendientes y no se afirman como end-to-end.", styles["BodyEA2"]),
        pdf_table(TESTS, [.5 * inch, 1.65 * inch, 2.25 * inch, 2.45 * inch], 6.2),
        Paragraph("Evidencia necesaria para casos pendientes", styles["H2EA2"]),
        pdf_table(PENDING, [1.75 * inch, 2.8 * inch, 2.3 * inch], 6.4),
        Paragraph("Consola de pruebas: entregables/evidencias/ea2_pruebas_backend.txt. Build: "
                  "entregables/evidencias/ea2_build_angular.txt. Los SVG son mockups de diseño, no "
                  "evidencia de una ejecución funcional.", styles["BodyEA2"]),
        Paragraph("9. Implementación y conclusión", styles["H1EA2"]),
        Paragraph("El código integra roles, gestión de cuentas y celdas con accesos. Los rechazos de cambio "
                  "de usuario/celda realizan rollback explícito. Repositorio: "
                  "https://github.com/jdcpa1978-IUD/parkea. Video previamente suministrado: "
                  "https://youtube.com/live/CyCH0SRFZp0?feature=share. Confirmar que muestre login, "
                  "gestión de usuarios, mapa y ciclo de mantenimiento; completar los casos pendientes con "
                  "capturas de prueba real antes de afirmar cobertura completa.", styles["BodyEA2"]),
    ]
    pdf = SimpleDocTemplate(str(PDF_PATH), pagesize=letter, leftMargin=.6 * inch,
                            rightMargin=.6 * inch, topMargin=.5 * inch, bottomMargin=.5 * inch)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Arial", 8)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(.6 * inch, .28 * inch, "PARKEA · Evidencia de Aprendizaje 2")
        canvas.drawRightString(7.9 * inch, .28 * inch, str(doc.page))
        canvas.restoreState()

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)


def main():
    global IMAGE_DIR
    with tempfile.TemporaryDirectory(prefix="parkea_ea2_") as image_dir:
        IMAGE_DIR = Path(image_dir)
        images = {
            "mockup_users": make_mockup_users(),
            "mockup_cells": make_mockup_cells(),
            "case_users": make_use_case("users"),
            "case_cells": make_use_case("cells"),
            "seq_users": make_sequence("users"),
            "seq_cells": make_sequence("cells"),
            "seq_access": make_sequence("access"),
            "components": make_components(),
        }
        build_docx(images)
        build_pdf(images)
    print(DOCX_PATH)
    print(PDF_PATH)


if __name__ == "__main__":
    main()
