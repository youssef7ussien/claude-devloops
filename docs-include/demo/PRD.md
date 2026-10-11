# Color Clicker

## Overview
A single web page whose background changes to a random color each time the user clicks
anywhere on it. The server picks the color and keeps the current one, so it survives a reload.

## Backend (HTTP API, JSON)
- `GET /api/state` returns `{"color": "<hex>"}`, where `<hex>` is `#RRGGBB` (upper case).
  A new server starts with `#FFFFFF`.
- `POST /api/changes` picks a random color, different from the current one, makes it the
  current color, and returns `{"color": "<hex>"}` with status 201.
- The state is kept in memory; a restart may reset it.

## Frontend
- On load, the page background is the color from `GET /api/state`.
- A click anywhere on the page sends `POST /api/changes`, and the background becomes the
  returned color.
- Reloading the page keeps the current color.
- The page title is `Color Clicker`.
- The page shows the current color's code, such as `#A3C2F0`, in large text at its center.
- The page shows a footer, fixed at the bottom, with the text "Built with devloops" linking to
  https://youssef7ussien.github.io/claude-devloops/ (it opens in a new tab).
- Clicking the footer link does not change the color.

## Out of scope
Users, logins, a database, and any styling or content this page does not describe.
