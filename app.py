from flask_cors import CORS
from flask import Flask, jsonify, request

from functions import classify_name

app = Flask(__name__)
CORS(app, origins="*")


@app.get("/")
def index():
    return jsonify({"message": "Hello"})


@app.get("/api")
@app.get("/api/classify")
def classify():
    try:
        params = request.args
        name = params.get("name")

        if not name:
            return jsonify({"status": "error", "message": "name not specified"}), 400

        if not isinstance(name, str):
            return (
                jsonify({"status": "error", "message": "name should be a string"}),
                422,
            )

        result = classify_name(name)

        if result.get("success", False):
            return jsonify({"status": "success", "data": result.get("data", {})})

        return jsonify({"status": "error", "message": result.get("message", "")}), 400
    except:
        return jsonify({"status": "error", "message": "failed to classify name"}), 500


if __name__ == "__main__":
    app.run(debug=True)
