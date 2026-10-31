from flask import Blueprint, jsonify
import os

agent_card_bp = Blueprint("agent_card", __name__)


@agent_card_bp.route("/.well-known/agent-card.json", methods=["GET"])
def agent_card():

    base_url = os.getenv(
        "A2A_BASE_URL",
        "http://127.0.0.1:5000/a2a/"
    )

    card = {
        "name": "A2A Invoice Agent",
        "description": (
            "An AI-powered invoice decision agent that "
            "evaluates invoices, proposes safe business actions "
            "and executes only approved actions."
        ),
        "version": "1.0.0",

        "supportedInterfaces": [
            {
                "url": base_url,
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0"
            }
        ],

        "capabilities": {},

        "defaultInputModes": [
            "application/vnd.ga5.invoice-claim-batch+json"
        ],

        "defaultOutputModes": [
            "application/vnd.ga5.invoice-action-proposals+json",
            "application/vnd.ga5.invoice-action-receipts+json"
        ],

        "skills": [
            {
                "id": "invoice_action_agent",
                "name": "Invoice Action Agent",
                "description": (
                    "Analyzes invoice packages, checks evidence, "
                    "identifies duplicates and approval requirements, "
                    "and executes accepted actions safely."
                ),
                "tags": [
                    "invoice",
                    "finance",
                    "approval",
                    "payment",
                    "evidence"
                ]
            }
        ]
    }

    return jsonify(card), 200