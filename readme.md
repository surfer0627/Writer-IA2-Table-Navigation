# Writer IA2 Table Navigation

Writer IA2 Table Navigation is an experimental NVDA add-on for navigating and reading tables in LibreOffice Writer on Windows through IAccessible2 (IA2).

This project explores a possible approach for [nvaccess/nvda#4133](https://github.com/nvaccess/nvda/issues/4133). It is not an official NVDA build or a final fix in NVDA core.

## Requirements

* Windows
* NVDA 2025.3 or later
* LibreOffice Writer 25.8.0.1 or later.

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

The prototype currently follows this route:

1. Find the current Writer table cell from the focused object.
2. Use `IAccessibleTableCell` and `IAccessibleTable2` to get the cell position, span, and table size.
3. Calculate the target row and column.
4. Find an NVDA table-cell object that covers the target coordinate. The add-on first tries `IAccessibleTable2.cellAt(row, column)`, then uses the cached coordinate map or descendant scanning if needed.
5. Move focus to the target `SymphonyIATableCell`.
6. Use Writer's focused text object for speech and the focused Symphony paragraph for braille.

The `SymphonyIATableCell` is mainly used for table structure and navigation. Cell text is taken from Writer's focused text object instead.

## Known limitations

Known limitations include:


* LibreOffice Writer only.
* Windows only.
* OpenOffice has not been tested yet.
* Browse mode table quick navigation is not supported.
* Merged cells are supported, but more testing is still needed.

### Table Say All integration

In applications where NVDA can navigate directly between table-cell TextInfos,
native Table Say All can consume each cell's TextInfo directly. In Writer,
however, the table structure is exposed through IA2 table-cell objects, while
the cell text is usually exposed through one or more Symphony paragraph
TextInfos.

The add-on therefore builds its own row or column sequence, creates a fresh
TextInfo for each cell from the cell object or its paragraph children, injects
the required table control fields, and supplies a custom next-cell function to
NVDA's native Say All engine using `CURSOR.TABLE`.

This additional layer connects Writer's IA2 table structure with its text
content. If Writer provides a direct and reliable TextInfo for each table cell
in the future, the custom wrappers, fallback handling, and traversal code could
be simplified.

## Testing

When reporting a problem, include:

* NVDA version.
* LibreOffice version.
* Windows version.
* The command used and the expected cell or text.
* Whether speech, braille, focus, and the system caret reached the expected location.
* Whether the table contains empty, merged, spanned, or multi-paragraph cells.

Useful test documents include simple tables, empty cells, horizontal and vertical merges, mixed row and column spans, and cells containing multiple paragraphs.

## Building

This project is based on the NVDA add-on template.

After installing the required build dependencies, build the add-on from the repository root with:

	scons

The generated `.nvda-addon` file can then be installed in NVDA for testing.
