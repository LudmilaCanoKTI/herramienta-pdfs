import streamlit as st
import PyPDF2
import re
import os
import io
import zipfile

# Función para limpiar nombres de archivos
def clean_filename(filename):
    """Limpia el nombre de archivo eliminando caracteres no válidos"""
    cleaned = re.sub(r'[<>:"/\\|?*]', '', filename)
    cleaned = re.sub(r'\s+', '_', cleaned)
    return cleaned[:50]

# Función para extraer el nombre de sección de un texto
def extract_section_name(text):
    """Extrae el nombre de sección después de 'Por leer en'"""
    match = re.search(r'Por leer en:?\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    return match.group(1).strip() if match else None

# Función para dividir el PDF según una condición específica
def split_pdf_by_condition(pdf_bytes):
    """Divide un PDF basándose en la condición 'Por leer en'"""
    pdf_file = io.BytesIO(pdf_bytes)
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
                pdfs_bytes.append((f'PDF_{section_count}.pdf', pdf_bytes_io.read()))
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

# Función para crear un archivo ZIP con los PDFs generados
def create_zip_from_pdfs(pdfs_bytes):
    """Crea un archivo zip con los PDFs generados"""
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, pdf_byte in pdfs_bytes:
            zip_file.writestr(filename, pdf_byte)
    zip_bytes.seek(0)
    return zip_bytes

# Función para verificar las credenciales
def check_credentials(username, password):
    USERNAME = os.environ.get("MY_APP_USERNAME", "default_user")
    PASSWORD = os.environ.get("MY_APP_PASSWORD", "default_password")
    return username == USERNAME and password == PASSWORD

def main():
    st.title('Separador de PDFs por Sección')

    # Inicio de sesión
    with st.container():
        username = st.text_input("Nombre de Usuario")
        password = st.text_input("Contraseña", type="password")
        login_button = st.button("Ingresar")

        if login_button:
            if check_credentials(username, password):
                run_app()
            else:
                st.error("Credenciales incorrectas. Intenta nuevamente.")

def run_app():
    st.markdown("""
    ### Instrucciones
    1. Sube un PDF con secciones marcadas con "Por leer en"
    2. La aplicación separará el PDF en archivos más pequeños
    3. Descarga el ZIP con todos los PDFs generados
    """)

    uploaded_file = st.file_uploader("Selecciona un archivo PDF", type=['pdf'])
    if uploaded_file is not None:
        pdf_bytes = uploaded_file.getvalue()
        if st.button('Separar PDF'):
            try:
                pdfs_bytes = split_pdf_by_condition(pdf_bytes)
                zip_bytes = create_zip_from_pdfs(pdfs_bytes)
                st.download_button("Descargar PDFs", zip_bytes, "PDFs_Separados.zip", "application/zip")
                st.success(f'Se han generado {len(pdfs_bytes)} PDFs')
            except Exception as e:
                st.error(f'Error al procesar el PDF: {str(e)}')

if __name__ == '__main__':
    main()
