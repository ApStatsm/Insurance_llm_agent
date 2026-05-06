# Step 0 State Transition Table

## Node ownership (write permissions)

| Node | Writable fields |
|---|---|
| `DB_LOOKUP` | `customer_db_info`, `status`, `audit_log`, `error`, `updated_at` |
| `ROUTER` | `next_route`, `status`, `audit_log`, `error`, `updated_at` |
| `POLICY_DIAGNOSIS_WORKER` | `draft_response`, `citations`, `status`, `audit_log`, `error`, `updated_at` |
| `PRECEDENT_DISPUTE_WORKER` | `draft_response`, `citations`, `status`, `audit_log`, `error`, `updated_at` |
| `DOCUMENT_CLAIM_WORKER` | `draft_response`, `citations`, `status`, `audit_log`, `error`, `updated_at` |
| `CS_COMPLAINT_WORKER` | `draft_response`, `citations`, `status`, `audit_log`, `error`, `updated_at` |
| `MANAGER` | `final_response`, `review_notes`, `retry_count`, `status`, `audit_log`, `error`, `updated_at` |

## Entry gates

| Node | Allowed state status | Required state fields | Route constraint |
|---|---|---|---|
| `DB_LOOKUP` | `INIT` | `user_id`, `user_query` | - |
| `ROUTER` | `DB_ENRICHED` | `customer_db_info` | - |
| `POLICY_DIAGNOSIS_WORKER` | `ROUTED` | `next_route` | `next_route=policy_diagnosis` |
| `PRECEDENT_DISPUTE_WORKER` | `ROUTED` | `next_route` | `next_route=precedent_dispute` |
| `DOCUMENT_CLAIM_WORKER` | `ROUTED` | `next_route` | `next_route=document_claim` |
| `CS_COMPLAINT_WORKER` | `ROUTED` | `next_route` | `next_route=cs_complaint` |
| `MANAGER` | `WORKER_DRAFTED` or `MANAGER_REVIEW` | `draft_response` | - |

## Status transitions

| Current status | Allowed next status |
|---|---|
| `INIT` | `DB_ENRICHED`, `ERROR` |
| `DB_ENRICHED` | `ROUTED`, `ERROR` |
| `ROUTED` | `WORKER_DRAFTED`, `ERROR` |
| `WORKER_DRAFTED` | `MANAGER_REVIEW`, `ROUTED`, `FINALIZED`, `ERROR` |
| `MANAGER_REVIEW` | `ROUTED`, `FINALIZED`, `ERROR` |
| `FINALIZED` | (terminal) |
| `ERROR` | (terminal) |

