import logging
from flask import g, has_request_context

class TraceIdFilter(logging.Filter):
    def filter(self, record):
        if has_request_context():
            record.trace_id = getattr(g, 'trace_id', 'N/A')
        else:
            record.trace_id = 'SYSTEM'
        return True

def setup_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Se já existirem handlers (para evitar logs duplicados ao reiniciar o Flask)
    if not logger.handlers:
        handler = logging.StreamHandler()
        
        # Criamos o filtro
        trace_filter = TraceIdFilter()
        handler.addFilter(trace_filter)
        
        # Definimos o formato NO HANDLER, garantindo que o filtro rode antes
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | trace=%(trace_id)s | %(message)s"
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
    
    # IMPORTANTE: Desativar a propagação para evitar que o log padrão do Flask
    # tente formatar a mensagem sem o nosso filtro.
    logging.getLogger('werkzeug').propagate = True