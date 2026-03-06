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


# ── PASO 1: Escanear páginas (solo texto, rápido) ──────────────────────────

def scan_pages(pdf_path):
    """Escanea el PDF y devuelve la lista de rangos de corte y metadatos.
    NO guarda páginas en memoria, solo registra los índices."""
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    # Detectar formato con las primeras 10 páginas
    fmt = 'candidates'
    for i in range(min(10, total_pages)):
        text = reader.pages[i].extract_text() or ""
        if extract_section_name(text) or is_page_separator(text):
            fmt = 'legacy'
            break

    # Escanear todas las páginas para encontrar puntos de corte
    cuts = []  # Lista de (start_page, end_page, include_first_page)
    section_name = ""
    position_name = ""
    current_start = None
    include_start = True

    for i in range(total_pages):
        text = reader.pages[i].extract_text() or ""

        if fmt == 'legacy':
            new_section = extract_section_name(text)
            is_sep = is_page_separator(text)

            if new_section or is_sep:
                if new_section:
                    section_name = new_section

                if current_start is not None:
                    cuts.append((current_start, i - 1, include_start))

                current_start = i
                include_start = bool(new_section)  # Solo incluir si es "Por leer en"
        else:
            if not position_name:
                extracted = extract_position_name(text)
                if extracted:
                    position_name = extracted

            if is_new_candidate_page(text):
                if current_start is not None:
                    cuts.append((current_start, i - 1, True))
                current_start = i

    # Último segmento
    if current_start is not None:
        cuts.append((current_start, total_pages - 1, include_start if fmt == 'legacy' else True))

    del reader
    gc.collect()

    key_name = section_name if fmt == 'legacy' else position_name
    return cuts, key_name, fmt


# ── PASO 2: Generar PDFs a partir de los rangos ────────────────────────────

def generate_zip(pdf_path, cuts, key_name, fmt, progress_bar):
    """Genera el ZIP leyendo el PDF una sola vez y escribiendo cada segmento a disco."""
    reader = PdfReader(pdf_path)
    clean_key = clean_name_for_filename(key_name)

    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    tmp_zip_path = tmp_zip.name

    total_cuts = len(cuts)

    with zipfile.ZipFile(tmp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for idx, (start, end, include_first) in enumerate(cuts):
            writer = PdfWriter()

            for page_num in range(start, end + 1):
                # En legacy, si es la primera página y no debe incluirse, saltar
                if page_num == start and not include_first:
                    continue
                writer.add_page(reader.pages[page_num])

            if len(writer.pages) > 0:
                pdf_buf = io.BytesIO()
                writer.write(pdf_buf)
                zf.writestr(f'{clean_key}_{idx + 1}.pdf', pdf_buf.getvalue())
                pdf_buf.close()
                del pdf_buf

            del writer
            gc.collect()

            # Actualizar progreso
            progress_bar.progress((idx + 1) / total_cuts, text=f'Generando PDF {idx + 1} de {total_cuts}...')

    tmp_zip.close()
    del reader
    gc.collect()

    zip_filename = f"{clean_key}.zip"
    return tmp_zip_path, zip_filename, total_cuts


# ── Autenticación ──────────────────────────────────────────────────────────

def check_credentials(username, password):
    USERNAME = os.getenv("MY_APP_USERNAME", "admin")
    PASSWORD = os.getenv("MY_APP_PASSWORD", "password")
    return username == USERNAME and password == PASSWORD


# ── App principal ──────────────────────────────────────────────────────────

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
            uploaded_files = st.file_uploader(
                "Selecciona uno o más archivos PDF",
                type=['pdf'],
                accept_multiple_files=True
            )

            if uploaded_files and st.button('Separar PDFs'):
                total_generated = 0
                all_zip_paths = []

                for file_idx, uploaded_file in enumerate(uploaded_files):
                    st.write(f'**Procesando:** {uploaded_file.name}')

                    # Guardar a disco
                    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                    tmp_pdf.write(uploaded_file.getvalue())
                    tmp_pdf.close()

                    # Paso 1: Escanear (rápido, solo texto)
                    with st.spinner('Analizando estructura del PDF...'):
                        cuts, key_name, fmt = scan_pages(tmp_pdf.name)

                    if not cuts:
                        st.warning(f'No se encontraron secciones en {uploaded_file.name}')
                        os.unlink(tmp_pdf.name)
                        continue

                    st.write(f'Se encontraron **{len(cuts)}** candidatos/secciones (formato: {fmt})')

                    # Paso 2: Generar ZIP con barra de progreso
                    progress_bar = st.progress(0, text='Generando PDFs...')
                    tmp_zip_path, zip_filename, count = generate_zip(
                        tmp_pdf.name, cuts, key_name, fmt, progress_bar
                    )
                    progress_bar.progress(1.0, text='¡Completado!')

                    total_generated += count

                    # Limpiar PDF temporal
                    os.unlink(tmp_pdf.name)

                    # Leer ZIP y ofrecer descarga
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

                st.success(f'Se han generado {total_generated} PDFs en total')

        else:
            st.error("Por favor, inicia sesión para usar esta funcionalidad.")


if __name__ == '__main__':
    main()
