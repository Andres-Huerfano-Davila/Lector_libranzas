# app.py

import re
import io
import pandas as pd
import streamlit as st
from pypdf import PdfReader
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract


# =========================================================
# CONFIGURACIÓN STREAMLIT
# =========================================================

st.set_page_config(
    page_title="Extractor de Libranzas",
    page_icon="📄",
    layout="wide"
)

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #f5fffc 0%, #e9fff8 45%, #ffffff 100%);
}
h1, h2, h3 {
    color: #066b5f;
}
.stButton button, .stDownloadButton button {
    background-color: #00b894;
    color: white;
    border-radius: 12px;
    border: none;
    padding: 0.6rem 1rem;
    font-weight: bold;
}
.stButton button:hover, .stDownloadButton button:hover {
    background-color: #008f76;
    color: white;
}
</style>
""", unsafe_allow_html=True)

st.title("📄 Extractor automático de Libranzas")
st.write(
    "Carga PDFs de libranza y el sistema intentará extraer automáticamente: "
    "**empleado, cédula, entidad, NIT, libranza, cuotas, saldo y método de lectura**."
)

st.info(
    "Los PDFs escaneados o escritos a mano se leen con OCR. "
    "Cuando el método sea OCR, valida los datos porque puede haber confusión en números manuscritos."
)


# =========================================================
# UTILIDADES
# =========================================================

def limpiar_texto(texto: str) -> str:
    if not texto:
        return ""

    reemplazos = {
        "\n": " ",
        "\t": " ",
        "  ": " "
    }

    for k, v in reemplazos.items():
        texto = texto.replace(k, v)

    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def normalizar_numero(valor):
    if not valor:
        return ""
    valor = re.sub(r"[^\d]", "", str(valor))
    return int(valor) if valor else ""


def normalizar_documento(valor):
    if not valor:
        return ""
    return re.sub(r"[^\d]", "", str(valor))


def limpiar_entidad(entidad):
    if not entidad:
        return ""

    entidad = entidad.strip()
    entidad = re.sub(r"\s+", " ", entidad)
    entidad = entidad.replace(" SAS", " S.A.S")
    entidad = entidad.replace("SAS", "S.A.S")
    entidad = entidad.replace("S.A.S S.A.S", "S.A.S")
    entidad = entidad.replace("_", " ")
    entidad = entidad.replace('"', "")
    entidad = entidad.strip(" .,-:")

    return entidad.upper()


def limpiar_nombre(nombre):
    if not nombre:
        return ""

    nombre = nombre.strip()
    nombre = re.sub(r"[_]+", " ", nombre)
    nombre = re.sub(r"\s+", " ", nombre)
    nombre = re.sub(r"[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]", "", nombre)
    return nombre.upper().strip()


def mejorar_imagen_para_ocr(img):
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.4)
    img = img.filter(ImageFilter.SHARPEN)
    return img


# =========================================================
# LECTURA PDF DIGITAL / OCR
# =========================================================

def extraer_texto_pdf_digital(archivo_pdf):
    texto = ""

    try:
        archivo_pdf.seek(0)
        reader = PdfReader(archivo_pdf)

        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                texto += " " + page_text

    except Exception:
        return ""

    return limpiar_texto(texto)


def extraer_texto_pdf_ocr(archivo_pdf):
    texto = ""

    try:
        archivo_pdf.seek(0)
        pdf_bytes = archivo_pdf.read()

        imagenes = convert_from_bytes(
            pdf_bytes,
            dpi=300
        )

        for img in imagenes:
            img = mejorar_imagen_para_ocr(img)

            try:
                texto += " " + pytesseract.image_to_string(img, lang="spa")
            except Exception:
                texto += " " + pytesseract.image_to_string(img)

    except Exception as e:
        return f"ERROR_OCR: {e}"

    return limpiar_texto(texto)


def texto_parece_basura(texto):
    if not texto:
        return True

    if len(texto) < 150:
        return True

    caracteres_raros = len(
        re.findall(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s\.\,\:\;\$\-\#\/]", texto)
    )

    proporcion_raros = caracteres_raros / max(len(texto), 1)

    palabras_clave = [
        "libranza",
        "cedula",
        "cédula",
        "cuota",
        "descuento",
        "nit",
        "salario",
        "pagare",
        "pagaré"
    ]

    tiene_palabras_clave = any(p in texto.lower() for p in palabras_clave)

    return proporcion_raros > 0.14 or not tiene_palabras_clave


def extraer_texto_pdf(archivo_pdf):
    texto_digital = extraer_texto_pdf_digital(archivo_pdf)

    if texto_parece_basura(texto_digital):
        texto_ocr = extraer_texto_pdf_ocr(archivo_pdf)

        if texto_ocr and not texto_ocr.startswith("ERROR_OCR"):
            return texto_ocr, "OCR"

        return texto_digital + " " + texto_ocr, "PDF digital / OCR con alerta"

    return texto_digital, "PDF digital"


# =========================================================
# EXTRACCIONES ESPECÍFICAS
# =========================================================

def extraer_nits(texto):
    nits = []

    patrones = [
        r"NIT\s*[:\.]?\s*([0-9\.\-]+)",
        r"con\s+NIT\s*[:\.]?\s*([0-9\.\-]+)",
        r"identificada\s+con\s+NIT\.?\s*([0-9\.\-]+)",
        r"identificado\s+con\s+NIT\.?\s*([0-9\.\-]+)"
    ]

    for patron in patrones:
        for match in re.finditer(patron, texto, re.IGNORECASE):
            nit = normalizar_documento(match.group(1))
            if nit:
                nits.append(nit)

    return list(set(nits))


def extraer_nit_entidad(texto):
    patrones = [
        r"NIT\s*[:\.]?\s*([0-9\.\-]+)",
        r"NIT\.?\s*([0-9\.\-]+)",
        r"identificado con NIT\s*([0-9\.\-]+)",
        r"identificada con NIT\.?\s*([0-9\.\-]+)"
    ]

    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extraer_cedula(texto):
    nits_detectados = extraer_nits(texto)

    patrones_prioritarios = [
        r"identificado(?:\(a\))?\s+con\s+c[eé]dula(?:\s+de\s+ciudadan[ií]a)?\s*(?:No\.?)?\s*([0-9\.\-\s]{6,20})",
        r"identificada(?:\(a\))?\s+con\s+c[eé]dula(?:\s+de\s+ciudadan[ií]a)?\s*(?:No\.?)?\s*([0-9\.\-\s]{6,20})",
        r"c[eé]dula(?:\s+de\s+ciudadan[ií]a)?\s*(?:No\.?)?\s*([0-9\.\-\s]{6,20})",
        r"C\.?C\.?\s*(?:No\.?)?\s*([0-9\.\-\s]{6,20})",
        r"N[uú]mero\s*([0-9\.\-\s]{6,20})",
        r"CC\s*o\s*NIT\s*[:\.]?\s*([0-9\.\-\s]{6,20})"
    ]

    candidatos = []

    for patron in patrones_prioritarios:
        for match in re.finditer(patron, texto, re.IGNORECASE):
            cedula = normalizar_documento(match.group(1))

            if not cedula:
                continue

            if cedula in nits_detectados:
                continue

            if 6 <= len(cedula) <= 10:
                candidatos.append(cedula)

    if candidatos:
        return candidatos[0]

    return ""


def extraer_empleado(texto):
    patrones = [
        r"su empleado\s+(.+?)\s+identificado con c[eé]dula",
        r"el señor\s+(.+?)\s+identificado con C\.?C\.?",
        r"el\(la\) señor\(a\s*\)\s+(.+?)\s+con c[eé]dula",
        r"señor\(a\)\s+(.+?)\s*,?\s*identificado",
        r"Yo,\s*(.+?)\s+identificado\(a\)",
        r"Nombre completo\s*[:\-]?\s*(.+?)\s+C\.?C\.?",
        r"notificando.*?pago del señor\s+(.+?)\s+identificado",
        r"Nombre\s*[:\-]?\s*(.+?)\s+identificado"
    ]

    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            nombre = limpiar_nombre(match.group(1))
            if nombre:
                return nombre

    return ""


def extraer_entidad(texto, nombre_archivo=""):
    texto_upper = texto.upper()
    archivo_upper = nombre_archivo.upper()

    if "COOMUNIDAD" in texto_upper or "COOMUNIDAD" in archivo_upper:
        return "COOPERATIVA DE CREDITO Y SERVICIO COOMUNIDAD"

    if "CREDIRUZ" in texto_upper or "CREDIRUZ" in archivo_upper:
        return "CREDIRUZ S.A.S"

    if "VISION FUTURO" in texto_upper or "VISIÓN FUTURO" in texto_upper:
        return "VISION FUTURO ORGANISMO COOPERATIVO"

    if "COMPAÑIA DE INVERSIONES Y LIBRANZAS" in texto_upper or "COMPAÑÍA DE INVERSIONES Y LIBRANZAS" in texto_upper:
        return "COMPAÑIA DE INVERSIONES Y LIBRANZAS S.A.S"

    patrones = [
        r"^(.+?)\s+NIT\s*[0-9\.\-]+",
        r"activa en\s+(.+?)\s+NIT",
        r"a nombre de\s+(.+?)\s+NIT",
        r"Representante Legal de\s+(.+?)\s+identificado con NIT",
        r"para con\s+(.+?)\s*,?\s*y que a la fecha",
        r"A favor de\s+(.+?)(?:\s+Libranza|\s+Como constancia|$)",
        r"consumidor financiero del Banco, Financiera o Cooperativa,\s*(.+?)\s+Y siendo empleado"
    ]

    descartes = [
        "JERONIMO MARTINS",
        "JERÓNIMO MARTINS",
        "SEÑORES",
        "BUCARAMANGA",
        "MEDELLÍN",
        "MEDELLIN",
        "CARTAGENA",
        "BOGOTA",
        "BOGOTÁ",
        "COLOMBIA"
    ]

    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            entidad = limpiar_entidad(match.group(1))

            if entidad and not any(x in entidad for x in descartes):
                return entidad

    return ""


def extraer_obligacion(texto):
    patrones = [
        r"libranza\s+N\.?\s*([A-Za-z0-9\.\-]+)",
        r"libranza\s+No\.?\s*([A-Za-z0-9\.\-]+)",
        r"Libranza\s+No\.?\s*([A-Za-z0-9\.\-]+)",
        r"obligaci[oó]n\s+N\s*([0-9\.\-]+)",
        r"Pagare\s+N\s*([0-9\.\-]+)",
        r"Pagar[eé]\s+N[°º]?\s*([0-9\.\-]+)",
        r"PAGAR[EÉ]\s+A\s+LA\s+ORDEN/LIBRANZA\s*([0-9\.\-]+)"
    ]

    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extraer_numero_cuotas(texto):
    patrones = [
        r"(\d+)\s+cuotas mensuales",
        r"descontadas.*?(\d+)\s+cuotas mensuales",
        r"total de\s+(\d+)\s+cuotas",
        r"se debe descontar el total de\s+(\d+)\s+cuotas"
    ]

    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            return normalizar_numero(match.group(1))

    return ""


def extraer_cuota_mensual(texto):
    patrones = [
        r"cuotas mensuales por valor cada una de\s*\$?\s*([0-9\.\,]+)",
        r"cuotas mensuales de\s*\$?\s*([0-9\.\,]+)",
        r"cada una de ellas por el valor de\s*\$?\s*([0-9\.\,]+)",
        r"por valor de\s*\$?\s*([0-9\.\,]+)",
        r"por valor cada una de\s*\$?\s*([0-9\.\,]+)",
        r"cuota mensual.*?\$?\s*([0-9\.\,]+)",
        r"valor total de la cuota mensual.*?\$?\s*([0-9\.\,]+)",
        r"cuotas de\s*\$?\s*([0-9\.\,]+)\s*mensual",
        r"cuotas?\s+mensuales.*?\$?\s*([0-9\.\,]+)"
    ]

    candidatos = []

    for patron in patrones:
        for match in re.finditer(patron, texto, re.IGNORECASE):
            valor = normalizar_numero(match.group(1))
            if valor and 1000 <= valor <= 10000000:
                candidatos.append(valor)

    if candidatos:
        return candidatos[0]

    return ""


def extraer_cuota_quincenal(texto):
    patrones = [
        r"valor a descontar ser[ií]an\s*\$?\s*([0-9\.\,]+)\s*en cada quincena",
        r"quincenal.*?\$?\s*([0-9\.\,]+)",
        r"cada quincena.*?\$?\s*([0-9\.\,]+)"
    ]

    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            return normalizar_numero(match.group(1))

    return ""


def extraer_saldo(texto):
    patrones = [
        r"saldo pendiente de\s*\$?\s*([0-9\.\,]+)",
        r"a la fecha suma la cifra de\s*\$?\s*([0-9\.\,]+)",
        r"hasta completar la suma de\s*\$?\s*([0-9\.\,]+)",
        r"valor total de\s*\$?\s*([0-9\.\,]+)",
        r"para un valor total de\s*\$?\s*([0-9\.\,]+)",
        r"saldo.*?\$?\s*([0-9\.\,]+)"
    ]

    candidatos = []

    for patron in patrones:
        for match in re.finditer(patron, texto, re.IGNORECASE):
            valor = normalizar_numero(match.group(1))
            if valor and valor >= 1000:
                candidatos.append(valor)

    if candidatos:
        return candidatos[0]

    return ""


# =========================================================
# VALIDACIÓN Y PROCESAMIENTO
# =========================================================

def validar_registro(registro):
    faltantes = []

    campos_obligatorios = [
        "Cédula",
        "Entidad",
        "Cuota mensual"
    ]

    for campo in campos_obligatorios:
        if registro.get(campo, "") in ["", None]:
            faltantes.append(campo)

    if faltantes:
        return "Revisar: falta " + ", ".join(faltantes)

    if registro.get("Método lectura") == "OCR":
        return "OK - validar OCR"

    return "OK"


def procesar_pdf(archivo):
    texto, metodo = extraer_texto_pdf(archivo)

    registro = {
        "Archivo": archivo.name,
        "Método lectura": metodo,
        "Empleado": extraer_empleado(texto),
        "Cédula": extraer_cedula(texto),
        "Entidad": extraer_entidad(texto, archivo.name),
        "NIT entidad": extraer_nit_entidad(texto),
        "Obligación/Libranza": extraer_obligacion(texto),
        "Número cuotas": extraer_numero_cuotas(texto),
        "Cuota mensual": extraer_cuota_mensual(texto),
        "Cuota quincenal": extraer_cuota_quincenal(texto),
        "Saldo": extraer_saldo(texto),
        "Texto leído": texto[:4000]
    }

    registro["Estado"] = validar_registro(registro)

    return registro


# =========================================================
# INTERFAZ
# =========================================================

st.subheader("📤 Carga de PDFs")

archivos = st.file_uploader(
    "Carga uno o varios PDF de libranzas",
    type=["pdf"],
    accept_multiple_files=True
)

if archivos:
    resultados = []
    errores = []

    progress = st.progress(0)
    status = st.empty()

    for i, archivo in enumerate(archivos, start=1):
        try:
            status.write(f"Procesando: {archivo.name}")
            resultados.append(procesar_pdf(archivo))

        except Exception as e:
            errores.append({
                "Archivo": archivo.name,
                "Error": str(e)
            })

            resultados.append({
                "Archivo": archivo.name,
                "Método lectura": "",
                "Empleado": "",
                "Cédula": "",
                "Entidad": "",
                "NIT entidad": "",
                "Obligación/Libranza": "",
                "Número cuotas": "",
                "Cuota mensual": "",
                "Cuota quincenal": "",
                "Saldo": "",
                "Estado": f"ERROR: {e}",
                "Texto leído": ""
            })

        progress.progress(i / len(archivos))

    status.success("Proceso finalizado ✅")

    df = pd.DataFrame(resultados)

    columnas_salida = [
        "Estado",
        "Archivo",
        "Método lectura",
        "Empleado",
        "Cédula",
        "Entidad",
        "NIT entidad",
        "Obligación/Libranza",
        "Número cuotas",
        "Cuota mensual",
        "Cuota quincenal",
        "Saldo"
    ]

    st.subheader("📊 Resultado consolidado")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("PDF procesados", len(df))
    col2.metric("OK", int(df["Estado"].astype(str).str.startswith("OK").sum()))
    col3.metric("Por revisar", int((~df["Estado"].astype(str).str.startswith("OK")).sum()))
    col4.metric("Leídos con OCR", int((df["Método lectura"] == "OCR").sum()))

    st.dataframe(df[columnas_salida], use_container_width=True)

    with st.expander("🔎 Ver texto leído por PDF"):
        for _, row in df.iterrows():
            st.markdown(f"### {row['Archivo']}")
            st.write(f"**Método:** {row['Método lectura']}")
            st.text(row["Texto leído"])

    if errores:
        st.subheader("⚠️ Errores técnicos")
        st.dataframe(pd.DataFrame(errores), use_container_width=True)

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df[columnas_salida].to_excel(
            writer,
            index=False,
            sheet_name="Consolidado"
        )

        df[df["Estado"].astype(str).str.startswith("OK")][columnas_salida].to_excel(
            writer,
            index=False,
            sheet_name="OK"
        )

        df[~df["Estado"].astype(str).str.startswith("OK")][columnas_salida + ["Texto leído"]].to_excel(
            writer,
            index=False,
            sheet_name="Revisar"
        )

        if errores:
            pd.DataFrame(errores).to_excel(
                writer,
                index=False,
                sheet_name="Errores"
            )

    st.download_button(
        label="📥 Descargar Excel consolidado",
        data=output.getvalue(),
        file_name="libranzas_extraidas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.warning("Carga uno o varios PDFs para iniciar.")


st.markdown("---")
st.caption("Creado por Andrés Huérfano Dávila")
