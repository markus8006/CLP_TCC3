from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from app.auth.decorators import require_permission
from app.models.plc import PLC

polling_bp = Blueprint('polling', __name__, url_prefix='/polling')

@polling_bp.route('/dashboard')
@login_required
@require_permission('read_plc')
def polling_dashboard():
    """Dashboard de controle de polling"""
    
    plcs = PLC.query.filter_by(is_active=True).all()
    polling_status = {}
    
    for plc in plcs:
        polling_status[plc.id] = {
            'plc': plc,
            'is_polling': plc.id in current_app.polling_manager.jobs,
            'is_online': plc.is_online,
            'last_seen': plc.last_seen,
            'register_count': len(plc.registers)
        }
    
    return render_template('polling/dashboard.html', 
                         polling_status=polling_status)

@polling_bp.route('/start/<int:plc_id>', methods=['POST'])
@login_required
@require_permission('control_polling')
def start_polling(plc_id):
    """Inicia polling para um PLC"""
    from flask import current_app
    
    success, message = current_app.polling_manager.start_polling_for_plc(plc_id)
    
    if success:
        # Log da ação
        current_app.audit_service.log_action(
            current_user.id,
            'START_POLLING',
            'PLC',
            plc_id,
            f"Polling iniciado para PLC {plc_id}"
        )
    
    return jsonify({
        'success': success,
        'message': message
    })
