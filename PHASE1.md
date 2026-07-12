# DriveNow Phase 1 — quick run notes (full README comes after Phase 3)

## Services
- Fleet API: http://localhost:8001/docs
- Rental API: http://localhost:8002/docs

## Run with Docker
```bash
cd /home/my/drivenow
sg docker -c 'docker compose up --build -d'
```

## Run tests locally
```bash
cd /home/my/drivenow
python3 -m venv .venv
source .venv/bin/activate
pip install -r services/fleet_service/requirements.txt
export PYTHONPATH="/home/my/drivenow/shared:/home/my/drivenow/services/fleet_service"
pytest services/fleet_service/tests -q
export PYTHONPATH="/home/my/drivenow/shared:/home/my/drivenow/services/rental_service"
pytest services/rental_service/tests -q
```
