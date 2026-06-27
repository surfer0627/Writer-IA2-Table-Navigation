# Writer IA2 Table Navigation

Writer IA2 Table Navigation is an experimental NVDA add-on proof of concept for IA2-based table cell navigation in LibreOffice Writer on Windows.

This project is intended to help test a possible approach for [nvaccess/nvda#4133](https://github.com/nvaccess/nvda/issues/4133).

This is not an official NVDA build and not a final fix.


## Commands

When the cursor is inside a LibreOffice Writer table, the add-on provides these commands:

| Command | Action |
| --- | --- |
| control+alt+leftArrow | Move to the previous table cell in the row |
| control+alt+rightArrow | Move to the next table cell in the row |
| control+alt+upArrow | Move to the previous table cell in the column |
| control+alt+downArrow | Move to the next table cell in the column |



## Technical approach

The prototype currently follows this route:

1. Resolve the current LibreOffice Writer table cell from the focused Symphony paragraph.
2. Use IAccessibleTableCell and IAccessibleTable2 to get the current row and column.
3. Use IAccessibleTable2.cellAt(row, column) to resolve the target cell.
4. Move focus to the target SymphonyIATableCell.
5. Let LibreOffice and NVDA naturally move focus into the cell's Symphony paragraph.
6. Use the naturally focused paragraph for speech and braille.

The add-on avoids speaking the SymphonyIATableCell object directly. The cell object is used for table coordinates and movement, while the focused paragraph is used for text content.

### Current findings

Early testing suggests that:

* SymphonyIATableCell can provide table cell coordinates.
* IAccessibleTable2.cellAt(row, column) can resolve target cells.
* After focusing a target table cell, LibreOffice and NVDA naturally move focus into the cell's Symphony paragraph.
* The Symphony paragraph provides the cell text through SymphonyTextInfo.
* Braille follows the naturally focused paragraph.
* Directly speaking or braille-routing the SymphonyIATableCell object can produce incorrect or duplicated output, so the prototype avoids that route.

### Known limitations

Known limitations include:

* LibreOffice Writer only.
* Windows only.
* OpenOffice is not yet tested.
* Empty cells may need fallback handling.
* Merged cells are not fully validated.
* This add-on does not implement browse mode quick navigation.
* This add-on does not implement table say-all commands.

## Testing

Useful testing information includes:

* NVDA version.
* LibreOffice or OpenOffice version.
* Windows version.
* Whether speech reports the expected cell content.
* Whether braille follows the expected cell content.
* Whether moving left, right, up, and down works.
* Whether edge-of-table reporting works.
* Whether the command correctly reports when it is not inside a table cell.
* Whether empty cells or merged cells behave incorrectly.

Useful test documents include:

* A simple table without merged cells.
* A table with empty cells.
* A table with horizontally merged cells.
* A table with vertically merged cells.
* A table with both row and column spans.
* A table containing multiple paragraphs in a cell.

## Building

This project is based on the NVDA add-on template.

After installing the required build dependencies, build the add-on from the repository root with:

```cmd
scons
```

The generated `.nvda-addon` file can then be installed in NVDA for testing.

## License

This project is licensed under the GNU General Public License v2.0 or later.
