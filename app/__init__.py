from flask import Flask, jsonify, request
from dotenv import load_dotenv
from app.extensions import db
from app.routes.messages import messages_bp
from app.services.auth import validate_request
from app.routes.agent_card import agent_card_bp
from app.routes.tasks import tasks_bp
from groq import Groq
import os

load_dotenv()


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "sqlite:///invoice_agent.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    app.register_blueprint(agent_card_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(messages_bp)
    @app.before_request
    def protect_a2a_routes():
        if request.path.startswith("/a2a/"):
            return validate_request()

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "healthy",
            "service": "A2A Invoice Agent"
        }), 200

    @app.route("/a2a/groq-check", methods=["GET"])
    def groq_check():
        try:
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            client.models.list()
            return jsonify({"status": "Groq authentication successful"}), 200
        except Exception:
            app.logger.exception("Groq authentication check failed")
            return jsonify({"status": "Groq authentication failed"}), 500

    with app.app_context():
        from app.models import Task, MessageRecord, DecisionCache
        db.create_all()

    return app