from dataclasses import dataclass

import api
import ui
import controlTypes


@dataclass
class WriterTableContext:
	"""Resolved Writer table context for one NVDA object."""

	inTable: bool = False
	cellObj: object | None = None
	tableObj: object | None = None
	tableUID: object | None = None
	rowNumber: int | None = None
	columnNumber: int | None = None
	rowCount: int | None = None
	columnCount: int | None = None
	source: str = ""
	sizeSource: str = ""
	countsKnown: bool = False


class WriterTableContextResolver:
	"""Resolve LibreOffice Writer table context from NVDA objects.

	This resolver keeps table detection independent from appModules/soffice.py.
	App module scripts, probes, WriterDocumentWalker, and future table quick-nav
	items can all reuse the same table context shape.
	"""

	def _safeGet(self, obj: object | None, name: str, default: object = None) -> object:
		"""Return an attribute value without raising."""
		if obj is None:
			return default

		try:
			return getattr(obj, name)
		except Exception:
			return default

	def _safeCall(self, fn: object, *args: object, **kwargs: object) -> tuple[bool, object]:
		"""Call a function without raising."""
		try:
			if not callable(fn):
				return False, None
			return True, fn(*args, **kwargs)
		except Exception as e:
			return False, e

	def _materializeMaybeCallable(self, value: object) -> object:
		"""Return a callable attribute value when needed."""
		if callable(value):
			ok, result = self._safeCall(value)
			if ok:
				return result
			return None

		return value

	def _safeGetMaterialized(self, obj: object | None, *names: str) -> object:
		"""Return the first available materialized attribute value."""
		for name in names:
			value = self._safeGet(obj, name, None)
			value = self._materializeMaybeCallable(value)
			if value is not None:
				return value

		return None

	def _className(self, obj: object | None) -> str:
		"""Return a stable class name."""
		if obj is None:
			return "None"

		try:
			return obj.__class__.__name__
		except Exception:
			return "<class error>"

	def _coerceInt(self, value: object) -> int | None:
		"""Return an int value, or None."""
		try:
			return int(value)
		except Exception:
			return None

	def findCellAndTable(self, obj: object | None) -> tuple[object | None, object | None, str]:
		"""Find the nearest Writer table cell and table from an object."""
		cell = None
		table = None
		sourceParts: list[str] = []

		cur = obj
		depth = 0

		while cur is not None and depth < 16:
			className = self._className(cur)

			if cell is None and "TableCell" in className:
				cell = cur
				sourceParts.append(f"cell=parent[{depth}]")

			if table is None and "Table" in className and "TableCell" not in className:
				table = cur
				sourceParts.append(f"table=parent[{depth}]")

			try:
				cur = getattr(cur, "parent", None)
			except Exception:
				cur = None

			depth += 1

		if cell is not None and table is None:
			cellTable = self._safeGet(cell, "table", None)
			if cellTable is not None:
				table = cellTable
				sourceParts.append("table=cell.table")

		if table is None:
			cur = obj
			depth = 0

			while cur is not None and depth < 16:
				ia2Table = self._safeGet(cur, "IAccessibleTable2Object", None)
				if ia2Table is not None:
					table = cur
					sourceParts.append(f"table=IAccessibleTable2Object[{depth}]")
					break

				try:
					cur = getattr(cur, "parent", None)
				except Exception:
					cur = None

				depth += 1

		return cell, table, ",".join(sourceParts)

	def getRowColumn(self, cellObj: object | None) -> tuple[int | None, int | None]:
		"""Return row and column numbers from a Writer table cell."""
		rowNumber = self._coerceInt(
			self._safeGet(cellObj, "rowNumber", None)
		)
		columnNumber = self._coerceInt(
			self._safeGet(cellObj, "columnNumber", None)
		)

		return rowNumber, columnNumber

	def getTableSize(self, tableObj: object | None, cellObj: object | None = None) -> tuple[int | None, int | None, str, bool]:
		"""Return table row count, column count, source, and confidence."""
		sourceParts: list[str] = []

		rowCount = self._coerceInt(
			self._safeGet(tableObj, "rowCount", None)
		)
		columnCount = self._coerceInt(
			self._safeGet(tableObj, "columnCount", None)
		)

		rowCountKnown = rowCount is not None
		columnCountKnown = columnCount is not None

		if rowCount is not None:
			sourceParts.append("nvda.rowCount")

		if columnCount is not None:
			sourceParts.append("nvda.columnCount")

		if tableObj is not None and (rowCount is None or columnCount is None):
			ia2Table = self._safeGet(tableObj, "IAccessibleTable2Object", None)

			if ia2Table is not None:
				if rowCount is None:
					for name in ("nRows", "rowCount"):
						rowCount = self._coerceInt(
							self._safeGet(ia2Table, name, None)
						)
						if rowCount is not None:
							rowCountKnown = True
							sourceParts.append(f"ia2.{name}")
							break

				if columnCount is None:
					for name in ("nColumns", "columnCount"):
						columnCount = self._coerceInt(
							self._safeGet(ia2Table, name, None)
						)
						if columnCount is not None:
							columnCountKnown = True
							sourceParts.append(f"ia2.{name}")
							break

		if cellObj is not None:
			rowNumber, columnNumber = self.getRowColumn(cellObj)

			if rowCount is None and rowNumber is not None:
				rowCount = rowNumber
				sourceParts.append("inferLowerBound.row")

			if columnCount is None and columnNumber is not None:
				columnCount = columnNumber
				sourceParts.append("inferLowerBound.column")

		countsKnown = bool(rowCountKnown and columnCountKnown)
		return rowCount, columnCount, ",".join(sourceParts), countsKnown

	def getTableUID(self, tableObj: object | None, cellObj: object | None = None) -> object:
		"""Return a stable table UID candidate."""
		if tableObj is not None:
			for name in (
				"IA2UniqueID",
				"uniqueID",
				"tableID",
				"IAccessibleUniqueID",
			):
				value = self._safeGetMaterialized(tableObj, name)
				if value is not None:
					return value

		if cellObj is not None:
			for name in (
				"tableID",
				"IAccessibleTableID",
			):
				value = self._safeGetMaterialized(cellObj, name)
				if value is not None:
					return value

			cellTable = self._safeGet(cellObj, "table", None)
			if cellTable is not None and cellTable is not tableObj:
				value = self.getTableUID(cellTable, None)
				if value is not None:
					return value

		if tableObj is not None:
			return f"id:{id(tableObj)}"

		return None

	def getContextFromObject(self, obj: object | None) -> WriterTableContext:
		"""Return Writer table context for one object."""
		cellObj, tableObj, source = self.findCellAndTable(obj)
		rowNumber, columnNumber = self.getRowColumn(cellObj)
		rowCount, columnCount, sizeSource, countsKnown = self.getTableSize(
			tableObj,
			cellObj,
		)
		tableUID = self.getTableUID(tableObj, cellObj)

		return WriterTableContext(
			inTable=bool(cellObj is not None and tableObj is not None),
			cellObj=cellObj,
			tableObj=tableObj,
			tableUID=tableUID,
			rowNumber=rowNumber,
			columnNumber=columnNumber,
			rowCount=rowCount,
			columnCount=columnCount,
			source=source,
			sizeSource=sizeSource,
			countsKnown=countsKnown,
		)

	def isSameTable(self, a: WriterTableContext | None, b: WriterTableContext | None) -> bool:
		"""Return whether two contexts point to the same table."""
		if a is None or b is None:
			return False

		if a.tableUID is None or b.tableUID is None:
			return False

		return a.tableUID == b.tableUID

	def formatContextFields(self, prefix: str, context: WriterTableContext) -> list[str]:
		"""Return stable debug fields for a table context."""
		lines: list[str] = []

		lines.append(f"{prefix}InTable={context.inTable!r}")
		lines.append(f"{prefix}FindSource={context.source!r}")
		lines.append(f"{prefix}CellExists={context.cellObj is not None}")
		lines.append(f"{prefix}CellClass={self._className(context.cellObj)!r}")
		lines.append(f"{prefix}CellUID={self._safeGet(context.cellObj, 'IA2UniqueID', None)!r}")
		lines.append(f"{prefix}RowNumber={context.rowNumber!r}")
		lines.append(f"{prefix}ColumnNumber={context.columnNumber!r}")
		lines.append(f"{prefix}TableExists={context.tableObj is not None}")
		lines.append(f"{prefix}TableClass={self._className(context.tableObj)!r}")
		lines.append(f"{prefix}TableUID={context.tableUID!r}")
		lines.append(f"{prefix}RowCount={context.rowCount!r}")
		lines.append(f"{prefix}ColumnCount={context.columnCount!r}")
		lines.append(f"{prefix}TableSizeSource={context.sizeSource!r}")
		lines.append(f"{prefix}CountsKnown={context.countsKnown!r}")

		return lines

class WriterTableTextInfoRegionFieldBridge:
	"""Build NVDA table control fields for TextInfoRegion.

	This bridge does not format braille text itself.
	It only converts Writer IA2 table context into NVDA native
	TABLE / TABLECELL ControlField and FieldCommand sequence.
	"""

	def _coerceInt(self, value: object, default: int | None = None) -> int | None:
		try:
			if value is None:
				return default
			return int(value)
		except Exception:
			return default

	def _newResult(self) -> dict[str, object]:
		return {
			"ok": False,
			"failStage": "",
			"failReason": "",
			"tableField": None,
			"cellField": None,
			"fieldSequence": [],
			"fieldSequenceShapeOk": False,
			"rowNumber": None,
			"columnNumber": None,
			"rowSpan": None,
			"columnSpan": None,
			"rowCount": None,
			"columnCount": None,
		}

	def _fail(
		self,
		result: dict[str, object],
		stage: str,
		reason: str,
	) -> dict[str, object]:
		result["ok"] = False
		result["failStage"] = stage
		result["failReason"] = reason
		return result

	def _buildControlField(self, values: dict[str, object]) -> object:
		import textInfos

		field = textInfos.ControlField()
		field.update(values)
		return field

	def buildTableControlField(
		self,
		rowCount: int | None,
		columnCount: int | None,
		tableID: int = 1,
	) -> object:
		"""Return a TABLE ControlField for TextInfoRegion."""
		import controlTypes

		return self._buildControlField(
			{
				"role": controlTypes.Role.TABLE,
				"roleText": "",
				"description": "",
				"_description-from": None,
				"hasDetails": False,
				"detailsRoles": tuple(),
				"states": set(),
				"_childcount": 0,
				"level": None,
				"table-id": tableID,
				"table-rowcount": rowCount,
				"table-columncount": columnCount,
				"_startOfNode": True,
			}
		)

	def buildTableCellControlField(
		self,
		rowNumber: int,
		columnNumber: int,
		rowSpan: int = 1,
		columnSpan: int = 1,
		includeTableCellCoords: bool = True,
		tableID: int = 1,
	) -> object:
		"""Return a TABLECELL ControlField for TextInfoRegion.

		The field intentionally carries both native table-* keys and
		getPropertiesBraille alias keys. The native keys preserve the
		ControlField shape, while rowNumber / columnNumber allow NVDA's
		braille formatter to produce table cell coordinates.
		"""
		import controlTypes

		return self._buildControlField(
			{
				"role": controlTypes.Role.TABLECELL,
				"roleText": "",
				"description": "",
				"_description-from": None,
				"hasDetails": False,
				"detailsRoles": tuple(),
				"states": {controlTypes.State.SELECTABLE},
				"_childcount": 0,
				"level": None,
				"table-id": tableID,
				"table-rownumber": rowNumber,
				"table-columnnumber": columnNumber,
				"table-rowheadertext": "",
				"table-columnheadertext": "",
				"table-rowsspanned": rowSpan,
				"table-columnsspanned": columnSpan,
				"rowNumber": rowNumber,
				"columnNumber": columnNumber,
				"rowSpan": rowSpan,
				"columnSpan": columnSpan,
				"includeTableCellCoords": includeTableCellCoords,
				"_startOfNode": True,
			}
		)

	def buildFieldSequence(
		self,
		text: str,
		rowNumber: int,
		columnNumber: int,
		rowCount: int | None,
		columnCount: int | None,
		rowSpan: int = 1,
		columnSpan: int = 1,
		includeTableCellCoords: bool = True,
		tableID: int = 1,
	) -> dict[str, object]:
		"""Return nested TABLE / TABLECELL FieldCommand sequence."""
		result = self._newResult()

		rowNumber = self._coerceInt(rowNumber)
		columnNumber = self._coerceInt(columnNumber)
		rowCount = self._coerceInt(rowCount)
		columnCount = self._coerceInt(columnCount)
		rowSpan = self._coerceInt(rowSpan, 1) or 1
		columnSpan = self._coerceInt(columnSpan, 1) or 1

		result["rowNumber"] = rowNumber
		result["columnNumber"] = columnNumber
		result["rowSpan"] = rowSpan
		result["columnSpan"] = columnSpan
		result["rowCount"] = rowCount
		result["columnCount"] = columnCount

		if rowNumber is None or columnNumber is None:
			return self._fail(result, "validateCellCoordinates", "rowOrColumnMissing")

		try:
			import controlTypes
			import textInfos

			tableField = self.buildTableControlField(
				rowCount=rowCount,
				columnCount=columnCount,
				tableID=tableID,
			)
			cellField = self.buildTableCellControlField(
				rowNumber=rowNumber,
				columnNumber=columnNumber,
				rowSpan=rowSpan,
				columnSpan=columnSpan,
				includeTableCellCoords=includeTableCellCoords,
				tableID=tableID,
			)

			fieldSequence = [
				textInfos.FieldCommand("controlStart", tableField),
				textInfos.FieldCommand("controlStart", cellField),
				text or "",
				textInfos.FieldCommand("controlEnd", cellField),
				textInfos.FieldCommand("controlEnd", tableField),
			]

			result["tableField"] = tableField
			result["cellField"] = cellField
			result["fieldSequence"] = fieldSequence
			result["fieldSequenceShapeOk"] = bool(
				len(fieldSequence) == 5
				and getattr(fieldSequence[0], "command", None) == "controlStart"
				and fieldSequence[0].field.get("role") == controlTypes.Role.TABLE
				and getattr(fieldSequence[1], "command", None) == "controlStart"
				and fieldSequence[1].field.get("role") == controlTypes.Role.TABLECELL
				and isinstance(fieldSequence[2], str)
				and getattr(fieldSequence[3], "command", None) == "controlEnd"
				and fieldSequence[3].field.get("role") == controlTypes.Role.TABLECELL
				and getattr(fieldSequence[4], "command", None) == "controlEnd"
				and fieldSequence[4].field.get("role") == controlTypes.Role.TABLE
			)
			result["ok"] = bool(result["fieldSequenceShapeOk"])
			if not result["ok"]:
				result["failStage"] = "validateFieldSequence"
				result["failReason"] = "fieldSequenceShapeMismatch"
			return result
		except Exception as e:
			return self._fail(result, "buildFieldSequence", repr(e))

	def buildFieldSequenceFromIA2Context(
		self,
		context: dict[str, object],
		text: str,
		rowSpan: int = 1,
		columnSpan: int = 1,
		includeTableCellCoords: bool = True,
		tableID: int = 1,
	) -> dict[str, object]:
		"""Build field sequence from WriterIA2TableNavigator context.

		WriterIA2TableNavigator context uses zero-based rowIndex / columnIndex.
		NVDA braille table coordinates use one-based rowNumber / columnNumber.
		"""
		rowIndex = self._coerceInt(context.get("rowIndex"))
		columnIndex = self._coerceInt(context.get("columnIndex"))

		if rowIndex is None or columnIndex is None:
			result = self._newResult()
			return self._fail(result, "validateIA2Context", "rowIndexOrColumnIndexMissing")

		return self.buildFieldSequence(
			text=text,
			rowNumber=rowIndex + 1,
			columnNumber=columnIndex + 1,
			rowCount=self._coerceInt(context.get("nRows")),
			columnCount=self._coerceInt(context.get("nColumns")),
			rowSpan=rowSpan,
			columnSpan=columnSpan,
			includeTableCellCoords=includeTableCellCoords,
			tableID=tableID,
		)

	def formatResultFields(self, prefix: str, result: dict[str, object]) -> list[str]:
		"""Return stable debug fields for bridge result."""
		tableField = result.get("tableField")
		cellField = result.get("cellField")
		fieldSequence = result.get("fieldSequence") or []

		return [
			f"{prefix}Ok={result.get('ok')!r}",
			f"{prefix}FailStage={result.get('failStage')!r}",
			f"{prefix}FailReason={result.get('failReason')!r}",
			f"{prefix}RowNumber={result.get('rowNumber')!r}",
			f"{prefix}ColumnNumber={result.get('columnNumber')!r}",
			f"{prefix}RowSpan={result.get('rowSpan')!r}",
			f"{prefix}ColumnSpan={result.get('columnSpan')!r}",
			f"{prefix}RowCount={result.get('rowCount')!r}",
			f"{prefix}ColumnCount={result.get('columnCount')!r}",
			f"{prefix}TableFieldExists={tableField is not None!r}",
			f"{prefix}TableFieldRole={tableField.get('role') if tableField is not None else None!r}",
			f"{prefix}CellFieldExists={cellField is not None!r}",
			f"{prefix}CellFieldRole={cellField.get('role') if cellField is not None else None!r}",
			f"{prefix}CellFieldRowNumber={cellField.get('rowNumber') if cellField is not None else None!r}",
			f"{prefix}CellFieldColumnNumber={cellField.get('columnNumber') if cellField is not None else None!r}",
			f"{prefix}FieldSequenceLength={len(fieldSequence)}",
			f"{prefix}FieldSequenceShapeOk={result.get('fieldSequenceShapeOk')!r}",
		]


class WriterIA2TableNavigator:
	"""Navigate LibreOffice Writer tables through IA2 table interfaces.

	This navigator follows the verified route:

	focus object
	-> nearest TABLECELL ancestor
	-> IAccessibleTableCell
	-> IAccessibleTable2
	-> cellAt(target row, target column)
	-> target IAccessible
	-> target NVDAObject
	-> setFocus()
	"""

	_DIRECTION_DELTAS: dict[str, tuple[int, int]] = {
		"up": (-1, 0),
		"down": (1, 0),
		"left": (0, -1),
		"right": (0, 1),
	}

	def _newResult(self, direction: str) -> dict[str, object]:
		"""Return the default navigation result shape."""
		return {
			"ok": False,
			"moved": False,
			"edge": False,
			"edgeReason": "",
			"failStage": "",
			"failReason": "",
			"direction": direction,
			"beforeRowIndex": None,
			"beforeColumnIndex": None,
			"targetRow": None,
			"targetColumn": None,
			"nRows": None,
			"nColumns": None,
			"targetNVDAObject": None,
			"targetNVDAObjectClass": "",
			"targetNVDAObjectModule": "",
			"targetNVDAObjectRole": None,
			"setFocusOk": False,
			"targetObjectMatchesTarget": False,
			"apiFocusMatchesTarget": False,
			"landedOnTarget": False,
			"afterRowIndex": None,
			"afterColumnIndex": None,
			"apiFocusRowIndex": None,
			"apiFocusColumnIndex": None,
		}

	def _fail(
		self,
		result: dict[str, object],
		stage: str,
		reason: str,
		ok: bool = False,
	) -> dict[str, object]:
		"""Store failure information and return the result."""
		result["ok"] = ok
		result["failStage"] = stage
		result["failReason"] = reason
		return result

	def _edge(
		self,
		result: dict[str, object],
		reason: str,
		targetRow: int | None,
		targetColumn: int | None,
	) -> dict[str, object]:
		"""Store table edge information and return the result."""
		result["ok"] = True
		result["moved"] = False
		result["edge"] = True
		result["edgeReason"] = reason
		result["targetRow"] = targetRow
		result["targetColumn"] = targetColumn
		return result

	def _getEdgeReason(
		self,
		direction: str,
		targetRow: int | None,
		targetColumn: int | None,
		nRows: int | None,
		nColumns: int | None,
	) -> str:
		"""Return a stable edge reason for an out-of-bounds target."""
		if direction == "up":
			return "firstRow"
		if direction == "down":
			return "lastRow"
		if direction == "left":
			return "firstColumn"
		if direction == "right":
			return "lastColumn"

		if isinstance(targetRow, int) and isinstance(nRows, int):
			if targetRow < 0:
				return "firstRow"
			if targetRow >= nRows:
				return "lastRow"

		if isinstance(targetColumn, int) and isinstance(nColumns, int):
			if targetColumn < 0:
				return "firstColumn"
			if targetColumn >= nColumns:
				return "lastColumn"

		return "outOfBounds"

	def getNearestTableCellFromObject(self, obj: object | None) -> object | None:
		"""Return the nearest TABLECELL object from obj or its ancestors."""
		currentObj = obj

		for _depth in range(0, 16):
			if currentObj is None:
				return None

			currentRole = getattr(currentObj, "role", None)
			if currentRole == controlTypes.Role.TABLECELL:
				return currentObj

			try:
				currentObj = getattr(currentObj, "parent", None)
			except Exception:
				return None

		return None

	def getIATableCellFromObject(self, cellObj: object | None) -> object | None:
		"""Return the IA2 table cell interface from an NVDA table cell object."""
		if cellObj is None:
			return None

		try:
			iaTableCell = getattr(cellObj, "_IATableCell", None)
		except Exception:
			return None

		return iaTableCell

	def getCellCoordinates(self, iaTableCell: object | None) -> tuple[bool, int | None, int | None, str]:
		"""Return row and column indexes from an IA2 table cell."""
		if iaTableCell is None:
			return False, None, None, "iaTableCellMissing"

		try:
			rowIndex = int(iaTableCell.rowIndex)
			columnIndex = int(iaTableCell.columnIndex)
		except Exception as e:
			return False, None, None, repr(e)

		return True, rowIndex, columnIndex, ""

	def getCellExtents(self, iaTableCell: object | None) -> tuple[bool, int | None, int | None, str]:
		"""Return row and column extents from an IA2 table cell."""
		if iaTableCell is None:
			return False, None, None, "iaTableCellMissing"

		rowSpan = None
		columnSpan = None

		for name in ("rowExtent", "rowSpan"):
			try:
				rowSpan = int(getattr(iaTableCell, name))
				break
			except Exception:
				pass

		for name in ("columnExtent", "columnSpan"):
			try:
				columnSpan = int(getattr(iaTableCell, name))
				break
			except Exception:
				pass

		if rowSpan is None:
			rowSpan = 1

		if columnSpan is None:
			columnSpan = 1

		return True, max(rowSpan, 1), max(columnSpan, 1), ""

	def getIA2TableFromCell(self, iaTableCell: object | None) -> tuple[bool, object | None, str]:
		"""Return IAccessibleTable2 from an IA2 table cell."""
		if iaTableCell is None:
			return False, None, "iaTableCellMissing"

		try:
			from comInterfaces import IAccessible2Lib as IA2
		except Exception as e:
			return False, None, f"importIA2Failed: {repr(e)}"

		try:
			tableUnknown = iaTableCell.table
			if tableUnknown is None:
				return False, None, "tableMissing"

			table2Obj = tableUnknown.QueryInterface(IA2.IAccessibleTable2)
			if table2Obj is None:
				return False, None, "table2Missing"

			return True, table2Obj, ""
		except Exception as e:
			return False, None, repr(e)

	def getTableSize(self, table2Obj: object | None) -> tuple[bool, int | None, int | None, str]:
		"""Return row and column count from IAccessibleTable2."""
		if table2Obj is None:
			return False, None, None, "table2Missing"

		try:
			nRows = int(table2Obj.nRows)
			nColumns = int(table2Obj.nColumns)
		except Exception as e:
			return False, None, None, repr(e)

		return True, nRows, nColumns, ""

	def computeTargetCell(
		self,
		rowIndex: int,
		columnIndex: int,
		nRows: int,
		nColumns: int,
		direction: str,
		rowSpan: int = 1,
		columnSpan: int = 1,
	) -> tuple[bool, int | None, int | None, str]:
		"""Return target row and column for one table navigation step.

		For merged cells, moving right/down must skip the current cell span.
		For example, B1:C1 merged has columnIndex=1 and columnSpan=2, so
		moving right should target column 3, not the covered column 2.
		"""
		if direction not in self._DIRECTION_DELTAS:
			return False, None, None, "unsupportedDirection"

		try:
			rowSpan = max(int(rowSpan), 1)
		except Exception:
			rowSpan = 1

		try:
			columnSpan = max(int(columnSpan), 1)
		except Exception:
			columnSpan = 1

		targetRow = rowIndex
		targetColumn = columnIndex

		if direction == "up":
			targetRow = rowIndex - 1
		elif direction == "down":
			targetRow = rowIndex + rowSpan
		elif direction == "left":
			targetColumn = columnIndex - 1
		elif direction == "right":
			targetColumn = columnIndex + columnSpan

		inBounds = (
			0 <= targetRow < nRows
			and 0 <= targetColumn < nColumns
		)

		if not inBounds:
			return False, targetRow, targetColumn, "targetOutOfBounds"

		return True, targetRow, targetColumn, ""

	def _contextContainsCoordinate(
		self,
		context: dict[str, object] | None,
		row: object,
		column: object,
	) -> bool:
		if not context:
			return False

		if not isinstance(row, int) or not isinstance(column, int):
			return False

		rowIndex = context.get("rowIndex")
		columnIndex = context.get("columnIndex")
		rowSpan = context.get("rowSpan") or 1
		columnSpan = context.get("columnSpan") or 1

		if not isinstance(rowIndex, int) or not isinstance(columnIndex, int):
			return False

		try:
			rowSpan = max(int(rowSpan), 1)
		except Exception:
			rowSpan = 1

		try:
			columnSpan = max(int(columnSpan), 1)
		except Exception:
			columnSpan = 1

		return (
			rowIndex <= row < rowIndex + rowSpan
			and columnIndex <= column < columnIndex + columnSpan
		)


	def _getContextSpanArea(self, context: dict[str, object] | None) -> int:
		if not context:
			return 1

		rowSpan = context.get("rowSpan") or 1
		columnSpan = context.get("columnSpan") or 1

		try:
			rowSpan = max(int(rowSpan), 1)
		except Exception:
			rowSpan = 1

		try:
			columnSpan = max(int(columnSpan), 1)
		except Exception:
			columnSpan = 1

		return rowSpan * columnSpan

	def _isSameCellObject(self, obj1: object | None, obj2: object | None) -> bool:
		if obj1 is None or obj2 is None:
			return False

		if id(obj1) == id(obj2):
			return True

		try:
			obj1IA2UniqueID = getattr(obj1, "IA2UniqueID", None)
		except Exception:
			obj1IA2UniqueID = None

		try:
			obj2IA2UniqueID = getattr(obj2, "IA2UniqueID", None)
		except Exception:
			obj2IA2UniqueID = None

		return obj1IA2UniqueID is not None and obj1IA2UniqueID == obj2IA2UniqueID

	def _findDescendantCellCoveringCoordinate(
		self,
		tableObj: object,
		row: int,
		column: int,
		excludeCellObj: object | None = None,
	) -> tuple[bool, object | None, str]:
		"""Find the best descendant table cell covering the requested coordinate.

		Prefer direct children of the table first, because Writer table cell objects
		are normally immediate children of the table. Only fall back to a deeper
		descendant scan when no direct child can cover the requested coordinate.
		"""
		descendantLookupDebug: dict[str, object] = {
			"requestedRow": row,
			"requestedColumn": column,
			"excludeCellObjExists": excludeCellObj is not None,
			"excludeCellObjDescription": None,
			"skippedExcludedCellCount": 0,
			"skippedExcludedCellDescription": None,
			"candidateCount": 0,
			"selectedDescription": None,
			"selectedSameAsExclude": False,
			"failReason": "",
		}
		if excludeCellObj is not None:
			try:
				descendantLookupDebug["excludeCellObjDescription"] = getattr(excludeCellObj, "description", None)
			except Exception:
				descendantLookupDebug["excludeCellObjDescription"] = None
		self._lastDescendantCellLookupDebug = descendantLookupDebug

		if tableObj is None:
			descendantLookupDebug["failReason"] = "tableObjMissing"
			return False, None, "tableObjMissing"

		def addCandidate(
			candidates: list[tuple[int, int, int, object]],
			candidateObjectsSeen: set[int],
			obj: object,
			scanOrder: int,
		) -> int:
			try:
				context = self.getContextFromObject(obj)
			except Exception:
				context = None

			if not self._contextContainsCoordinate(context, row, column):
				return scanOrder

			cellObj = context.get("cellObj") if context else None
			candidateObj = cellObj or obj

			if (
				excludeCellObj is not None
				and self._isSameCellObject(candidateObj, excludeCellObj)
			):
				descendantLookupDebug["skippedExcludedCellCount"] = (
					int(descendantLookupDebug.get("skippedExcludedCellCount") or 0) + 1
				)
				try:
					descendantLookupDebug["skippedExcludedCellDescription"] = getattr(candidateObj, "description", None)
				except Exception:
					descendantLookupDebug["skippedExcludedCellDescription"] = None
				return scanOrder

			candidateObjIdentity = id(candidateObj)
			if candidateObjIdentity in candidateObjectsSeen:
				return scanOrder

			candidateObjectsSeen.add(candidateObjIdentity)

			rowIndex = context.get("rowIndex") if context else None
			columnIndex = context.get("columnIndex") if context else None
			exactStartPenalty = 0 if rowIndex == row and columnIndex == column else 1
			spanArea = self._getContextSpanArea(context)

			candidates.append((
				exactStartPenalty,
				spanArea,
				scanOrder,
				candidateObj,
			))
			return scanOrder + 1

		def chooseBestCandidate(
			candidates: list[tuple[int, int, int, object]],
		) -> tuple[bool, object | None, str]:
			descendantLookupDebug["candidateCount"] = len(candidates)

			if not candidates:
				descendantLookupDebug["failReason"] = "descendantCellCoveringCoordinateNotFound"
				return False, None, "descendantCellCoveringCoordinateNotFound"

			candidates.sort(key=lambda item: (item[0], item[1], item[2]))
			selectedObj = candidates[0][3]

			try:
				descendantLookupDebug["selectedDescription"] = getattr(selectedObj, "description", None)
			except Exception:
				descendantLookupDebug["selectedDescription"] = None

			descendantLookupDebug["selectedSameAsExclude"] = (
				excludeCellObj is not None
				and self._isSameCellObject(selectedObj, excludeCellObj)
			)

			return True, selectedObj, ""


		try:
			directChildren = list(getattr(tableObj, "children", None) or [])
		except Exception:
			directChildren = []

		# Fast path: Writer table cells are normally direct children of the table.
		# This avoids walking into paragraphs/text objects on every table move.
		candidates: list[tuple[int, int, int, object]] = []
		candidateObjectsSeen: set[int] = set()
		scanOrder = 0

		for child in directChildren:
			scanOrder = addCandidate(candidates, candidateObjectsSeen, child, scanOrder)

		if candidates:
			return chooseBestCandidate(candidates)

		# Slow path: only scan deeper if direct children did not provide a covering
		# cell. This preserves the previous fallback behavior for unusual trees.
		maxNodes = 500
		visitedCount = 0
		seen: set[int] = set()
		pending: list[object] = list(directChildren)
		candidates = []
		candidateObjectsSeen = set()
		scanOrder = 0

		while pending and visitedCount < maxNodes:
			obj = pending.pop(0)
			if obj is None:
				continue

			objIdentity = id(obj)
			if objIdentity in seen:
				continue

			seen.add(objIdentity)
			visitedCount += 1

			scanOrder = addCandidate(candidates, candidateObjectsSeen, obj, scanOrder)

			try:
				children = getattr(obj, "children", None)
			except Exception:
				children = None

			if not children:
				continue

			try:
				pending.extend(list(children))
			except Exception:
				continue

		return chooseBestCandidate(candidates)

	def getTargetNVDAObject(
		self,
		table2Obj: object | None,
		targetRow: int,
		targetColumn: int,
		tableObj: object | None = None,
		sourceCellObj: object | None = None,
	) -> tuple[bool, object | None, str]:
		"""Return the target table cell object for the requested table coordinate.

		The direct IAccessibleTable2.cellAt(row, column) result is validated before
		use. If the direct result does not resolve to a cell covering the requested
		coordinate, fall back to ranked descendant lookup when tableObj is available.

		When sourceCellObj is provided, the direct and fallback paths must not
		accept the source cell itself as the target. This prevents false source spans
		from causing movement to stay on the same cell.
		"""
		targetLookupDebug: dict[str, object] = {
			"sourceCellObjExists": sourceCellObj is not None,
			"sourceCellObjDescription": None,
			"directRejectedBecauseSource": False,
			"directFailReason": "",
			"fallbackAttempted": False,
			"fallbackExcludeCellObjExists": sourceCellObj is not None,
			"fallbackOk": False,
			"fallbackReason": "",
			"fallbackSelectedDescription": None,
			"fallbackSelectedSameAsSource": False,
			"fallbackSkippedExcludedCellCount": 0,
			"fallbackSkippedExcludedCellDescription": None,
		}
		if sourceCellObj is not None:
			try:
				targetLookupDebug["sourceCellObjDescription"] = getattr(sourceCellObj, "description", None)
			except Exception:
				targetLookupDebug["sourceCellObjDescription"] = None

		self._lastTargetLookupDebug = targetLookupDebug

		if not isinstance(targetRow, int) or not isinstance(targetColumn, int):
			targetLookupDebug["directFailReason"] = "invalidTargetCoordinate"
			return False, None, "invalidTargetCoordinate"

		directFailReason = ""

		if table2Obj is not None:
			try:
				targetObj = table2Obj.cellAt(targetRow, targetColumn)
			except Exception as e:
				targetObj = None
				directFailReason = f"cellAtFailed: {e!r}"
				targetLookupDebug["directFailReason"] = directFailReason
			else:
				if targetObj is not None:
					try:
						targetContext = self.getContextFromObject(targetObj)
					except Exception as e:
						targetContext = None
						directFailReason = f"targetContextFailed: {e!r}"
						targetLookupDebug["directFailReason"] = directFailReason
					else:
						directFailReason = (
							targetContext.get("failReason", "")
							if targetContext
							else "targetContextMissing"
						)
						targetLookupDebug["directFailReason"] = directFailReason

					contextCellObj = targetContext.get("cellObj") if targetContext else None
					resolvedTargetObj = contextCellObj or targetObj

					if (
						sourceCellObj is not None
						and self._isSameCellObject(resolvedTargetObj, sourceCellObj)
					):
						directFailReason = "targetObjectIsSourceCell"
						targetLookupDebug["directRejectedBecauseSource"] = True
						targetLookupDebug["directFailReason"] = directFailReason
					elif self._contextContainsCoordinate(targetContext, targetRow, targetColumn):
						return True, resolvedTargetObj, ""
					else:
						directFailReason = "targetObjectDoesNotCoverRequestedCoordinate"
						targetLookupDebug["directFailReason"] = directFailReason
				else:
					directFailReason = "cellAtReturnedNone"
					targetLookupDebug["directFailReason"] = directFailReason
		else:
			directFailReason = "table2ObjMissing"
			targetLookupDebug["directFailReason"] = directFailReason

		if tableObj is not None:
			targetLookupDebug["fallbackAttempted"] = True

			fallbackOk, fallbackObj, fallbackReason = self._findDescendantCellCoveringCoordinate(
				tableObj,
				targetRow,
				targetColumn,
				excludeCellObj=sourceCellObj,
			)

			descendantDebug = getattr(self, "_lastDescendantCellLookupDebug", {})
			targetLookupDebug["fallbackOk"] = fallbackOk
			targetLookupDebug["fallbackReason"] = fallbackReason
			targetLookupDebug["fallbackSkippedExcludedCellCount"] = descendantDebug.get(
				"skippedExcludedCellCount",
				0,
			)
			targetLookupDebug["fallbackSkippedExcludedCellDescription"] = descendantDebug.get(
				"skippedExcludedCellDescription",
			)
			targetLookupDebug["fallbackSelectedDescription"] = descendantDebug.get("selectedDescription")
			targetLookupDebug["fallbackSelectedSameAsSource"] = descendantDebug.get(
				"selectedSameAsExclude",
				False,
			)

			if fallbackOk:
				return True, fallbackObj, ""

			return False, None, fallbackReason or directFailReason or "targetObjectNotFound"

		return False, None, directFailReason or "targetObjectNotFound"




	def getContextFromObject(self, obj: object | None) -> dict[str, object]:
		"""Return the IA2 table navigation context for an object."""
		context: dict[str, object] = {
			"inTable": False,
			"cellObj": None,
			"iaTableCell": None,
			"table2Obj": None,
			"rowIndex": None,
			"columnIndex": None,
			"rowSpan": None,
			"columnSpan": None,
			"nRows": None,
			"nColumns": None,
			"failStage": "",
			"failReason": "",
		}

		cellObj = self.getNearestTableCellFromObject(obj)
		if cellObj is None:
			context["failStage"] = "findNearestTableCell"
			context["failReason"] = "nearestTableCellNotFound"
			return context

		iaTableCell = self.getIATableCellFromObject(cellObj)
		if iaTableCell is None:
			context["failStage"] = "getIATableCell"
			context["failReason"] = "iaTableCellNotFound"
			return context

		coordsOk, rowIndex, columnIndex, coordsFailReason = self.getCellCoordinates(iaTableCell)
		if not coordsOk:
			context["failStage"] = "getCellCoordinates"
			context["failReason"] = coordsFailReason
			return context

		extentsOk, rowSpan, columnSpan, extentsFailReason = self.getCellExtents(iaTableCell)
		if not extentsOk:
			context["failStage"] = "getCellExtents"
			context["failReason"] = extentsFailReason
			return context

		try:
			rowSpan = max(int(iaTableCell.rowExtent), 1)
		except Exception:
			rowSpan = 1

		try:
			columnSpan = max(int(iaTableCell.columnExtent), 1)
		except Exception:
			columnSpan = 1

		table2Ok, table2Obj, table2FailReason = self.getIA2TableFromCell(iaTableCell)
		if not table2Ok:
			context["failStage"] = "getIA2TableFromCell"
			context["failReason"] = table2FailReason
			return context

		sizeOk, nRows, nColumns, sizeFailReason = self.getTableSize(table2Obj)
		if not sizeOk:
			context["failStage"] = "getTableSize"
			context["failReason"] = sizeFailReason
			return context

		context["inTable"] = True
		context["cellObj"] = cellObj
		context["iaTableCell"] = iaTableCell
		context["table2Obj"] = table2Obj
		context["rowIndex"] = rowIndex
		context["columnIndex"] = columnIndex
		context["rowSpan"] = rowSpan
		context["columnSpan"] = columnSpan
		context["nRows"] = nRows
		context["nColumns"] = nColumns
		return context

	def normalizeCellInfo(
		self,
		context: dict[str, object],
		includeTableCellCoords: bool = True,
		source: str = "IAccessibleTableCell",
	) -> dict[str, object]:
		"""Return NVDA-style table-cell properties derived from Writer IA2.

		Writer currently exposes table structure through IA2, while the focused
		Symphony text object exposes the text/caret side. These are not yet
		combined into native NVDA TextInfo/control-field properties for Writer.

		This adapter is an interim bridge. It converts IA2 0-based row/column
		indexes and row/column extents into the property shape used by NVDA
		speech/braille formatting: rowNumber, columnNumber, rowSpan,
		columnSpan and includeTableCellCoords.

		This helper should not present anything to the user directly. Speech and
		braille code should consume the returned properties.
		"""
		if not context or not context.get("inTable"):
			return {
				"inTable": False,
				"source": source,
			}

		rowIndex = context.get("rowIndex")
		columnIndex = context.get("columnIndex")
		rowSpan = context.get("rowSpan") or 1
		columnSpan = context.get("columnSpan") or 1
		nRows = context.get("nRows")
		nColumns = context.get("nColumns")

		if not isinstance(rowIndex, int) or not isinstance(columnIndex, int):
			return {
				"inTable": False,
				"source": source,
				"failReason": "missingRowOrColumnIndex",
				"rowIndex": rowIndex,
				"columnIndex": columnIndex,
			}

		try:
			rowSpan = max(int(rowSpan), 1)
		except Exception:
			rowSpan = 1

		try:
			columnSpan = max(int(columnSpan), 1)
		except Exception:
			columnSpan = 1

		rowNumber = rowIndex + 1
		columnNumber = columnIndex + 1

		return {
			"inTable": True,
			"source": source,

			# IA2 raw / 0-based data.
			"rowIndex": rowIndex,
			"columnIndex": columnIndex,
			"rowSpan": rowSpan,
			"columnSpan": columnSpan,
			"nRows": nRows,
			"nColumns": nColumns,

			# NVDA-style / user-facing 1-based properties.
			"rowNumber": rowNumber,
			"columnNumber": columnNumber,
			"rowEndNumber": rowNumber + rowSpan - 1,
			"columnEndNumber": columnNumber + columnSpan - 1,
			"includeTableCellCoords": includeTableCellCoords,
		}

	def getBrailleProperties(
		self,
		cellInfo: dict[str, object],
	) -> dict[str, object]:
		"""Return properties compatible with NVDA braille table formatting."""
		if not cellInfo or not cellInfo.get("inTable"):
			return {}

		return {
			"rowNumber": cellInfo.get("rowNumber"),
			"columnNumber": cellInfo.get("columnNumber"),
			"rowSpan": cellInfo.get("rowSpan", 1),
			"columnSpan": cellInfo.get("columnSpan", 1),
			"includeTableCellCoords": cellInfo.get("includeTableCellCoords", True),
		}

	def containsCoordinate(
		self,
		cellInfo: dict[str, object],
		rowIndex: int,
		columnIndex: int,
	 ) -> bool:
		"""Return whether a 0-based table coordinate is covered by this cell.

		This is important for merged cells. IA2 may return the owner cell for a
		covered coordinate. For example, when A1:C3 is merged, requesting row 1,
		column 2 may return the owner cell at row 0, column 0. That is valid if
		the requested coordinate is inside the owner cell's span.
		"""

		if not cellInfo or not cellInfo.get("inTable"):
			return False

		startRow = cellInfo.get("rowIndex")
		startColumn = cellInfo.get("columnIndex")
		rowSpan = cellInfo.get("rowSpan", 1)
		columnSpan = cellInfo.get("columnSpan", 1)

		if not isinstance(startRow, int) or not isinstance(startColumn, int):
			return False

		try:
			rowSpan = max(int(rowSpan), 1)
		except Exception:
			rowSpan = 1

		try:
			columnSpan = max(int(columnSpan), 1)
		except Exception:
			columnSpan = 1

		return (
			startRow <= rowIndex < startRow + rowSpan
			and startColumn <= columnIndex < startColumn + columnSpan
		)

	def formatCellInfoDebugFields(
		self,
		cellInfo: dict[str, object],
		prefix: str = "",
	) -> list[str]:
		"""Return stable debug fields for Writer IA2 table-cell info."""
		def key(name: str) -> str:
			return f"{prefix}{name}" if prefix else name

		return [
			f"{key('inTable')}={cellInfo.get('inTable')!r}",
			f"{key('source')}={cellInfo.get('source')!r}",
			f"{key('rowIndex')}={cellInfo.get('rowIndex')!r}",
			f"{key('columnIndex')}={cellInfo.get('columnIndex')!r}",
			f"{key('rowSpan')}={cellInfo.get('rowSpan')!r}",
			f"{key('columnSpan')}={cellInfo.get('columnSpan')!r}",
			f"{key('rowNumber')}={cellInfo.get('rowNumber')!r}",
			f"{key('columnNumber')}={cellInfo.get('columnNumber')!r}",
			f"{key('rowEndNumber')}={cellInfo.get('rowEndNumber')!r}",
			f"{key('columnEndNumber')}={cellInfo.get('columnEndNumber')!r}",
			f"{key('nRows')}={cellInfo.get('nRows')!r}",
			f"{key('nColumns')}={cellInfo.get('nColumns')!r}",
			f"{key('includeTableCellCoords')}={cellInfo.get('includeTableCellCoords')!r}",
		]

	def _contextContainsCoordinate(
		self,
		context: dict[str, object],
		row: int,
		column: int,
	) -> bool:
		"""Return whether a table cell context covers the requested coordinate."""
		rowIndex = context.get("rowIndex")
		columnIndex = context.get("columnIndex")
		rowSpan = context.get("rowSpan") or 1
		columnSpan = context.get("columnSpan") or 1

		if not isinstance(rowIndex, int) or not isinstance(columnIndex, int):
			return False

		try:
			rowSpan = max(int(rowSpan), 1)
		except Exception:
			rowSpan = 1

		try:
			columnSpan = max(int(columnSpan), 1)
		except Exception:
			columnSpan = 1

		return (
			rowIndex <= row < rowIndex + rowSpan
			and columnIndex <= column < columnIndex + columnSpan
		)

	def _sanitizeSourceCellSpan(
		self,
		context: dict[str, object],
		tableObj: object | None,
	) -> tuple[int, int, dict[str, object]]:
		"""Return conservative source row/column spans for movement.

		LibreOffice Writer can expose incorrect rowSpan / columnSpan for ordinary
		cells near merged cells. If a source cell claims to span over another
		exact-start cell in the same row or column, clamp the source span so
		computeTargetCell does not skip over that real cell.
		"""
		rowIndex = context.get("rowIndex")
		columnIndex = context.get("columnIndex")
		nRows = context.get("nRows")
		nColumns = context.get("nColumns")

		rawRowSpan = context.get("rowSpan") or 1
		rawColumnSpan = context.get("columnSpan") or 1

		try:
			effectiveRowSpan = max(int(rawRowSpan), 1)
		except Exception:
			effectiveRowSpan = 1

		try:
			effectiveColumnSpan = max(int(rawColumnSpan), 1)
		except Exception:
			effectiveColumnSpan = 1

		details: dict[str, object] = {
			"sourceSpanSanityAttempted": True,
			"sourceSpanSanityApplied": False,
			"sourceSpanSanityFailReason": "",
			"sourceOriginalRowSpan": effectiveRowSpan,
			"sourceOriginalColumnSpan": effectiveColumnSpan,
			"sourceEffectiveRowSpan": effectiveRowSpan,
			"sourceEffectiveColumnSpan": effectiveColumnSpan,
			"sourceRowSpanClamped": False,
			"sourceColumnSpanClamped": False,
		}

		if not isinstance(rowIndex, int) or not isinstance(columnIndex, int):
			details["sourceSpanSanityFailReason"] = "invalidSourceCoordinate"
			return effectiveRowSpan, effectiveColumnSpan, details

		if tableObj is None:
			details["sourceSpanSanityFailReason"] = "tableObjMissing"
			return effectiveRowSpan, effectiveColumnSpan, details

		try:
			directChildren = list(getattr(tableObj, "children", None) or [])
		except Exception as e:
			details["sourceSpanSanityFailReason"] = f"childrenAccessFailed: {e!r}"
			return effectiveRowSpan, effectiveColumnSpan, details

		details["sourceSpanSanityDirectChildCount"] = len(directChildren)

		sourceCellObj = context.get("cellObj")
		sourceCellObjIdentity = id(sourceCellObj) if sourceCellObj is not None else None

		try:
			sourceCellIA2UniqueID = getattr(sourceCellObj, "IA2UniqueID", None)
		except Exception:
			sourceCellIA2UniqueID = None

		def isSourceCellObject(cellObj: object | None, cellContext: dict[str, object]) -> bool:
			"""Return True if the candidate is the source cell itself.

			Object identity is preferred, but IA2 objects may be re-wrapped while
			still representing the same underlying cell. IA2UniqueID and the source
			start coordinate are used as conservative fallbacks.
			"""
			if cellObj is None:
				return False

			if sourceCellObjIdentity is not None and id(cellObj) == sourceCellObjIdentity:
				return True

			try:
				cellIA2UniqueID = getattr(cellObj, "IA2UniqueID", None)
			except Exception:
				cellIA2UniqueID = None

			if sourceCellIA2UniqueID is not None and cellIA2UniqueID == sourceCellIA2UniqueID:
				return True

			return (
				cellContext.get("rowIndex") == rowIndex
				and cellContext.get("columnIndex") == columnIndex
			)

		def getForeignCoveringCell(
			targetRow: int,
			targetColumn: int,
		) -> tuple[bool, object | None, dict[str, object] | None]:
			"""Find the best non-source cell that covers the requested coordinate.

			Do not return the first covering cell. Writer may expose false spans on
			neighbouring ordinary cells, so exact-start cells and smaller spans must
			win over broad false-span candidates.
			"""
			candidates: list[tuple[int, int, int, object, dict[str, object]]] = []
			scanOrder = 0

			for child in directChildren:
				try:
					childContext = self.getContextFromObject(child)
				except Exception:
					continue

				if not childContext or not childContext.get("inTable"):
					continue

				try:
					coversCoordinate = self._contextContainsCoordinate(
						childContext,
						targetRow,
						targetColumn,
					)
				except Exception:
					coversCoordinate = False

				if not coversCoordinate:
					continue

				cellObj = childContext.get("cellObj") or child
				if isSourceCellObject(cellObj, childContext):
					continue

				exactStartPenalty = (
					0
					if (
						childContext.get("rowIndex") == targetRow
						and childContext.get("columnIndex") == targetColumn
					)
					else 1
				)
				spanArea = self._getContextSpanArea(childContext)

				candidates.append((
					exactStartPenalty,
					spanArea,
					scanOrder,
					cellObj,
					childContext,
				))
				scanOrder += 1

			if not candidates:
				return False, None, None

			candidates.sort(key=lambda item: (item[0], item[1], item[2]))
			return True, candidates[0][3], candidates[0][4]

		rowLimit = rowIndex + effectiveRowSpan
		if isinstance(nRows, int):
			rowLimit = min(rowLimit, nRows)

		for checkRow in range(rowIndex + 1, rowLimit):
			exists, blockerObj, blockerContext = getForeignCoveringCell(checkRow, columnIndex)
			if not exists:
				continue

			effectiveRowSpan = max(checkRow - rowIndex, 1)
			details["sourceSpanSanityApplied"] = True
			details["sourceRowSpanClamped"] = True
			details["sourceRowSpanBlockerRow"] = checkRow
			try:
				details["sourceRowSpanBlockerDescription"] = getattr(blockerObj, "description", None)
			except Exception:
				details["sourceRowSpanBlockerDescription"] = None
			break

		columnLimit = columnIndex + effectiveColumnSpan
		if isinstance(nColumns, int):
			columnLimit = min(columnLimit, nColumns)

		for checkColumn in range(columnIndex + 1, columnLimit):
			exists, blockerObj, blockerContext = getForeignCoveringCell(rowIndex, checkColumn)
			if not exists:
				continue

			effectiveColumnSpan = max(checkColumn - columnIndex, 1)
			details["sourceSpanSanityApplied"] = True
			details["sourceColumnSpanClamped"] = True
			details["sourceColumnSpanBlockerColumn"] = checkColumn
			try:
				details["sourceColumnSpanBlockerDescription"] = getattr(blockerObj, "description", None)
			except Exception:
				details["sourceColumnSpanBlockerDescription"] = None
			break

		details["sourceEffectiveRowSpan"] = effectiveRowSpan
		details["sourceEffectiveColumnSpan"] = effectiveColumnSpan

		return effectiveRowSpan, effectiveColumnSpan, details

	def move(self, obj: object | None, direction: str) -> dict[str, object]:
		"""Move one table cell in the requested direction.

		:param obj: Starting NVDAObject.
		:param direction: One of up, down, left, or right.
		:return: A stable result dictionary for scripts and probes.
		"""
		result = self._newResult(direction)

		context = self.getContextFromObject(obj)
		if not context["inTable"]:
			return self._fail(
				result,
				str(context["failStage"]),
				str(context["failReason"]),
			)

		rowIndex = context["rowIndex"]
		columnIndex = context["columnIndex"]
		rowSpan = context.get("rowSpan") or 1
		columnSpan = context.get("columnSpan") or 1
		nRows = context["nRows"]
		nColumns = context["nColumns"]
		table2Obj = context["table2Obj"]

		if not isinstance(rowIndex, int) or not isinstance(columnIndex, int):
			return self._fail(result, "validateCoordinates", "invalidCoordinates")

		try:
			rowSpan = max(int(rowSpan), 1)
		except Exception:
			rowSpan = 1

		try:
			columnSpan = max(int(columnSpan), 1)
		except Exception:
			columnSpan = 1

		if not isinstance(nRows, int) or not isinstance(nColumns, int):
			return self._fail(result, "validateTableSize", "invalidTableSize")

		sourceCellObj = context.get("cellObj")
		try:
			tableObj = getattr(sourceCellObj, "parent", None) if sourceCellObj is not None else None
		except Exception:
			tableObj = None

		rowSpan, columnSpan, sourceSpanDetails = self._sanitizeSourceCellSpan(
			context,
			tableObj,
		)
		result.update(sourceSpanDetails)

		result["beforeRowIndex"] = rowIndex
		result["beforeColumnIndex"] = columnIndex
		result["beforeRowSpan"] = rowSpan
		result["beforeColumnSpan"] = columnSpan
		result["beforeEffectiveRowSpan"] = rowSpan
		result["beforeEffectiveColumnSpan"] = columnSpan
		result["nRows"] = nRows
		result["nColumns"] = nColumns

		targetOk, targetRow, targetColumn, targetFailReason = self.computeTargetCell(
			rowIndex,
			columnIndex,
			nRows,
			nColumns,
			direction,
			rowSpan=rowSpan,
			columnSpan=columnSpan,
		)

		result["targetRow"] = targetRow
		result["targetColumn"] = targetColumn

		if not targetOk:
			edgeReason = self._getEdgeReason(
				direction,
				targetRow,
				targetColumn,
				nRows,
				nColumns,
			)
			return self._edge(result, edgeReason, targetRow, targetColumn)

		if not isinstance(targetRow, int) or not isinstance(targetColumn, int):
			return self._fail(result, "computeTargetCell", targetFailReason)

		targetOk, targetNVDAObject, targetFailReason = self.getTargetNVDAObject(
			table2Obj,
			targetRow,
			targetColumn,
			tableObj=tableObj,
			sourceCellObj=sourceCellObj,
		)
		if not targetOk:
			return self._fail(result, "getTargetNVDAObject", targetFailReason)

		result["targetNVDAObject"] = targetNVDAObject
		result["targetNVDAObjectClass"] = targetNVDAObject.__class__.__name__
		result["targetNVDAObjectModule"] = targetNVDAObject.__class__.__module__
		result["targetNVDAObjectRole"] = getattr(targetNVDAObject, "role", None)

		# Verify the target object before moving focus.
		# In block-merged tables, getTargetNVDAObject may return a merged
		# owner cell that does not actually cover the requested coordinate.
		# Do not call setFocus until this is known to be safe.
		targetContext = self.getContextFromObject(targetNVDAObject)

		targetObjectRowIndex = targetContext.get("rowIndex")
		targetObjectColumnIndex = targetContext.get("columnIndex")
		targetObjectRowSpan = targetContext.get("rowSpan")
		targetObjectColumnSpan = targetContext.get("columnSpan")

		result["targetObjectRowIndex"] = targetObjectRowIndex
		result["targetObjectColumnIndex"] = targetObjectColumnIndex
		result["targetObjectRowSpan"] = targetObjectRowSpan
		result["targetObjectColumnSpan"] = targetObjectColumnSpan

		targetObjectMatchesTarget = self._contextContainsCoordinate(
			targetContext,
			targetRow,
			targetColumn,
		)

		result["targetObjectMatchesTarget"] = targetObjectMatchesTarget

		if not targetContext.get("inTable"):
			return self._fail(
				result,
				"resolveTargetObject",
				"targetObjectNotInTable",
			)

		if not targetObjectMatchesTarget:
			return self._fail(
				result,
				"resolveTargetObject",
				"targetObjectDoesNotCoverRequestedCoordinate",
			)

		setFocusOk = False
		setFocusFailReason = ""

		try:
			targetNVDAObject.setFocus()
			setFocusOk = True
		except Exception as e:
			setFocusFailReason = repr(e)

		result["setFocusOk"] = setFocusOk

		if not setFocusOk:
			return self._fail(result, "setFocus", setFocusFailReason)

		apiSetFocusObjectOk = False
		apiSetFocusObjectFailReason = ""

		try:
			api.setFocusObject(targetNVDAObject)
			apiSetFocusObjectOk = True
		except Exception as e:
			apiSetFocusObjectFailReason = repr(e)

		result["apiSetFocusObjectOk"] = apiSetFocusObjectOk
		result["apiSetFocusObjectFailReason"] = apiSetFocusObjectFailReason

		# Keep legacy after* fields for existing probes. These describe the
		# accepted target object, not necessarily a fresh focus event from NVDA.
		result["afterRowIndex"] = targetObjectRowIndex
		result["afterColumnIndex"] = targetObjectColumnIndex
		result["afterRowSpan"] = targetObjectRowSpan
		result["afterColumnSpan"] = targetObjectColumnSpan

		apiFocusRowIndex = None
		apiFocusColumnIndex = None
		apiFocusRowSpan = None
		apiFocusColumnSpan = None
		apiFocusMatchesTarget = False

		try:
			apiFocusObj = api.getFocusObject()
			apiFocusContext = self.getContextFromObject(apiFocusObj)
			apiFocusRowIndex = apiFocusContext.get("rowIndex")
			apiFocusColumnIndex = apiFocusContext.get("columnIndex")
			apiFocusRowSpan = apiFocusContext.get("rowSpan")
			apiFocusColumnSpan = apiFocusContext.get("columnSpan")
			apiFocusMatchesTarget = self._contextContainsCoordinate(
				apiFocusContext,
				targetRow,
				targetColumn,
			)
		except Exception:
			apiFocusMatchesTarget = False

		result["apiFocusRowIndex"] = apiFocusRowIndex
		result["apiFocusColumnIndex"] = apiFocusColumnIndex
		result["apiFocusRowSpan"] = apiFocusRowSpan
		result["apiFocusColumnSpan"] = apiFocusColumnSpan
		result["apiFocusMatchesTarget"] = apiFocusMatchesTarget

		# Keep this legacy field for existing probes.
		# Here it means the target object matches the requested target cell,
		# not necessarily that api.getFocusObject() has already updated.
		result["landedOnTarget"] = targetObjectMatchesTarget

		result["ok"] = True
		result["moved"] = True

		return result


	def formatResultFields(self, prefix: str, result: dict[str, object]) -> list[str]:
		"""Return stable debug fields for a move result."""
		return [
			f"{prefix}ok={result.get('ok')!r}",
			f"{prefix}moved={result.get('moved')!r}",
			f"{prefix}edge={result.get('edge')!r}",
			f"{prefix}edgeReason={result.get('edgeReason')!r}",
			f"{prefix}failStage={result.get('failStage')!r}",
			f"{prefix}failReason={result.get('failReason')!r}",
			f"{prefix}direction={result.get('direction')!r}",
			f"{prefix}beforeRowIndex={result.get('beforeRowIndex')!r}",
			f"{prefix}beforeColumnIndex={result.get('beforeColumnIndex')!r}",
			f"{prefix}targetRow={result.get('targetRow')!r}",
			f"{prefix}targetColumn={result.get('targetColumn')!r}",
			f"{prefix}nRows={result.get('nRows')!r}",
			f"{prefix}nColumns={result.get('nColumns')!r}",
			f"{prefix}targetNVDAObjectClass={result.get('targetNVDAObjectClass')!r}",
			f"{prefix}targetNVDAObjectModule={result.get('targetNVDAObjectModule')!r}",
			f"{prefix}targetNVDAObjectRole={result.get('targetNVDAObjectRole')!r}",
			f"{prefix}setFocusOk={result.get('setFocusOk')!r}",
			f"{prefix}apiSetFocusObjectOk={result.get('apiSetFocusObjectOk')!r}",
			f"{prefix}apiSetFocusObjectFailReason={result.get('apiSetFocusObjectFailReason')!r}",
			f"{prefix}targetObjectMatchesTarget={result.get('targetObjectMatchesTarget')!r}",
			f"{prefix}apiFocusMatchesTarget={result.get('apiFocusMatchesTarget')!r}",
			f"{prefix}landedOnTarget={result.get('landedOnTarget')!r}",
			f"{prefix}afterRowIndex={result.get('afterRowIndex')!r}",
			f"{prefix}afterColumnIndex={result.get('afterColumnIndex')!r}",
			f"{prefix}apiFocusRowIndex={result.get('apiFocusRowIndex')!r}",
			f"{prefix}apiFocusColumnIndex={result.get('apiFocusColumnIndex')!r}",
		]




def _normalizeWriterIA2SpeechText(text: object) -> str:
	"""Normalize real Writer cell text for speech.

	Return an empty string if the value is not real user-visible text.
	"""
	if not isinstance(text, str):
		return ""

	text = text.replace("\x00", "")
	text = text.replace("\r\n", "\n").replace("\r", "\n")

	lines = []
	for line in text.split("\n"):
		line = line.strip()
		if line:
			lines.append(line)

	return " ".join(lines).strip()


def _getWriterIA2SingleObjectTextForSpeech(obj: object | None) -> str:
	"""Get real text from one NVDA object.

	Do not use name or description here. In LibreOffice Writer table cells,
	description may contain accessibility coordinates such as A4, not the real
	cell content.
	"""
	if obj is None:
		return ""

	try:
		import textInfos
	except Exception:
		return ""

	try:
		info = obj.makeTextInfo(textInfos.POSITION_ALL)
	except Exception:
		return ""

	try:
		text = info.text
	except Exception:
		return ""

	return _normalizeWriterIA2SpeechText(text)


def _getWriterIA2ObjectTextForSpeech(obj: object | None) -> str:
	"""Get real user-visible text from a Writer table object.

	The target object may be a table cell object. The actual content is often on
	a child paragraph or text object. If no real text is found, return an empty
	string. Do not return fallback speech such as blank, table cell, row/column,
	name, or description.
	"""
	if obj is None:
		return ""

	text = _getWriterIA2SingleObjectTextForSpeech(obj)
	if text:
		return text

	try:
		directChildren = list(getattr(obj, "children", None) or [])
	except Exception:
		directChildren = []

	for child in directChildren:
		text = _getWriterIA2SingleObjectTextForSpeech(child)
		if text:
			return text

	maxNodes = 60
	visitedCount = 0
	seen: set[int] = set()
	pending: list[object] = list(directChildren)

	while pending and visitedCount < maxNodes:
		current = pending.pop(0)
		if current is None:
			continue

		currentIdentity = id(current)
		if currentIdentity in seen:
			continue

		seen.add(currentIdentity)
		visitedCount += 1

		text = _getWriterIA2SingleObjectTextForSpeech(current)
		if text:
			return text

		try:
			children = list(getattr(current, "children", None) or [])
		except Exception:
			children = []

		if children:
			pending.extend(children)

	return ""

def _getWriterIA2TableContentSpeechText(result: dict[str, object]) -> str:
	"""Return real Writer table cell content text from a move result."""
	for key in (
		"targetContentText",
		"contentText",
		"afterText",
		"targetText",
	):
		value = result.get(key)
		if isinstance(value, str) and value.strip():
			return value.strip()

	return ""


def _getWriterIA2TableCellCoordsSpeechText(result: dict[str, object]) -> str:
	"""Return Writer table cell coordinates from a move result."""
	targetRow = result.get("targetRow")
	targetColumn = result.get("targetColumn")

	if isinstance(targetRow, int) and isinstance(targetColumn, int):
		# Translators: fallback speech for a Writer table cell location.
		return _("row {row}, column {column}").format(
			row=targetRow + 1,
			column=targetColumn + 1,
		)

	return ""


def _getWriterIA2TableMoveSpeech(result: dict[str, object]) -> str:
	"""Return speech text for a Writer IA2 table move result.

	Use real cell content when available, and add table coordinates when they
	are available. Do not use object description, name, or cellName as content.
	"""
	contentText = _getWriterIA2TableContentSpeechText(result)
	coordinateText = _getWriterIA2TableCellCoordsSpeechText(result)

	if contentText and coordinateText:
		return f"{contentText}, {coordinateText}"

	if contentText:
		return contentText

	if coordinateText:
		return coordinateText

	# Translators: fallback speech when a Writer table cell has no text or coordinates.
	return _("table cell")



def moveAndReportWriterIA2TableCell(
	direction: str,
	focusObj: object | None = None,
) -> bool:
	"""Move in a Writer IA2 table and report the target cell."""
	import api
	import ui

	focus = focusObj or api.getFocusObject()

	try:
		result = WriterIA2TableNavigator().move(focus, direction)
	except Exception:
		return False

	if result.get("moved"):
		targetObj = result.get("targetNVDAObject")
		contentText = _getWriterIA2ObjectTextForSpeech(targetObj)

		if not contentText:
			contentText = _getWriterIA2ObjectTextForSpeech(api.getFocusObject())

		if contentText:
			result["targetContentText"] = contentText
			result["contentText"] = contentText

		speechText = _getWriterIA2TableMoveSpeech(result)
		if speechText:
			ui.message(speechText)
		return True


	if result.get("edge"):
		# Translators: Reported when table navigation reaches the edge of a table.
		ui.message(_("Edge of table"))
		return True

	if result.get("inTable") is False:
		# Translators: Reported when table navigation is requested outside a table cell.
		ui.message(_("Not in a table cell"))
		return True

	# Translators: Reported when Writer table navigation failed.
	ui.message(_("Cannot move table cell"))
	return True

