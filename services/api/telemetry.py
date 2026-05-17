"""OpenTelemetry initialization for the ConceptNet API service.

Sets up OTLP gRPC exporters for traces and logs, auto-instruments Flask,
psycopg2, requests, and the Python logging module, and registers atexit
hooks to flush the batch processors on shutdown.

Propagators are not set explicitly: importing ``opentelemetry.propagate``
already installs ``tracecontext,baggage`` as the global textmap (or whatever
``OTEL_PROPAGATORS`` overrides it to), so adding code here would just
duplicate the SDK default.
"""

import atexit
import logging
import os

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_DEFAULT_ATTRIBUTES = {
    "service.name": "conceptnet-api",
    "service.namespace": "conceptnet",
    "service.version": "5.7.0",
}


def _build_resource() -> Resource:
    """Build the OTel Resource.

    Precedence: env-supplied attributes win over the hard-coded defaults.
    ``Resource.create({})`` invokes ``OTELResourceDetector`` which reads
    ``OTEL_SERVICE_NAME`` and ``OTEL_RESOURCE_ATTRIBUTES``; merging that on top
    of the defaults lets compose.yml override anything while still leaving
    sensible values if the service is run without those env vars set.
    """
    defaults = Resource.create(_DEFAULT_ATTRIBUTES)
    from_env = Resource.create({})
    return defaults.merge(from_env)


def _init_tracing(resource: Resource) -> TracerProvider:
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(insecure=True)))
    trace.set_tracer_provider(provider)
    atexit.register(provider.shutdown)
    return provider


class _ExcludeOpenTelemetryLogs(logging.Filter):
    """Drop log records from the ``opentelemetry`` namespace.

    These records still reach stderr via the StreamHandler installed by
    ``LoggingInstrumentor``; this filter only prevents them from being
    re-exported through OTLP, which would cause an unbounded failure loop
    if the collector is unreachable AND can break the OTLP log encoder
    when an SDK internal error logs a non-primitive object as its message
    (e.g. a ``DependencyConflict``).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith("opentelemetry")


def _init_logging(resource: Resource) -> LoggerProvider:
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(insecure=True))
    )
    set_logger_provider(provider)

    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    handler.addFilter(_ExcludeOpenTelemetryLogs())
    root = logging.getLogger()
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)
    root.addHandler(handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    atexit.register(provider.shutdown)
    return provider


def init_telemetry(app):
    """Wire OTel into the Flask app. Must be called after the app is imported."""
    resource = _build_resource()
    _init_tracing(resource)
    LoggingInstrumentor().instrument(set_logging_format=True)
    _init_logging(resource)
    FlaskInstrumentor().instrument_app(app)
    # skip_dep_check=True: the project uses psycopg2-binary, whose pip
    # distribution name does not match "psycopg2" so the instrumentor's
    # version check returns DependencyConflict. The underlying psycopg2
    # module is still importable and the patch applies correctly.
    Psycopg2Instrumentor().instrument(
        skip_dep_check=True,
        enable_commenter=True,
        commenter_options={"db_driver": True},
    )
    RequestsInstrumentor().instrument()

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "<unset>")
    logging.getLogger(__name__).info(
        "OpenTelemetry initialized (otlp endpoint=%s)", endpoint
    )
    return app
