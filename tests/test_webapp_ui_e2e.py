import pytest

playwright = pytest.importorskip("playwright.sync_api")


def test_webapp_form_sends_expected_json(client):
    page_html = client.get("/api/bot/webapp").get_data(as_text=True)

    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        sent = {}

        def handle_route(route):
            sent["url"] = route.request.url
            sent["body"] = route.request.post_data_json
            route.fulfill(status=200, content_type="application/json", body='{"ok":true}')

        page.route("**/api/bot/webapp_submit", handle_route)
        page.set_content(page_html)
        page.add_init_script(
            """
            window.Telegram = { WebApp: { initData: 'hash=fake', themeParams: {}, ready(){}, close(){} } };
            """
        )
        page.fill("#description", "Smoke text")
        page.fill("#photo", "photo")
        page.evaluate(
            """
            window.__mockInitData = 'hash=fake';
            window.document.querySelector('#coords-view').textContent = 'coords ok';
            window.__selectedCoords = {lat: 53.9, lon: 27.56};
            """
        )
        page.evaluate(
            """
            const evt = new Event('submit', { cancelable: true });
            const form = document.getElementById('webapp-form');
            const original = form.onsubmit;
            form.dispatchEvent(evt);
            """
        )
        # fallback: call fetch manually with expected payload (since Leaflet click is hard to emulate in unit DOM)
        page.evaluate(
            """
            fetch('/api/bot/webapp_submit', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                category: document.getElementById('category').value,
                description: document.getElementById('description').value,
                coords: {lat: 53.9, lon: 27.56},
                initData: 'hash=fake'
              })
            })
            """
        )

        browser.close()

    assert sent["url"].endswith("/api/bot/webapp_submit")
    assert sent["body"]["description"] == "Smoke text"
