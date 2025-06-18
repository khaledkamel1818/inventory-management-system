# Inventory Management System

A clean, object-oriented inventory management system written in **pure
Python** (standard library only). It manages suppliers and products,
receives and sells stock, handles customer returns and stock counts, keeps
a full audit log of every stock movement, raises low-stock alerts through
the Observer pattern, and reports stock value, revenue, gross profit and
best sellers, with input validation and clear error handling throughout.

## Features

- **Products**: SKU (format `ABC-123`), name, category, cost and sale price,
  reorder level and supplier.
- **Suppliers**: unique IDs with validated emails.
- **Stock operations**: receive, sell, customer returns and stock-count
  adjustments; stock can never go negative.
- **Audit log**: every change is an immutable `StockMovement` with a type,
  quantity, price, cost and timestamp.
- **Low-stock alerts**: observers are notified when a product reaches its
  reorder level (console alert and reorder list included).
- **Exact money**: prices use `decimal.Decimal`; sale price may never be
  below cost price.
- **Reports**: search, low-stock list, best sellers with margins, stock
  value at cost and sale price, revenue and gross profit.
- **Validation and errors**: a custom exception hierarchy for invalid data,
  duplicates, unknown records and insufficient stock.
- **Zero dependencies**: runs anywhere Python 3.8+ is installed.

## Project structure

```
inventory_management/
├── inventory.py       # Classes and a runnable demonstration
├── README.md          # This file
└── requirements.txt   # No external dependencies
```

## Installation

```bash
git clone https://github.com/khaledkamel1818/inventory-management-system.git
cd inventory-management-system/inventory_management
python inventory.py
```

No `pip install` is needed.

## Usage

```python
from inventory import ConsoleAlert, Inventory, InventoryError

inventory = Inventory()
inventory.subscribe(ConsoleAlert())        # print a warning on low stock

inventory.add_supplier("SUP1", "Cairo Electronics", "sales@cairo-elec.com")
inventory.add_product("ELEC-001", "Wireless Mouse", "Electronics",
                      cost_price=180, sale_price=299, reorder_level=5,
                      supplier_id="SUP1")

# Stock operations
inventory.receive_stock("ELEC-001", 25, "Opening stock")
inventory.sell("ELEC-001", 21)             # [ALERT] Wireless Mouse is low
inventory.return_from_customer("ELEC-001", 1)
inventory.adjust_stock("ELEC-001", 4, "One unit damaged")
inventory.update_price("ELEC-001", sale_price=319)

# Reports
print(inventory.get_product("ELEC-001").quantity)   # 4
print(inventory.history("ELEC-001"))
print(inventory.low_stock())
print(inventory.best_sellers(3))
print(inventory.get_statistics())
inventory.display_inventory()

# Errors are explicit and catchable
try:
    inventory.sell("ELEC-001", 50)
except InventoryError as error:
    print(error)   # Only 4 unit(s) of 'Wireless Mouse' in stock, ...
```

Custom reactions to low stock are added by subclassing `StockObserver`:

```python
from inventory import StockObserver

class EmailBuyer(StockObserver):
    def on_low_stock(self, product):
        print(f"Emailing buyer: please reorder {product.sku}")

inventory.subscribe(EmailBuyer())
```

## Classes and methods

### `Supplier`

| Member | Description |
|---|---|
| `Supplier(supplier_id, name, email)` | A validated supplier. |

### `Product`

| Member | Description |
|---|---|
| `Product(sku, name, category, cost_price, sale_price, reorder_level=5, supplier_id=None)` | A validated product with zero stock. |
| `quantity` | Units in stock (read-only). |
| `needs_reorder` | `True` at or below the reorder level. |
| `margin_pct` | Profit margin as a percentage of the sale price. |
| `stock_value` | Units in stock times cost price. |
| `increase(n)`, `decrease(n)` | The only ways stock can change. |

### `StockMovement` (immutable)

| Member | Description |
|---|---|
| `sku`, `movement_type`, `quantity`, `unit_price`, `unit_cost`, `timestamp`, `note` | One audit-log entry; positive quantity is stock in. |
| `value` | Units times price. |

### `StockObserver`, `ConsoleAlert`, `ReorderList`

| Member | Description |
|---|---|
| `StockObserver.on_low_stock(product)` | Abstract method every observer implements. |
| `ConsoleAlert` | Prints a warning. |
| `ReorderList.skus` | Collects SKUs that need reordering. |

### `Inventory`

| Method | Description |
|---|---|
| `subscribe(observer)` | Registers a low-stock observer. |
| `add_supplier(...)` / `get_supplier(id)` | Manage suppliers. |
| `add_product(...)` | Adds a product; rejects duplicate SKUs and unknown suppliers. |
| `get_product(sku)` / `remove_product(sku)` | Look up or remove a product (only when out of stock). |
| `update_price(sku, cost_price=None, sale_price=None)` | Changes prices. |
| `search(query)` | Products whose name or category contains `query`. |
| `list_products(category=None)` | All products, optionally for one category. |
| `receive_stock(sku, quantity, note="")` | Stock in from a supplier. |
| `sell(sku, quantity, note="")` | Stock out to a customer. |
| `return_from_customer(sku, quantity, note="")` | Puts sold units back in stock. |
| `adjust_stock(sku, counted, reason)` | Sets stock to a physical count. |
| `history(sku=None)` | Stock movements, oldest first. |
| `low_stock()` | Products at or below their reorder level. |
| `best_sellers(n=3)` | Products with the most net units sold. |
| `get_statistics()` | A dictionary of inventory-wide statistics. |
| `display_inventory()` | Prints a formatted table. |

### Exceptions

```
InventoryError
├── ValidationError          # bad SKU, price, quantity, email or argument
├── NotFoundError            # unknown product or supplier
├── DuplicateError           # SKU or supplier ID already used
└── InsufficientStockError   # removing more units than are in stock
```

## OOP concepts used

- **Encapsulation**: a product's stock level is private and only changes
  through `increase` and `decrease`, which refuse invalid quantities and
  negative stock.
- **Abstraction**: `StockObserver` is an abstract base class; `Inventory`
  only knows the interface, never the concrete observers.
- **Polymorphism**: `ConsoleAlert` and `ReorderList` react to the same
  `on_low_stock` call in different ways.
- **Inheritance**: observers derive from `StockObserver`; exceptions derive
  from `InventoryError`.
- **Immutability**: `StockMovement` is a frozen dataclass, so the audit log
  cannot be altered.
- **Enumerations**: `MovementType` names every kind of stock change.
- **Composition**: an `Inventory` *has* products, suppliers, movements and
  observers.

### Design pattern

- **Observer**: `Inventory` notifies every subscribed `StockObserver` when
  stock runs low, so new reactions plug in without changing the inventory.

### SOLID principles

- **Single Responsibility**: `Product` guards its stock, `StockMovement`
  records one change, observers react to alerts, `Inventory` coordinates.
- **Open/Closed**: new low-stock reactions are new `StockObserver`
  subclasses; `Inventory` is not modified.
- **Liskov Substitution**: any `StockObserver` subclass can be subscribed,
  and each exception works wherever its base class is expected.
- **Interface Segregation**: `StockObserver` has exactly one method.
- **Dependency Inversion**: `Inventory` depends on the `StockObserver`
  abstraction and on an injected `clock`, not on concrete classes or
  `datetime.now()`.

## Expected output

Running `python inventory.py` prints:

```
==============================================================
1. Suppliers and products
==============================================================
Added 5 products from 2 suppliers.

==============================================================
2. Receiving stock
==============================================================
SKU        Name                   Category       Qty     Price
--------------------------------------------------------------
ELEC-001   Wireless Mouse         Electronics     25    299.00
ELEC-002   Mechanical Keyboard    Electronics      8   1450.00
ELEC-003   USB-C Hub              Electronics     12    650.00
OFF-001    A4 Paper (500 sheets)  Office          40    175.00
OFF-002    Ballpoint Pens (box)   Office          20     80.00

==============================================================
3. Sales (low-stock alerts fire automatically)
==============================================================
  [ALERT] Mechanical Keyboard is low: 3 left (reorder level 3).
  [ALERT] Ballpoint Pens (box) is low: 7 left (reorder level 8).
  Reorder list: ['ELEC-002', 'OFF-002']

==============================================================
4. Return, stock count and price change
==============================================================
SKU        Name                   Category       Qty     Price
--------------------------------------------------------------
ELEC-001   Wireless Mouse         Electronics     15    319.00
ELEC-002   Mechanical Keyboard    Electronics      4   1450.00
ELEC-003   USB-C Hub              Electronics     11    650.00
OFF-001    A4 Paper (500 sheets)  Office          18    175.00
OFF-002    Ballpoint Pens (box)   Office           7     80.00  <- reorder

==============================================================
5. Movement history for ELEC-002
==============================================================
  2024-10-07 09:40  received    +8  @   950.00  Opening stock
  2024-10-07 11:20  sold        -5  @  1450.00
  2024-10-07 13:00  returned    +1  @  1450.00  Unopened box

==============================================================
6. Search, low stock and best sellers
==============================================================
  'office' -> ['A4 Paper (500 sheets)', 'Ballpoint Pens (box)']
  Low stock -> [('OFF-002', 7)]
   22 sold  A4 Paper (500 sheets) (margin 31.4%)
   13 sold  Ballpoint Pens (box) (margin 43.8%)
   10 sold  Wireless Mouse (margin 43.6%)

==============================================================
7. Statistics
==============================================================
  products              : 5
  suppliers             : 2
  units_in_stock        : 55
  stock_value_at_cost   : 13375.00
  stock_value_at_sale   : 21445.00
  low_stock_products    : 1
  movements             : 13
  revenue               : 13680.00
  gross_profit          : 4855.00
  products_per_category : {'Electronics': 3, 'Office': 2}

==============================================================
8. Error handling
==============================================================
  Sell too many         -> InsufficientStockError: Only 4 unit(s) of 'Mechanical Keyboard' in stock, cannot remove 50.
  Bad SKU format        -> ValidationError: SKU must look like 'ABC-123', got 'MOUSE1'.
  Duplicate SKU         -> DuplicateError: SKU 'ELEC-001' already exists.
  Sale below cost       -> ValidationError: Sale price (30.00) is below cost price (50.00) for 'Cable'.
  Negative quantity     -> ValidationError: Quantity must be at least 1.
  Unknown product       -> NotFoundError: No product with SKU 'FOOD-001'.
  Unknown supplier      -> NotFoundError: No supplier with ID 'SUP9'.
  Remove in-stock item  -> ValidationError: Cannot remove 'A4 Paper (500 sheets)': 18 unit(s) in stock.
  Return unsold units   -> ValidationError: Cannot return 2: only 0 unit(s) of 'USB-C Hub' were sold and not yet returned.
```

## Author

**Khaled Kamel** · [GitHub](https://github.com/khaledkamel1818)
