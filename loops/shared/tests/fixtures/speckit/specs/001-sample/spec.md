# Feature Specification: Notes

## User Scenarios & Testing

### User Story 1 - List notes (Priority: P1)

A reader sees every saved note.

**Acceptance Scenarios**:

1. **Given** two saved notes, **When** the reader lists notes, **Then** both are returned.

### User Story 2 - Add a note (Priority: P2)

A writer adds a note with a text.

**Acceptance Scenarios**:

1. **Given** no notes, **When** the writer adds "hello", **Then** listing notes returns "hello".
2. **Given** an empty text, **When** the writer adds it, **Then** it is refused.
