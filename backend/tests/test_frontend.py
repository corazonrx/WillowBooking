def test_homepage_and_local_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Willow Hotel" in response.text
    assert 'id="search-form"' in response.text
    for path in (
        "/static/css/style.css", "/static/js/app.js",
        "/static/images/lounge.jpg", "/static/images/favicon.svg",
        "/static/fonts/baskerville-regular.ttf", "/static/fonts/lato-regular.ttf",
    ):
        assert client.get(path).status_code == 200


def test_private_backend_files_are_not_served(client):
    for path in ("/.env", "/static/.env", "/backend/.env", "/static/../backend/.env"):
        assert client.get(path).status_code == 404
