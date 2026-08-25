

def test_the_loopback_address_is_an_allowed_origin():
    """A browser treats 127.0.0.1 and localhost as different origins.

    The failure is nasty out of proportion to its size: the client reports a
    refused origin as "Could not reach the server", which sends whoever is
    debugging it at the network, the port and the process before the CORS
    list. Both names already resolve to this host, so allowing the second
    grants nothing.
    """
    from app.config import Settings

    fresh = Settings(_env_file=None)
    assert "http://127.0.0.1:3010" in fresh.cors_origins
    assert "http://localhost:3010" in fresh.cors_origins
