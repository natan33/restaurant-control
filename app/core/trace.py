import uuid
from flask import g, request

def register_trace_id(app):

    @app.before_request
    def start_trace():
        # Busca o ID no cabeçalho ou gera um novo
        trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
        g.trace_id = trace_id

    @app.after_request
    def end_trace(response):
        # Importante: Retorna o ID para o cliente ver no navegador/console
        if hasattr(g, 'trace_id'):
            response.headers["X-Trace-Id"] = g.trace_id
        return response