# W04 Evidence: Inspector Reopen

Date: 2026-09-29
Environment: local Runtime HTTP service, Inspector Vite dev server,
Chromium browser

## Procedure

1. Started the Runtime service against the real completed coding-delivery
   SQLite database.
2. Opened Inspector at `http://127.0.0.1:4173`.
3. Connected to:
   - Runtime: `http://127.0.0.1:8787`
   - namespace: `local`
   - run: `run_c29c8c04b37a41268b1002b2f0f69111`
4. Verified the live projection showed:
   - workflow ID `delivery`
   - Run status `已完成`
   - event sequence `40`
   - Runtime artifact `codex-producer.md`
5. Reloaded the same browser tab.

## Result

After reload, Inspector automatically reconnected from the current browser
session and rebuilt the Runtime projection. It still showed:

- `delivery`
- `run_c29c8c04b37a41268b1002b2f0f69111`
- `已完成`
- event sequence `40`
- the registered Codex artifact

The page did not fall back to demo data.

## Implementation Boundary

Runtime connection fields are kept in `sessionStorage` for the current browser
session only. They are not written to the URL or persistent `localStorage`.
Importing a local snapshot clears the Runtime session connection.

This is local Inspector reopen evidence. It does not claim multi-user
authentication or a production browser credential store.
