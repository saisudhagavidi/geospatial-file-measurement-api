from __future__ import annotations
import io, shutil, tempfile, uuid, zipfile
from pathlib import Path
from typing import Any
import geopandas as gpd
from fastapi import FastAPI, File, HTTPException, UploadFile
from pyproj import CRS, Transformer
from shapely.geometry import mapping
from shapely.ops import transform as transform_geometry

app = FastAPI(title="Geospatial File Measurement API", version="1.0.0",
              description="Upload a zipped Shapefile or KML and retrieve feature measurements.")
# Assignment starter: results are in memory and disappear on restart.
FILES: dict[str, dict[str, Any]] = {}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".zip", ".kml"}

def read_geodataframe(path: Path, extension: str) -> gpd.GeoDataFrame:
    try:
        gdf = gpd.read_file(path, driver="KML") if extension == ".kml" else gpd.read_file(f"zip://{path.as_posix()}")
    except Exception as exc:
        raise ValueError("Could not read the file. Check KML validity or include .shp, .shx, .dbf and .prj in the ZIP.") from exc
    if gdf.empty:
        raise ValueError("The uploaded file contains no features.")
    if "geometry" not in gdf:
        raise ValueError("The uploaded file has no geometry column.")
    if gdf.crs is None:
        if extension == ".kml":
            gdf = gdf.set_crs("EPSG:4326")
        else:
            raise ValueError("The Shapefile has no CRS. Include a .prj file in the ZIP.")
    return gdf

def process_features(gdf: gpd.GeoDataFrame):
    source_crs = CRS.from_user_input(gdf.crs)
    try:
        target_crs = CRS.from_user_input(gdf.estimate_utm_crs())
    except Exception as exc:
        raise ValueError("Could not determine a suitable projected CRS for this dataset.") from exc
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    features = []
    for index, row in gdf.iterrows():
        geom = row.geometry
        properties = {}
        for key, value in row.drop(labels=["geometry"]).to_dict().items():
            if hasattr(value, "item"):
                value = value.item()
            if value is not None and not isinstance(value, (str, int, float, bool)):
                value = str(value)
            properties[str(key)] = value
        item = {
            "feature_id": str(index),
            "geometry_type": geom.geom_type if geom is not None else None,
            "geometry": mapping(geom) if geom is not None and not geom.is_empty else None,
            "crs": source_crs.to_string(),
            "properties": properties,
            "measurement": None,
            "measurement_unit": None,
            "measurement_status": "NOT_APPLICABLE",
        }
        if geom is None or geom.is_empty:
            item["measurement_status"] = "EMPTY_GEOMETRY"
        elif geom.geom_type in ("Polygon", "MultiPolygon"):
            projected = transform_geometry(transformer.transform, geom)
            item.update(measurement=float(projected.area), measurement_unit="m²", measurement_status="COMPLETED")
        elif geom.geom_type in ("LineString", "MultiLineString"):
            projected = transform_geometry(transformer.transform, geom)
            item.update(measurement=float(projected.length), measurement_unit="m", measurement_status="COMPLETED")
        elif geom.geom_type in ("Point", "MultiPoint"):
            item["measurement_status"] = "NO_MEASUREMENT_REQUIRED"
        else:
            item["measurement_status"] = "UNSUPPORTED_GEOMETRY"
        features.append(item)
    return features, source_crs.to_string(), target_crs.to_string()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/files/", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Only .kml and .zip files are accepted.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the 25 MB upload limit.")
    temp_dir = Path(tempfile.mkdtemp(prefix="geo_measure_"))
    path = temp_dir / filename
    try:
        path.write_bytes(content)
        if extension == ".zip":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    names = archive.namelist()
                    if not any(name.lower().endswith(".shp") for name in names):
                        raise ValueError("ZIP does not contain a .shp file.")
                    if any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
                        raise ValueError("ZIP contains an unsafe path.")
            except zipfile.BadZipFile as exc:
                raise ValueError("The uploaded ZIP file is invalid.") from exc
        gdf = read_geodataframe(path, extension)
        features, source_crs, measurement_crs = process_features(gdf)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, "Unable to process this geospatial file.") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    file_id = uuid.uuid4().hex[:12]
    FILES[file_id] = {
        "id": file_id, "filename": filename, "feature_count": len(features),
        "crs": source_crs, "measurement_crs": measurement_crs,
        "status": "COMPLETED", "features": features,
    }
    return {
        "id": file_id, "filename": filename, "feature_count": len(features),
        "crs": source_crs, "measurement_crs": measurement_crs,
        "status": "COMPLETED", "measurements_url": f"/api/files/{file_id}/measurements/",
    }

@app.get("/api/files/{file_id}/")
def get_file_info(file_id: str):
    record = FILES.get(file_id)
    if record is None:
        raise HTTPException(404, "File not found.")
    return {key: record[key] for key in ("id", "filename", "feature_count", "crs", "measurement_crs", "status")}

@app.get("/api/files/{file_id}/measurements/")
def get_measurements(file_id: str):
    record = FILES.get(file_id)
    if record is None:
        raise HTTPException(404, "File not found.")
    return {key: record[key] for key in ("id", "filename", "crs", "measurement_crs", "feature_count", "features")}
