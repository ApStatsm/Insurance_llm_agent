# Multi-Agent Pipeline (Internal DB mode)

## Current data sources

- Policy diagnosis: local vector DB (`data/vectorstore/insurance_chroma_db`)
- Precedent/dispute: internal case DB (`data/knowledge/precedent_cases.json`)
- Document/claim rules: product-based internal rule DB (`data/knowledge/product_required_docs.json`)
- Customer metadata: internal CSV (`data/customer_db/customers.csv`)

## Flow

1. Step0: state schema + validator
2. Step1: DB lookup (`user_id -> customer_db_info`)
3. Step2: router (`user_query -> next_route`)
4. Step3: worker execution by route
5. Step4: manager compliance check and finalization

## Note

- Manager phrase policy currently uses default baseline messages.
- External court/FSS APIs are not wired yet; this build is fully internal-DB mode.

