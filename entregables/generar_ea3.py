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
    ("RF-PAG-05", "El personal autorizado consulta los últimos 100 pagos; cada cliente autenticado consulta únicamente sus propios pagos."),
    ("RF-PAG-06", "Después de un registro exitoso, la interfaz confirma la fecha de vencimiento y actualiza historial y resumen de vigencias."),
]

QUALITY = [
    ("RNF-PAG-01 · Seguridad", "Las rutas requieren JWT; solo ADMINISTRADOR y OPERADOR pueden registrar pagos. CLIENTE no puede registrar ni consultar pagos de otras personas."),
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
        "HU-PAG-02 · Consultar historial propio",
        "Como cliente, quiero consultar mis pagos y fechas de vigencia para conocer el estado de mi mensualidad.",
        [
            "Al abrir Mensualidades, veo mis pagos con monto, fechas de vigencia y método.",
            "La consulta filtra por la identidad autenticada, incluso si se altera información en el navegador.",
            "Si no tengo pagos, se muestra un estado vacío informativo y no datos de otros clientes.",
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
]

TESTS = [
    ["ID", "Escenario / datos", "Resultado esperado", "Evidencia / estado"],
    ["CP-01", "Registrar $120.000, 1 mes, EFECTIVO sin pagos previos.", "El periodo empieza hoy, se calcula fecha final y se confirma el commit.", "Automatizada: test_registration_without_previous_payment_starts_today — PASA."],
    ["CP-02", "Registrar pago cuando el cliente ya tiene vencimiento futuro.", "El nuevo periodo empieza al día siguiente del último vencimiento; no hay solapamiento.", "Automatizada: test_registration_chains_new_period_after_existing_vigency — PASA."],
    ["CP-03", "Registrar para cliente con mensualidad vencida.", "El nuevo periodo inicia hoy y se calcula la fecha final de acuerdo con los meses.", "Automatizada: test_registration_starts_today_when_previous_period_expired — PASA."],
    ["CP-04", "Monto 0, negativo o con más de 2 decimales.", "Validación rechaza la solicitud; no se inserta pago.", "Automatizada: test_payment_rejects_non_positive_amount_and_invalid_month_range — PASA."],
    ["CP-05", "Duración 0 o 25 meses; método fuera del catálogo.", "Validación rechaza la solicitud; no se inserta pago.", "Automatizada: test_payment_rejects_non_positive_amount_and_invalid_month_range — PASA."],
    ["CP-06", "Cliente inexistente o inactivo.", "HTTP 404; no se agrega ni confirma pago.", "Automatizada: test_registration_rejects_missing_or_inactive_client_without_commit — PASA."],
    ["CP-07", "Cliente intenta consultar pagos de otro usuario o registrar un pago.", "Solo se devuelve historial propio; alta denegada por rol.", "Filtro de historial automatizado — PASA; verificar alta denegada en demostración."],
    ["CP-08", "Operador consulta historial con muchos pagos.", "Se muestran máximo 100 pagos, de más reciente a más antiguo.", "Límite de consulta automatizado — PASA; verificar presentación visual en demostración."],
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


def make_mockup():
    image, d = canvas(1200, 760)
    d.rectangle((0, 0, 1200, 68), fill=NAVY)
    text(d, (34, 20), "PARKEA", 25, "#ffffff", True)
    text(d, (150, 25), "Gestión de parqueadero", 15, "#cbd5e1")
    d.rectangle((0, 68, 220, 760), fill="#ffffff")
    for y, label in [(112, "MENÚ PRINCIPAL"), (164, "Resumen general"), (210, "Entradas y salidas"),
                     (256, "Mapa de celdas"), (302, "Usuarios")]:
        text(d, (30, y), label, 14, MUTED if y == 112 else "#475569", y == 112)
    d.rounded_rectangle((12, 326, 208, 370), 8, fill="#eff6ff")
    text(d, (27, 338), "Pagos de mensualidad", 14, BLUE, True)
    text(d, (252, 103), "ADMINISTRACIÓN / PAGOS", 13, MUTED, True)
    text(d, (252, 128), "Pagos de mensualidad", 28, INK, True)
    text(d, (252, 165), "Registra pagos y consulta la vigencia e historial.", 14, MUTED)
    d.rounded_rectangle((252, 203, 1166, 468), 12, fill="#ffffff", outline="#e2e8f0", width=2)
    text(d, (278, 225), "Registrar un pago", 19, INK, True)
    text(d, (278, 253), "La vigencia nueva se encadena después del vencimiento vigente.", 13, MUTED)
    for x, label, value, w in [
        (278, "CLIENTE", "Cliente de prueba · Doc. •••456", 405),
        (713, "MONTO (COP)", "$ 120.000", 190),
        (923, "MESES", "1 (máximo 24)", 217),
    ]:
        text(d, (x, 286), label, 12, "#334155", True)
        d.rounded_rectangle((x, 307, x + w, 351), 6, fill="#ffffff", outline=LINE, width=2)
        text(d, (x + 12, 319), value, 13, "#334155")
    text(d, (278, 370), "MÉTODO DE PAGO", 12, "#334155", True)
    d.rounded_rectangle((278, 390, 683, 429), 6, fill="#ffffff", outline=LINE, width=2)
    text(d, (290, 401), "Efectivo ▾", 13, "#334155")
    d.rounded_rectangle((713, 389, 903, 431), 7, fill=BLUE)
    text(d, (738, 401), "Registrar pago", 14, "#ffffff", True)
    d.rounded_rectangle((252, 490, 1166, 722), 12, fill="#ffffff", outline="#e2e8f0", width=2)
    text(d, (278, 510), "Historial reciente", 19, INK, True)
    text(d, (278, 537), "Últimos 100 pagos", 13, MUTED)
    d.rounded_rectangle((278, 565, 1140, 603), 4, fill="#f8fafc")
    cols = [(294, "CLIENTE"), (468, "MONTO"), (615, "VIGENCIA DESDE"),
            (794, "VIGENCIA HASTA"), (1001, "MÉTODO")]
    for x, label in cols:
        text(d, (x, 577), label, 11, "#475569", True)
    d.line((278, 609, 1140, 609), fill="#e2e8f0", width=2)
    for x, value in [(294, "Cliente de prueba"), (468, "$120.000"), (615, "01/12/2026"),
                     (794, "31/12/2026"), (1001, "EFECTIVO")]:
        text(d, (x, 626), value, 12, "#334155")
    text(d, (278, 678), "Confirmación: Pago registrado. Vigencia hasta 31/12/2026.", 13, "#15803d")
    path = IMAGE_DIR / "mockup.png"
    image.save(path)
    return path


def make_use_case():
    image, d = canvas(1100, 570)
    d.rectangle((250, 35, 1055, 530), outline="#334155", width=3)
    text(d, (480, 48), "PARKEA · GESTIÓN DE PAGOS", 20, NAVY, True)
    for y, label in [(190, "Administrador"), (300, "Operador"), (410, "Cliente")]:
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
        (365, 400, 635, 470, "Consultar vigencia propia"),
    ]
    for x1, y1, x2, y2, label in ellipses:
        d.ellipse((x1, y1, x2, y2), fill="#eff6ff", outline=BLUE, width=2)
        box = d.textbbox((0, 0), label, font=font(14, True))
        d.text(((x1 + x2 - (box[2] - box[0])) / 2, (y1 + y2 - (box[3] - box[1])) / 2 - 5),
               label, fill=INK, font=font(14, True))
    for start, end in [((95, 220), (365, 175)), ((95, 330), (365, 175)),
                       ((95, 330), (365, 305)), ((95, 440), (365, 305)),
                       ((95, 440), (365, 435)), ((635, 175), (690, 175)),
                       ((635, 175), (690, 305))]:
        d.line((*start, *end), fill="#475569", width=2)
    text(d, (368, 505), "Cliente autenticado: solo historial propio · Personal: últimos 100 pagos", 13, MUTED)
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
        "del registro. Los clientes consultan solo su propio historial."
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
        ["RF-PAG-05; RNF-PAG-01, 03", "HU-PAG-02", "Consulta del cliente y aislamiento de información."],
        ["RF-PAG-05, RF-PAG-06; RNF-PAG-04", "HU-PAG-03", "Consulta operativa, historial y actualización de interfaz."],
    ])

    doc.add_page_break()
    doc.add_heading("4. Diagrama de casos de uso", 1)
    doc.add_paragraph(
        "Los actores son Administrador, Operador y Cliente. El administrador y el operador pueden "
        "registrar pagos; el personal consulta el historial operativo. El cliente consulta su propio "
        "historial y vigencia. El registro incluye validar cliente/datos y calcular el periodo."
    )
    add_docx_image(doc, images["use_case"], 6.7)
    doc.add_paragraph("Fuente editable del diagrama: entregables/diagramas/07_casos_uso_pagos.puml.")
    doc.add_heading("5. Mockup de gestión de pagos", 1)
    doc.add_paragraph(
        "La pantalla separa el formulario de registro del historial. Los controles limitan visualmente "
        "los valores y el mensaje de confirmación muestra la fecha final calculada. El cliente solo ve "
        "sus pagos; el personal ve la identificación del cliente."
    )
    add_docx_image(doc, images["mockup"], 6.75)
    doc.add_paragraph("Mockup vectorial adjunto: entregables/mockups/mockup_gestion_pagos.svg.")

    doc.add_page_break()
    doc.add_heading("6. Diagramas actualizados de secuencia y componentes", 1)
    doc.add_heading("6.1 Secuencia integrada de las iteraciones 1, 2 y 3", 2)
    doc.add_paragraph(
        "El diagrama integrado resume el intercambio entre actores, Angular, ApiService, FastAPI, "
        "autenticación, servicio de acceso y PostgreSQL. Incluye accesos de la Iteración 1, usuarios/celdas "
        "de la Iteración 2 y consulta/registro de pagos de la Iteración 3, con respuestas de éxito y error."
    )
    add_docx_image(doc, images["sequence"], 6.8)
    doc.add_paragraph("Fuente editable: entregables/diagramas/08_secuencia_iteraciones1a3.puml.")
    doc.add_heading("6.2 Componentes actualizados", 2)
    doc.add_paragraph(
        "El cliente web contiene la pantalla de pagos y ApiService; FastAPI ofrece GET/POST /api/pagos, "
        "aplica JWT/roles y utiliza SQLAlchemy para acceder a PostgreSQL. Se muestran también los "
        "componentes existentes de accesos, usuarios y celdas."
    )
    add_docx_image(doc, images["components"], 6.8)
    doc.add_paragraph("Fuente editable: entregables/diagramas/06_componentes_iteraciones1a3.puml.")

    doc.add_page_break()
    doc.add_heading("7. Plan de pruebas resumido", 1)
    doc.add_paragraph(
        "Precondiciones: API y base de datos disponibles; usuario de personal autenticado; cliente de "
        "prueba activo y cuentas separadas para verificar autorización. Los casos automatizados se ejecutan "
        "con `python -m unittest test.test_payments -v` desde backend. Completar en la demostración los "
        "casos manuales de interfaz y los permisos con cuentas reales."
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
        "un registro de pago, su confirmación, el historial y la consulta con cuenta de cliente. Si el video "
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
        p("Especificar y evidenciar una gestión de pagos que permita registrar transacciones válidas, mantener periodos de cobertura continuos y restringir la consulta según el rol. Administrador y operador registran pagos de clientes activos; cliente consulta su historial propio. La nueva vigencia comienza hoy si no hay periodo futuro; de lo contrario, el día siguiente al vencimiento más lejano.", styles["Bodyx"]),
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
            ["RF-PAG-05; RNF-PAG-01,03", "HU-PAG-02", "Consulta propia y protección de datos."],
            ["RF-PAG-05,06; RNF-PAG-04", "HU-PAG-03", "Consulta operativa e historial."],
        ], [2.4 * inch, 1.0 * inch, 3.45 * inch]),
        PageBreak(), Paragraph("4. Diagrama de casos de uso", styles["H1x"]),
        p("Administrador y operador registran pagos y consultan el historial operativo. Cliente consulta su historial y vigencia propias. El registro incluye validar datos y cliente, y calcular el periodo.", styles["Bodyx"]),
        PdfImage(str(images["use_case"]), width=6.8 * inch, height=3.52 * inch),
        p("Fuente editable: entregables/diagramas/07_casos_uso_pagos.puml.", styles["Smallx"]),
        PageBreak(),
        Paragraph("5. Mockup de gestión de pagos", styles["H1x"]),
        p("El formulario diferencia el registro del historial, muestra límites de meses y confirma la fecha de vencimiento calculada. Datos ilustrativos no corresponden a clientes reales.", styles["Bodyx"]),
        PdfImage(str(images["mockup"]), width=6.85 * inch, height=4.34 * inch),
        p("Mockup vectorial adjunto: entregables/mockups/mockup_gestion_pagos.svg.", styles["Smallx"]),
        PageBreak(), Paragraph("6. Diagramas actualizados de secuencia y componentes", styles["H1x"]),
        Paragraph("6.1 Secuencia integrada de las iteraciones 1, 2 y 3", styles["H2x"]),
        p("La secuencia integra accesos, usuarios/celdas y el registro/consulta de pagos entre Angular, ApiService, FastAPI, autenticación, servicio de acceso y PostgreSQL. Incluye rutas de éxito y error.", styles["Bodyx"]),
        PdfImage(str(images["sequence"]), width=6.9 * inch, height=3.91 * inch),
        p("Fuente editable: entregables/diagramas/08_secuencia_iteraciones1a3.puml.", styles["Smallx"]),
        Paragraph("6.2 Componentes", styles["H2x"]),
        PdfImage(str(images["components"]), width=6.9 * inch, height=3.22 * inch),
        p("Fuente editable: entregables/diagramas/06_componentes_iteraciones1a3.puml.", styles["Smallx"]),
        PageBreak(), Paragraph("7. Plan de pruebas resumido", styles["H1x"]),
        p("Precondiciones: API y base disponibles; usuario autenticado; cliente de prueba activo e identidades separadas para comprobar permisos. Ejecutar pruebas automatizadas desde backend con `python -m unittest test.test_payments -v`. Completar en la demostración las comprobaciones manuales de interfaz y permisos.", styles["Bodyx"]),
        make_pdf_table(TESTS, [.48 * inch, 1.65 * inch, 2.85 * inch, 1.42 * inch]),
        p("Aceptación global: un pago aparece una sola vez, las fechas son correctas, no se pierden días pagados y las solicitudes inválidas/no autorizadas no cambian datos.", styles["Bodyx"]),
        PageBreak(), Paragraph("8. Repositorio y video", styles["H1x"]),
        Paragraph('Repositorio: <link href="https://github.com/jdcpa1978-IUD/parkea" color="blue">https://github.com/jdcpa1978-IUD/parkea</link>', styles["Bodyx"]),
        Paragraph('Video disponible: <link href="https://youtube.com/live/CyCH0SRFZp0?feature=share" color="blue">https://youtube.com/live/CyCH0SRFZp0?feature=share</link>', styles["Bodyx"]),
        p("Antes de entregar, verificar que el video público muestre las tres iteraciones y, especialmente, registro de pago, confirmación, historial y consulta como cliente. Si no cubre ese flujo, reemplazar el enlace por una grabación actualizada.", styles["Bodyx"]),
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
        images = {
            "mockup": make_mockup(),
            "use_case": make_use_case(),
            "sequence": make_sequence(),
            "components": make_components(),
        }
        build_docx(images)
        build_pdf(images)
    print(OUT_DOCX)
    print(OUT_PDF)


if __name__ == "__main__":
    main()
