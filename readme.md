# Writer IA2 Table Navigation

Writer IA2 Table Navigation is an experimental NVDA add-on for navigating and reading tables in LibreOffice Writer on Windows through IAccessible2 (IA2).

This project explores a possible approach for [nvaccess/nvda#4133](https://github.com/nvaccess/nvda/issues/4133). It is not an official NVDA build or a final fix in NVDA core.

## Requirements

- Windows
- NVDA 2025.3 or later
- LibreOffice Writer

The add-on metadata currently declares NVDA 2026.1 as the latest tested version.

## Commands

The following commands are available when the cursor is inside a LibreOffice Writer table:

| Command | Action |
| --- | --- |
| `control+alt+leftArrow` | Move to the previous column |
| `control+alt+rightArrow` | Move to the next column |
| `control+alt+upArrow` | Move to the previous row |
| `control+alt+downArrow` | Move to the next row |
| `control+alt+pageUp` | Move to the first row |
| `control+alt+pageDown` | Move to the last row |
| `control+alt+home` | Move to the first column |
| `control+alt+end` | Move to the last column |
| `NVDA+control+alt+downArrow` | Read from the current cell to the end of the row with Say All |
| `NVDA+control+alt+rightArrow` | Read from the current cell to the end of the column with Say All |
| `NVDA+control+alt+leftArrow` | Read the complete current row without moving the system caret |
| `NVDA+control+alt+upArrow` | Read the complete current column without moving the system caret |
| `control+alt+r` | Alias for row Say All |
| `control+alt+c` | Alias for column Say All |

## Technical approach

The add-on separates Writer table support into focused layers:

1. Resolve the focused Writer table, cell coordinates, spans, and IA2 table interfaces.
2. Cache direct coordinate-to-cell mappings and account for merged cells when resolving movement targets.
3. Move focus to the target `SymphonyIATableCell` and use the naturally focused Writer text object for speech and braille.
4. Build reusable row and column content sequences for direct reading and Say All.
5. Adapt table and cell properties to NVDA TextInfo control fields.
6. Apply a Writer-specific collapsed-chunk workaround so braille can retain table field information.

The TextInfo field injection manager is available but disabled by default. The collapsed braille workaround is enabled only through the LibreOffice AppModule and restores the original NVDA methods when the AppModule terminates.

## Known limitations

- LibreOffice Writer and Windows only.
- OpenOffice has not been tested.
- Empty, merged, vertically spanned, and multi-paragraph cells have dedicated handling but still need broad document testing.
- Browse mode table quick navigation is not implemented.
- The add-on depends on internal NVDA and LibreOffice accessibility behavior and may require updates when either project changes.
- This remains an experimental development-channel add-on.

## Testing

When reporting a problem, include:

- NVDA version.
- LibreOffice version.
- Windows version.
- The command used and the expected cell or text.
- Whether speech, braille, focus, and the system caret reached the expected location.
- Whether the table contains empty, merged, spanned, or multi-paragraph cells.

Useful test documents include simple tables, empty cells, horizontal and vertical merges, mixed row and column spans, and cells containing multiple paragraphs.

## Building

Install the locked development dependencies and build from the repository root:

```cmd
uv sync
uv run scons
```

The generated `writerIa2TableNavigation-0.2.0.nvda-addon` file can then be installed in NVDA for testing.
