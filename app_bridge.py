"""Minimal bridge to expose dashboard_api and monitor_api on a Flask app."""
from flask import Flask, send_file
from dashboard_api import dashboard_api
from monitor_api import monitor_api
app = Flask(__name__)
app.register_blueprint(dashboard_api)
app.register_blueprint(monitor_api)
@app.get('/dashboard/tools')
def dashboard_tools(): return send_file('dashboard_tools.html')
@app.get('/dashboard/installer')
def dashboard_installer(): return send_file('installer_dashboard.html')
if __name__ == '__main__': app.run(port=8766, debug=True)
