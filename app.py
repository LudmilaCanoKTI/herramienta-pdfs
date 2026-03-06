import streamlit as st
from pypdf import PdfReader, PdfWriter
import re
import os
import io
import gc
import zipfile
import tempfile


def extract_section_name(text):
    """Extrae el nombre de sección después de 'Por leer en'"""
    match = re.search(r'Por leer en:?\s*(.+?)((?:\n|$))', text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def is_page_separator(text):
    """Detecta si una página contiene 'page X of Y' o 'En proceso en' y debe actuar como separador"""
    has_page_of = bool(re.search(r'page\s+\d+\s+of\s+\d+', text, re.IGNORECASE))
    has_en_proceso = bool(re.search(r'En proceso en', text, re.IGNORECASE))
    return has_page_of or has_en_proceso


def is_new_candidate_page(text):
    """Detecta si una página es el inicio de un nuevo candidato.
    Busca indicadores como 'Datos del candidato' y '% ajuste'."""
    has_datos = bool(re.search(r'Datos del candidato', text, re.IGNORECASE))
    has_ajuste = bool(re.search(r'\d+%\s*ajuste', text, re.IGNORECASE))
    return has_datos or has_ajuste


def extract_position_name(text):
    """Extrae el nombre de la posición del encabezado de la página.
    El nombre de la posición aparece como encabezado visual en cada página,
    pero en el texto extraído se ubica como la última línea."""
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]

    if not lines:
        return None

    last_line = lines[-1]

    if re.match(r'^\d+/\d+$', last_line):
        return None
    if re.search(r'@|\d{3}\s\d{3}\s\d{3}|% ajuste|Datos del candidato', last_line):
        return None

    if len(last_line) > 5:
        return last_line

    return None


def clean_name_for_filename(name):
    """Limpia el nombre de la posición para usarlo como nombre de archivo."""
    if not name:
        return "PDF"
    clean = re.sub(r'[^\w\s]', '', name)
    clean = re.sub(r'\s+', '_', clean.strip())
    return clean[:50] if clean else "PDF"


def detect_format(pdf_file):
    """Detecta el formato del PDF: 'legacy' o 'candidates'.
    Lee solo las primeras páginas para no cargar todo en memoria."""
    pdf_reader = PdfReader(pdf_file)
    pages_to_check = min(10, len(pdf_reader.pages))
    for page_num in range(pages_to_check):
        text = pdf_reader.pages[page_num].extract_text() or ""
        if extract_section_name(text) or is_page_separator(text):
            return 'legacy'
    return 'candidates'


def save_writer_to_zip(zip_file, pdf_writer, filename):
    """Escribe un PdfWriter directamente al ZIP sin acumular en memoria."""
    if pdf_writer and len(pdf_writer.pages) > 0:
        pdf_bytes_io = io.BytesIO()
        pdf_writer.write(pdf_bytes_io)
        zip_file.writestr(filename, pdf_bytes_io.getvalue())
        pdf_bytes_io.close()
        del pdf_bytes_io
        gc.collect()


def split_pdf_legacy_to_zip(pdf_file, zip_file, start_count):
    """Divide un PDF (formato legacy) escribiendo directo al ZIP."""
    pdf_reader = PdfReader(pdf_file)
    current_pdf_writer = None
    section_count = start_count
    section_name = ""
    total_pdfs = 0

    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text = page.extract_text() or ""

        new_section_name = extract_section_name(text)
        is_separator_to_exclude = is_page_separator(text)

        if new_section_name or is_separator_to_exclude:
            if new_section_name:
                section_name = new_section_name

            if current_pdf_writer:
                clean_section = clean_name_for_filename(section_name)
                save_writer_to_zip(zip_file, current_pdf_writer, f'{clean_section}_{section_count}.pdf')
                section_count += 1
                total_pdfs += 1
                del current_pdf_writer

            current_pdf_writer = PdfWriter()

            if new_section_name:
                current_pdf_writer.add_page(page)
        else:
            if current_pdf_writer:
                current_pdf_writer.add_page(page)

    if current_pdf_writer and len(current_pdf_writer.pages) > 0:
        clean_section = clean_name_for_filename(section_name)
        save_writer_to_zip(zip_file, current_pdf_writer, f'{clean_section}_{section_count}.pdf')
        total_pdfs += 1
        del current_pdf_writer

    del pdf_reader
    gc.collect()
    return section_name, section_count + 1, total_pdfs


def split_pdf_by_candidates_to_zip(pdf_file, zip_file, start_count):
    """Divide un PDF por candidato escribiendo directo al ZIP."""
    pdf_reader = PdfReader(pdf_file)
    current_pdf_writer = None
    section_count = start_count
    position_name = ""
    total_pdfs = 0

    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text = page.extract_text() or ""

        if not position_name:
            extracted_name = extract_position_name(text)
            if extracted_name:
                position_name = extracted_name

        if is_new_candidate_page(text):
            if current_pdf_writer:
                clean_position = clean_name_for_filename(position_name)
                save_writer_to_zip(zip_file, current_pdf_writer, f'{clean_position}_{section_count}.pdf')
                section_count += 1
                total_pdfs += 1
                del current_pdf_writer

            current_pdf_writer = PdfWriter()

        if current_pdf_writer:
            current_pdf_writer.add_page(page)

    if current_pdf_writer:
        clean_position = clean_name_for_filename(position_name)
        save_writer_to_zip(zip_file, current_pdf_writer, f'{clean_position}_{section_count}.pdf')
        total_pdfs += 1
        del current_pdf_writer

    del pdf_reader
    gc.collect()
    return position_name, section_count + 1, total_pdfs


def process_files_to_zip(uploaded_files):
    """Procesa todos los archivos y genera un ZIP en disco (no en memoria)."""
    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    tmp_zip_path = tmp_zip.name
    section_name = ""
    current_count = 1
    total_pdfs = 0

    with zipfile.ZipFile(tmp_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for uploaded_file in uploaded_files:
            # Guardar PDF subido a disco temporalmente para no duplicar en memoria
            tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            tmp_pdf.write(uploaded_file.getvalue())
            tmp_pdf.close()

            # Detectar formato
            with open(tmp_pdf.name, 'rb') as f:
                fmt = detect_format(f)

            # Procesar según formato
            with open(tmp_pdf.name, 'rb') as f:
                if fmt == 'legacy':
                    last_name, next_count, count = split_pdf_legacy_to_zip(
                        f, zip_file, current_count
                    )
                else:
                    last_name, next_count, count = split_pdf_by_candidates_to_zip(
                        f, zip_file, current_count
                    )

            current_count = next_count
            total_pdfs += count
            if last_name:
                section_name = last_name

            # Limpiar archivo temporal
            os.unlink(tmp_pdf.name)
            gc.collect()

    # Generar nombre del ZIP
    clean_zip_name = re.sub(r'[^\w\s]', '', section_name).replace(' ', '')
    if not clean_zip_name:
        clean_zip_name = "Separados"
    zip_filename = f"{clean_zip_name}_PDFsSeparados.zip"

    return tmp_zip_path, zip_filename, total_pdfs


def check_credentials(username, password):
    USERNAME = os.getenv("MY_APP_USERNAME", "admin")
    PASSWORD = os.getenv("MY_APP_PASSWORD", "password")
    return username == USERNAME and password == PASSWORD


def main():
    st.title('Separador de PDFs por Sección')

    tab1, tab2 = st.tabs(["Iniciar sesión", "Procesar PDF"])

    with tab1:
        if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
            username = st.text_input("Nombre de usuario")
            password = st.text_input("Contraseña", type="password")
            if st.button("Ingresar"):
                if check_credentials(username, password):
                    st.session_state['logged_in'] = True
                    st.success("Has ingresado correctamente.")
                else:
                    st.error("Credenciales incorrectas. Intenta nuevamente.")
        else:
            st.success("Ya estás autenticado.")

    with tab2:
        if 'logged_in' in st.session_state and st.session_state['logged_in']:
            st.markdown("""
            ### Instrucciones
            1. Sube uno o más PDFs con secciones marcadas
            2. La aplicación detecta automáticamente el formato:
               - **Formato anterior**: separadores "Por leer en", "page X of Y", "En proceso en"
               - **Formato nuevo**: separación directa por candidato (detecta "Datos del candidato" / "% ajuste")
            3. Cada candidato/sección se separa en un PDF individual
            4. Descarga el ZIP con todos los PDFs generados
            """)
            uploaded_files = st.file_uploader("Selecciona uno o más archivos PDF", type=['pdf'], accept_multiple_files=True)
            if uploaded_files and st.button('Separar PDFs'):
                with st.spinner('Procesando PDFs...'):
                    tmp_zip_path, zip_filename, total_pdfs = process_files_to_zip(uploaded_files)

                # Leer ZIP desde disco para el botón de descarga
                with open(tmp_zip_path, 'rb') as f:
                    zip_data = f.read()

                # Limpiar archivo temporal
                os.unlink(tmp_zip_path)

                st.download_button("Descargar PDFs", zip_data, zip_filename, "application/zip")
                st.success(f'Se han generado {total_pdfs} PDFs')

        else:
            st.error("Por favor, inicia sesión para usar esta funcionalidad.")


if __name__ == '__main__':
    main()
