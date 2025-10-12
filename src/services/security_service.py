import re
import json
from datetime import datetime
from app.extensions import db
from app.models.audit_log import AuditLog

class SecurityMonitor:
    def __init__(self):
        self.suspicious_patterns = [
            r'(?i)(union|select|insert|delete|drop|exec)',  # SQL Injection
            r'<script.*?>.*?</script>',  # XSS
            r'\.\./',  # Directory traversal
        ]
    
    def analyze_request(self, request):
        """Analisa requisições em busca de padrões suspeitos"""
        suspicious_score = 0
        
        # Verifica URL e parâmetros
        full_url = str(request.url)
        for pattern in self.suspicious_patterns:
            if re.search(pattern, full_url):
                suspicious_score += 10
                
        # Verifica headers suspeitos
        user_agent = request.headers.get('User-Agent', '')
        if 'sqlmap' in user_agent.lower() or 'nmap' in user_agent.lower():
            suspicious_score += 20
            
        if suspicious_score > 15:
            self.log_security_event(request, suspicious_score)
            return False  # Bloquear requisição
            
        return True
    
    def log_security_event(self, request, score):
        """Registra evento de segurança"""
        # Você precisa criar este modelo
        from app.models.security_event import SecurityEvent
        
        security_log = SecurityEvent(
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            url=str(request.url),
            method=request.method,
            threat_score=score,
            timestamp=datetime.utcnow()
        )
        db.session.add(security_log)
        db.session.commit()

class ConnectionMonitor:
    def __init__(self):
        self.active_connections = {}
        self.failed_attempts = {}
        
    def track_connection(self, ip, protocol, success):
        if not success:
            self.failed_attempts[ip] = self.failed_attempts.get(ip, 0) + 1
            if self.failed_attempts[ip] > 5:
                self.blacklist_ip(ip)
                
    def blacklist_ip(self, ip):
        # Implementar blacklist temporário
        logger.warning(f"IP {ip} bloqueado por tentativas excessivas")

class AuditService:
    def __init__(self, db):
        self.db = db
    
    def log_action(self, user_id, action, resource_type, resource_id=None, 
                   description=None, old_values=None, new_values=None):
        """Registra todas as ações no sistema"""
        from flask import request
        
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            old_values=json.dumps(old_values) if old_values else None,
            new_values=json.dumps(new_values) if new_values else None,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        
        self.db.session.add(audit_log)
        self.db.session.commit()
        
        # Alertas para ações críticas
        if action in ['DELETE_PLC', 'DELETE_USER', 'CHANGE_CRITICAL_CONFIG']:
            self.send_security_alert(audit_log)
    
    def send_security_alert(self, audit_log):
        """Envia alertas para ações de segurança críticas"""
        # Implementar notificação por email/SMS
        pass
