import streamlit as st
from pypdf import PdfReader, PdfWriter
import re
import os
import io
import gc
import zipfile
import tempfile
import time


def extract_section_name(text):
    """Extrae el nombre de sección después de 'Por leer en'"""
    match = re.search(r'Por leer en:?\s*(.+?)((?:\n|$))', text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def is_page_separator(text):
    """Detecta si una página contiene 'page X of Y' o 'En proceso en'"""
    has_page_of = bool(re.search(r'page\s+\d+\s+of\s+\d+', text, re.IGNORECASE))
    has_en_proceso = bool(re.search(r'En proceso en', text, re.IGNORECASE))
    return has_page_of or has_en_proceso


def is_new_candidate_page(text):
    """Detecta si una página es el inicio de un nuevo candidato."""
    has_datos = bool(re.search(r'Datos del candidato', text, re.IGNORECASE))
    has_ajuste = bool(re.search(r'\d+%\s*ajuste', text, re.IGNORECASE))
    return has_datos or has_ajuste


def extract_position_name(text):
    """Extrae el nombre de la posición (última línea del texto extraído)."""
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
    """Limpia el nombre para usarlo como nombre de archivo."""
    if not name:
        return "PDF"
    clean = re.sub(r'[^\w\s]', '', name)
    clean = re.sub(r'\s+', '_', clean.strip())
    return clean[:50] if clean else "PDF"


def detect_format_fast(pdf_path):
    """Detecta el formato leyendo solo las primeras 10 páginas."""
    reader = PdfReader(pdf_path)
    for i in range(min(10, len(reader.pages))):
        text = reader.pages[i].extract_text() or ""
        if extract_section_name(text) or is_page_separator(text):
            del reader
            return 'legacy'
    del reader
    return 'candidates'


def process_single_pass(pdf_path, progress_bar, status_text):
    """Procesa el PDF en una sola pasada, escribiendo cada candidato al ZIP
    apenas se detecta el siguiente. Mínimo uso de memoria."""

    fmt = detect_format_fast(pdf_path)
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    # ZIP en disco
    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    tmp_zip_path = tmp_zip.name

    key_name = ""
    section_count = 1
    current_writer = None
    current_include = True  # Si la primera página del segmento se incluye

    with zipfile.ZipFile(tmp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:

        for page_num in range(total_pages):
            text = reader.pages[page_num].extract_text() or ""
            is_boundary = False
            include_this_page = True

            if fmt == 'legacy':
                new_section = extract_section_name(text)
                is_sep = is_page_separator(text)

                if new_section or is_sep:
                    is_boundary = True
                    if new_section:
                        key_name = new_section
                        include_this_page = True
                    else:
                        include_this_page = False
            else:
                if not key_name:
                    extracted = extract_position_name(text)
                    if extracted:
                        key_name = extracted

                if is_new_candidate_page(text):
                    is_boundary = True
                    include_this_page = True

            # Si encontramos frontera, guardar el segmento anterior
            if is_boundary:
                if current_writer and len(current_writer.pages) > 0:
                    clean_key = clean_name_for_filename(key_name)
                    buf = io.BytesIO()
                    current_writer.write(buf)
                    zf.writestr(f'{clean_key}_{section_count}.pdf', buf.getvalue())
                    buf.close()
                    del buf
                    section_count += 1

                del current_writer
                current_writer = PdfWriter()
                gc.collect()

                if include_this_page:
                    current_writer.add_page(reader.pages[page_num])
            else:
                if current_writer:
                    current_writer.add_page(reader.pages[page_num])

            # Actualizar progreso cada página
            progress = (page_num + 1) / total_pages
            status_text.text(f'Página {page_num + 1} de {total_pages} — {section_count - 1} PDFs generados')
            progress_bar.progress(progress)

        # Guardar último segmento
        if current_writer and len(current_writer.pages) > 0:
            clean_key = clean_name_for_filename(key_name)
            buf = io.BytesIO()
            current_writer.write(buf)
            zf.writestr(f'{clean_key}_{section_count}.pdf', buf.getvalue())
            buf.close()
            del buf

    del current_writer
    del reader
    tmp_zip.close()
    gc.collect()

    zip_filename = f"{clean_name_for_filename(key_name)}.zip"
    return tmp_zip_path, zip_filename, section_count


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
               - **Formato nuevo**: separación por candidato (detecta "Datos del candidato" / "% ajuste")
            3. Cada candidato/sección se separa en un PDF individual
            4. Descarga el ZIP con todos los PDFs generados
            """)
            uploaded_files = st.file_uploader(
                "Selecciona uno o más archivos PDF",
                type=['pdf'],
                accept_multiple_files=True
            )

            if uploaded_files and st.button('Separar PDFs'):
                for file_idx, uploaded_file in enumerate(uploaded_files):
                    st.write(f'**Procesando:** {uploaded_file.name}')

                    # Guardar a disco para no mantener en memoria
                    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                    tmp_pdf.write(uploaded_file.getvalue())
                    tmp_pdf.close()

                    # Procesar en una sola pasada
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    tmp_zip_path, zip_filename, total = process_single_pass(
                        tmp_pdf.name, progress_bar, status_text
                    )

                    progress_bar.progress(1.0)
                    status_text.text(f'¡Completado! {total} PDFs generados')

                    # Limpiar PDF temporal
                    os.unlink(tmp_pdf.name)

                    # Leer ZIP para descarga
                    with open(tmp_zip_path, 'rb') as f:
                        zip_data = f.read()
                    os.unlink(tmp_zip_path)

                    st.download_button(
                        f"Descargar {zip_filename}",
                        zip_data,
                        zip_filename,
                        "application/zip",
                        key=f"download_{file_idx}"
                    )
                    del zip_data
                    gc.collect()

                st.success('¡Proceso finalizado!')

        else:
            st.error("Por favor, inicia sesión para usar esta funcionalidad.")


if __name__ == '__main__':
    main()
