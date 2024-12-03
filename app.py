import streamlit as st
import PyPDF2
import re
import io
import zipfile
import logging

def cleanfilename(filename):
    """Limpia el nombre de archivo eliminando caracteres no válidos"""
    cleaned = re.sub(r'[<>:"/\\|?*]', '', filename)
    cleaned = re.sub(r'\s+', '', cleaned)
    return cleaned[:50]

def extract_section_name(text):
    """Extrae el nombre de sección después de 'Por leer en'"""
    match = re.search(r'Por leer en:?\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    return match.group(1).strip() if match else None

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

        # Buscar la condición "Por leer en"
        section_name = extract_section_name(text)

        if section_name:
            # Guardar PDF anterior si existe
            if current_pdf_writer:
                pdf_bytes_io = io.BytesIO()
                current_pdf_writer.write(pdf_bytes_io)
                pdf_bytes_io.seek(0)
                pdfsbytes.append((f'PDF{section_count}.pdf', pdf_bytes_io.read()))
                section_count += 1

            # Iniciar nuevo PDF
            current_pdf_writer = PyPDF2.PdfWriter()

        # Agregar página al PDF actual si existe
        if current_pdf_writer:
            current_pdf_writer.add_page(page)

    # Guardar último PDF
    if current_pdf_writer:
        pdf_bytes_io = io.BytesIO()
        current_pdf_writer.write(pdf_bytes_io)
        pdf_bytes_io.seek(0)
        pdfsbytes.append((f'PDF{section_count}.pdf', pdf_bytes_io.read()))

    return pdfs_bytes

def create_zip_from_pdfs(pdfs_bytes):
    """Crea un archivo zip con los PDFs generados"""
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, pdf_byte in pdfs_bytes:
            zip_file.writestr(filename, pdf_byte)
    zip_bytes.seek(0)
    return zip_bytes

logging.basicConfig(level=logging.INFO)


def main():
    st.set_page_config(page_title="PDF Splitter", page_icon=":page_with_curl:")
    st.title('Separador de PDFs por Sección')

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

                st.download_button(
                    label='Descargar PDFs',
                    data=zip_bytes,
                    file_name='PDFs_Separados.zip',
                    mime='application/zip'
                )

                st.success(f'Se han generado {len(pdfs_bytes)} PDFs')

            except Exception as e:
                st.error(f'Error al procesar el PDF: {str(e)}')


if __name__ == '__main__':
    main()