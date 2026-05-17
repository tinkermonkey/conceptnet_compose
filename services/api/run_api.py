#!/usr/bin/env python3
"""Entry point for the ConceptNet API with OpenTelemetry instrumentation."""

from conceptnet_web.api import app
from telemetry import init_telemetry

init_telemetry(app)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8084, debug=False, threaded=True, use_reloader=False)
