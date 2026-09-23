from flask import Blueprint


main = Blueprint('main', __name__)


from . import home_page,painel_vendas