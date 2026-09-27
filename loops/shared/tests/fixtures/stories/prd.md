# Product requirements: item catalogue

A small service that keeps a list of items. This file is a generic test fixture for single-story
runs; it describes no real application.

## Rules

- Every item has a non-empty `name` of at most 80 characters.
- Items are returned in the order they were created.

## Stories

### US-1: List items

As a client, I can list every item.

- Acceptance: listing returns all items, in creation order.

### US-2: Create an item

As a client, I can create an item with a name.

- Acceptance: creating an item with a valid name returns it with a new ID.
- Acceptance: creating an item with an empty name is rejected.
