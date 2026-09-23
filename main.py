from app import create_app, db
from flask_migrate import Migrate
import os

# IMPORTANTE: Importar todos os módulos de modelos aqui
from app.models.auth.user import *
from app.models.pages.gerenciamento_vendas import *
# from app.models.pages.students import *
# from app.models.pages.academy import *
# from app.models.pages.finance import *
# from app.models.pages.core import *

app = create_app(os.getenv('FLASK_ENV', 'development'))
migrate = Migrate(app, db)

# O shell_context ajuda muito para você testar no terminal depois
@app.shell_context_processor
def make_shell_context():
    return dict(
        db=db,
        User=User,
        Produto=Produto,
        Vendedor=Vendedor,
        Venda=Venda
        # Student=Student, 
        # Plan=Plan, 
        # Invoice=Invoice,
        # Modality=Modality
    )