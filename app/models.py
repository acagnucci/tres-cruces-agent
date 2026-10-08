"""Modelos Pydantic de request y response."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Categoria = Literal["avicola", "tipicos"]
Modalidad = Literal["domicilio", "recoger"]
Estado = Literal["recibido", "en_preparacion", "entregado", "cancelado"]


class Producto(BaseModel):
    id: str
    nombre: str
    categoria: Categoria
    presentacion: str
    unidad: str
    precio: int
    stock: int
    disponible: bool
    descripcion: str


class ProductosResponse(BaseModel):
    productos: list[Producto]
    total: int


class ItemIn(BaseModel):
    producto_id: str = Field(min_length=1)
    cantidad: int = Field(ge=1)


class PedidoIn(BaseModel):
    cliente: str = Field(min_length=1)
    telefono: str = Field(min_length=1)
    modalidad: Modalidad
    direccion: str | None = None
    notas: str | None = None
    items: list[ItemIn] = Field(min_length=1)

    @model_validator(mode="after")
    def direccion_si_domicilio(self) -> "PedidoIn":
        if self.modalidad == "domicilio" and not (self.direccion and self.direccion.strip()):
            raise ValueError("La dirección es obligatoria para pedidos a domicilio")
        return self


class ItemOut(BaseModel):
    producto_id: str
    nombre: str
    cantidad: int
    precio_unitario: int
    subtotal: int


class Pedido(BaseModel):
    numero_pedido: str
    estado: Estado
    cliente: str
    telefono: str
    modalidad: Modalidad
    direccion: str | None
    notas: str | None
    items: list[ItemOut]
    subtotal: int
    costo_domicilio: int
    total: int
    tiempo_estimado: str
    creado_en: str


class PedidosResponse(BaseModel):
    pedidos: list[Pedido]
    total: int


class EstadoUpdate(BaseModel):
    estado: Estado


class ProblemaItem(BaseModel):
    producto_id: str
    nombre: str | None
    solicitado: int
    disponible: int


class ResetResponse(BaseModel):
    ok: bool
    productos_cargados: int


class HealthResponse(BaseModel):
    ok: bool


class AdminData(BaseModel):
    inventario: list[Producto]
    pedidos: list[Pedido]
