# tests/unit_test_alarm_service.py
import sys
from datetime import datetime, timezone

# tenta garantir app context (ajuste se seu projeto usa create_app)
try:
    from src.app import create_app  # se existir factory
    app = create_app()
except Exception:
    try:
        from src.app import app  # ou app diretamente
    except Exception:
        app = None

if app is None:
    raise RuntimeError("Não foi possível importar o app. Ajuste imports em tests/unit_test_alarm_service.py")

with app.app_context():
    # imports que dependem do db
    from src.repository.Alarms_repository import AlarmDefinitionRepo, AlarmRepo
    from src.services.Alarms_service import AlarmService
    from src.models.Alarms import AlarmDefinition

    # limpar estado (cuidado em ambiente real!)
    def_repo = AlarmDefinitionRepo()
    alarm_repo = AlarmRepo()

    # opcional: apagar defs/alarms de teste (ajuste se quiser preservar)
    # for a in alarm_repo.find_by(): alarm_repo.delete(a)
    # for d in def_repo.find_by(): def_repo.delete(d)

    # criar definição de teste
    ad = AlarmDefinition(
        plc_id=999,          # id de teste (escolha um não usado)
        register_id=888,
        name="T Alta Test",
        condition_type="above",
        setpoint=50.0,
        deadband=1.0,
        priority="HIGH",
        is_active=True,
        email_enabled=False
    )
    def_repo.add(ad)
    print("Created AlarmDefinition id=", ad.id)

    svc = AlarmService()

    readings = [45.0, 48.0, 51.0, 52.0, 49.0, 47.0]
    for v in readings:
        triggered = svc.check_and_handle(ad.plc_id, ad.register_id, v)
        print(f"{datetime.now(timezone.utc).isoformat()} value={v} -> triggered={triggered}")

    # listar alarms criados
    alarms = alarm_repo.find_by(plc_id=ad.plc_id, register_id=ad.register_id)
    print("Alarms in DB for test:", len(alarms))
    for a in alarms:
        print(a.id, a.state, a.trigger_value, a.current_value, a.triggered_at)
