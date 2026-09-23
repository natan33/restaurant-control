from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, HiddenField, SelectField, IntegerField, RadioField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, NumberRange


class VendaForm(FlaskForm):

    produto_id = SelectField(
        "Produto",
        coerce=int,
        validators=[DataRequired()]
    )

    quantidade = IntegerField(
        "Quantidade",
        validators=[DataRequired(), NumberRange(min=1)]
    )

    vendedor_id = HiddenField('vendedor')

    comprador_nome = StringField("Nome do Comprador", validators=[DataRequired()])

    tipo_vendedor = RadioField(
        "Tipo de Vendedor",
        choices=[
            ("Jovem", "Jovem"),
            ("Senhor", "Senhor"),
            ("Membro", "Membro")
        ],
        validators=[DataRequired()]
    )

    status_pagamento = RadioField(
        "Status Pagamento",
        choices=[
            ("Pago", "Pago"),
            ("Pendente", "Pendente")
        ],
        validators=[DataRequired()]
    )

    observacao = TextAreaField("Observação")

    data_venda = DateTimeLocalField(
        "Data da Venda",
        format="%Y-%m-%dT%H:%M",
        validators=[],  # opcional
        default=None
    )

    submit = SubmitField("Registrar Venda")