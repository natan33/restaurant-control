from flask import Blueprint


main = Blueprint('main', __name__)


from . import compras, home_page, painel_vendas, produtos
