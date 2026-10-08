"""Tests de la API con TestClient y una base SQLite temporal por test."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

API_KEY = "clave-de-prueba"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("API_KEY", API_KEY)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))
    with TestClient(app) as c:
        yield c


def stock_de(client: TestClient, producto_id: str) -> int:
    res = client.get(f"/api/productos/{producto_id}", headers=HEADERS)
    assert res.status_code == 200
    return res.json()["stock"]


def pedido_domicilio(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "cliente": "Carlos Rueda",
        "telefono": "3001234567",
        "modalidad": "domicilio",
        "direccion": "Calle 36 # 20-15, Cabecera",
        "notas": "timbre dañado",
        "items": items,
    }


def test_productos_sin_api_key_401(client: TestClient) -> None:
    res = client.get("/api/productos")
    assert res.status_code == 401
    assert res.json() == {"error": "no_autorizado", "mensaje": "API key inválida"}


def test_buscar_huevos_devuelve_dos(client: TestClient) -> None:
    res = client.get("/api/productos", params={"q": "huevos"}, headers=HEADERS)
    assert res.status_code == 200
    cuerpo = res.json()
    assert cuerpo["total"] == 2
    assert {p["nombre"] for p in cuerpo["productos"]} == {"Huevos criollos", "Huevos AA"}


def test_buscar_hormiga_singular_encuentra_por_alias(client: TestClient) -> None:
    res = client.get("/api/productos", params={"q": "hormiga"}, headers=HEADERS)
    assert res.status_code == 200
    nombres = [p["nombre"] for p in res.json()["productos"]]
    assert nombres == ["Hormigas culonas"]


def test_crear_pedido_valido_descuenta_stock(client: TestClient) -> None:
    stock_pollo = stock_de(client, "pollo-campesino")
    stock_bocadillo = stock_de(client, "bocadillo-veleno-caja")
    body = pedido_domicilio(
        [
            {"producto_id": "pollo-campesino", "cantidad": 1},
            {"producto_id": "bocadillo-veleno-caja", "cantidad": 2},
        ]
    )
    res = client.post("/api/pedidos", json=body, headers=HEADERS)
    assert res.status_code == 201, res.text
    pedido = res.json()
    assert pedido["numero_pedido"] == "TC-0001"
    assert pedido["estado"] == "recibido"
    assert pedido["subtotal"] == 42000 + 2 * 14000
    assert pedido["costo_domicilio"] == 5000
    assert pedido["total"] == 75000
    assert pedido["tiempo_estimado"] == "45 a 60 minutos"
    assert pedido["creado_en"].endswith("-05:00")
    assert stock_de(client, "pollo-campesino") == stock_pollo - 1
    assert stock_de(client, "bocadillo-veleno-caja") == stock_bocadillo - 2


def test_pedido_stock_insuficiente_409_sin_cambios(client: TestClient) -> None:
    stock_hormigas = stock_de(client, "hormigas-culonas-100g")
    stock_pollo = stock_de(client, "pollo-campesino")
    body = pedido_domicilio(
        [
            {"producto_id": "pollo-campesino", "cantidad": 1},
            {"producto_id": "hormigas-culonas-100g", "cantidad": stock_hormigas + 2},
        ]
    )
    res = client.post("/api/pedidos", json=body, headers=HEADERS)
    assert res.status_code == 409
    cuerpo = res.json()
    assert cuerpo["error"] == "stock_insuficiente"
    assert cuerpo["problemas"] == [
        {
            "producto_id": "hormigas-culonas-100g",
            "nombre": "Hormigas culonas",
            "solicitado": stock_hormigas + 2,
            "disponible": stock_hormigas,
        }
    ]
    assert stock_de(client, "hormigas-culonas-100g") == stock_hormigas
    assert stock_de(client, "pollo-campesino") == stock_pollo
    assert client.get("/api/pedidos", headers=HEADERS).json()["total"] == 0


def test_domicilio_sin_direccion_422(client: TestClient) -> None:
    body = pedido_domicilio([{"producto_id": "pollo-campesino", "cantidad": 1}])
    body["direccion"] = None
    res = client.post("/api/pedidos", json=body, headers=HEADERS)
    assert res.status_code == 422
    cuerpo = res.json()
    assert cuerpo["error"] == "datos_invalidos"
    assert "dirección es obligatoria" in cuerpo["mensaje"]


def test_cancelar_pedido_devuelve_stock(client: TestClient) -> None:
    stock_inicial = stock_de(client, "tamal-santandereano")
    body = pedido_domicilio([{"producto_id": "tamal-santandereano", "cantidad": 3}])
    numero = client.post("/api/pedidos", json=body, headers=HEADERS).json()["numero_pedido"]
    assert stock_de(client, "tamal-santandereano") == stock_inicial - 3

    res = client.patch(f"/api/pedidos/{numero}", json={"estado": "cancelado"}, headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["estado"] == "cancelado"
    assert stock_de(client, "tamal-santandereano") == stock_inicial


def test_reset_restaura_stock_del_seed(client: TestClient) -> None:
    stock_seed = stock_de(client, "pechuga-libra")
    body = pedido_domicilio([{"producto_id": "pechuga-libra", "cantidad": 4}])
    assert client.post("/api/pedidos", json=body, headers=HEADERS).status_code == 201
    assert stock_de(client, "pechuga-libra") == stock_seed - 4

    res = client.post("/api/admin/reset", headers=HEADERS)
    assert res.status_code == 200
    assert res.json() == {"ok": True, "productos_cargados": 16}
    assert stock_de(client, "pechuga-libra") == stock_seed
    assert client.get("/api/pedidos", headers=HEADERS).json()["total"] == 0
