# Dispatcher-First Agent Routing

## Summary

- added a new `dispatcher` agent role as the only user-entry routing agent
- removed the `data_scientist` role from the internal agent roster
- changed Discord-triggered dispatch requests to enter the dispatcher first
- kept explicit specialist-to-specialist handoffs, while blocking handoffs back to the dispatcher

## Behavior

- market-analysis requests now route to the market analyst
- ambiguous requests now default to the product manager
- clearly irrelevant requests are rejected directly with a product-scope explanation

## Validation

- added focused registry and orchestration tests for dispatcher routing, rejection, and invalid handoff protection
