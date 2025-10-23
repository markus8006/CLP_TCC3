import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_alert_email(subject: str, body: str, recipients: list):
    # Configurações do servidor SMTP (exemplo Gmail)
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "@gmail.com"
    sender_password = ""  # senha de app, não a normal do Gmail

    # Monta mensagem
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Conecta e envia
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)

        for recipient in recipients:
            msg['To'] = recipient
            server.sendmail(sender_email, recipient, msg.as_string())
            print(f"[+] Alerta enviado para {recipient}")

        server.quit()
    except Exception as e:
        print(f"[!] Erro ao enviar email: {e}")

# ---------- TESTE ----------
if __name__ == "__main__":
    subject = "🚨 ALERTA DE TESTE"
    body = "Teste de alerta automático. Ignorar."
    recipients = ["@gmail.com"]
    send_alert_email(subject, body, recipients)
