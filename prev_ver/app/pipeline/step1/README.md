# Step 1 DB Lookup Node

## Purpose

Use `user_id` to load customer metadata from CSV and update `customer_db_info`.

## API

```python
from app.pipeline.step0 import create_initial_state
from app.pipeline.step1 import run_db_lookup

state = create_initial_state(
    user_id="CUST-1029",
    user_query="도수치료 청구 가능한가요?",
)

next_state = run_db_lookup(state)
```

## Default CSV path

`data/customer_db/customers.csv`

## Input CSV headers

- English: `user_id`, `join_year`, `product_name`, `policy_number`, `coverage_limits`, `special_clauses`
- Korean aliases: `고객ID`, `가입연도`, `상품명`, `증권번호`, `담보한도`, `특약`

## Parsing notes

- `coverage_limits`: separators `|`, `;`, `,` supported
- `coverage_limits` entry format: `담보명:금액` or `담보명=금액`
- `special_clauses`: separators `|`, `;`, `,` supported

