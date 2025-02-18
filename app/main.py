from fastapi import FastAPI, UploadFile, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pathlib import Path
import shutil
import os
import zipfile
import subprocess

app = FastAPI()

UPLOAD_FOLDER = Path("csv")
OUTPUT_FOLDER = Path("output")
TEMPLATE_FOLDER = Path("template")
LOG_FILE = Path("process_log.txt")

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
TEMPLATE_FOLDER.mkdir(parents=True, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
def home():
    index_path = Path(__file__).parent / "templates" / "index.html"
    if index_path.exists():
        return index_path.read_text()
    return "<h1>Eroare: Fișierul index.html lipsește.</h1>"

@app.post("/upload/")
def upload_csv(files: list[UploadFile]):
    """
    Salvează fișierele CSV în folderul dedicat.
    - Dacă fișierul există deja, îl rescrie și va fi raportat ca 'overwritten'.
    - Dacă fișierul NU există, va fi raportat ca 'newly_created'.
    """
    overwritten_files = []
    new_files = []
    
    for file in files:
        file_path = UPLOAD_FOLDER / file.filename
        
        # Verificăm dacă fișierul există deja
        if file_path.exists():
            overwritten_files.append(file.filename)
        else:
            new_files.append(file.filename)
        
        # Copiem conținutul, suprascriind dacă fișierul există
        with file_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    
    # Construiește HTML pentru fișierele rescrise
    if overwritten_files:
        overwritten_html = "<ul>" + "".join(f"<li>{f}</li>" for f in overwritten_files) + "</ul>"
    else:
        overwritten_html = "<p><em>Niciun fișier rescris.</em></p>"

    # Construiește HTML pentru fișierele noi
    if new_files:
        new_files_html = "<ul>" + "".join(f"<li>{f}</li>" for f in new_files) + "</ul>"
    else:
        new_files_html = "<p><em>Niciun fișier nou.</em></p>"

    html_response = f"""
    <p>Fișiere încărcate cu succes.</p>
    <p><strong>Rescrise</strong>:</p>
    {overwritten_html}
    <p><strong>Noi</strong>:</p>
    {new_files_html}
    """
    return HTMLResponse(content=html_response)


@app.post("/process/")
def process_files():
    """Execută scriptul de procesare CSV -> XLSX."""
    try:
        LOG_FILE.unlink(missing_ok=True)  # Șterge log-ul anterior
        subprocess.run(["python", "app/process_script.py"], check=True)  # Rulează scriptul de procesare
        return JSONResponse(content={"message": "Procesare finalizată!"})
    except subprocess.CalledProcessError as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

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

    # Șterge fișierele după descărcare
    def cleanup():
        for file in OUTPUT_FOLDER.glob("*.xlsx"):
            file.unlink(missing_ok=True)
        for csv_file in UPLOAD_FOLDER.glob("*.csv"):
            csv_file.unlink(missing_ok=True)
        archive_path.unlink(missing_ok=True)

    background_tasks.add_task(cleanup)  # Rulează cleanup în fundal
    return response


@app.get("/log")
def get_log():
    """Returnează conținutul fișierului log."""
    if LOG_FILE.exists():
        return FileResponse(LOG_FILE, filename="process_log.txt")
    return JSONResponse(content={"message": "Nu există erori."})

@app.get("/list_files/")
def list_files():
    """Returnează lista fișierelor generate pentru descărcare."""
    files = list(OUTPUT_FOLDER.glob("*.xlsx"))
    if not files:
        return HTMLResponse("<p>Niciun fișier generat încă.</p>")
    file_links = "".join(f'<li><a href="/download/{file.name}" download>{file.name}</a></li>' for file in files)
    return HTMLResponse(f"<ul>{file_links}</ul>")
