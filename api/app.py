import csv
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI()
PRODUCTS_FILE = Path(__file__).resolve().parent.parent / "products.csv"
FIELDNAMES = ["id", "name", "quantity", "unit"]
EXAMPLE_PRODUCTS = [
    {"id": 1, "name": "Leche de avena", "quantity": 8, "unit": "litros"},
    {"id": 2, "name": "Café arábica", "quantity": 25, "unit": "bolsas"},
    {"id": 3, "name": "Vasos de cartón", "quantity": 200, "unit": "unidades"},
    {"id": 4, "name": "Azúcar", "quantity": 5, "unit": "kg"},
    {"id": 5, "name": "Sirope de vainilla", "quantity": 12, "unit": "botellas"},
]


class ProductInput(BaseModel):
    name: str
    quantity: int = Field(ge=0)
    unit: str


class StockDelta(BaseModel):
    delta: int


class Product(BaseModel):
    id: int
    name: str
    quantity: int
    unit: str


def ensure_products_file() -> None:
    """Crea el CSV con datos de ejemplo si todavía no existe."""
    if not PRODUCTS_FILE.exists():
        with PRODUCTS_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(EXAMPLE_PRODUCTS)


ensure_products_file()


def read_products() -> list[dict]:
    ensure_products_file()
    with PRODUCTS_FILE.open("r", newline="", encoding="utf-8") as file:
        return [
            {"id": int(row["id"]), "name": row["name"], "quantity": int(row["quantity"]), "unit": row["unit"]}
            for row in csv.DictReader(file)
        ]


def write_products(products: list[dict]) -> None:
    with PRODUCTS_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(products)


@app.get("/inventory", response_model=list[Product])
def get_inventory() -> list[dict]:
    return read_products()


@app.post("/inventory", response_model=Product, status_code=201)
def create_product(product: ProductInput) -> dict:
    products = read_products()
    next_id = max((item["id"] for item in products), default=0) + 1
    new_product = {"id": next_id, **product.model_dump()}
    products.append(new_product)
    write_products(products)
    return new_product


@app.patch("/inventory/{product_id}", response_model=Product)
def update_stock(product_id: int, update: StockDelta) -> dict:
    products = read_products()
    product = next((item for item in products if item["id"] == product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No existe un producto con el ID {product_id}.")

    new_quantity = product["quantity"] + update.delta
    if new_quantity < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Stock insuficiente: hay {product['quantity']} {product['unit']} disponibles.",
        )

    product["quantity"] = new_quantity
    write_products(products)
    return product


@app.get("/inventory/alerts", response_model=list[Product])
def get_inventory_alerts(threshold: int = 10) -> list[dict]:
    return [product for product in read_products() if product["quantity"] < threshold]
