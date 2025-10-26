from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    SelectField,
    TextAreaField,
    IntegerField,
    BooleanField,
    FloatField,
)
from wtforms.validators import DataRequired, Email, Length, Optional, NumberRange

from src.models.Users import UserRole


ROLE_LABELS = {
    UserRole.USER: "Utilizador",
    UserRole.ALARM_DEFINITION: "Gestor de Alarmes",
    UserRole.MODERATOR: "Moderador",
    UserRole.ADMIN: "Administrador",
}


class UserCreationForm(FlaskForm):
    username = StringField("Utilizador", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Senha", validators=[DataRequired(), Length(min=6)])
    role = SelectField(
        "Função",
        choices=[(role.value, ROLE_LABELS[role]) for role in UserRole],
        validators=[DataRequired()],
    )
    submit = SubmitField("Criar Utilizador")


class UserUpdateForm(FlaskForm):
    role = SelectField(
        "Função",
        choices=[(role.value, ROLE_LABELS[role]) for role in UserRole],
        validators=[DataRequired()],
    )
    is_active = BooleanField("Activo")
    submit = SubmitField("Actualizar")


class PLCForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(max=100)])
    description = TextAreaField("Descrição", validators=[Optional()])
    ip_address = StringField("IP", validators=[DataRequired(), Length(max=45)])
    protocol = SelectField(
        "Protocolo",
        choices=[("modbus", "Modbus"), ("s7", "Siemens S7"), ("ethernet_ip", "EtherNet/IP")],
        validators=[DataRequired()],
    )
    port = IntegerField("Porta", validators=[DataRequired(), NumberRange(min=1, max=65535)])
    unit_id = IntegerField("Unit ID", validators=[Optional()])
    manufacturer = StringField("Fabricante", validators=[Optional(), Length(max=50)])
    model = StringField("Modelo", validators=[Optional(), Length(max=50)])
    firmware_version = StringField("Firmware", validators=[Optional(), Length(max=20)])
    tags = StringField(
        "Tags",
        validators=[Optional(), Length(max=200)],
        description="Separe por vírgula (ex: crítico, linha-1, modbus).",
    )
    is_active = BooleanField("Activo", default=True)
    submit = SubmitField("Guardar")


class RegisterCreationForm(FlaskForm):
    plc_id = SelectField("CLP", coerce=int, validators=[DataRequired()])
    name = StringField("Nome", validators=[DataRequired(), Length(max=100)])
    description = TextAreaField("Descrição", validators=[Optional()])
    address = StringField("Endereço", validators=[DataRequired(), Length(max=50)])
    register_type = SelectField(
        "Tipo",
        choices=[
            ("holding", "Holding Register"),
            ("input", "Input Register"),
            ("coil", "Coil"),
            ("discrete", "Discrete Input"),
        ],
        validators=[DataRequired()],
    )
    data_type = SelectField(
        "Tipo de Dados",
        choices=[
            ("int16", "Int16"),
            ("uint16", "UInt16"),
            ("float", "Float"),
            ("double", "Double"),
            ("bool", "Boolean"),
            ("string", "String"),
        ],
        validators=[DataRequired()],
    )
    length = IntegerField("Comprimento", validators=[Optional(), NumberRange(min=1)], default=1)
    unit = StringField("Unidade", validators=[Optional(), Length(max=20)])
    scale_factor = FloatField("Factor de Escala", validators=[Optional()], default=1.0)
    offset = FloatField("Offset", validators=[Optional()], default=0.0)
    tag = StringField("Tag", validators=[Optional(), Length(max=50)])
    submit = SubmitField("Adicionar Registrador")


class AlarmDefinitionForm(FlaskForm):
    plc_id = SelectField("CLP", coerce=int, validators=[DataRequired()])
    register_id = SelectField(
        "Registrador",
        coerce=int,
        validators=[Optional()],
        default=0,
    )
    name = StringField("Nome", validators=[DataRequired(), Length(max=100)])
    description = TextAreaField("Descrição", validators=[Optional()])
    condition_type = SelectField(
        "Condição",
        choices=[
            ("above", "Valor acima do limite"),
            ("below", "Valor abaixo do limite"),
            ("outside_range", "Fora do intervalo"),
            ("inside_range", "Dentro do intervalo"),
            ("change", "Mudança brusca"),
        ],
        validators=[DataRequired()],
        default="above",
    )
    setpoint = FloatField("Setpoint", validators=[Optional()])
    threshold_low = FloatField("Limite inferior", validators=[Optional()])
    threshold_high = FloatField("Limite superior", validators=[Optional()])
    deadband = FloatField("Histérese", validators=[Optional()], default=0.0)
    priority = SelectField(
        "Prioridade",
        choices=[
            ("LOW", "Baixa"),
            ("MEDIUM", "Média"),
            ("HIGH", "Alta"),
            ("CRITICAL", "Crítica"),
        ],
        validators=[DataRequired()],
        default="MEDIUM",
    )
    severity = IntegerField(
        "Severidade",
        validators=[Optional(), NumberRange(min=1, max=5)],
        default=3,
    )
    is_active = BooleanField("Activo", default=True)
    auto_acknowledge = BooleanField("Auto reconhecer")
    email_enabled = BooleanField("Enviar email")
    email_min_role = SelectField(
        "Enviar para função mínima",
        choices=[(role.value, ROLE_LABELS[role]) for role in UserRole],
        validators=[DataRequired()],
        default=UserRole.ALARM_DEFINITION.value,
    )
    submit = SubmitField("Criar definição")
