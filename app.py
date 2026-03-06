import streamlit as st
from pypdf import PdfReader, PdfWriter
import re
import os
import io
import zipfile


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


def detect_format(pdf_reader):
    """Detecta el formato del PDF: 'legacy' (Por leer en / page of / En proceso en)
    o 'candidates' (separación directa por candidato)."""
    pages_to_check = min(10, len(pdf_reader.pages))
    for page_num in range(pages_to_check):
        text = pdf_reader.pages[page_num].extract_text() or ""
        if extract_section_name(text) or is_page_separator(text):
            return 'legacy'
    return 'candidates'


def split_pdf_legacy(pdf_file, start_count):
    """Divide un PDF basándose en 'Por leer en', 'page X of Y' o 'En proceso en'"""
    pdf_reader = PdfReader(pdf_file)
    pdfs_bytes = []
    current_pdf_writer = None
    section_count = start_count
    section_name = ""

    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text = page.extract_text()

        new_section_name = extract_section_name(text)
        is_separator_to_exclude = is_page_separator(text)

        if new_section_name or is_separator_to_exclude:
            if new_section_name:
                section_name = new_section_name

            if current_pdf_writer:
                pdf_bytes_io = io.BytesIO()
                current_pdf_writer.write(pdf_bytes_io)
                pdf_bytes_io.seek(0)
                clean_section = clean_name_for_filename(section_name)
                pdfs_bytes.append((f'{clean_section}_{section_count}.pdf', pdf_bytes_io.read()))
                section_count += 1

            current_pdf_writer = PdfWriter()

            if new_section_name:
                current_pdf_writer.add_page(page)
        else:
            if current_pdf_writer:
                current_pdf_writer.add_page(page)

    if current_pdf_writer and len(current_pdf_writer.pages) > 0:
        pdf_bytes_io = io.BytesIO()
        current_pdf_writer.write(pdf_bytes_io)
        pdf_bytes_io.seek(0)
        clean_section = clean_name_for_filename(section_name)
        pdfs_bytes.append((f'{clean_section}_{section_count}.pdf', pdf_bytes_io.read()))

    return pdfs_bytes, section_name, section_count + 1


def split_pdf_by_candidates(pdf_file, start_count):
    """Divide un PDF separando por cada candidato nuevo.
    Detecta el inicio de un nuevo candidato por 'Datos del candidato' o '% ajuste'.
    Nombra los archivos con la posición + número."""
    pdf_reader = PdfReader(pdf_file)
    pdfs_bytes = []
    current_pdf_writer = None
    section_count = start_count
    position_name = ""

    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text = page.extract_text() or ""

        if not position_name:
            extracted_name = extract_position_name(text)
            if extracted_name:
                position_name = extracted_name

        if is_new_candidate_page(text):
            if current_pdf_writer:
                pdf_bytes_io = io.BytesIO()
                current_pdf_writer.write(pdf_bytes_io)
                pdf_bytes_io.seek(0)
                clean_position = clean_name_for_filename(position_name)
                pdfs_bytes.append((f'{clean_position}_{section_count}.pdf', pdf_bytes_io.read()))
                section_count += 1

            current_pdf_writer = PdfWriter()

        if current_pdf_writer:
            current_pdf_writer.add_page(page)

    if current_pdf_writer:
        pdf_bytes_io = io.BytesIO()
        current_pdf_writer.write(pdf_bytes_io)
        pdf_bytes_io.seek(0)
        clean_position = clean_name_for_filename(position_name)
        pdfs_bytes.append((f'{clean_position}_{section_count}.pdf', pdf_bytes_io.read()))

    return pdfs_bytes, position_name, section_count + 1


def split_pdf_auto(pdf_file, start_count):
    """Detecta automáticamente el formato del PDF y aplica la lógica correspondiente."""
    pdf_bytes = pdf_file.read()

    pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
    fmt = detect_format(pdf_reader)

    if fmt == 'legacy':
        return split_pdf_legacy(io.BytesIO(pdf_bytes), start_count)
    else:
        return split_pdf_by_candidates(io.BytesIO(pdf_bytes), start_count)


def create_zip_from_pdfs(pdfs_bytes, zip_name):
    """Crea un archivo zip con los PDFs generados y nombre basado en la última sección procesada"""
    zip_bytes = io.BytesIO()
    clean_zip_name = re.sub(r'[^\w\s]', '', zip_name).replace(' ', '')
    if not clean_zip_name:
        clean_zip_name = "Separados"
    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, pdf_byte in pdfs_bytes:
            zip_file.writestr(filename, pdf_byte)
    zip_bytes.seek(0)
    return zip_bytes, f"{clean_zip_name}_PDFsSeparados.zip"


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
            if uploaded_files:
                all_pdfs_bytes = []
                section_name = ""
                current_count = 1

                for uploaded_file in uploaded_files:
                    pdfs_bytes, last_section_name, next_count = split_pdf_auto(
                        io.BytesIO(uploaded_file.getvalue()),
                        current_count
                    )
                    all_pdfs_bytes.extend(pdfs_bytes)
                    current_count = next_count
                    if last_section_name:
                        section_name = last_section_name

                if all_pdfs_bytes and st.button('Separar PDFs'):
                    zip_bytes, zip_filename = create_zip_from_pdfs(all_pdfs_bytes, section_name)
                    st.download_button("Descargar PDFs", zip_bytes, zip_filename, "application/zip")
                    st.success(f'Se han generado {len(all_pdfs_bytes)} PDFs')

        else:
            st.error("Por favor, inicia sesión para usar esta funcionalidad.")


if __name__ == '__main__':
    main()
