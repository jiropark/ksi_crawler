"""Flask 앱 팩토리"""

from flask import Flask


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    from app.web.routes import bp
    app.register_blueprint(bp)
    return app
