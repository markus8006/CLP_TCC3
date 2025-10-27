# Roles pré-definidas com herança
ROLES_HIERARCHY = {
    'VIEWER': {
        'permissions': ['read_plc', 'read_data', 'read_alarms'],
        'description': 'Acesso somente leitura aos painéis e indicadores.'
    },
    'USER': {
        'inherits': 'VIEWER',
        'permissions': ['acknowledge_basic_alerts'],
        'description': 'Utilizador padrão com capacidade de reconhecer notificações básicas.'
    },
    'OPERATOR': {
        'inherits': 'USER',
        'permissions': ['acknowledge_alarms', 'control_runtime'],
        'description': 'Responsável por operar a planta e reagir aos alarmes.'
    },
    'ALARM_DEFINITION': {
        'inherits': 'OPERATOR',
        'permissions': ['manage_alarm_definitions'],
        'description': 'Pode criar e ajustar regras de alarmes.'
    },
    'TECHNICIAN': {
        'inherits': 'ALARM_DEFINITION',
        'permissions': ['update_plc', 'update_registers', 'maintenance_mode'],
        'description': 'Equipa técnica responsável pela manutenção de dispositivos.'
    },
    'MODERATOR': {
        'inherits': 'TECHNICIAN',
        'permissions': ['manage_registers', 'manage_plcs'],
        'description': 'Supervisiona o cadastro de CLPs e registradores.'
    },
    'GERENTE': {
        'inherits': 'MODERATOR',
        'permissions': ['control_polling', 'approve_changes'],
        'description': 'Controla o serviço de polling e aprova alterações operacionais.'
    },
    'ENGINEER': {
        'inherits': 'GERENTE',
        'permissions': ['create_plc', 'delete_registers', 'system_config'],
        'description': 'Configura a arquitetura e integra novos equipamentos.'
    },
    'ADMIN': {
        'inherits': 'ENGINEER',
        'permissions': ['manage_users', 'system_admin', 'delete_plc'],
        'description': 'Administração completa do ambiente.'
    }
}
