# TradingViewXLSX
python3 -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt

python run.py


pe vpn
uvicorn run:app --host 0.0.0.0 --port 8001

kill pe vpn

pkill -f uvicorn


git pull --force
