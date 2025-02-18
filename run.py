import uvicorn
import os
from app.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))   # Dacă PORT nu e setat, default 8000
    uvicorn.run(app, host="0.0.0.0", port=port)
# DACA vrei să deschizi automat un browser:
#    import webbrowser
