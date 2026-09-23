from flask import jsonify, g

class ApiResponse:
    @staticmethod
    def success(message="Sucesso", data=None, status_code=200):
        return jsonify({
            "success": True,
            "code": "SUCCESS",
            "message": message,
            "trace_id": getattr(g, "trace_id", None),
            "data": data,
            "errors": None,
        }), status_code
    
    @staticmethod
    def error(message="Erro", errors=None, status_code=400, code="ERROR"):
        return jsonify({
            "success": False,
            "code": code,
            "message": message,
            "trace_id": getattr(g, "trace_id", None),
            "data": None,
            "errors": errors or [],
        }), status_code