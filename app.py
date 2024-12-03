import streamlit as st
import os
import PyPDF2
import io
import zipfile
import re

# Definir funciones para limpieza de nombre, extracción de sección, división y creación de zip
def clean_filename(filename):
    cleaned = re.sub(r'[<>:"/\\|?*]', '', filename)
    cleaned = re.sub(r'\s+', '_', cleaned)
    return cleaned[:50]

def extract_section_name(text):
    match = re.search(r'Por leer en:?\s*(.+?)((?:\n|$))', text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def split_pdf_by_condition(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    pdfs_bytes = []
    current_pdf_writer = None
    section_count = 1
    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text = page.extract_text()
        section_name = extract_section_name(text)
        if section_name:
            if current_pdf_writer:
                pdf_bytes_io = io.BytesIO()
                current_pdf_writer.write(pdf_bytes_io)
                pdf_bytes_io.seek(0)
                pdfs_bytes.append((f'PDF_{section_count}_{clean_filename(section_name)}.pdf', pdf_bytes_io.read()))
                section_count += 1
            current_pdf_writer = PyPDF2.PdfWriter()
        if current_pdf_writer:
            current_pdf_writer.add_page(page)
    if current_pdf_writer:
        pdf_bytes_io = io.BytesIO()
        current_pdf_writer.write(pdf_bytes_io)
        pdf_bytes_io.seek(0)
        pdfs_bytes.append((f'PDF_{section_count}.pdf', pdf_bytes_io.read()))
    return pdfs_bytes

def create_zip_from_pdfs(pdfs_bytes):
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, pdf_byte in pdfs_bytes:
            zip_file.writestr(filename, pdf_byte)
    zip_bytes.seek(0)
    return zip_bytes

def check_credentials(username, password):
    return username == os.getenv("MY_APP_USERNAME", "admin") and password == os.getenv("MY_APP_PASSWORD", "password")

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
            1. Sube uno o más PDFs con secciones marcadas con "Por leer en"
            2. La aplicación separará cada PDF en archivos más pequeños
            3. Descarga el ZIP con todos los PDFs generados
            """)
            uploaded_files = st.file_uploader("Selecciona uno o más archivos PDF", type=['pdf'], accept_multiple_files=True)
            if uploaded_files:
                all_pdfs_bytes = []
                for uploaded_file in uploaded_files:
                    pdfs_bytes = split_pdf_by_condition(io.BytesIO(uploaded_file.getvalue()))
                    all_pdfs_bytes.extend(pdfs_bytes)
                if st.button('Separar PDFs'):
                    zip_bytes = create_zip_from_pdfs(all_pdfs_bytes)
                    st.download_button("Descargar PDFs", zip_bytes, "PDFs_Separados.zip", "application/zip")
                    st.success(f'Se han generado {len(all_pdfs_bytes)} PDFs')
        else:
            st.error("Por favor, inicia sesión para usar esta funcionalidad.")

if __name__ == '__main__':
    main()
