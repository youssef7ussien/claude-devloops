# Contract: dashboard export

Replaces specs/002-devloops-init/contracts/full-dashboard.md (its Name and location, Content,
Safety, and Output report sections). Written by `devloops dashboard --export [<path>]`
(`dashboard_export.py`).

## Name and location

```text
<workspace>/exports/<YYYYMMDDTHHMMSSZ>.html      # UTC time of the export
<workspace>/exports/<YYYYMMDDTHHMMSSZ>-2.html    # same-second collision (-3, …)
<path>                                           # when given: written, replacing a file there
```

Written to a temp file beside the target and moved into place, so a failed write leaves what was
there; without a path, the name is taken exclusively, so an export never replaces an earlier one.
The target folder is checked before the page is built. The
workspace folder is git-ignored, so exports are too.

## Structure

```html
<!doctype html>
<html data-source="embedded" data-workspace="…" data-exported-at="…" data-devloops-version="…"
      data-running="true|false">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline';
        style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
  <style>/* assets/app/app.css */</style>
</head>
<body>
  <!-- the app shell, as served -->
  <script type="application/json" id="d:summary">{…}</script>
  <script type="application/json" id="d:loops/backend-dev">{…}</script>
  <!-- one element per API response: every view, trial, call, file, index, and the search corpus -->
  <script>/* the joined app script, without vendor/ (no syntax highlighting, FR-033) */</script>
</body>
</html>
```

- Keys are the API paths without the `/w/<ws>/api/` prefix (e.g. `d:calls/backend-dev/12`,
  `d:files/f-backend-dev-progress-md`), plus `d:search-corpus`.
- Inside each element, `<` is written `\u003c` (JSON reads it the same), so no `</script` or
  `<!--` in a file or a conversation can end or change the element. A text file is
  `{kind, lang, size, text}` (the text as the server sends it); images and other binary files are
  `{kind, size, type, base64}`; files over 5 MB are `{not_embedded: true, size, path}`.
- The workspace's `exports/` folder, any other export inside the workspace (known by its root
  element), and a summary page (`dashboard.html`) left by an earlier devloops are never listed
  (nor part of the workspace version), so an export holds no earlier export.
- Every value has passed through the workspace's redactor (SC-008). Conversations are embedded
  whole.
- The app reads an element only when that data is first asked for; nothing is fetched and nothing
  polls. The top bar shows "Snapshot · <exported-at> · devloops <version>", "run in progress" when
  `data-running` is true, and the notice "Contains full Claude Code conversations — review before
  sharing".
- `d:search-corpus` is `{items: [{kind, id, label, route, text}]}`, the server's searchable texts;
  a file's item has `file: <id>` instead of `text`, which is read from that file's element.
- Search runs in the page over `d:index` and `d:search-corpus`, with the server's rules (contracts/
  api.md).
- Nothing outside the file is referenced: no `src`/`href` to another file or the network, except
  the project's GitHub link, which only navigates when clicked (SC-007).

## Output report

Path and size in bytes; the five largest embedded items (path, bytes); the number of
conversations marked unavailable; the files not embedded (path, bytes).
