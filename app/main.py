from fastapi import FastAPI, UploadFile, Form, BackgroundTasks, File, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import List
from pathlib import Path
import shutil
import uuid
import zipfile
import subprocess
from datetime import datetime
import time  # Pentru a ține evidența duratei sesiunii

app = FastAPI()

# Servește fișierele HTML
app.mount("/static", StaticFiles(directory="static"), name="static")
BASE_DIR = Path("tw")
# -----------------------------------------------------------------------------------
# Variabile globale existente
# -----------------------------------------------------------------------------------
selected_file_type = None  # Aceasta rămâne, dar vom folosi una bazată pe session_id
UPLOAD_FOLDER = Path("csv")
OUTPUT_FOLDER = Path("output")
TEMPLATE_FOLDER = Path("template")
LOG_FILE = Path("process_log.txt")
SESSION_FOLDER = Path("sessions")

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
TEMPLATE_FOLDER.mkdir(parents=True, exist_ok=True)
SESSION_FOLDER.mkdir(parents=True, exist_ok=True)

BLOCKED_BOTS = ["Googlebot", "Bingbot", "Slurp", "DuckDuckBot", "Baiduspider", "YandexBot"]

# -----------------------------------------------------------------------------------
# Nou: gestionare sesiuni per utilizator cu durată de 8 ore
# -----------------------------------------------------------------------------------
SESSIONS = {}  # Dicționar pentru a memora momentul de creare al sesiunii {session_id: timestamp}
USER_SELECTED_FILE_TYPE = {}  # Dicționar pentru a asocia session_id -> tipul fișierului (în loc de variabila globală)

@app.middleware("http")
async def block_bots_and_add_session(request: Request, call_next):
    """
    Middleware pentru:
     1. Blocare boți (codul original).
     2. Crearea / validarea unui session_id pentru fiecare utilizator (durată 8 ore).
    """
    user_agent = request.headers.get("user-agent", "").lower()
    if any(bot.lower() in user_agent for bot in BLOCKED_BOTS):
        return JSONResponse(status_code=403, content={"message": "Access Forbidden for Bots"})
    
    # ----------------------------------------------------------------
    # Partea de Sesiune
    # ----------------------------------------------------------------
    session_id_cookie = request.cookies.get("session_id")
    current_time = time.time()

    # Preiau IP-ul clientului (dacă e disponibil)
    client_ip = "unknown_ip"
    if request.client:
        client_ip = request.client.host  # ex: 127.0.0.1

    # Data/ora curentă în format "YYYYmmdd_HHMMSS"
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ----------------------------------------------------------------
    # Vechea variantă (folosind uuid4) a fost comentată, nu ștearsă:
    # ----------------------------------------------------------------
    # if not session_id or session_id not in SESSIONS:
    #     session_id = str(uuid.uuid4())
    #     SESSIONS[session_id] = current_time
    # else:
    #     # Verifică expirarea (8 ore = 8 * 3600 sec)
    #     creation_time = SESSIONS[session_id]
    #     if (current_time - creation_time) > 8 * 3600:
    #         # Sesiune expirată -> generăm una nouă
    #         del SESSIONS[session_id]
    #         session_id = str(uuid.uuid4())
    #         SESSIONS[session_id] = current_time

    # ----------------------------------------------------------------
    # Noua variantă: session_id = <client_ip>_<YYYYmmdd_HHMMSS>
    # ----------------------------------------------------------------
    # Dacă cookie-ul "session_id" nu există sau nu se află în SESSIONS,
    # generăm un nou session_id bazat pe IP și timestamp.
    # (Ex: 192.168.1.10_20250119_160452)
    if not session_id_cookie or session_id_cookie not in SESSIONS:
        session_id = client_ip
        SESSIONS[session_id] = current_time
    else:
        # Avem cookie, deci extragem creation_time
        creation_time = SESSIONS[session_id_cookie]
        if (current_time - creation_time) > 8 * 3600:
            # Sesiunea cookie-ului a expirat -> generăm una nouă
            del SESSIONS[session_id_cookie]
            session_id = f"{client_ip}_{now_str}"
            SESSIONS[session_id] = current_time
        else:
            # Sesiunea cookie-ului încă e validă
            session_id = session_id_cookie

    # Transmitem session_id mai departe în request.state
    request.state.session_id = session_id

    response = await call_next(request)
    # Setăm cookie-ul cu session_id; max_age = 8 ore
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=8 * 3600, 
        httponly=True
    )
    return response

@app.get("/", response_class=HTMLResponse)
def serve_index():
    return FileResponse("static/index.html")

# def home():
#     index_path = Path(__file__).parent / "templates" / "index.html"
#     if index_path.exists():
#         return index_path.read_text()
#     return "<h1>Eroare: Fișierul index.html lipsește.</h1>"

@app.get("/main", response_class=HTMLResponse)
def serve_main():
    return FileResponse("static/main.html")

@app.get("/instructions", response_class=HTMLResponse)
def serve_instructions():
    return FileResponse("static/instructions.html")

@app.get("/sidebar", response_class=HTMLResponse)
def serve_main():
     return FileResponse("static/sidebar.html")


@app.post("/upload/")
def upload_csv(
    request: Request,
    files: List[UploadFile] = File(...),
    file_type: str = Form(...)
):
    """
    Salvează fișierele CSV într-un folder dedicat sesiunii curente.
    - Dacă fișierul există deja, îl rescrie și va fi raportat ca 'overwritten'.
    - Dacă fișierul NU există, va fi raportat ca 'newly_created'.
    """
    # global selected_file_type  # Comentăm, vom folosi un dicționar bazat pe session_id
    # selected_file_type = file_type
    
    session_id = request.state.session_id
    USER_SELECTED_FILE_TYPE[session_id] = file_type  # Stocăm tipul în dict, per session_id

    # --------------------------------------------------------------------------------
    # Comentăm liniile care șterg global tot din CSV/ și OUTPUT/, 
    # deoarece acum vrem să avem subfoldere pe sesiune.
    # --------------------------------------------------------------------------------
    # for existing_file in UPLOAD_FOLDER.iterdir():
    #     if existing_file.is_file():
    #         existing_file.unlink()
    # for existing_file in OUTPUT_FOLDER.iterdir():
    #     if existing_file.is_file():
    #         existing_file.unlink()

    # Creăm foldere separate pentru această sesiune
    session_folder = SESSION_FOLDER / session_id
    session_csv_folder = session_folder / "csv"
    session_output_folder = session_folder / "output"
    session_folder.mkdir(parents=True, exist_ok=True)
    session_csv_folder.mkdir(parents=True, exist_ok=True)
    session_output_folder.mkdir(parents=True, exist_ok=True)

    # 🔹 Ștergem toate fișierele din folderul `csv/`
    for existing_file in session_output_folder.iterdir():  # Verifică toate fișierele și subfolderele
        if existing_file.is_file():  # Asigură că ștergem doar fișiere, nu subfoldere
            existing_file.unlink()  # Șterge fișierul
    # 🔹 Ștergem toate fișierele din folderul `csv/`
    for existing_file in session_csv_folder.iterdir():  # Verifică toate fișierele și subfolderele
        if existing_file.is_file():  # Asigură că ștergem doar fișiere, nu subfoldere
            existing_file.unlink()  # Șterge fișierul

    new_files = []
    
    for file in files:
        file_path = session_csv_folder / file.filename
        new_files.append(file.filename)
        
        # Copiem conținutul, suprascriind dacă fișierul există
        with file_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)

    if new_files:
        new_files_html = "<ul>" + "".join(f"<li>{f}</li>" for f in new_files) + "</ul>"
    else:
        new_files_html = "<p><em>Niciun fișier nou.</em></p>"

    html_response = f"""
    <p><strong>Fișiere încărcate cu succes pentru sesiunea curentă:</strong></p>
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
def process_files(request: Request):
    """
    Aici apelăm scriptul specific în funcție de tipul selectat (PPI, CPI etc.),
    dar acum tipul este luat din dicționar, pe baza session_id.
    """
    session_id = request.state.session_id
    # if not selected_file_type:
    #     return JSONResponse(content={"error": "Nu a fost selectat niciun tip anterior."}, status_code=400})

    file_type = USER_SELECTED_FILE_TYPE.get(session_id)
    if not file_type:
        return JSONResponse(
            content={"error": "Nu a fost selectat niciun tip anterior pentru această sesiune."},
            status_code=400
        )
    
    try:
        if file_type == "PPI":
            # Rulăm process_script.py adica Full PC Procent
            subprocess.run([
                "python", "app/process_script.py",
                "--csv-folder", f"sessions/{session_id}/csv",
                "--template-path", "template/template.xlsx",
                "--output-folder", f"sessions/{session_id}/output",
                "--log-file", f"sessions/{session_id}/process_log.txt"
            ], check=True)
            msg = f"Procesare PPI finalizată!"
        elif file_type == "GDPQOQYOY":
            # Rulăm gppqoqyoy.py (când îl vei crea)
            subprocess.run(["python", "app/gppqoqyoy.py",
                "--csv-folder", f"sessions/{session_id}/csv",
                "--template-path", "template/template.xlsx",
                "--output-folder", f"sessions/{session_id}/output",
                "--log-file", f"sessions/{session_id}/process_log.txt"], check=True)
            msg = f"Procesare GDPQOQYOY finalizată!"
        elif file_type == "PMIPCNOMINAL":
            # Rulăm pmipcnominal.py (când îl vei crea)
            subprocess.run(["python", "app/pmipcnominal.py",
                "--csv-folder", f"sessions/{session_id}/csv",
                "--template-path", "template/template.xlsx",
                "--output-folder", f"sessions/{session_id}/output",
                "--log-file", f"sessions/{session_id}/process_log.txt"], check=True)
            msg = f"Procesare PMI PC Valoare Nominala finalizată!"
        else:
            # Rulăm momyoy.py (exemplu)
            subprocess.run(["python", "app/momyoy.py",
                "--csv-folder", f"sessions/{session_id}/csv",
                "--template-path", "template/template.xlsx",
                "--output-folder", f"sessions/{session_id}/output",
                "--log-file", f"sessions/{session_id}/process_log.txt"], check=True)
            msg = f"Procesare MOM YOY finalizată!"
        
        return HTMLResponse(content=msg)
    except subprocess.CalledProcessError as e:
        return HTMLResponse(content=f"<p><strong>ERROR:</strong> {str(e)}</p>", status_code=500)


@app.get("/download/{filename}")
def download_file(filename: str, background_tasks: BackgroundTasks, request: Request):
    """
    Permite descărcarea unui fișier XLSX generat pentru sesiunea curentă
    (în loc să le șteargă global).
    """
    session_id = request.state.session_id
    session_folder = SESSION_FOLDER / session_id / "output"
    file_path = session_folder / filename

    if file_path.exists():
        response = FileResponse(file_path, filename=filename)
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        
        # # Șterge fișierul și CSV-urile după descărcare
        # def cleanup():
        #     file_path.unlink(missing_ok=True)
        #     for csv_file in UPLOAD_FOLDER.glob("*.csv"):
        #         csv_file.unlink(missing_ok=True)
        # background_tasks.add_task(cleanup)

        return response

    return JSONResponse(content={"error": f"Fișierul {filename} nu există pentru această sesiune."}, status_code=404)


@app.get("/download_all/")
def download_all(background_tasks: BackgroundTasks, request: Request):
    """
    Arhivează și permite descărcarea tuturor fișierelor XLSX pentru sesiunea curentă.
    """
    session_id = request.state.session_id
    session_output_folder = SESSION_FOLDER / session_id / "output"
    archive_path = session_output_folder / "output.zip"

    with zipfile.ZipFile(archive_path, "w") as zipf:
        for file in session_output_folder.glob("*.xlsx"):
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
    # background_tasks.add_task(cleanup)

    return response


@app.get("/log", response_class=HTMLResponse)
def get_log(request: Request):
    """
    Returnează conținutul fișierului log *din sesiunea curentă*.
    """
    session_id = request.state.session_id
    session_log_file = (SESSION_FOLDER / session_id / "process_log.txt").resolve()

    if session_log_file.exists():
        with session_log_file.open("r", encoding="utf-8") as f:
            log_content = f.read()
        return HTMLResponse(content=f"<div>{log_content}</div>", status_code=200)
    return HTMLResponse(content=f"<pre><em>Nu există erori în log pentru sesiunea curentă.</em></pre>", status_code=200)



@app.get("/list_files/")
def list_files(request: Request):
    """
    Returnează lista fișierelor generate pentru descărcare pentru sesiunea curentă.
    """
    session_id = request.state.session_id
    session_output_folder = SESSION_FOLDER / session_id / "output"
    files = list(session_output_folder.glob("*.xlsx"))
    if not files:
        return HTMLResponse(f"<p>Niciun fișier generat încă pentru sesiunea curentă.</p>")
    file_links = "".join(f'<li><a href="/download/{file.name}" download>{file.name}</a></li>' for file in files)
    return HTMLResponse(f"<ul>{file_links}</ul>")


from fastapi.responses import HTMLResponse

@app.delete("/delete_files/")
def delete_files(request: Request):
    """
    Șterge toate fișierele încărcate și generate pentru sesiunea curentă.
    Returnează un mesaj HTML formatat.
    """
    deleted_files = []
    session_id = request.state.session_id
    session_folder = SESSION_FOLDER / session_id
    session_csv_folder = session_folder / "csv"
    session_output_folder = session_folder / "output"

    if session_csv_folder.exists():
        for file in session_csv_folder.glob("*"):
            try:
                file.unlink()
                deleted_files.append(f"{session_id}/csv/{file.name}")
            except Exception as e:
                return HTMLResponse(
                    content=f"<p><strong>Eroare:</strong> Nu s-a putut șterge {file.name}: {e}</p>",
                    status_code=500
                )

    if session_output_folder.exists():
        for file in session_output_folder.glob("*"):
            try:
                file.unlink()
                deleted_files.append(f"{session_id}/output/{file.name}")
            except Exception as e:
                return HTMLResponse(
                    content=f"<p><strong>Eroare:</strong> Nu s-a putut șterge {file.name}: {e}</p>",
                    status_code=500
                )

    # Construim mesajul HTML
    if deleted_files:
        deleted_files_html = "<ul class='list-disc pl-5'>" + "".join(f"<li>{file}</li>" for file in deleted_files) + "</ul>"
        return HTMLResponse(content=f"<p>Fișiere șterse cu succes pentru sesiunea curentă:</p>{deleted_files_html}")
    else:
        return HTMLResponse(
            content=f"<p><em>Nu au fost găsite fișiere de șters pentru sesiunea curentă.</em></p>"
        )
