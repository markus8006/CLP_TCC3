# Roles pré-definidas com herança
ROLES_HIERARCHY = {
    'VIEWER': {
        'permissions': ['read_plc', 'read_data', 'read_alarms'],
        'description': 'Apenas visualização'
    },
    'OPERATOR': {
        'inherits': 'VIEWER',
        'permissions': ['acknowledge_alarms', 'control_polling'],
        'description': 'Operação básica'
    },
    'TECHNICIAN': {
        'inherits': 'OPERATOR', 
        'permissions': ['update_plc', 'update_registers', 'maintenance_mode'],
        'description': 'Manutenção técnica'
    },
    'ENGINEER': {
        'inherits': 'TECHNICIAN',
        'permissions': ['create_plc', 'delete_registers', 'system_config'],
        'description': 'Engenharia de processo'
    },
    'ADMIN': {
        'inherits': 'ENGINEER',
        'permissions': ['manage_users', 'system_admin', 'delete_plc'],
        'description': 'Administração completa'
    }
}
