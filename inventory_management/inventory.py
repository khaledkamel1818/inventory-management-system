"""
Inventory Management System.

A small, dependency-free system for tracking a shop's or warehouse's
stock. It demonstrates object-oriented design in pure Python:

* ``Supplier``       - who a product is bought from.
* ``Product``        - one SKU with prices, stock level and reorder point.
* ``StockMovement``  - an immutable record of stock coming in or going out.
* ``Inventory``      - the product catalogue, stock operations and reports.
* ``StockObserver``  - an interface for reacting to low stock (Observer).

Money is handled with ``decimal.Decimal`` so totals are always exact.

Run this file directly to see a full demonstration::

    python inventory.py
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Callable, Dict, List, Optional, Union


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------

class InventoryError(Exception):
    """Base class for every error raised by this module."""


class ValidationError(InventoryError, ValueError):
    """Raised when input data is invalid (bad SKU, negative price...)."""


class NotFoundError(InventoryError, KeyError):
    """Raised when a product or supplier does not exist."""

    def __str__(self) -> str:  # KeyError would otherwise wrap it in quotes
        return str(self.args[0]) if self.args else ""


class DuplicateError(InventoryError):
    """Raised when adding a product or supplier whose ID is already used."""


class InsufficientStockError(InventoryError):
    """Raised when removing more units than are in stock."""


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------

Number = Union[int, float, str, Decimal]
CENT = Decimal("0.01")
_SKU_PATTERN = re.compile(r"^[A-Z]{2,5}-\d{3,6}$")
_EMAIL_PATTERN = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def _require_text(value: str, field_name: str) -> str:
    """Return ``value`` stripped, or raise if it is empty or not a string."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _validate_sku(sku: str) -> str:
    """SKUs look like ``ELEC-001``: 2-5 letters, a dash and 3-6 digits."""
    sku = _require_text(sku, "SKU").upper()
    if not _SKU_PATTERN.match(sku):
        raise ValidationError(
            f"SKU must look like 'ABC-123', got {sku!r}.")
    return sku


def _validate_email(email: str) -> str:
    email = _require_text(email, "Email").lower()
    if not _EMAIL_PATTERN.match(email):
        raise ValidationError(f"Invalid email address: {email!r}.")
    return email


def _validate_quantity(value: int, field_name: str = "Quantity",
                       allow_zero: bool = False) -> int:
    # bool is a subclass of int, but True/False are never valid counts.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field_name} must be a whole number.")
    if value < 0 or (value == 0 and not allow_zero):
        lowest = "zero or more" if allow_zero else "at least 1"
        raise ValidationError(f"{field_name} must be {lowest}.")
    return value


def to_money(value: Number, field_name: str = "Price") -> Decimal:
    """Convert ``value`` to a non-negative Decimal rounded to cents."""
    if isinstance(value, bool) or not isinstance(value,
                                                 (int, float, str, Decimal)):
        raise ValidationError(f"{field_name} must be a number.")
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        amount = Decimal("NaN")
    if not amount.is_finite() or amount < 0 or amount > 10 ** 9:
        raise ValidationError(
            f"{field_name} must be a number between 0 and 1,000,000,000.")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------
# Domain classes
# --------------------------------------------------------------------------

class MovementType(Enum):
    """Why stock changed."""

    RECEIVED = "received"       # bought from a supplier
    SOLD = "sold"               # sold to a customer
    RETURNED = "returned"       # returned by a customer
    ADJUSTED = "adjusted"       # stock count correction (damage, loss...)


@dataclass(frozen=True)
class StockMovement:
    """One immutable change to a product's stock (an audit-log entry)."""

    sku: str
    movement_type: MovementType
    quantity: int               # positive = in, negative = out
    unit_price: Decimal         # price the units moved at
    unit_cost: Decimal          # cost price at that moment, for profit
    timestamp: datetime
    note: str = ""

    @property
    def value(self) -> Decimal:
        return abs(self.quantity) * self.unit_price


@dataclass
class Supplier:
    """A company that supplies products."""

    supplier_id: str
    name: str
    email: str

    def __post_init__(self) -> None:
        self.supplier_id = _require_text(self.supplier_id,
                                         "Supplier ID").upper()
        self.name = _require_text(self.name, "Supplier name")
        self.email = _validate_email(self.email)


@dataclass
class Product:
    """One stock-keeping unit.

    Responsibility (SRP): hold one product's data and protect its stock
    level, which can only change through ``increase`` and ``decrease``.
    """

    sku: str
    name: str
    category: str
    cost_price: Decimal
    sale_price: Decimal
    reorder_level: int = 5
    supplier_id: Optional[str] = None
    _quantity: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.sku = _validate_sku(self.sku)
        self.name = _require_text(self.name, "Product name")
        self.category = _require_text(self.category, "Category").title()
        self.cost_price = to_money(self.cost_price, "Cost price")
        self.sale_price = to_money(self.sale_price, "Sale price")
        if self.sale_price < self.cost_price:
            raise ValidationError(
                f"Sale price ({self.sale_price}) is below cost price "
                f"({self.cost_price}) for {self.name!r}.")
        self.reorder_level = _validate_quantity(
            self.reorder_level, "Reorder level", allow_zero=True)

    @property
    def quantity(self) -> int:
        """Units in stock (read-only)."""
        return self._quantity

    @property
    def needs_reorder(self) -> bool:
        return self._quantity <= self.reorder_level

    @property
    def margin_pct(self) -> float:
        """Profit margin as a percentage of the sale price."""
        if not self.sale_price:
            return 0.0
        return round(float((self.sale_price - self.cost_price)
                           / self.sale_price * 100), 1)

    @property
    def stock_value(self) -> Decimal:
        """Value of the units in stock at cost price."""
        return self._quantity * self.cost_price

    def increase(self, quantity: int) -> None:
        self._quantity += _validate_quantity(quantity)

    def decrease(self, quantity: int) -> None:
        quantity = _validate_quantity(quantity)
        if quantity > self._quantity:
            raise InsufficientStockError(
                f"Only {self._quantity} unit(s) of {self.name!r} in stock, "
                f"cannot remove {quantity}.")
        self._quantity -= quantity

    def __str__(self) -> str:
        flag = "  <- reorder" if self.needs_reorder else ""
        return (f"{self.sku:<10} {self.name:<22} {self.category:<12} "
                f"{self._quantity:>5} {self.sale_price:>9.2f}{flag}")


class StockObserver(ABC):
    """Anything that wants to be told when a product runs low.

    New reactions (email the buyer, log to a file, create a purchase
    order...) are added as new observers without changing ``Inventory``
    (Open/Closed principle).
    """

    @abstractmethod
    def on_low_stock(self, product: Product) -> None:
        """Called after a stock change leaves ``product`` at or below its
        reorder level."""


class ConsoleAlert(StockObserver):
    """Prints a warning when stock runs low."""

    def on_low_stock(self, product: Product) -> None:
        print(f"  [ALERT] {product.name} is low: {product.quantity} left "
              f"(reorder level {product.reorder_level}).")


class ReorderList(StockObserver):
    """Collects SKUs that need reordering, without duplicates."""

    def __init__(self) -> None:
        self.skus: List[str] = []

    def on_low_stock(self, product: Product) -> None:
        if product.sku not in self.skus:
            self.skus.append(product.sku)


class Inventory:
    """The product catalogue, stock operations and reports.

    Responsibility (SRP): coordinate products, suppliers and the movement
    log. The clock is injected (Dependency Inversion) so timestamps can be
    controlled in demos and tests.
    """

    def __init__(self,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self._clock = clock
        self._products: Dict[str, Product] = {}
        self._suppliers: Dict[str, Supplier] = {}
        self._movements: List[StockMovement] = []
        self._observers: List[StockObserver] = []

    # ----- observers ------------------------------------------------------

    def subscribe(self, observer: StockObserver) -> None:
        if not isinstance(observer, StockObserver):
            raise ValidationError("Observer must be a StockObserver.")
        self._observers.append(observer)

    def _notify_if_low(self, product: Product) -> None:
        if product.needs_reorder:
            for observer in self._observers:
                observer.on_low_stock(product)

    # ----- suppliers ------------------------------------------------------

    def add_supplier(self, supplier_id: str, name: str,
                     email: str) -> Supplier:
        supplier = Supplier(supplier_id, name, email)
        if supplier.supplier_id in self._suppliers:
            raise DuplicateError(
                f"Supplier {supplier.supplier_id!r} already exists.")
        self._suppliers[supplier.supplier_id] = supplier
        return supplier

    def get_supplier(self, supplier_id: str) -> Supplier:
        try:
            return self._suppliers[str(supplier_id).upper()]
        except KeyError:
            raise NotFoundError(
                f"No supplier with ID {supplier_id!r}.") from None

    # ----- products -------------------------------------------------------

    def add_product(self, sku: str, name: str, category: str,
                    cost_price: Number, sale_price: Number,
                    reorder_level: int = 5,
                    supplier_id: Optional[str] = None) -> Product:
        """Add a new product with zero stock."""
        if supplier_id is not None:
            supplier_id = self.get_supplier(supplier_id).supplier_id
        product = Product(sku, name, category, cost_price, sale_price,
                          reorder_level, supplier_id)
        if product.sku in self._products:
            raise DuplicateError(f"SKU {product.sku!r} already exists.")
        self._products[product.sku] = product
        return product

    def get_product(self, sku: str) -> Product:
        try:
            return self._products[_validate_sku(sku)]
        except KeyError:
            raise NotFoundError(f"No product with SKU {sku!r}.") from None

    def update_price(self, sku: str, *, cost_price: Optional[Number] = None,
                     sale_price: Optional[Number] = None) -> Product:
        """Change a product's prices; sale price may not drop below cost."""
        product = self.get_product(sku)
        cost = (to_money(cost_price, "Cost price")
                if cost_price is not None else product.cost_price)
        sale = (to_money(sale_price, "Sale price")
                if sale_price is not None else product.sale_price)
        if sale < cost:
            raise ValidationError(
                f"Sale price ({sale}) is below cost price ({cost}).")
        product.cost_price, product.sale_price = cost, sale
        return product

    def remove_product(self, sku: str) -> Product:
        """Remove a product. Refused while units are still in stock."""
        product = self.get_product(sku)
        if product.quantity:
            raise ValidationError(f"Cannot remove {product.name!r}: "
                                  f"{product.quantity} unit(s) in stock.")
        del self._products[product.sku]
        return product

    def search(self, query: str) -> List[Product]:
        """Products whose name or category contains ``query``."""
        query = _require_text(query, "Search query").lower()
        return [p for p in self.list_products()
                if query in p.name.lower() or query in p.category.lower()]

    def list_products(self, category: Optional[str] = None) -> List[Product]:
        """All products sorted by SKU, optionally for one category."""
        products = sorted(self._products.values(), key=lambda p: p.sku)
        if category is None:
            return products
        wanted = _require_text(category, "Category").title()
        return [p for p in products if p.category == wanted]

    # ----- stock operations -----------------------------------------------

    def _record(self, product: Product, movement_type: MovementType,
                quantity: int, unit_price: Decimal,
                note: str) -> StockMovement:
        movement = StockMovement(product.sku, movement_type, quantity,
                                 unit_price, product.cost_price,
                                 self._clock(), note.strip())
        self._movements.append(movement)
        self._notify_if_low(product)
        return movement

    def receive_stock(self, sku: str, quantity: int,
                      note: str = "") -> StockMovement:
        """Add units bought from the supplier at cost price."""
        product = self.get_product(sku)
        product.increase(quantity)
        return self._record(product, MovementType.RECEIVED, quantity,
                            product.cost_price, note)

    def sell(self, sku: str, quantity: int, note: str = "") -> StockMovement:
        """Remove units sold to a customer at sale price."""
        product = self.get_product(sku)
        product.decrease(quantity)
        return self._record(product, MovementType.SOLD, -quantity,
                            product.sale_price, note)

    def return_from_customer(self, sku: str, quantity: int,
                             note: str = "") -> StockMovement:
        """Put units a customer returned back in stock."""
        product = self.get_product(sku)
        sold = -sum(m.quantity for m in self.history(sku)
                    if m.movement_type is MovementType.SOLD)
        returned = sum(m.quantity for m in self.history(sku)
                       if m.movement_type is MovementType.RETURNED)
        if quantity > sold - returned:
            raise ValidationError(
                f"Cannot return {quantity}: only {sold - returned} unit(s) "
                f"of {product.name!r} were sold and not yet returned.")
        product.increase(quantity)
        return self._record(product, MovementType.RETURNED, quantity,
                            product.sale_price, note)

    def adjust_stock(self, sku: str, counted: int,
                     reason: str) -> Optional[StockMovement]:
        """Set stock to a physical count; the difference is logged."""
        product = self.get_product(sku)
        counted = _validate_quantity(counted, "Counted quantity",
                                     allow_zero=True)
        reason = _require_text(reason, "Reason")
        difference = counted - product.quantity
        if difference == 0:
            return None
        if difference > 0:
            product.increase(difference)
        else:
            product.decrease(-difference)
        return self._record(product, MovementType.ADJUSTED, difference,
                            product.cost_price, reason)

    # ----- reports --------------------------------------------------------

    def history(self, sku: Optional[str] = None) -> List[StockMovement]:
        """Stock movements, oldest first, optionally for one product."""
        if sku is None:
            return list(self._movements)
        sku = self.get_product(sku).sku
        return [m for m in self._movements if m.sku == sku]

    def low_stock(self) -> List[Product]:
        """Products at or below their reorder level, emptiest first."""
        return sorted((p for p in self._products.values()
                       if p.needs_reorder),
                      key=lambda p: (p.quantity, p.sku))

    def best_sellers(self, n: int = 3) -> List[tuple]:
        """The ``n`` products with the most net units sold."""
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ValidationError("n must be a positive integer.")
        sold: Dict[str, int] = {}
        for m in self._movements:
            if m.movement_type in (MovementType.SOLD, MovementType.RETURNED):
                sold[m.sku] = sold.get(m.sku, 0) - m.quantity
        ranked = sorted(((sku, units) for sku, units in sold.items()
                         if units > 0 and sku in self._products),
                        key=lambda kv: (-kv[1], kv[0]))
        return [(self._products[sku], units) for sku, units in ranked[:n]]

    def get_statistics(self) -> Dict[str, object]:
        """Inventory-wide statistics as a dictionary."""
        products = self._products.values()
        zero = Decimal("0.00")

        def total(kind: MovementType) -> Decimal:
            return sum((m.value for m in self._movements
                        if m.movement_type is kind), zero)

        revenue = total(MovementType.SOLD) - total(MovementType.RETURNED)
        cost_of_sales = -sum((m.quantity * m.unit_cost
                              for m in self._movements
                              if m.movement_type in (MovementType.SOLD,
                                                     MovementType.RETURNED)),
                             zero)

        categories: Dict[str, int] = {}
        for p in products:
            categories[p.category] = categories.get(p.category, 0) + 1

        return {
            "products": len(self._products),
            "suppliers": len(self._suppliers),
            "units_in_stock": sum(p.quantity for p in products),
            "stock_value_at_cost": sum((p.stock_value for p in products),
                                       zero),
            "stock_value_at_sale": sum((p.quantity * p.sale_price
                                        for p in products), zero),
            "low_stock_products": len(self.low_stock()),
            "movements": len(self._movements),
            "revenue": revenue,
            "gross_profit": revenue - cost_of_sales,
            "products_per_category": dict(sorted(categories.items())),
        }

    def display_inventory(self) -> None:
        """Print every product as a formatted table."""
        if not self._products:
            print("The inventory is empty.")
            return
        print(f"{'SKU':<10} {'Name':<22} {'Category':<12} "
              f"{'Qty':>5} {'Price':>9}")
        print("-" * 62)
        for product in self.list_products():
            print(product)


# --------------------------------------------------------------------------
# Demonstration
# --------------------------------------------------------------------------

class _DemoClock:
    """A clock that moves 20 minutes per call, so the demo is repeatable."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def __call__(self) -> datetime:
        self._now += timedelta(minutes=20)
        return self._now


def _section(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def main() -> None:
    """Walk through every feature of the system."""
    inventory = Inventory(_DemoClock(datetime(2024, 10, 7, 9, 0)))
    reorder_list = ReorderList()
    inventory.subscribe(ConsoleAlert())
    inventory.subscribe(reorder_list)

    _section("1. Suppliers and products")
    inventory.add_supplier("SUP1", "Cairo Electronics", "sales@cairo-elec.com")
    inventory.add_supplier("SUP2", "Nile Office Supply", "orders@nile.com")
    catalogue = [
        ("ELEC-001", "Wireless Mouse", "electronics", 180, 299, 5, "SUP1"),
        ("ELEC-002", "Mechanical Keyboard", "electronics", 950, 1450, 3,
         "SUP1"),
        ("ELEC-003", "USB-C Hub", "electronics", 400, 650, 4, "SUP1"),
        ("OFF-001", "A4 Paper (500 sheets)", "office", 120, 175, 10, "SUP2"),
        ("OFF-002", "Ballpoint Pens (box)", "office", 45, 80, 8, "SUP2"),
    ]
    for sku, name, cat, cost, sale, reorder, supplier in catalogue:
        inventory.add_product(sku, name, cat, cost, sale, reorder, supplier)
    print(f"Added {len(inventory.list_products())} products "
          f"from 2 suppliers.")

    _section("2. Receiving stock")
    for sku, qty in [("ELEC-001", 25), ("ELEC-002", 8), ("ELEC-003", 12),
                     ("OFF-001", 40), ("OFF-002", 20)]:
        inventory.receive_stock(sku, qty, "Opening stock")
    inventory.display_inventory()

    _section("3. Sales (low-stock alerts fire automatically)")
    for sku, qty in [("ELEC-001", 6), ("ELEC-002", 5), ("OFF-001", 18),
                     ("OFF-002", 13), ("ELEC-001", 4), ("OFF-001", 4)]:
        inventory.sell(sku, qty)
    print(f"  Reorder list: {reorder_list.skus}")

    _section("4. Return, stock count and price change")
    inventory.return_from_customer("ELEC-002", 1, "Unopened box")
    inventory.adjust_stock("ELEC-003", 11, "One unit damaged")
    inventory.update_price("ELEC-001", sale_price=319)
    inventory.display_inventory()

    _section("5. Movement history for ELEC-002")
    for m in inventory.history("ELEC-002"):
        line = (f"  {m.timestamp:%Y-%m-%d %H:%M}  {m.movement_type.value:<9}"
                f" {m.quantity:>+4}  @ {m.unit_price:>8.2f}  {m.note}")
        print(line.rstrip())

    _section("6. Search, low stock and best sellers")
    print(f"  'office' -> "
          f"{[p.name for p in inventory.search('office')]}")
    print(f"  Low stock -> "
          f"{[(p.sku, p.quantity) for p in inventory.low_stock()]}")
    for product, units in inventory.best_sellers(3):
        print(f"  {units:>3} sold  {product.name} "
              f"(margin {product.margin_pct}%)")

    _section("7. Statistics")
    for key, value in inventory.get_statistics().items():
        print(f"  {key:<22}: {value}")

    _section("8. Error handling")
    bad_calls = [
        ("Sell too many", lambda: inventory.sell("ELEC-002", 50)),
        ("Bad SKU format",
         lambda: inventory.add_product("mouse1", "X", "Y", 1, 2)),
        ("Duplicate SKU",
         lambda: inventory.add_product("ELEC-001", "X", "Y", 1, 2)),
        ("Sale below cost",
         lambda: inventory.add_product("ELEC-009", "Cable", "Electronics",
                                       50, 30)),
        ("Negative quantity", lambda: inventory.receive_stock("OFF-001", -3)),
        ("Unknown product", lambda: inventory.sell("FOOD-001", 1)),
        ("Unknown supplier",
         lambda: inventory.add_product("OFF-009", "Stapler", "Office",
                                       60, 95, supplier_id="SUP9")),
        ("Remove in-stock item", lambda: inventory.remove_product("OFF-001")),
        ("Return unsold units",
         lambda: inventory.return_from_customer("ELEC-003", 2)),
    ]
    for label, call in bad_calls:
        try:
            call()
        except InventoryError as error:
            print(f"  {label:<21} -> {type(error).__name__}: {error}")


if __name__ == "__main__":
    main()
