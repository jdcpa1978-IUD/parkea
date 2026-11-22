from pathlib import Path
import tempfile

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
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
OUT_DOCX = ROOT / "Pineda_Jose_EA3.docx"
OUT_PDF = ROOT / "Pineda_Jose_EA3.pdf"
IMAGE_DIR = None

NAVY = "#172554"
BLUE = "#2563eb"
INK = "#0f172a"
MUTED = "#64748b"
LINE = "#cbd5e1"
PALE = "#f3f5f9"

REQUIREMENTS = [
    ("RF-PAG-01", "El administrador o el operador registra un pago para un cliente activo indicando monto, duración de 1 a 24 meses y método de pago."),
    ("RF-PAG-02", "El sistema acepta únicamente montos positivos de hasta 10 dígitos y 2 decimales; los métodos permitidos son efectivo, transferencia y tarjeta."),
    ("RF-PAG-03", "Si el cliente tiene una vigencia actual o futura, el siguiente periodo inicia el día posterior al último vencimiento; de lo contrario, inicia en la fecha actual."),
    ("RF-PAG-04", "El sistema calcula la fecha final según los meses pagados, guarda fecha, monto, método y periodo en una transacción y no persiste pagos inválidos."),
    ("RF-PAG-05", "El administrador y el operador consultan los últimos 100 pagos."),
    ("RF-PAG-06", "Después de un registro exitoso, la interfaz confirma la fecha de vencimiento y actualiza historial y resumen de vigencias."),
    ("RF-PAG-07", "El administrador o el operador consulta por cliente el historial completo de pagos y de entradas y salidas de sus vehículos."),
    ("RF-PAG-08", "El administrador o el operador identifica los clientes sin mensualidad vigente hoy, con su estado de cuenta, incluyendo quienes no tienen pagos o solo tienen pagos vencidos o futuros."),
]

QUALITY = [
    ("RNF-PAG-01 · Seguridad", "Las rutas requieren JWT; solo ADMINISTRADOR y OPERADOR pueden acceder al sistema y gestionar pagos."),
    ("RNF-PAG-02 · Integridad", "El monto y rango de fechas tienen restricciones de validación/modelo; el registro se confirma completo o se revierte."),
    ("RNF-PAG-03 · Trazabilidad", "Cada pago conserva cliente, fecha de pago, monto, método y fechas de vigencia para consulta posterior."),
    ("RNF-PAG-04 · Usabilidad", "El formulario presenta campos etiquetados, límites visibles y mensajes explícitos de éxito o error; no confirma una operación fallida."),
    ("RNF-PAG-05 · Concurrencia", "El cliente se bloquea durante el registro para serializar pagos concurrentes y evitar periodos superpuestos."),
]

STORIES = [
    (
        "HU-PAG-01 · Registrar mensualidad",
        "Como administrador u operador, quiero registrar un pago de un cliente activo para extender su mensualidad y dejar constancia de la transacción.",
        [
            "Dado un cliente activo y datos válidos, al guardar el pago, se registra el monto, método, fecha y periodo, y se informa el vencimiento.",
            "Si el cliente tiene vigencia futura, el periodo nuevo comienza al día siguiente del último vencimiento, sin perder días pagados.",
            "Si el cliente no existe o está inactivo, el sistema informa el error y no registra el pago.",
            "Si el monto no es positivo, los meses no están entre 1 y 24 o el método no está permitido, la validación rechaza la solicitud.",
        ],
    ),
    (
        "HU-PAG-03 · Consultar historial operativo",
        "Como administrador u operador, quiero consultar los pagos recientes para verificar las transacciones registradas.",
        [
            "El historial presenta los últimos 100 pagos, ordenados del más reciente al más antiguo.",
            "Cada fila permite identificar al cliente, monto, periodo y método.",
            "Si no hay pagos, se informa claramente que el historial está vacío.",
        ],
    ),
    (
        "HU-PAG-04 · Consultar historial por cliente",
        "Como administrador u operador, quiero consultar los pagos y accesos de un cliente para conocer su historial.",
        [
            "Al seleccionar un cliente, se presentan todos sus pagos y los accesos de sus vehículos, con placa, celda, entrada, salida y estado.",
            "Si el cliente no tiene pagos o accesos, se informa en cada sección; la consulta está reservada al personal.",
        ],
    ),
    (
        "HU-PAG-05 · Identificar clientes sin vigencia",
        "Como administrador u operador, quiero identificar los clientes sin mensualidad vigente hoy para conocer cuáles no tienen cobertura actual.",
        [
            "La lista incluye clientes sin pagos y con pagos vencidos o únicamente futuros; muestra por separado si la cuenta está activa o inactiva.",
            "Una mensualidad es vigente cuando hoy está entre sus fechas de inicio y fin, inclusive; la lista se actualiza tras registrar un pago.",
        ],
    ),
]

MOCKUPS = [
    ("5.1 Registro de pago · HU-PAG-01", "El personal ingresa cliente, monto, meses y método de pago.", "mockup_registro_pago.png"),
    ("5.2 Clientes sin vigencia · HU-PAG-05", "El personal identifica clientes sin vigencia hoy y distingue el estado de cada cuenta.", "mockup_clientes_sin_vigencia.png"),
    ("5.3 Historial por cliente · HU-PAG-04", "La consulta presenta pagos y accesos, incluidos ingresos activos y finalizados.", "mockup_historial_cliente.png"),
    ("5.4 Historial sin registros · HU-PAG-04", "Cuando no hay pagos ni accesos, se muestra un estado vacío para cada sección.", "mockup_historial_cliente_vacio.png"),
]

TESTS = [
    ["ID", "Escenario / datos", "Resultado esperado", "Evidencia / estado"],
    ["CP-01", "Registrar $120.000, 1 mes, EFECTIVO sin pagos previos.", "La vigencia empieza hoy; el pago queda guardado y aparece en los historiales.", "API aislada: pasa. Interfaz: primer pago confirmado en historial por cliente; historial reciente pendiente."],
    ["CP-02", "Registrar otro pago con vigencia futura.", "El periodo inicia al día siguiente del último vencimiento, sin solaparse.", "API aislada: pasa. Interfaz: renovación comprobada en video local."],
    ["CP-03", "Registrar para cliente con mensualidad vencida.", "El periodo inicia hoy y su fecha final corresponde a los meses pagados.", "Unitario simulado: pasa. Interfaz: pendiente."],
    ["CP-04", "Monto cero, negativo o con más de 2 decimales.", "La validación rechaza la solicitud y no se guarda un pago inválido.", "Esquema y API: pruebas parciales pasan. Interfaz: mensajes confirmados para los tres valores. Componente aislado: no envía pagos inválidos."],
    ["CP-05", "Duración 0 o 25 meses; método fuera del catálogo.", "La validación rechaza la solicitud y no se inserta un pago.", "Esquema: pasa; API aislada: 25 meses y método inválido pasan. Interfaz: mensajes confirmados con 0 y 25 meses."],
    ["CP-06", "Registrar pago para cliente inexistente o inactivo.", "HTTP 404 y ningún pago adicional.", "API aislada: pasa. Interfaz: se observa mensaje de cliente no activo; el cliente sigue seleccionado."],
    ["CP-07", "Intentar iniciar sesión como cliente o usar una sesión anterior.", "El acceso de cliente es rechazado; solo el personal puede acceder.", "Pruebas aisladas: inicio y sesión de cliente rechazados. Interfaz: pendiente."],
    ["CP-08", "Consultar historial reciente con más de 100 pagos.", "El personal recibe hasta 100 pagos recientes.", "API aislada: pasa. Video local: historial visible; límite no comprobado."],
    ["CP-09", "Consultar vigencias con pagos ausentes, vencidos, futuros y en límites.", "La vigencia actual usa fechas inclusivas y se identifica el estado de cuenta.", "API aislada: pasa. Interfaz: cliente sin pagos aparece en lista y sale tras pagar; otros casos pendientes."],
    ["CP-10", "Consultar historial por cliente con más de 100 pagos y varios accesos.", "Se devuelven todos sus pagos y accesos activos/finalizados, sin datos de otros clientes.", "API aislada: pasa. Video local: un pago y dos accesos finalizados; prueba parcial."],
    ["CP-11", "Consultar historial de un cliente sin pagos ni accesos.", "Se devuelven ambas listas vacías; la interfaz informa el estado vacío.", "API aislada: listas vacías. Interfaz: ambos mensajes confirmados en captura."],
    ["CP-12", "Registrar para un cliente con pagos solo futuros.", "El nuevo periodo se encadena; el cliente sigue sin vigencia hoy.", "API aislada: pasa. Interfaz: pendiente."],
]


def font(size, bold=False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    path = Path("C:/Windows/Fonts") / name
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def canvas(width, height):
    image = Image.new("RGB", (width, height), PALE)
    return image, ImageDraw.Draw(image)


def text(draw, xy, value, size=15, color=INK, bold=False):
    draw.text(xy, value, fill=color, font=font(size, bold))


def wrap(draw, value, x, y, max_width, size=15, color=INK, bold=False, gap=7):
    words = value.split()
    lines, line = [], ""
    f = font(size, bold)
    for word in words:
        candidate = (line + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=f)[2] > max_width and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    for item in lines:
        text(draw, (x, y), item, size, color, bold)
        y += size + gap
    return y


def make_use_case():
    image, d = canvas(1100, 570)
    d.rectangle((250, 35, 1055, 530), outline="#334155", width=3)
    text(d, (480, 48), "PARKEA · GESTIÓN DE PAGOS", 20, NAVY, True)
    for y, label in [(190, "Administrador"), (300, "Operador")]:
        d.ellipse((35, y, 85, y + 50), outline="#334155", width=3)
        d.line((60, y + 50, 60, y + 105), fill="#334155", width=3)
        d.line((25, y + 72, 95, y + 72), fill="#334155", width=3)
        d.line((60, y + 105, 30, y + 150), fill="#334155", width=3)
        d.line((60, y + 105, 90, y + 150), fill="#334155", width=3)
        text(d, (15, y + 160), label, 15, INK, True)
    ellipses = [
        (365, 140, 635, 210, "Registrar pago mensual"),
        (690, 140, 960, 210, "Validar cliente y pago"),
        (365, 270, 635, 340, "Consultar historial"),
        (690, 270, 960, 340, "Calcular vigencia"),
    ]
    for x1, y1, x2, y2, label in ellipses:
        d.ellipse((x1, y1, x2, y2), fill="#eff6ff", outline=BLUE, width=2)
        box = d.textbbox((0, 0), label, font=font(14, True))
        d.text(((x1 + x2 - (box[2] - box[0])) / 2, (y1 + y2 - (box[3] - box[1])) / 2 - 5),
               label, fill=INK, font=font(14, True))
    for start, end in [((95, 220), (365, 175)), ((95, 330), (365, 175)),
                       ((95, 220), (365, 305)), ((95, 330), (365, 305)),
                       ((635, 175), (690, 175)),
                       ((635, 175), (690, 305))]:
        d.line((*start, *end), fill="#475569", width=2)
    text(d, (368, 505), "Personal autorizado: últimos 100 pagos", 13, MUTED)
    path = IMAGE_DIR / "casos_uso.png"
    image.save(path)
    return path


def make_sequence():
    image, d = canvas(1200, 680)
    labels = ["Actor", "Angular", "API / JWT", "Servicio", "PostgreSQL"]
    xs = [100, 330, 560, 790, 1050]
    for x, label in zip(xs, labels):
        d.rounded_rectangle((x - 85, 25, x + 85, 75), 8, fill="#eff6ff", outline=BLUE, width=2)
        text(d, (x - 55, 42), label, 16, NAVY, True)
        d.line((x, 75, x, 635), fill="#94a3b8", width=2)
    steps = [
        (100, 330, "Selecciona cliente, monto, meses y método"),
        (330, 560, "POST /api/pagos + token"),
        (560, 790, "Autoriza ADMINISTRADOR / OPERADOR"),
        (790, 1050, "Bloquea cliente y obtiene último vencimiento"),
        (1050, 790, "Cliente activo + historial de pagos"),
        (790, 1050, "Inserta pago y periodo calculado"),
        (1050, 790, "Pago persistido"),
        (790, 560, "Pago + fechas de vigencia"),
        (560, 330, "201 + detalle"),
        (330, 100, "Confirma y refresca historial/resumen"),
    ]
    y = 110
    for x1, x2, label in steps:
        d.line((x1, y, x2, y), fill=BLUE, width=2)
        d.polygon([(x2, y), (x2 - (10 if x2 > x1 else -10), y - 6),
                   (x2 - (10 if x2 > x1 else -10), y + 6)], fill=BLUE)
        text(d, (min(x1, x2) + 10, y - 22), label, 12, INK)
        y += 48
    d.rounded_rectangle((125, 600, 1080, 650), 10, fill="#fff7ed", outline="#fdba74", width=2)
    text(d, (155, 616), "Alternativa: cliente inexistente/inactivo o datos inválidos → error explícito; no se crea pago.", 13, "#9a3412")
    path = IMAGE_DIR / "secuencia.png"
    image.save(path)
    return path


def make_components():
    image, d = canvas(1200, 560)
    boxes = [
        (40, 100, 280, 220, "Usuario\nAdministrador / Operador / Cliente"),
        (355, 100, 610, 220, "Angular\nPantallas + ApiService"),
        (685, 55, 975, 245, "FastAPI\nJWT / roles\nAccesos · Usuarios · Celdas · Pagos"),
        (685, 330, 975, 490, "SQLAlchemy\nModelos y sesión"),
        (1015, 330, 1170, 490, "PostgreSQL\nusuarios, pagos,\naccesos, celdas"),
    ]
    for x1, y1, x2, y2, label in boxes:
        d.rounded_rectangle((x1, y1, x2, y2), 12, fill="#eff6ff", outline=BLUE, width=3)
        lines = label.split("\n")
        for i, line in enumerate(lines):
            text(d, (x1 + 16, y1 + 20 + i * 27), line, 16 if i == 0 else 13, NAVY if i == 0 else INK, i == 0)
    for start, end, label in [
        ((280, 160), (355, 160), "Navegador"), ((610, 160), (685, 160), "HTTPS / JSON"),
        ((830, 245), (830, 330), "consultas"),
        ((975, 410), (1015, 410), "SQL"),
    ]:
        d.line((*start, *end), fill="#475569", width=3)
        text(d, ((start[0] + end[0]) // 2 - 35, (start[1] + end[1]) // 2 - 25), label, 11, MUTED)
    text(d, (45, 295), "Iteración 1: accesos entrada/salida", 15, INK, True)
    text(d, (45, 335), "Iteración 2: usuarios y celdas", 15, INK, True)
    text(d, (45, 375), "Iteración 3: GET/POST pagos; historial y vigencias", 15, INK, True)
    path = IMAGE_DIR / "componentes.png"
    image.save(path)
    return path


def docx_setup():
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(.7)
    section.bottom_margin = Inches(.7)
    section.left_margin = Inches(.75)
    section.right_margin = Inches(.75)
    styles = doc.styles
    styles["Normal"].font.name = "Arial"
    styles["Normal"].font.size = Pt(10)
    styles["Normal"].font.color.rgb = RGBColor(35, 45, 65)
    for style_name, size, color in [("Title", 28, "172554"), ("Heading 1", 19, "172554"), ("Heading 2", 13, "2563EB")]:
        styles[style_name].font.name = "Arial"
        styles[style_name].font.size = Pt(size)
        styles[style_name].font.bold = True
        styles[style_name].font.color.rgb = RGBColor.from_string(color)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("PARKEA · Evidencia de Aprendizaje 3 · Gestión de pagos")
    return doc


def add_docx_table(doc, rows, widths=None):
    table = doc.add_table(rows=0, cols=len(rows[0]))
    table.style = "Light Shading Accent 1"
    if widths:
        table.autofit = False
    for ri, row in enumerate(rows):
        cells = table.add_row().cells
        for ci, value in enumerate(row):
            cells[ci].text = value
            cells[ci].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for p in cells[ci].paragraphs:
                for run in p.runs:
                    run.font.size = Pt(8 if len(row) > 3 else 9)
                    if ri == 0:
                        run.bold = True
                        run.font.color.rgb = RGBColor(255, 255, 255)
                if ri == 0:
                    p.paragraph_format.space_after = Pt(0)
            if ri == 0:
                shading = cells[ci]._tc.get_or_add_tcPr()
                from docx.oxml import OxmlElement
                from docx.oxml.ns import qn

                fill = OxmlElement("w:shd")
                fill.set(qn("w:fill"), "172554")
                shading.append(fill)
    return table


def add_docx_image(doc, path, width=6.7):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Inches(width))


def build_docx(images):
    doc = docx_setup()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(95)
    r = p.add_run("PARKEA")
    r.bold = True
    r.font.size = Pt(34)
    r.font.color.rgb = RGBColor(37, 99, 235)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Evidencia de Aprendizaje 3\nDiseño del Sistema de Información – Iteración 3")
    r.bold = True
    r.font.size = Pt(23)
    r.font.color.rgb = RGBColor(23, 37, 84)
    p = doc.add_paragraph("Gestión de pagos de mensualidad")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.runs[0].font.size = Pt(17)
    p.runs[0].font.color.rgb = RGBColor(100, 116, 139)
    for line in ["Estudiante: José Pineda", "Programa: Ingeniería de Software", "Institución: IU Digital de Antioquia", "Fecha: 22 de noviembre de 2026"]:
        p = doc.add_paragraph(line)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()

    doc.add_heading("1. Introducción", 1)
    doc.add_paragraph(
        "Este documento presenta la Iteración 3 de PARKEA para el parqueadero Autos Colombia. "
        "La iteración aborda el registro de pagos de mensualidad, la extensión de vigencias y la consulta "
        "de historiales, integrándose con las iteraciones previas de accesos, usuarios y celdas."
    )
    doc.add_heading("Objetivo", 2)
    doc.add_paragraph(
        "Especificar y evidenciar una gestión de pagos que permita registrar transacciones válidas, "
        "mantener periodos de cobertura continuos y restringir la consulta de información según el rol."
    )
    doc.add_heading("Alcance y regla de negocio", 2)
    doc.add_paragraph(
        "La aplicación permite que el administrador y el operador registren pagos para clientes activos. "
        "Un pago cubre de 1 a 24 meses; cuando existe una vigencia actual o futura, la siguiente inicia "
        "al día posterior al vencimiento más lejano. Cuando no existe vigencia futura, inicia en la fecha "
        "del registro. El acceso a la aplicación está reservado al personal."
    )

    doc.add_heading("2. Requerimientos", 1)
    doc.add_heading("2.1 Requerimientos funcionales", 2)
    add_docx_table(doc, [["Código", "Descripción"]] + [list(row) for row in REQUIREMENTS])
    doc.add_heading("2.2 Requerimientos no funcionales", 2)
    add_docx_table(doc, [["Código / atributo", "Criterio verificable"]] + [list(row) for row in QUALITY])

    doc.add_page_break()
    doc.add_heading("3. Historias de usuario", 1)
    for title, story, criteria in STORIES:
        doc.add_heading(title, 2)
        doc.add_paragraph(story)
        for criterion in criteria:
            doc.add_paragraph(criterion, style="List Bullet")
    doc.add_heading("Trazabilidad", 2)
    add_docx_table(doc, [
        ["Requerimientos", "Historias", "Cobertura"],
        ["RF-PAG-01 a RF-PAG-04; RNF-PAG-02, 03, 05", "HU-PAG-01", "Registro, validación, persistencia transaccional y cálculo de vigencia."],
        ["RF-PAG-05, RF-PAG-06; RNF-PAG-04", "HU-PAG-03", "Consulta operativa, historial y actualización de interfaz."],
        ["RF-PAG-07; RNF-PAG-01, 03", "HU-PAG-04", "Historial de pagos y accesos por cliente."],
        ["RF-PAG-08; RNF-PAG-01, 04", "HU-PAG-05", "Clientes sin vigencia actual y estado de cuenta."],
    ])

    doc.add_page_break()
    doc.add_heading("4. Diagrama de casos de uso", 1)
    doc.add_paragraph(
        "Los actores son Administrador y Operador. Ambos pueden "
        "registrar pagos y consultar el historial de pagos y accesos por cliente, además de los clientes "
        "sin mensualidad vigente hoy. El registro "
        "incluye validar cliente/datos y calcular el periodo."
    )
    add_docx_image(doc, images["use_case"], 6.7)
    doc.add_paragraph("Modelo editable de StarUML: entregables/diagramas/EA3_Casos_de_uso_pagos.mdj.")
    doc.add_heading("5. Mockups de gestión de pagos", 1)
    doc.add_paragraph(
        "Diseños ilustrativos con datos ficticios, basados en la distribución y los estilos de la aplicación. "
        "Las vistas de consulta muestran el contenido al desplazarse por el módulo."
    )
    for index, (title, description, filename) in enumerate(MOCKUPS):
        if index:
            doc.add_page_break()
        doc.add_heading(title, 2)
        doc.add_paragraph(description)
        add_docx_image(doc, ROOT / "mockups" / filename, 6.75)
        doc.add_paragraph(f"Diseño gráfico: entregables/mockups/{filename}.")
    doc.add_paragraph(
        "Fuente editable: entregables/mockups/mockups_pagos.html. El parámetro vista admite registro, "
        "sin-vigencia, historial e historial-vacio; utiliza los estilos del frontend."
    )

    doc.add_page_break()
    doc.add_heading("6. Diagramas actualizados de secuencia y componentes", 1)
    doc.add_heading("6.1 Secuencia integrada de las iteraciones 1, 2 y 3", 2)
    doc.add_paragraph(
        "Las secuencias se presentan en seis vistas para conservar su legibilidad: inicio de sesión, "
        "accesos, usuarios y celdas, pagos y las dos consultas por cliente. Los mensajes condicionados entre corchetes representan "
        "alternativas de éxito o rechazo, incluida la denegación de acceso y el rollback de cambios rechazados."
    )
    for title, image in images["sequences"]:
        doc.add_heading(title, 2)
        add_docx_image(doc, image, 6.7)
    doc.add_paragraph("Modelo editable de StarUML: entregables/diagramas/EA3_Secuencias_iteraciones_1_a_3.mdj.")
    doc.add_heading("6.2 Componentes actualizados", 2)
    doc.add_paragraph(
        "El cliente web contiene la pantalla de pagos y ApiService; FastAPI ofrece rutas de pagos y consultas por cliente, "
        "aplica JWT/roles y utiliza SQLAlchemy para acceder a PostgreSQL. Se muestran también los "
        "componentes existentes de accesos, usuarios y celdas."
    )
    add_docx_image(doc, images["components"], 6.8)
    doc.add_paragraph("Modelo editable de StarUML: entregables/diagramas/EA3_Componentes_iteraciones_1_a_3.mdj.")
    doc.add_paragraph("Las imágenes fueron exportadas desde StarUML sin registrar y conservan la marca de agua de la herramienta.")

    doc.add_page_break()
    doc.add_heading("7. Plan de pruebas resumido", 1)
    doc.add_paragraph(
        "El 22/11/2026 se ejecutaron 33 pruebas automatizadas de usuarios y pagos: unitarias con objetos simulados y "
        "solicitudes HTTP a la API con SQLite en memoria. Pasaron las 33; no verifican la interfaz, "
        "PostgreSQL ni la concurrencia. Evidencia: entregables/evidencias/ea3_pruebas_pagos.txt."
    )
    doc.add_paragraph(
        "Para la ejecución manual: usar clientes ficticios y cuentas de personal. "
        "Los pagos registrados permanecen en la base de datos. Registrar resultados y capturas o video; "
        "los casos de interfaz siguen pendientes hasta comprobarlos."
    )
    doc.add_paragraph(
        "Revisión parcial de fotogramas de la grabación local del 22/11/2026: alrededor de 00:40 "
        "se observa la lista de clientes sin vigencia y entre 00:54 y 00:58 un historial con un pago "
        "y dos accesos finalizados. En una segunda grabación, se registró una renovación de dos "
        "meses en efectivo: la vigencia anterior termina el 21/02/2027 y la nueva va del 22/02/2027 "
        "al 21/04/2027; aparece en los historiales. Una captura posterior de CP-01 muestra el primer "
        "pago de $120.000 en efectivo con vigencia del 22/11/2026 al 21/12/2026 y al cliente fuera "
        "de la lista sin vigencia; el historial reciente no se ve en esa captura. Se revisaron fotogramas, "
        "no el audio. Los videos permanecen locales; antes de compartirlos, proteger los datos personales visibles."
    )
    doc.add_paragraph(
        "En la prueba manual de monto cero se observó un mensaje de conexión inadecuado. "
        "Se ajustó el componente y capturas posteriores confirman que con monto cero y negativo "
        "se muestra «Monto inválido. Debe ser mayor que cero.». La prueba con más de dos decimales "
        "mostró también un mensaje de conexión; tras la corrección, otra captura confirma "
        "«Monto inválido. Debe tener máximo dos decimales.». La validación del componente se "
        "comprobó de forma aislada, sin enviar pagos inválidos."
    )
    doc.add_paragraph(
        "En la prueba manual de cero meses también se observó un mensaje de conexión inadecuado. "
        "Se ajustó el componente para indicar que los meses deben ser un número entero entre 1 y 24. "
        "Dos capturas confirman el mensaje con 0 y 25 meses. "
        "El componente rechazó valores fuera de rango en una prueba aislada."
    )
    doc.add_paragraph(
        "En la prueba de cliente inactivo, la interfaz mostró «No se encontró un cliente activo» "
        "al intentar registrar el pago, aunque el cliente seguía seleccionado en el formulario. "
        "La captura no verifica por sí sola el estado de la base ni la exclusión de la lista."
    )
    add_docx_table(doc, TESTS)
    doc.add_paragraph(
        "Criterio de aceptación global: un pago aparece una sola vez, sus fechas son correctas, la "
        "vigencia no pierde días pagados y una entrada no autorizada o inválida no modifica los datos."
    )

    doc.add_page_break()
    doc.add_heading("8. Repositorio y video de funcionamiento", 1)
    doc.add_paragraph("Repositorio de código fuente: https://github.com/jdcpa1978-IUD/parkea")
    doc.add_paragraph(
        "Video disponible: https://youtube.com/live/CyCH0SRFZp0?feature=share"
    )
    doc.add_paragraph(
        "Antes de entregar, verificar que el video público muestre las tres iteraciones y, en particular, "
        "un registro de pago, su confirmación y las consultas operativas. Si el video "
        "actual no muestra ese flujo, reemplazar el enlace por una grabación actualizada."
    )
    doc.add_heading("9. Conclusiones", 1)
    doc.add_paragraph(
        "La Iteración 3 complementa la operación de PARKEA al vincular el registro financiero con la "
        "vigencia que se valida en los accesos. La validación de montos, duración, estado del cliente y rol, "
        "junto con el encadenamiento de periodos y el historial, reduce errores y mantiene trazabilidad. "
        "Los casos automatizados y el plan resumido permiten verificar tanto el cálculo como los rechazos; "
        "la demostración final debe evidenciar también el flujo desde la interfaz."
    )
    doc.save(OUT_DOCX)


def p(text_value, style):
    return Paragraph(text_value.replace("&", "&amp;"), style)


def pdf_diagram(path, max_width=6.8 * inch, max_height=7.6 * inch):
    with Image.open(path) as image:
        width, height = image.size
    scale = min(max_width / width, max_height / height)
    return PdfImage(str(path), width=width * scale, height=height * scale)


def build_pdf(images):
    pdfmetrics.registerFont(TTFont("Arial", r"C:\Windows\Fonts\arial.ttf"))
    pdfmetrics.registerFont(TTFont("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf"))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Arial-Bold",
                              fontSize=24, leading=30, textColor=colors.HexColor(NAVY), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="Arial-Bold", fontSize=18, leading=22,
                              textColor=colors.HexColor(NAVY), spaceBefore=8, spaceAfter=8))
    styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Arial-Bold", fontSize=12, leading=15,
                              textColor=colors.HexColor(BLUE), spaceBefore=6, spaceAfter=5))
    styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontName="Arial", fontSize=9, leading=13, spaceAfter=6))
    styles.add(ParagraphStyle(name="Smallx", parent=styles["BodyText"], fontName="Arial", fontSize=7.1, leading=9))
    story = [
        Spacer(1, 1.15 * inch),
        Paragraph("PARKEA", styles["CoverTitle"]),
        Spacer(1, .2 * inch),
        Paragraph("Evidencia de Aprendizaje 3<br/>Diseño del Sistema de Información – Iteración 3", styles["CoverTitle"]),
        Spacer(1, .18 * inch),
        Paragraph("Gestión de pagos de mensualidad", styles["Heading2"]),
        Spacer(1, .6 * inch),
        Paragraph("Estudiante: José Pineda<br/>Programa: Ingeniería de Software<br/>Institución: IU Digital de Antioquia<br/>Fecha: 22 de noviembre de 2026", styles["Bodyx"]),
        PageBreak(),
        Paragraph("1. Introducción", styles["H1x"]),
        p("Este documento presenta la Iteración 3 de PARKEA para el parqueadero Autos Colombia. La iteración aborda el registro de pagos de mensualidad, la extensión de vigencias y la consulta de historiales, integrándose con las iteraciones previas de accesos, usuarios y celdas.", styles["Bodyx"]),
        Paragraph("Objetivo y alcance", styles["H2x"]),
        p("Especificar y evidenciar una gestión de pagos que permita registrar transacciones válidas, mantener periodos de cobertura continuos y restringir el acceso al personal. Administrador y operador registran pagos de clientes activos. La nueva vigencia comienza hoy si no hay periodo futuro; de lo contrario, el día siguiente al vencimiento más lejano.", styles["Bodyx"]),
        Paragraph("2. Requerimientos funcionales", styles["H1x"]),
    ]
    story.append(make_pdf_table([["Código", "Descripción"]] + [list(r) for r in REQUIREMENTS], [1.0 * inch, 5.85 * inch]))
    story += [Spacer(1, 10), Paragraph("2.1 Requerimientos no funcionales", styles["H2x"])]
    story.append(make_pdf_table([["Atributo", "Criterio verificable"]] + [list(r) for r in QUALITY], [1.7 * inch, 5.15 * inch]))
    story += [
        PageBreak(), Paragraph("3. Historias de usuario", styles["H1x"])
    ]
    for title, story_text, criteria in STORIES:
        story.append(Paragraph(title, styles["H2x"]))
        story.append(p(story_text, styles["Bodyx"]))
        for item in criteria:
            story.append(p("• " + item, styles["Bodyx"]))
    story += [
        Paragraph("Trazabilidad", styles["H2x"]),
        make_pdf_table([
            ["Requerimientos", "Historia", "Cobertura"],
            ["RF-PAG-01 a 04; RNF-PAG-02,03,05", "HU-PAG-01", "Registro, validación, transacción y vigencia."],
            ["RF-PAG-05,06; RNF-PAG-04", "HU-PAG-03", "Consulta operativa e historial."],
            ["RF-PAG-07; RNF-PAG-01,03", "HU-PAG-04", "Historial de pagos y accesos por cliente."],
            ["RF-PAG-08; RNF-PAG-01,04", "HU-PAG-05", "Clientes sin vigencia y estado de cuenta."],
        ], [2.4 * inch, 1.0 * inch, 3.45 * inch]),
        PageBreak(), Paragraph("4. Diagrama de casos de uso", styles["H1x"]),
        p("Administrador y operador registran pagos, consultan pagos y accesos por cliente e identifican clientes sin mensualidad vigente hoy. El registro incluye validar datos y cliente, y calcular el periodo.", styles["Bodyx"]),
        pdf_diagram(images["use_case"]),
        p("Modelo editable de StarUML: entregables/diagramas/EA3_Casos_de_uso_pagos.mdj.", styles["Smallx"]),
        PageBreak(),
        Paragraph("5. Mockups de gestión de pagos", styles["H1x"]),
        p("Diseños ilustrativos con datos ficticios, basados en los estilos de la aplicación. Las consultas muestran el contenido al desplazarse por el módulo.", styles["Bodyx"]),
    ]
    for index, (title, description, filename) in enumerate(MOCKUPS):
        if index:
            story.append(PageBreak())
        story += [
            Paragraph(title, styles["H2x"]),
            p(description, styles["Bodyx"]),
            pdf_diagram(ROOT / "mockups" / filename, max_width=6.85 * inch, max_height=6 * inch),
            p(f"Diseño gráfico: entregables/mockups/{filename}.", styles["Smallx"]),
        ]
    story += [
        p("Fuente editable: entregables/mockups/mockups_pagos.html. El parámetro vista admite registro, sin-vigencia, historial e historial-vacio; utiliza los estilos del frontend.", styles["Smallx"]),
        PageBreak(), Paragraph("6. Diagramas actualizados de secuencia y componentes", styles["H1x"]),
        Paragraph("6.1 Secuencia integrada de las iteraciones 1, 2 y 3", styles["H2x"]),
        p("Las seis vistas integran el inicio de sesión y las tres iteraciones, incluidas las consultas de historial y vigencia por cliente. Las condiciones entre corchetes distinguen alternativas de éxito y rechazo; se incluyen acceso denegado y rollback de cambios rechazados.", styles["Bodyx"]),
    ]
    for title, image in images["sequences"]:
        story += [
            Paragraph(title, styles["H2x"]),
            pdf_diagram(image, max_height=6.8 * inch),
            PageBreak(),
        ]
    story += [
        p("Modelo editable de StarUML: entregables/diagramas/EA3_Secuencias_iteraciones_1_a_3.mdj.", styles["Smallx"]),
        Paragraph("6.2 Componentes", styles["H2x"]),
        pdf_diagram(images["components"]),
        p("Modelo editable de StarUML: entregables/diagramas/EA3_Componentes_iteraciones_1_a_3.mdj.", styles["Smallx"]),
        p("Las imágenes fueron exportadas desde StarUML sin registrar y conservan la marca de agua de la herramienta.", styles["Smallx"]),
        PageBreak(), Paragraph("7. Plan de pruebas resumido", styles["H1x"]),
        p("El 22/11/2026 pasaron 33 pruebas automatizadas de usuarios y pagos: unitarias con objetos simulados y solicitudes HTTP a la API con SQLite en memoria. No verifican interfaz, PostgreSQL ni concurrencia. Evidencia: entregables/evidencias/ea3_pruebas_pagos.txt.", styles["Bodyx"]),
        p("Para la ejecución manual, usar clientes ficticios y cuentas de personal. Los pagos registrados permanecen en la base de datos. Los demás casos de interfaz siguen pendientes hasta comprobarlos.", styles["Bodyx"]),
        p("Revisión parcial de fotogramas de la primera grabación local del 22/11/2026: alrededor de 00:40 se observa la lista de clientes sin vigencia y entre 00:54 y 00:58 un historial con un pago y dos accesos finalizados. En una segunda grabación se registró una renovación de dos meses en efectivo: la vigencia anterior termina el 21/02/2027 y la nueva va del 22/02/2027 al 21/04/2027; aparece en los historiales. Una captura posterior de CP-01 muestra el primer pago de $120.000 en efectivo con vigencia del 22/11/2026 al 21/12/2026 y al cliente fuera de la lista sin vigencia; el historial reciente no se ve en esa captura. Se revisaron fotogramas, no el audio. Los videos permanecen locales; antes de compartirlos, proteger los datos personales visibles.", styles["Bodyx"]),
        p("En la prueba manual de monto cero se observó un mensaje de conexión inadecuado. Se ajustó el componente y capturas posteriores confirman que con monto cero y negativo se muestra «Monto inválido. Debe ser mayor que cero.». La prueba con más de dos decimales mostró también un mensaje de conexión; tras la corrección, otra captura confirma «Monto inválido. Debe tener máximo dos decimales.». La validación del componente se comprobó de forma aislada, sin enviar pagos inválidos.", styles["Bodyx"]),
        p("En la prueba manual de cero meses también se observó un mensaje de conexión inadecuado. Se ajustó el componente para indicar que los meses deben ser un número entero entre 1 y 24. Dos capturas confirman el mensaje con 0 y 25 meses. El componente rechazó valores fuera de rango en una prueba aislada.", styles["Bodyx"]),
        p("En la prueba de cliente inactivo, la interfaz mostró «No se encontró un cliente activo» al intentar registrar el pago, aunque el cliente seguía seleccionado en el formulario. La captura no verifica por sí sola el estado de la base ni la exclusión de la lista.", styles["Bodyx"]),
        make_pdf_table(TESTS, [.48 * inch, 1.65 * inch, 2.85 * inch, 1.42 * inch]),
        p("Aceptación global: un pago aparece una sola vez, las fechas son correctas, no se pierden días pagados y las solicitudes inválidas/no autorizadas no cambian datos.", styles["Bodyx"]),
        PageBreak(), Paragraph("8. Repositorio y video", styles["H1x"]),
        Paragraph('Repositorio: <link href="https://github.com/jdcpa1978-IUD/parkea" color="blue">https://github.com/jdcpa1978-IUD/parkea</link>', styles["Bodyx"]),
        Paragraph('Video disponible: <link href="https://youtube.com/live/CyCH0SRFZp0?feature=share" color="blue">https://youtube.com/live/CyCH0SRFZp0?feature=share</link>', styles["Bodyx"]),
        p("Antes de entregar, verificar que el video público muestre las tres iteraciones y, especialmente, registro de pago, confirmación e historiales operativos. Si no cubre ese flujo, reemplazar el enlace por una grabación actualizada.", styles["Bodyx"]),
        Paragraph("9. Conclusiones", styles["H1x"]),
        p("La Iteración 3 integra el registro financiero con la vigencia que se valida al ingresar vehículos. La validación de monto, duración, cliente y rol, el encadenamiento de periodos y el historial aportan control y trazabilidad. El plan de pruebas y los casos automatizados verifican cálculos y rechazos; la demostración debe completar la evidencia desde la interfaz.", styles["Bodyx"]),
    ]
    pdf = SimpleDocTemplate(str(OUT_PDF), pagesize=letter, rightMargin=.65 * inch,
                            leftMargin=.65 * inch, topMargin=.55 * inch, bottomMargin=.55 * inch)

    def page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(.65 * inch, .32 * inch, "PARKEA · Evidencia de Aprendizaje 3")
        canvas.drawRightString(7.85 * inch, .32 * inch, str(doc.page))
        canvas.restoreState()

    pdf.build(story, onFirstPage=page_footer, onLaterPages=page_footer)


def make_pdf_table(rows, widths):
    data = []
    for ri, row in enumerate(rows):
        cell_style = ParagraphStyle(
            name=f"TableCell{ri}",
            fontName="Arial-Bold" if ri == 0 else "Arial",
            fontSize=7.1,
            leading=9,
            textColor=colors.white if ri == 0 else colors.HexColor(INK),
        )
        data.append([Paragraph(str(value).replace("&", "&amp;"), cell_style) for value in row])
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    return table


def main():
    global IMAGE_DIR
    with tempfile.TemporaryDirectory(prefix="parkea_ea3_") as image_dir:
        IMAGE_DIR = Path(image_dir)
        diagrams = ROOT / "diagramas"
        images = {
            "use_case": diagrams / "EA3_01_casos_uso_pagos.png",
            "sequences": [
                ("Inicio de sesión", diagrams / "EA3_02_secuencia_inicio_sesion.png"),
                ("Iteración 1: accesos", diagrams / "EA3_03_secuencia_accesos.png"),
                ("Iteración 2: usuarios y celdas", diagrams / "EA3_04_secuencia_usuarios_celdas.png"),
                ("Iteración 3: pagos", diagrams / "EA3_05_secuencia_pagos.png"),
                ("Iteración 3: clientes sin vigencia", diagrams / "EA3_07_secuencia_clientes_sin_vigencia.png"),
                ("Iteración 3: historial por cliente", diagrams / "EA3_08_secuencia_historial_cliente.png"),
            ],
            "components": diagrams / "EA3_06_componentes.png",
        }
        build_docx(images)
        build_pdf(images)
    print(OUT_DOCX)
    print(OUT_PDF)


if __name__ == "__main__":
    main()
