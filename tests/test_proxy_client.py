from app.network.proxy_client import PROXY_URL, get_proxy_session


def test_proxy_session_uses_socks_proxy():
    session = get_proxy_session()
    assert session.proxies.get('http') == PROXY_URL
    assert session.proxies.get('https') == PROXY_URL
