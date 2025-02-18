import uvicorn
from app.main import app  # Asigură-te că 'app.main' este corect

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
# DACA vrei să deschizi automat un browser:
    import webbrowser
    webbrowser.open("http://127.0.0.1:8000")