from flask import Flask, send_file
from dashboard_api import dashboard_api

app = Flask(__name__)
app.register_blueprint(dashboard_api)

@app.get("/dashboard/tools")
def dashboard_tools():
    return send_file("dashboard_tools.html")

if __name__ == "__main__":
    app.run(port=8766, debug=True)
