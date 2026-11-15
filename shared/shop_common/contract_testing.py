"""Provider side of contract testing (pattern 11): replays a consumer's Pact contract against a
real, running copy of this service. Used by the payment and catalog test suites."""
import threading
from pathlib import Path
from typing import Callable


def verify_provider(app, provider: str, consumer: str, states: dict[str, Callable[[], None]], pact_dir: Path) -> None:
    """Starts the Flask app on a free port and verifies every interaction in <consumer>-<provider>.json.

    Raises if any interaction fails. states maps each provider state named in the contract to a
    function that puts the service into that state.
    """
    from pact import Verifier
    from werkzeug.serving import make_server

    def handler(state: str, action: str = "setup", parameters: dict | None = None) -> None:
        if action == "setup" and state in states:
            states[state]()

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        (
            Verifier(provider, host="127.0.0.1")
            .add_transport(url=f"http://127.0.0.1:{server.server_port}")
            .add_source(pact_dir / f"{consumer}-{provider}.json")
            .state_handler(handler, teardown=False)
            .verify()
        )
    finally:
        server.shutdown()
