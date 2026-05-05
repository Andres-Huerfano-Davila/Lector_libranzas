# app.py

import re
import io
import pandas as pd
import streamlit as st
from pypdf import PdfReader


st.set_page_config(
    page_title="Extractor de Libranzas",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Extractor automático de Libranzas")
st.write("Carga PDFs de libranzas y el sistema intentará extraer: cédula, cuota y entidad.")


def limpiar_texto(texto):
    texto = texto.replace("\n", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def extraer_texto_pdf(archivo_pdf):
    reader = PdfReader(archivo_pdf)
    texto = ""

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            texto += " " + page_text

    return limpiar_texto(texto)


def extraer_cedula(texto):
    patrones = [
        r"c[eé]dula de ciudadan[ií]a No\.?\s*([0-9\.\-]+)",
        r"identificado\(a\).*?No\.?\s*([0-9\.\-]+)",
        r"c[eé]dula.*?No\.?\s*([0-9\.\-]+)",
        r"\bcc\.?\s*([0-9\.\-]+)"
    ]

    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            return re.sub(r"\D", "", match.group(1))

    return ""


def extraer_cuota(texto):
    patrones = [
        r"cuotas mensuales de\s*\$?\s*([0-9\.\,]+)",
        r"retener.*?cuotas.*?\$?\s*([0-9\.\,]+)",
        r"descuento.*?\$?\s*([0-9\.\,]+)"
    ]

    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            valor = match.group(1)
            valor_limpio = re.sub(r"[^\d]", "", valor)
            return int(valor_limpio) if valor_limpio else ""

    return ""


def extraer_entidad(texto):
    patrones = [
        r"Representante Legal de\s+(.+?)\s+identificado con NIT",
        r"para con\s+(.+?)\s*,?\s*y que a la fecha",
        r"a favor de\s+(.+?)\s+identificado con NIT"
    ]

    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            entidad = match.group(1).strip()
            entidad = re.sub(r"\s+", " ", entidad)
            return entidad.upper()

    return ""


def procesar_pdf(archivo):
    texto = extraer_texto_pdf(archivo)

    return {
        "Archivo": archivo.name,
        "Cédula": extraer_cedula(texto),
        "Cuota": extraer_cuota(texto),
        "Entidad": extraer_entidad(texto),
        "Texto encontrado": texto[:500]
    }


archivos = st.file_uploader(
    "Carga uno o varios PDF",
    type=["pdf"],
    accept_multiple_files=True
)

if archivos:
    resultados = []

    with st.spinner("Leyendo PDFs..."):
        for archivo in archivos:
            try:
                resultados.append(procesar_pdf(archivo))
            except Exception as e:
                resultados.append({
                    "Archivo": archivo.name,
                    "Cédula": "",
                    "Cuota": "",
                    "Entidad": "",
                    "Texto encontrado": f"ERROR: {e}"
                })

    df = pd.DataFrame(resultados)

    st.subheader("Resultado consolidado")
    st.dataframe(df, use_container_width=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.drop(columns=["Texto encontrado"], errors="ignore").to_excel(
            writer,
            index=False,
            sheet_name="Libranzas"
        )

    st.download_button(
        label="📥 Descargar Excel consolidado",
        data=output.getvalue(),
        file_name="libranzas_extraidas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
