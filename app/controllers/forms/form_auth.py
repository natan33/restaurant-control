from flask_wtf import FlaskForm
from wtforms import HiddenField, StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length

class LoginForm(FlaskForm):
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    password = PasswordField('Senha', validators=[DataRequired()])
    remember_me = BooleanField('Manter conectado')
    submit = SubmitField('Entrar')

class ForgotPasswordForm(FlaskForm):
    email = StringField('E-mail', validators=[DataRequired(), Email()])
    submit = SubmitField('Enviar Código')

class ResetPasswordForm(FlaskForm):
    email = HiddenField()
    code = StringField('Código de Recuperação', validators=[DataRequired()])
    password = PasswordField('Nova Senha', validators=[DataRequired()])
    submit = SubmitField('Redefinir Senha')


class RedefinirSenhaForm(FlaskForm):

    senha_atual = PasswordField(
        "Senha atual",
        validators=[DataRequired()]
    )

    nova_senha = PasswordField(
        "Nova senha",
        validators=[
            DataRequired(),
            Length(min=6, message="A senha deve ter pelo menos 6 caracteres")
        ]
    )

    confirmar_senha = PasswordField(
        "Confirmar senha",
        validators=[
            DataRequired(),
            EqualTo("nova_senha", message="As senhas não coincidem")
        ]
    )

    submit = SubmitField("Salvar nova senha")