import streamlit as st
import PyPDF2
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

def split_pdf_by_condition(pdf_file, start_count):
    """Divide un PDF basándose en 'Por leer en', 'page X of Y' o 'En proceso en'"""
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    pdfs_bytes = []
    current_pdf_writer = None
    section_count = start_count
    section_name = ""

    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text = page.extract_text()
        
        # Verificar si es separador "Por leer en"
        new_section_name = extract_section_name(text)
        # Verificar si es separador "page of" o "En proceso en"
        is_separator_to_exclude = is_page_separator(text)
        
        # Si encontramos cualquier tipo de separador
        if new_section_name or is_separator_to_exclude:
            if new_section_name:
                section_name = new_section_name
            
            # Guardar el PDF anterior si existe
            if current_pdf_writer:
                pdf_bytes_io = io.BytesIO()
                current_pdf_writer.write(pdf_bytes_io)
                pdf_bytes_io.seek(0)
                pdfs_bytes.append((f'PDF_{section_count}.pdf', pdf_bytes_io.read()))
                section_count += 1
            
            # Crear nuevo PDF writer
            current_pdf_writer = PyPDF2.PdfWriter()
            
            # IMPORTANTE: Si es "Por leer en", incluir la página
            # Si es "page of" o "En proceso en", NO incluir la página (skip)
            if new_section_name:
                current_pdf_writer.add_page(page)
            # Si es is_separator_to_exclude, no agregamos la página (se salta)
        else:
            # Página normal de contenido
            if current_pdf_writer:
                current_pdf_writer.add_page(page)
    
    # Guardar el último PDF si existe y tiene páginas
    if current_pdf_writer and len(current_pdf_writer.pages) > 0:
        pdf_bytes_io = io.BytesIO()
        current_pdf_writer.write(pdf_bytes_io)
        pdf_bytes_io.seek(0)
        pdfs_bytes.append((f'PDF_{section_count}.pdf', pdf_bytes_io.read()))

    return pdfs_bytes, section_name, section_count + 1

def create_zip_from_pdfs(pdfs_bytes, zip_name):
    """Crea un archivo zip con los PDFs generados y nombre basado en la última sección procesada"""
    zip_bytes = io.BytesIO()
    clean_zip_name = re.sub(r'[^\w\s]', '', zip_name).replace(' ', '')
    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, pdf_byte in pdfs_bytes:
            zip_file.writestr(filename, pdf_byte)
    zip_bytes.seek(0)
    return zip_bytes, f"{clean_zip_name}PDFsSeparados.zip"

def check_credentials(username, password):
    USERNAME = os.getenv("MY_APP_USERNAME", "admin")
    PASSWORD = os.getenv("MY_APP_PASSWORD", "password")
    return username == USERNAME and password == PASSWORD

def main():
    st.title('Separador de PDFs por Sección')

    # Menú con pestañas
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
            2. La aplicación separará cada PDF en archivos más pequeños
            3. Descarga el ZIP con todos los PDFs generados
            """)
            uploaded_files = st.file_uploader("Selecciona uno o más archivos PDF", type=['pdf'], accept_multiple_files=True)
            if uploaded_files:
                all_pdfs_bytes = []
                section_name = ""
                current_count = 1  # Contador global para nombres únicos
                
                for uploaded_file in uploaded_files:
                    pdfs_bytes, last_section_name, next_count = split_pdf_by_condition(
                        io.BytesIO(uploaded_file.getvalue()), 
                        current_count
                    )
                    all_pdfs_bytes.extend(pdfs_bytes)
                    current_count = next_count  # Actualizar el contador para el siguiente archivo
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