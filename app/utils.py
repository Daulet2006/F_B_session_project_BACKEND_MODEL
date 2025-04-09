from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import jsonify

def role_required(*roles):  # Используем *roles для поддержки нескольких ролей
    def wrapper(fn):
        @jwt_required()
        def decorator(*args, **kwargs):
            current_user = get_jwt_identity()
            if current_user['role'] not in roles:  # Проверяем, что роль пользователя есть в списке разрешенных ролей
                return jsonify({'message': 'Access forbidden'}), 403
            return fn(*args, **kwargs)
        decorator.__name__ = fn.__name__
        return decorator
    return wrapper
