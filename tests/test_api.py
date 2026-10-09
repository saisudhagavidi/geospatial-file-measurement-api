from fastapi.testclient import TestClient
from main import app, FILES
client = TestClient(app)

def setup_function():
    FILES.clear()

def sample_kml():
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        '<Placemark><name>Sample square</name><Polygon><outerBoundaryIs><LinearRing>'
        '<coordinates>80.0,16.0 80.001,16.0 80.001,16.001 80.0,16.001 80.0,16.0</coordinates>'
        '</LinearRing></outerBoundaryIs></Polygon></Placemark>'
        '</Document></kml>'
    ).encode()

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_upload_kml_and_get_measurements():
    response = client.post("/api/files/", files={"file": ("sample.kml", sample_kml(), "application/vnd.google-earth.kml+xml")})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["feature_count"] == 1
    assert body["status"] == "COMPLETED"
    info = client.get(f"/api/files/{body['id']}/")
    assert info.status_code == 200
    assert info.json()["crs"] == "EPSG:4326"
    result = client.get(f"/api/files/{body['id']}/measurements/")
    assert result.status_code == 200
    feature = result.json()["features"][0]
    assert feature["geometry_type"] == "Polygon"
    assert feature["measurement"] > 0
    assert feature["measurement_unit"] == "m²"

def test_rejects_unsupported_extension():
    response = client.post("/api/files/", files={"file": ("notes.txt", b"not geospatial", "text/plain")})
    assert response.status_code == 400

def test_unknown_file_returns_404():
    assert client.get("/api/files/not-real/").status_code == 404
    assert client.get("/api/files/not-real/measurements/").status_code == 404

def test_invalid_kml_returns_validation_error():
    response = client.post("/api/files/", files={"file": ("broken.kml", b"<not-kml>", "application/xml")})
    assert response.status_code == 422
