# Geospatial File Measurement API

FastAPI service that accepts KML or a ZIP archive containing a Shapefile, extracts features and calculates polygon area and line length after transforming geometries to a projected CRS.

## Features
- `POST /api/files/` — upload `.kml` or `.zip` containing a Shapefile.
- `GET /api/files/{id}/` — retrieve file metadata.
- `GET /api/files/{id}/measurements/` — retrieve geometry, properties, CRS and measurements.
- `GET /health` — health check.
- Polygon/MultiPolygon area in square metres; LineString/MultiLineString length in metres.
- Point/MultiPoint has no measurement; unsupported geometry is reported without crashing.
- Geographic coordinates are transformed to an estimated local UTM CRS before measuring.

## Requirements
Python 3.10+ and GDAL/Fiona support for KML and Shapefile drivers. KML support depends on the GDAL build in your environment.

## Setup (Windows PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --reload
```
Open `http://127.0.0.1:8000/docs` for Swagger UI. On macOS/Linux, activate with `source .venv/bin/activate`.

## API
### Upload
```bash
curl -X POST "http://127.0.0.1:8000/api/files/" -F "file=@survey.kml"
```
For Shapefile, ZIP the `.shp`, `.shx`, `.dbf` and `.prj` files together:
```bash
curl -X POST "http://127.0.0.1:8000/api/files/" -F "file=@survey.zip"
```
Example response (values are illustrative):
```json
{
  "id": "a1b2c3d4e5f6",
  "filename": "survey.kml",
  "feature_count": 1,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32644",
  "status": "COMPLETED",
  "measurements_url": "/api/files/a1b2c3d4e5f6/measurements/"
}
```
### File info
`GET /api/files/{id}/`
```json
{
  "id": "a1b2c3d4e5f6",
  "filename": "survey.kml",
  "feature_count": 1,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32644",
  "status": "COMPLETED"
}
```
### Measurements
`GET /api/files/{id}/measurements/` returns a feature list. Each feature includes `feature_id`, `geometry_type`, `geometry`, `crs`, `properties`, `measurement`, `measurement_unit` and `measurement_status`. Example abbreviated feature:
```json
{
  "feature_id": "0",
  "geometry_type": "Polygon",
  "geometry": {"type": "Polygon", "coordinates": []},
  "crs": "EPSG:4326",
  "properties": {"Name": "Sample field"},
  "measurement": 12345.6,
  "measurement_unit": "m²",
  "measurement_status": "COMPLETED"
}
```
The empty coordinates are abbreviated for documentation; actual responses include the full geometry.

## Architecture
- `main.py`: routes, file validation, data reading, CRS transformation and calculations.
- `tests/test_api.py`: endpoint and validation tests.
- `requirements.txt`: dependencies.

Flow: validate extension/size → inspect ZIP paths → read with GeoPandas → identify source CRS → estimate local UTM CRS → transform measurable geometries → calculate area/length → return JSON results.

## CRS and design decisions
Area/length on longitude/latitude coordinates would be in angular degrees, so geometries are transformed to a projected CRS before measuring. The app estimates a local UTM CRS, appropriate for many local/regional datasets. Datasets spanning multiple UTM zones or continents need per-region CRS selection or geodesic calculations. KML is assigned EPSG:4326 if the reader omits CRS. Shapefiles without `.prj` are rejected rather than silently assuming a CRS.

## Errors and limits
- Unsupported extensions: HTTP 400.
- Invalid/unreadable files: HTTP 422.
- Uploads over 25 MB: HTTP 413.
- Unknown IDs: HTTP 404.
- ZIP member paths are checked before reading.
- Unsupported geometries receive a status.
- This starter uses in-memory storage; metadata/results disappear when the app restarts.

## Tests
```powershell
pytest -q
```
Tests cover health, KML upload and measurement, metadata retrieval, invalid extensions, malformed KML and unknown IDs.

## Learning
This project practises REST API design, multipart uploads, geospatial formats, CRS, Shapely geometry processing, PyProj transformations, validation and API testing.

## Future scope
- Persist metadata in PostgreSQL/PostGIS and files in durable storage.
- Add authentication, per-user access control, auditing and stronger resource limits.
- Move large jobs to a background queue with progress reporting.
- Improve CRS selection for multi-zone/global datasets and add geodesic measurement.
- Add Docker deployment and CI tests.

This is an assignment starter, not a fully hardened production service. Run the tests and try both a real KML and a zipped Shapefile in your environment before submission.
