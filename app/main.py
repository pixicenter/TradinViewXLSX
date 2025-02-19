from fastapi import FastAPI, UploadFile, Form, BackgroundTasks, File
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import List
from pathlib import Path
import shutil
import os
import zipfile
import subprocess

app = FastAPI()

# Servește fișierele HTML
app.mount("/static", StaticFiles(directory="static"), name="static")


selected_file_type = None

UPLOAD_FOLDER = Path("csv")
OUTPUT_FOLDER = Path("output")
TEMPLATE_FOLDER = Path("template")
LOG_FILE = Path("process_log.txt")

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
TEMPLATE_FOLDER.mkdir(parents=True, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
def serve_index():
    return FileResponse("static/index.html")
# def home():
#     index_path = Path(__file__).parent / "templates" / "index.html"
#     if index_path.exists():
#         return index_path.read_text()
#     return "<h1>Eroare: Fișierul index.html lipsește.</h1>"
@app.get("/main")
def serve_main():
    return FileResponse("static/main.html")

@app.get("/instructions")
def serve_instructions():
    return FileResponse("static/instructions.html")

@app.get("/sidebar")
def serve_main():
    return FileResponse("static/sidebar.html")

@app.post("/upload/")
def upload_csv(files: List[UploadFile] = File(...),
    file_type: str = Form(...)
):
    """
    Salvează fișierele CSV în folderul dedicat.
    - Dacă fișierul există deja, îl rescrie și va fi raportat ca 'overwritten'.
    - Dacă fișierul NU există, va fi raportat ca 'newly_created'.
    """
    global selected_file_type
    selected_file_type = file_type  # stocăm tipul într-o variabilă globală exemplificativ
    
    # 🔹 Ștergem toate fișierele din folderul `csv/`
    for existing_file in UPLOAD_FOLDER.iterdir():  # Verifică toate fișierele și subfolderele
        if existing_file.is_file():  # Asigură că ștergem doar fișiere, nu subfoldere
            existing_file.unlink()  # Șterge fișierul
    # 🔹 Ștergem toate fișierele din folderul `csv/`
    for existing_file in OUTPUT_FOLDER.iterdir():  # Verifică toate fișierele și subfolderele
        if existing_file.is_file():  # Asigură că ștergem doar fișiere, nu subfoldere
            existing_file.unlink()  # Șterge fișierul

    new_files = []
    
    for file in files:
        file_path = UPLOAD_FOLDER / file.filename
        new_files.append(file.filename)
        
        # Copiem conținutul, suprascriind dacă fișierul există
        with file_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    

    # Construiește HTML pentru fișierele noi
    if new_files:
        new_files_html = "<ul>" + "".join(f"<li>{f}</li>" for f in new_files) + "</ul>"
    else:
        new_files_html = "<p><em>Niciun fișier nou.</em></p>"

    html_response = f"""
    
    <p><strong>Fișiere încărcate cu succes:</strong></p>
    {new_files_html}
    <p><strong>Tip Fișier CSV:</strong> {file_type}</p>
    
    """
    return HTMLResponse(content=html_response)


# @app.post("/process/")
# def process_files():
#     """Execută scriptul de procesare CSV -> XLSX."""
#     try:
#         LOG_FILE.unlink(missing_ok=True)  # Șterge log-ul anterior
#         subprocess.run(["python", "app/process_script.py"], check=True)  # Rulează scriptul de procesare
#         return JSONResponse(content={"message": "Procesare finalizată!"})
#     except subprocess.CalledProcessError as e:
#         return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/process/")
def process_files():
    """
    Aici apelăm scriptul specific în funcție de tipul selectat (PPI, CPI etc.)
    """
    if not selected_file_type:
        return JSONResponse(content={"error": "Nu a fost selectat niciun tip anterior."}, status_code=400)
    
    try:
        if selected_file_type == "PPI":
            # Rulăm process_script.py adica Full PC Procent
            subprocess.run(["python", "app/process_script.py"], check=True)
            msg = "Procesare PPI finalizată!"
        elif selected_file_type == "GDPQOQYOY":
            # Rulăm gppqoqyoy.py (când îl vei crea)
            subprocess.run(["python", "app/gppqoqyoy.py"], check=True)
            msg = "Procesare GDPQOQYOY finalizată!"
        elif selected_file_type == "PMIPCNOMINAL":
            # Rulăm pmipcnominal.py (când îl vei crea)
            subprocess.run(["python", "app/pmipcnominal.py"], check=True)
            msg = "Procesare PMI PC Valoare Nominala finalizată!"
        else:
            # Rulăm momyoy.py (exemplu)
            subprocess.run(["python", "app/momyoy.py"], check=True)
            msg = "Procesare MOM YOY finalizată!"
        
        # Returnăm mesajul HTML către interfață
        return HTMLResponse(content=msg)
    except subprocess.CalledProcessError as e:
        return HTMLResponse(content=f"<p><strong>ERROR:</strong> {str(e)}</p>", status_code=500)


@app.get("/download/{filename}")
def download_file(filename: str, background_tasks: BackgroundTasks):
    """Permite descărcarea unui fișier XLSX generat și îl șterge după descărcare împreună cu CSV-urile sursă."""
    file_path = OUTPUT_FOLDER / filename
    if file_path.exists():
        response = FileResponse(file_path, filename=filename)
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        
        # # Șterge fișierul și CSV-urile după descărcare
        # def cleanup():
        #     file_path.unlink(missing_ok=True)
        #     for csv_file in UPLOAD_FOLDER.glob("*.csv"):
        #         csv_file.unlink(missing_ok=True)
        
        # background_tasks.add_task(cleanup)  # Rulează cleanup în fundal
        return response

    return JSONResponse(content={"error": "Fișierul nu există."}, status_code=404)

@app.get("/download_all/")
def download_all(background_tasks: BackgroundTasks):
    """Arhivează și permite descărcarea tuturor fișierelor XLSX, apoi șterge fișierele generatate și CSV-urile."""
    archive_path = OUTPUT_FOLDER / "output.zip"
    with zipfile.ZipFile(archive_path, "w") as zipf:
        for file in OUTPUT_FOLDER.glob("*.xlsx"):
            zipf.write(file, file.name)

    response = FileResponse(archive_path, filename="output.zip")
    response.headers["Content-Disposition"] = "attachment; filename=output.zip"

    # # Șterge fișierele după descărcare
    # def cleanup():
    #     for file in OUTPUT_FOLDER.glob("*.xlsx"):
    #         file.unlink(missing_ok=True)
    #     for csv_file in UPLOAD_FOLDER.glob("*.csv"):
    #         csv_file.unlink(missing_ok=True)
    #     archive_path.unlink(missing_ok=True)

    # background_tasks.add_task(cleanup)  # Rulează cleanup în fundal
    # return response


@app.get("/log", response_class=HTMLResponse)
def get_log():
    """Returnează conținutul fișierului log pentru afișare în UI."""
    if LOG_FILE.exists():
        with LOG_FILE.open("r", encoding="utf-8") as f:
            log_content = f.read()
        return f"<div>{log_content}</div>"  # Returnăm log-ul formatat
    return "<pre><em>Nu există erori în log.</em></pre>"


@app.get("/list_files/")
def list_files():
    """Returnează lista fișierelor generate pentru descărcare."""
    files = list(OUTPUT_FOLDER.glob("*.xlsx"))
    if not files:
        return HTMLResponse("<p>Niciun fișier generat încă.</p>")
    file_links = "".join(f'<li><a href="/download/{file.name}" download>{file.name}</a></li>' for file in files)
    return HTMLResponse(f"<ul>{file_links}</ul>")

from fastapi.responses import HTMLResponse

@app.delete("/delete_files/")
def delete_files():
    """Șterge toate fișierele încărcate și generate și returnează un mesaj HTML formatat."""
    deleted_files = []

    # Șterge fișierele din folderul CSV (încărcate)
    if UPLOAD_FOLDER.exists():
        for file in UPLOAD_FOLDER.glob("*"):
            try:
                file.unlink()
                deleted_files.append(file.name)
            except Exception as e:
                return HTMLResponse(content=f"<p><strong>Eroare:</strong> Nu s-a putut șterge {file.name}: {e}</p>", status_code=500)

    # Șterge fișierele din folderul OUTPUT (generate)
    if OUTPUT_FOLDER.exists():
        for file in OUTPUT_FOLDER.glob("*.xlsx"):
            try:
                file.unlink()
                deleted_files.append(file.name)
            except Exception as e:
                return HTMLResponse(content=f"<p><strong>Eroare:</strong> Nu s-a putut șterge {file.name}: {e}</p>", status_code=500)

    # Construim mesajul HTML
    if deleted_files:
        deleted_files_html = "<ul class='list-disc pl-5'>" + "".join(f"<li>{file}</li>" for file in deleted_files) + "</ul>"
        return HTMLResponse(content=f"<p>Fișiere șterse cu succes:</p>{deleted_files_html}")
    else:
        return HTMLResponse(content="<p><em>Nu au fost găsite fișiere de șters.</em></p>")
