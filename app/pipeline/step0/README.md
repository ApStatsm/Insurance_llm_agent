# Step 0 Quickstart

## What is included

- `agent_state.py`: initial state factory (`create_initial_state`)
- `agent_state.schema.json`: JSON Schema contract
- `state_rules.py`: node ownership and transition rules
- `validator.py`: shape validation, node entry gate checks, update permission checks
- `error_codes.py`: standard error code constants
- `state_transition_table.md`: human-readable rule table

## Minimal usage

```python
from app.pipeline.step0 import (
    create_initial_state,
    validate_node_entry,
    validate_node_update,
)

state = create_initial_state(
    user_id="CUST-1029",
    user_query="도수치료 청구 가능한가요?",
    user_docs=[{"doc_id": "DOC-1", "doc_type": "receipt", "storage_uri": "s3://bucket/doc-1"}],
)

validate_node_entry("DB_LOOKUP", state)

patch = {
    "customer_db_info": {
        "join_year": 2020,
        "product_name": "실손보험A",
        "policy_number": "P-001",
    },
    "status": "DB_ENRICHED",
}
validate_node_update("DB_LOOKUP", state, patch)
```

