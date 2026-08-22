from dataclasses import dataclass

import api
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
			self._safeGet(cellObj, "rowNumber", None),
		)
		columnNumber = self._coerceInt(
			self._safeGet(cellObj, "columnNumber", None),
		)

		return rowNumber, columnNumber

	def getTableSize(
		self,
		tableObj: object | None,
		cellObj: object | None = None,
	) -> tuple[int | None, int | None, str, bool]:
		"""Return table row count, column count, source, and confidence."""
		sourceParts: list[str] = []

		rowCount = self._coerceInt(
			self._safeGet(tableObj, "rowCount", None),
		)
		columnCount = self._coerceInt(
			self._safeGet(tableObj, "columnCount", None),
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
							self._safeGet(ia2Table, name, None),
						)
						if rowCount is not None:
							rowCountKnown = True
							sourceParts.append(f"ia2.{name}")
							break

				if columnCount is None:
					for name in ("nColumns", "columnCount"):
						columnCount = self._coerceInt(
							self._safeGet(ia2Table, name, None),
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
			},
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
			},
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
				and fieldSequence[4].field.get("role") == controlTypes.Role.TABLE,
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

		inBounds = 0 <= targetRow < nRows and 0 <= targetColumn < nColumns

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

		return rowIndex <= row < rowIndex + rowSpan and columnIndex <= column < columnIndex + columnSpan

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

	def _getDirectCellCoordinateCacheTableKey(
		self,
		tableObj: object | None,
	) -> tuple[object, ...] | None:
		"""Return a stable-enough table identity for the 1i cache experiment."""
		if tableObj is None:
			return None

		try:
			processID = getattr(tableObj, "processID", None)
		except Exception:
			processID = None

		try:
			windowHandle = getattr(tableObj, "windowHandle", None)
		except Exception:
			windowHandle = None

		try:
			ia2UniqueID = getattr(tableObj, "IA2UniqueID", None)
		except Exception:
			ia2UniqueID = None

		if ia2UniqueID is not None:
			return (
				"ia2",
				processID,
				windowHandle,
				ia2UniqueID,
			)

		return (
			"object",
			id(tableObj),
		)

	def _getDirectCellCoordinateCacheState(
		self,
	) -> dict[str, object]:
		"""Return the lazy single-table coordinate cache."""
		cache = getattr(
			self,
			"_directCellCoordinateCache",
			None,
		)

		if not isinstance(cache, dict):
			cache = {
				"built": False,
				"tableKey": None,
				"directChildren": [],
				"contextByObjectIdentity": {},
				"coordinateMap": {},
				"coordinateCount": 0,
				"candidateEntryCount": 0,
			}
			self._directCellCoordinateCache = cache

		return cache

	def _clearDirectCellCoordinateCache(self) -> None:
		"""Discard the current 1i direct-cell coordinate cache."""
		self._directCellCoordinateCache = {
			"built": False,
			"tableKey": None,
			"directChildren": [],
			"contextByObjectIdentity": {},
			"coordinateMap": {},
			"coordinateCount": 0,
			"candidateEntryCount": 0,
		}

	def _buildDirectCellCoordinateCache(
		self,
		tableObj: object,
		tableKey: tuple[object, ...],
		timing: dict | None = None,
	) -> dict[str, object]:
		"""Build a direct-child context and covered-coordinate map.

		Each coordinate stores ranked candidates rather than only one object.
		This preserves merged-cell ranking and allows the source cell to be
		excluded during an individual movement.
		"""
		import time

		self._markMoveTimingProbe1c(
			timing,
			"descendantCacheBuildStartPerf",
		)

		self._markMoveTimingProbe1c(
			timing,
			"descendantBeforeDirectChildrenAccessPerf",
		)
		try:
			directChildren = list(
				getattr(tableObj, "children", None) or [],
			)
		except Exception:
			directChildren = []
		self._markMoveTimingProbe1c(
			timing,
			"descendantAfterDirectChildrenAccessPerf",
		)

		contextByObjectIdentity: dict[int, dict[str, object]] = {}
		coordinateMap: dict[
			tuple[int, int],
			list[
				tuple[
					int,
					int,
					int,
					object,
					dict[str, object],
				]
			],
		] = {}

		directContextCallCount = 0
		directContextTotalMs = 0.0
		directValidContextCount = 0
		candidateObjectsSeen: set[int] = set()

		self._markMoveTimingProbe1c(
			timing,
			"descendantBeforeDirectScanPerf",
		)

		for childScanOrder, child in enumerate(directChildren):
			directContextCallCount += 1

			contextStart = time.perf_counter()
			try:
				context = self.getContextFromObject(child)
			except Exception:
				context = None
			contextEnd = time.perf_counter()

			directContextTotalMs += (contextEnd - contextStart) * 1000

			if not isinstance(context, dict):
				continue

			contextByObjectIdentity[id(child)] = context

			if not context.get("inTable"):
				continue

			rowIndex = context.get("rowIndex")
			columnIndex = context.get("columnIndex")

			if not isinstance(rowIndex, int) or not isinstance(columnIndex, int):
				continue

			candidateObj = context.get("cellObj") or child
			candidateObjIdentity = id(candidateObj)

			contextByObjectIdentity[candidateObjIdentity] = context

			if candidateObjIdentity in candidateObjectsSeen:
				continue

			candidateObjectsSeen.add(candidateObjIdentity)
			directValidContextCount += 1

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

			nRows = context.get("nRows")
			nColumns = context.get("nColumns")

			rowEnd = rowIndex + rowSpan
			columnEnd = columnIndex + columnSpan

			if isinstance(nRows, int):
				rowEnd = min(rowEnd, nRows)

			if isinstance(nColumns, int):
				columnEnd = min(columnEnd, nColumns)

			spanArea = rowSpan * columnSpan

			for coveredRow in range(
				rowIndex,
				rowEnd,
			):
				for coveredColumn in range(
					columnIndex,
					columnEnd,
				):
					exactStartPenalty = 0 if (coveredRow == rowIndex and coveredColumn == columnIndex) else 1

					coordinateMap.setdefault(
						(
							coveredRow,
							coveredColumn,
						),
						[],
					).append(
						(
							exactStartPenalty,
							spanArea,
							childScanOrder,
							candidateObj,
							context,
						),
					)

		for candidates in coordinateMap.values():
			candidates.sort(
				key=lambda item: (
					item[0],
					item[1],
					item[2],
				),
			)

		self._markMoveTimingProbe1c(
			timing,
			"descendantAfterDirectScanPerf",
		)

		candidateEntryCount = sum(len(candidates) for candidates in coordinateMap.values())

		cache: dict[str, object] = {
			"built": True,
			"tableKey": tableKey,
			"directChildren": directChildren,
			"contextByObjectIdentity": contextByObjectIdentity,
			"coordinateMap": coordinateMap,
			"coordinateCount": len(coordinateMap),
			"candidateEntryCount": candidateEntryCount,
			"directChildCount": len(directChildren),
			"directContextCallCount": directContextCallCount,
			"directContextTotalMs": directContextTotalMs,
			"directValidContextCount": directValidContextCount,
		}

		self._directCellCoordinateCache = cache

		self._markMoveTimingProbe1c(
			timing,
			"descendantCacheBuildEndPerf",
		)

		return cache

	def _lookupDirectCellCoordinateCache(
		self,
		cache: dict[str, object],
		row: int,
		column: int,
		excludeCellObj: object | None,
		descendantLookupDebug: dict[str, object],
		timing: dict | None = None,
	) -> tuple[str, object | None]:
		"""Return hit, miss, or stale for one cached coordinate."""
		coordinateMap = cache.get("coordinateMap")

		if not isinstance(coordinateMap, dict):
			return "miss", None

		candidates = coordinateMap.get(
			(row, column),
			[],
		)

		self._setMoveTimingProbe1cValue(
			timing,
			"descendant.cacheCandidateCountAtCoordinate",
			len(candidates),
		)

		if not candidates:
			descendantLookupDebug["candidateCount"] = 0
			return "miss", None

		acceptedCandidateCount = 0

		for candidate in candidates:
			candidateObj = candidate[3]

			if excludeCellObj is not None and self._isSameCellObject(
				candidateObj,
				excludeCellObj,
			):
				descendantLookupDebug["skippedExcludedCellCount"] = (
					int(
						descendantLookupDebug.get(
							"skippedExcludedCellCount",
						)
						or 0,
					)
					+ 1
				)

				try:
					descendantLookupDebug["skippedExcludedCellDescription"] = getattr(
						candidateObj,
						"description",
						None,
					)
				except Exception:
					descendantLookupDebug["skippedExcludedCellDescription"] = None

				continue

			acceptedCandidateCount += 1

			# 1i safety check:
			# Do not trust a cached NVDAObject blindly across movements.
			self._markMoveTimingProbe1c(
				timing,
				"descendantCacheValidationStartPerf",
			)
			try:
				currentContext = self.getContextFromObject(
					candidateObj,
				)
			except Exception:
				currentContext = None
			self._markMoveTimingProbe1c(
				timing,
				"descendantCacheValidationEndPerf",
			)

			if not self._contextContainsCoordinate(
				currentContext,
				row,
				column,
			):
				self._setMoveTimingProbe1cValue(
					timing,
					"descendant.cacheValidationOk",
					False,
				)
				return "stale", None

			self._setMoveTimingProbe1cValue(
				timing,
				"descendant.cacheValidationOk",
				True,
			)

			descendantLookupDebug["candidateCount"] = acceptedCandidateCount

			try:
				descendantLookupDebug["selectedDescription"] = getattr(
					candidateObj,
					"description",
					None,
				)
			except Exception:
				descendantLookupDebug["selectedDescription"] = None

			descendantLookupDebug["selectedSameAsExclude"] = False

			return "hit", candidateObj

		descendantLookupDebug["candidateCount"] = 0

		return "miss", None

	def _findDescendantCellCoveringCoordinate(
		self,
		tableObj: object,
		row: int,
		column: int,
		excludeCellObj: object | None = None,
		timing: dict | None = None,
	) -> tuple[bool, object | None, str]:
		"""Find the best descendant table cell covering the requested coordinate.

		Use the 1i direct-child covered-coordinate cache first.
		Only use deeper descendant traversal when no usable direct-child
		candidate exists.
		"""
		import time

		self._markMoveTimingProbe1c(
			timing,
			"descendantLookupInternalStartPerf",
		)

		stats: dict[str, object] = {
			"resultPath": "",
			"directChildCount": 0,
			"directVisitedCount": 0,
			"directContextCallCount": 0,
			"directContextTotalMs": 0.0,
			"directCoveringCount": 0,
			"directCandidateCount": 0,
			"deepScanUsed": False,
			"deepInitialPendingCount": 0,
			"deepVisitedCount": 0,
			"deepContextCallCount": 0,
			"deepContextTotalMs": 0.0,
			"deepCoveringCount": 0,
			"deepCandidateCount": 0,
			"deepChildrenExpandCount": 0,
			"deepChildrenAddedCount": 0,
			"cacheHit": False,
			"cacheBuilt": False,
			"cacheRebuiltAfterStale": False,
		}

		def _writeStats() -> None:
			for key, value in stats.items():
				self._setMoveTimingProbe1cValue(
					timing,
					f"descendant.{key}",
					value,
				)

		def _finishReturn(
			ok: bool,
			obj: object | None,
			reason: str,
			resultPath: str,
		) -> tuple[bool, object | None, str]:
			stats["resultPath"] = resultPath
			_writeStats()

			self._markMoveTimingProbe1c(
				timing,
				"descendantLookupInternalEndPerf",
			)

			return ok, obj, reason

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
				descendantLookupDebug["excludeCellObjDescription"] = getattr(
					excludeCellObj,
					"description",
					None,
				)
			except Exception:
				descendantLookupDebug["excludeCellObjDescription"] = None

		self._lastDescendantCellLookupDebug = descendantLookupDebug

		self._setMoveTimingProbe1cValue(
			timing,
			"descendant.requestedRow",
			row,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"descendant.requestedColumn",
			column,
		)

		if tableObj is None:
			descendantLookupDebug["failReason"] = "tableObjMissing"

			return _finishReturn(
				False,
				None,
				"tableObjMissing",
				"tableObjMissing",
			)

		tableKey = self._getDirectCellCoordinateCacheTableKey(
			tableObj,
		)

		self._setMoveTimingProbe1cValue(
			timing,
			"descendant.cacheTableKey",
			tableKey,
		)

		cache = self._getDirectCellCoordinateCacheState()

		cacheMatchesTable = bool(cache.get("built")) and cache.get("tableKey") == tableKey

		self._setMoveTimingProbe1cValue(
			timing,
			"descendant.cacheAvailableBeforeLookup",
			cacheMatchesTable,
		)

		if cacheMatchesTable:
			stats["directChildCount"] = int(
				cache.get("directChildCount") or 0,
			)

			self._markMoveTimingProbe1c(
				timing,
				"descendantCacheLookupStartPerf",
			)

			cacheStatus, cachedObj = self._lookupDirectCellCoordinateCache(
				cache,
				row,
				column,
				excludeCellObj,
				descendantLookupDebug,
				timing=timing,
			)

			self._markMoveTimingProbe1c(
				timing,
				"descendantCacheLookupEndPerf",
			)

			self._setMoveTimingProbe1cValue(
				timing,
				"descendant.cacheLookupStatus",
				cacheStatus,
			)

			if cacheStatus == "hit":
				stats["cacheHit"] = True

				return _finishReturn(
					True,
					cachedObj,
					"",
					"coordinateCache",
				)

			if cacheStatus == "stale":
				stats["cacheRebuiltAfterStale"] = True
				self._clearDirectCellCoordinateCache()
				cacheMatchesTable = False

		if not cacheMatchesTable:
			cache = self._buildDirectCellCoordinateCache(
				tableObj,
				tableKey,
				timing=timing,
			)

			stats["cacheBuilt"] = True
			stats["directChildCount"] = int(
				cache.get("directChildCount") or 0,
			)
			stats["directVisitedCount"] = int(
				cache.get("directChildCount") or 0,
			)
			stats["directContextCallCount"] = int(
				cache.get("directContextCallCount") or 0,
			)
			stats["directContextTotalMs"] = float(
				cache.get("directContextTotalMs") or 0.0,
			)

			self._markMoveTimingProbe1c(
				timing,
				"descendantCacheLookupStartPerf",
			)

			cacheStatus, cachedObj = self._lookupDirectCellCoordinateCache(
				cache,
				row,
				column,
				excludeCellObj,
				descendantLookupDebug,
				timing=timing,
			)

			self._markMoveTimingProbe1c(
				timing,
				"descendantCacheLookupEndPerf",
			)

			self._setMoveTimingProbe1cValue(
				timing,
				"descendant.cacheLookupStatus",
				cacheStatus,
			)

			coordinateMap = cache.get(
				"coordinateMap",
				{},
			)

			if isinstance(coordinateMap, dict):
				rawCandidates = coordinateMap.get(
					(row, column),
					[],
				)
			else:
				rawCandidates = []

			stats["directCoveringCount"] = len(
				rawCandidates,
			)
			stats["directCandidateCount"] = int(
				descendantLookupDebug.get(
					"candidateCount",
				)
				or 0,
			)

			if cacheStatus == "hit":
				return _finishReturn(
					True,
					cachedObj,
					"",
					"directChildrenCacheBuild",
				)

		self._setMoveTimingProbe1cValue(
			timing,
			"descendant.cacheCoordinateCount",
			cache.get("coordinateCount", 0),
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"descendant.cacheCandidateEntryCount",
			cache.get("candidateEntryCount", 0),
		)

		# No usable direct-child candidate.
		# Preserve the existing deeper fallback behavior.
		stats["deepScanUsed"] = True

		directChildren = cache.get(
			"directChildren",
			[],
		)

		if not isinstance(directChildren, list):
			directChildren = list(
				directChildren or [],
			)

		contextByObjectIdentity = cache.get(
			"contextByObjectIdentity",
			{},
		)

		if not isinstance(
			contextByObjectIdentity,
			dict,
		):
			contextByObjectIdentity = {}

		def addDeepCandidate(
			candidates: list[tuple[int, int, int, object]],
			candidateObjectsSeen: set[int],
			obj: object,
			scanOrder: int,
		) -> int:
			stats["deepContextCallCount"] = int(stats["deepContextCallCount"]) + 1

			contextStart = time.perf_counter()

			context = contextByObjectIdentity.get(
				id(obj),
			)

			if context is None:
				try:
					context = self.getContextFromObject(
						obj,
					)
				except Exception:
					context = None

			contextEnd = time.perf_counter()

			stats["deepContextTotalMs"] = float(stats["deepContextTotalMs"]) + (
				(contextEnd - contextStart) * 1000
			)

			if not self._contextContainsCoordinate(
				context,
				row,
				column,
			):
				return scanOrder

			stats["deepCoveringCount"] = int(stats["deepCoveringCount"]) + 1

			cellObj = context.get("cellObj") if context else None
			candidateObj = cellObj or obj

			if excludeCellObj is not None and self._isSameCellObject(
				candidateObj,
				excludeCellObj,
			):
				descendantLookupDebug["skippedExcludedCellCount"] = (
					int(
						descendantLookupDebug.get(
							"skippedExcludedCellCount",
						)
						or 0,
					)
					+ 1
				)
				return scanOrder

			candidateObjIdentity = id(
				candidateObj,
			)

			if candidateObjIdentity in candidateObjectsSeen:
				return scanOrder

			candidateObjectsSeen.add(
				candidateObjIdentity,
			)

			rowIndex = context.get("rowIndex") if context else None
			columnIndex = context.get("columnIndex") if context else None

			exactStartPenalty = 0 if (rowIndex == row and columnIndex == column) else 1

			spanArea = self._getContextSpanArea(
				context,
			)

			candidates.append(
				(
					exactStartPenalty,
					spanArea,
					scanOrder,
					candidateObj,
				),
			)

			return scanOrder + 1

		def chooseBestCandidate(
			candidates: list[tuple[int, int, int, object]],
		) -> tuple[
			bool,
			object | None,
			str,
		]:
			descendantLookupDebug["candidateCount"] = len(candidates)

			if not candidates:
				descendantLookupDebug["failReason"] = "descendantCellCoveringCoordinateNotFound"

				return (
					False,
					None,
					"descendantCellCoveringCoordinateNotFound",
				)

			candidates.sort(
				key=lambda item: (
					item[0],
					item[1],
					item[2],
				),
			)

			selectedObj = candidates[0][3]

			try:
				descendantLookupDebug["selectedDescription"] = getattr(
					selectedObj,
					"description",
					None,
				)
			except Exception:
				descendantLookupDebug["selectedDescription"] = None

			descendantLookupDebug["selectedSameAsExclude"] = (
				excludeCellObj is not None
				and self._isSameCellObject(
					selectedObj,
					excludeCellObj,
				)
			)

			return True, selectedObj, ""

		maxNodes = 500
		visitedCount = 0
		seen: set[int] = set()
		pending: list[object] = list(
			directChildren,
		)

		stats["deepInitialPendingCount"] = len(
			pending,
		)

		candidates: list[tuple[int, int, int, object]] = []
		candidateObjectsSeen: set[int] = set()
		scanOrder = 0

		self._markMoveTimingProbe1c(
			timing,
			"descendantBeforeDeepScanPerf",
		)

		while pending and visitedCount < maxNodes:
			obj = pending.pop(0)

			if obj is None:
				continue

			objIdentity = id(obj)

			if objIdentity in seen:
				continue

			seen.add(objIdentity)
			visitedCount += 1

			stats["deepVisitedCount"] = visitedCount

			scanOrder = addDeepCandidate(
				candidates,
				candidateObjectsSeen,
				obj,
				scanOrder,
			)

			try:
				children = getattr(
					obj,
					"children",
					None,
				)
			except Exception:
				children = None

			if not children:
				continue

			try:
				childrenList = list(children)
			except Exception:
				continue

			stats["deepChildrenExpandCount"] = (
				int(
					stats["deepChildrenExpandCount"],
				)
				+ 1
			)

			stats["deepChildrenAddedCount"] = int(
				stats["deepChildrenAddedCount"],
			) + len(childrenList)

			pending.extend(childrenList)

		self._markMoveTimingProbe1c(
			timing,
			"descendantAfterDeepScanPerf",
		)

		stats["deepCandidateCount"] = len(
			candidates,
		)

		self._markMoveTimingProbe1c(
			timing,
			"descendantBeforeDeepChoosePerf",
		)

		ok, selectedObj, reason = chooseBestCandidate(candidates)

		self._markMoveTimingProbe1c(
			timing,
			"descendantAfterDeepChoosePerf",
		)

		return _finishReturn(
			ok,
			selectedObj,
			reason,
			"deepScan",
		)

	def getTargetNVDAObject(
		self,
		table2Obj: object | None,
		targetRow: int,
		targetColumn: int,
		tableObj: object | None = None,
		sourceCellObj: object | None = None,
		timing: dict | None = None,
	) -> tuple[bool, object | None, str]:
		"""Return the target table cell object for the requested table coordinate.

		The direct IAccessibleTable2.cellAt(row, column) result is validated before
		use. If the direct result does not resolve to a cell covering the requested
		coordinate, fall back to ranked descendant lookup when tableObj is available.

		When sourceCellObj is provided, the direct and fallback paths must not
		accept the source cell itself as the target. This prevents false source spans
		from causing movement to stay on the same cell.
		"""
		self._markMoveTimingProbe1c(
			timing,
			"targetLookupInternalStartPerf",
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"targetLookup.targetRow",
			targetRow,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"targetLookup.targetColumn",
			targetColumn,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"targetLookup.table2ObjExists",
			table2Obj is not None,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"targetLookup.tableObjExists",
			tableObj is not None,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"targetLookup.sourceCellObjExists",
			sourceCellObj is not None,
		)

		def _finishReturn(
			ok: bool,
			targetObj: object | None,
			failReason: str,
			resultPath: str,
		) -> tuple[bool, object | None, str]:
			self._setMoveTimingProbe1cValue(
				timing,
				"targetLookup.resultPath",
				resultPath,
			)
			self._markMoveTimingProbe1c(
				timing,
				"targetLookupInternalEndPerf",
			)
			return ok, targetObj, failReason

		def _safeClassName(obj: object | None) -> str:
			if obj is None:
				return "<None>"

			try:
				return obj.__class__.__name__
			except Exception:
				return "<unknown>"

		def _safeModuleName(obj: object | None) -> str:
			if obj is None:
				return "<None>"

			try:
				return obj.__class__.__module__
			except Exception:
				return "<unknown>"

		def _safeAttr(obj: object | None, attrName: str):
			if obj is None:
				return None

			try:
				return getattr(obj, attrName, None)
			except Exception as e:
				return f"<error: {e!r}>"

		def _writeObjectBasics(prefix: str, obj: object | None) -> None:
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.exists",
				obj is not None,
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.class",
				_safeClassName(obj),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.module",
				_safeModuleName(obj),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.role",
				_safeAttr(obj, "role"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.description",
				_safeAttr(obj, "description"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.IA2UniqueID",
				_safeAttr(obj, "IA2UniqueID"),
			)

		def _writeContextBasics(prefix: str, context: dict[str, object] | None) -> None:
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.exists",
				context is not None,
			)
			if not isinstance(context, dict):
				return

			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.inTable",
				context.get("inTable"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.rowIndex",
				context.get("rowIndex"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.columnIndex",
				context.get("columnIndex"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.rowSpan",
				context.get("rowSpan"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.columnSpan",
				context.get("columnSpan"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.nRows",
				context.get("nRows"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.nColumns",
				context.get("nColumns"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.failStage",
				context.get("failStage", ""),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				f"{prefix}.failReason",
				context.get("failReason", ""),
			)

		def _contextCoversTarget(context: dict[str, object] | None) -> bool:
			try:
				return self._contextContainsCoordinate(
					context,
					targetRow,
					targetColumn,
				)
			except Exception:
				return False

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

		_writeObjectBasics(
			"targetLookup.sourceCellObj",
			sourceCellObj,
		)

		if sourceCellObj is not None:
			try:
				targetLookupDebug["sourceCellObjDescription"] = getattr(sourceCellObj, "description", None)
			except Exception:
				targetLookupDebug["sourceCellObjDescription"] = None

		self._lastTargetLookupDebug = targetLookupDebug

		if not isinstance(targetRow, int) or not isinstance(targetColumn, int):
			targetLookupDebug["directFailReason"] = "invalidTargetCoordinate"
			self._setMoveTimingProbe1cValue(
				timing,
				"targetLookup.directFailReason",
				"invalidTargetCoordinate",
			)
			return _finishReturn(
				False,
				None,
				"invalidTargetCoordinate",
				"invalidTargetCoordinate",
			)

		directFailReason = ""

		if table2Obj is not None:
			self._markMoveTimingProbe1c(
				timing,
				"targetLookupBeforeDirectCellAtPerf",
			)
			try:
				targetObj = table2Obj.cellAt(targetRow, targetColumn)
			except Exception as e:
				targetObj = None
				directFailReason = f"cellAtFailed: {e!r}"
				targetLookupDebug["directFailReason"] = directFailReason
				self._markMoveTimingProbe1c(
					timing,
					"targetLookupAfterDirectCellAtPerf",
				)
			else:
				self._markMoveTimingProbe1c(
					timing,
					"targetLookupAfterDirectCellAtPerf",
				)
				self._setMoveTimingProbe1cValue(
					timing,
					"targetLookup.directCellAtReturnedObject",
					targetObj is not None,
				)
				_writeObjectBasics(
					"targetLookup.directRawObject",
					targetObj,
				)

				if targetObj is not None:
					self._markMoveTimingProbe1c(
						timing,
						"targetLookupBeforeDirectTargetContextPerf",
					)
					try:
						targetContext = self.getContextFromObject(targetObj)
					except Exception as e:
						targetContext = None
						directFailReason = f"targetContextFailed: {e!r}"
						targetLookupDebug["directFailReason"] = directFailReason
						self._markMoveTimingProbe1c(
							timing,
							"targetLookupAfterDirectTargetContextPerf",
						)
					else:
						self._markMoveTimingProbe1c(
							timing,
							"targetLookupAfterDirectTargetContextPerf",
						)
						directFailReason = (
							targetContext.get("failReason", "") if targetContext else "targetContextMissing"
						)
						targetLookupDebug["directFailReason"] = directFailReason

					_writeContextBasics(
						"targetLookup.directContext",
						targetContext,
					)

					contextCellObj = targetContext.get("cellObj") if targetContext else None
					resolvedTargetObj = contextCellObj or targetObj

					_writeObjectBasics(
						"targetLookup.directContextCellObj",
						contextCellObj,
					)
					_writeObjectBasics(
						"targetLookup.directResolvedObject",
						resolvedTargetObj,
					)

					self._markMoveTimingProbe1c(
						timing,
						"targetLookupBeforeDirectCoordinateCheckPerf",
					)
					directTargetCoversRequestedCoordinate = _contextCoversTarget(targetContext)
					self._markMoveTimingProbe1c(
						timing,
						"targetLookupAfterDirectCoordinateCheckPerf",
					)

					directResolvedSameAsSource = False
					try:
						directResolvedSameAsSource = sourceCellObj is not None and self._isSameCellObject(
							resolvedTargetObj,
							sourceCellObj,
						)
					except Exception:
						directResolvedSameAsSource = False

					self._setMoveTimingProbe1cValue(
						timing,
						"targetLookup.directCoversTargetCoordinate",
						directTargetCoversRequestedCoordinate,
					)
					self._setMoveTimingProbe1cValue(
						timing,
						"targetLookup.directResolvedSameAsSource",
						directResolvedSameAsSource,
					)

					if directResolvedSameAsSource:
						directFailReason = "targetObjectIsSourceCell"
						targetLookupDebug["directRejectedBecauseSource"] = True
						targetLookupDebug["directFailReason"] = directFailReason
					elif directTargetCoversRequestedCoordinate:
						self._setMoveTimingProbe1cValue(
							timing,
							"targetLookup.directFailReason",
							"",
						)
						self._setMoveTimingProbe1cValue(
							timing,
							"targetLookup.directAccepted",
							True,
						)
						return _finishReturn(
							True,
							resolvedTargetObj,
							"",
							"direct",
						)
					else:
						directFailReason = "targetObjectDoesNotCoverRequestedCoordinate"
						targetLookupDebug["directFailReason"] = directFailReason
				else:
					directFailReason = "cellAtReturnedNone"
					targetLookupDebug["directFailReason"] = directFailReason
		else:
			directFailReason = "table2ObjMissing"
			targetLookupDebug["directFailReason"] = directFailReason

		self._setMoveTimingProbe1cValue(
			timing,
			"targetLookup.directAccepted",
			False,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"targetLookup.directFailReason",
			directFailReason,
		)

		if tableObj is not None:
			targetLookupDebug["fallbackAttempted"] = True

			self._markMoveTimingProbe1c(
				timing,
				"targetLookupBeforeFallbackDescendantPerf",
			)
			fallbackOk, fallbackObj, fallbackReason = self._findDescendantCellCoveringCoordinate(
				tableObj,
				targetRow,
				targetColumn,
				excludeCellObj=sourceCellObj,
				timing=timing,
			)
			self._markMoveTimingProbe1c(
				timing,
				"targetLookupAfterFallbackDescendantPerf",
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

			_writeObjectBasics(
				"targetLookup.fallbackObject",
				fallbackObj,
			)

			self._markMoveTimingProbe1c(
				timing,
				"targetLookupBeforeFallbackSelectedContextPerf",
			)
			try:
				fallbackContext = self.getContextFromObject(fallbackObj) if fallbackObj is not None else None
			except Exception as e:
				fallbackContext = {
					"inTable": False,
					"failStage": "fallbackSelectedContext",
					"failReason": f"fallbackSelectedContextFailed: {e!r}",
				}
			self._markMoveTimingProbe1c(
				timing,
				"targetLookupAfterFallbackSelectedContextPerf",
			)

			_writeContextBasics(
				"targetLookup.fallbackContext",
				fallbackContext,
			)

			fallbackCoversTargetCoordinate = _contextCoversTarget(fallbackContext)
			fallbackSameAsSource = False
			try:
				fallbackSameAsSource = sourceCellObj is not None and self._isSameCellObject(
					fallbackObj,
					sourceCellObj,
				)
			except Exception:
				fallbackSameAsSource = False

			self._setMoveTimingProbe1cValue(
				timing,
				"targetLookup.fallbackOk",
				fallbackOk,
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"targetLookup.fallbackReason",
				fallbackReason,
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"targetLookup.fallbackSelectedDescription",
				descendantDebug.get("selectedDescription"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"targetLookup.fallbackCoversTargetCoordinate",
				fallbackCoversTargetCoordinate,
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"targetLookup.fallbackSameAsSource",
				fallbackSameAsSource,
			)

			if fallbackOk:
				return _finishReturn(
					True,
					fallbackObj,
					"",
					"fallback",
				)

			return _finishReturn(
				False,
				None,
				fallbackReason or directFailReason or "targetObjectNotFound",
				"failedWithFallback",
			)

		return _finishReturn(
			False,
			None,
			directFailReason or "targetObjectNotFound",
			"failedNoFallback",
		)

	def getContextFromObject(self, obj: object | None) -> dict[str, object]:
		"""Return the IA2 table raw context for an object.

		This method is the raw IA2 context provider. It should collect source
		objects, IA2 row/column/span data, table size, and table-object identity
		materials. It must not create NVDA-style rowNumber/columnNumber values,
		TextInfo ControlFields, speech text, or braille text.
		"""
		context: dict[str, object] = {
			"inTable": False,
			"cellObj": None,
			"iaTableCell": None,
			"table2Obj": None,
			"tableObj": None,
			"tableObjClass": "",
			"tableObjModule": "",
			"tableObjRole": None,
			"tableObjName": None,
			"tableObjDescription": None,
			"tableObjIA2UniqueID": None,
			"tableObjWindowHandle": None,
			"tableObjProcessID": None,
			"tableObjChildCount": None,
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

		context["cellObj"] = cellObj

		tableObj = None
		try:
			tableObj = self._findAncestorTableObject(cellObj)
		except Exception:
			tableObj = None

		if tableObj is None:
			try:
				tableObj = getattr(cellObj, "parent", None)
			except Exception:
				tableObj = None

		context.update(self._getTableObjectIdentityRawFields(tableObj))

		iaTableCell = self.getIATableCellFromObject(cellObj)
		if iaTableCell is None:
			context["failStage"] = "getIATableCell"
			context["failReason"] = "iaTableCellNotFound"
			return context

		context["iaTableCell"] = iaTableCell

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

		table2Ok, table2Obj, table2FailReason = self.getIA2TableFromCell(iaTableCell)
		if not table2Ok:
			context["failStage"] = "getIA2TableFromCell"
			context["failReason"] = table2FailReason
			return context

		context["table2Obj"] = table2Obj

		sizeOk, nRows, nColumns, sizeFailReason = self.getTableSize(table2Obj)
		if not sizeOk:
			context["failStage"] = "getTableSize"
			context["failReason"] = sizeFailReason
			return context

		context["inTable"] = True
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
		"""Return normalized Writer IA2 table-cell information.

		This is the only place that converts IA2 raw context into NVDA-style
		table-cell data.

		Responsibilities:
		- Keep IA2 rowIndex / columnIndex as 0-based raw data.
		- Convert rowIndex / columnIndex into 1-based rowNumber / columnNumber.
		- Normalize rowSpan / columnSpan.
		- Compute rowEndNumber / columnEndNumber.
		- Build a stable tableID from raw table-object identity materials.

		This helper must not create TextInfo ControlFields and must not present
		anything to the user directly. TextInfo, speech, and braille code should
		consume the returned cellInfo.
		"""
		if not context or not context.get("inTable"):
			return {
				"inTable": False,
				"source": source,
				"failReason": (
					context.get("failReason", "notInTable") if isinstance(context, dict) else "contextMissing"
				),
				"failStage": (context.get("failStage", "") if isinstance(context, dict) else ""),
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
		rowEndNumber = rowNumber + rowSpan - 1
		columnEndNumber = columnNumber + columnSpan - 1

		tableObjProcessID = context.get("tableObjProcessID")
		tableObjWindowHandle = context.get("tableObjWindowHandle")
		tableObjIA2UniqueID = context.get("tableObjIA2UniqueID")

		tableID = ""
		tableIDSource = ""
		tableIDFailReason = ""

		if (
			tableObjProcessID is not None
			and tableObjWindowHandle is not None
			and tableObjIA2UniqueID is not None
		):
			tableID = "writer-ia2-table:%s:%s:%s" % (
				tableObjProcessID,
				tableObjWindowHandle,
				tableObjIA2UniqueID,
			)
			tableIDSource = "processID+windowHandle+tableIA2UniqueID"
		elif tableObjProcessID is not None and tableObjIA2UniqueID is not None:
			tableID = "writer-ia2-table:%s:%s" % (
				tableObjProcessID,
				tableObjIA2UniqueID,
			)
			tableIDSource = "processID+tableIA2UniqueID"
		elif tableObjWindowHandle is not None and tableObjIA2UniqueID is not None:
			tableID = "writer-ia2-table:%s:%s" % (
				tableObjWindowHandle,
				tableObjIA2UniqueID,
			)
			tableIDSource = "windowHandle+tableIA2UniqueID"
		else:
			tableIDFailReason = "identityFieldsMissing"

		return {
			"inTable": True,
			"source": source,
			# Table identity.
			"tableID": tableID,
			"tableIDSource": tableIDSource,
			"tableIDFailReason": tableIDFailReason,
			"tableObj": context.get("tableObj"),
			"tableObjClass": context.get("tableObjClass", ""),
			"tableObjModule": context.get("tableObjModule", ""),
			"tableObjRole": context.get("tableObjRole"),
			"tableObjName": context.get("tableObjName"),
			"tableObjDescription": context.get("tableObjDescription"),
			"tableObjIA2UniqueID": tableObjIA2UniqueID,
			"tableObjWindowHandle": tableObjWindowHandle,
			"tableObjProcessID": tableObjProcessID,
			"tableObjChildCount": context.get("tableObjChildCount"),
			# IA2 raw / 0-based data.
			"cellObj": context.get("cellObj"),
			"iaTableCell": context.get("iaTableCell"),
			"table2Obj": context.get("table2Obj"),
			"rowIndex": rowIndex,
			"columnIndex": columnIndex,
			"rowSpan": rowSpan,
			"columnSpan": columnSpan,
			"nRows": nRows,
			"nColumns": nColumns,
			# NVDA-style / user-facing 1-based properties.
			"rowNumber": rowNumber,
			"columnNumber": columnNumber,
			"rowEndNumber": rowEndNumber,
			"columnEndNumber": columnEndNumber,
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

	def getControlFieldProperties(
		self,
		cellInfo: dict[str, object],
	) -> dict[str, object]:
		"""Return TextInfo ControlField properties from normalized cellInfo.

		This is a field adapter only. It must not query IA2, compute row/column
		numbers from row/column indexes, or present anything to the user.
		"""
		result: dict[str, object] = {
			"ok": False,
			"failReason": "",
			"tableID": "",
			"tableField": None,
			"cellField": None,
		}

		if not cellInfo or not cellInfo.get("inTable"):
			result["failReason"] = (
				cellInfo.get("failReason", "notInTable") if isinstance(cellInfo, dict) else "cellInfoMissing"
			)
			return result

		tableID = cellInfo.get("tableID", "")
		if not tableID:
			result["failReason"] = cellInfo.get("tableIDFailReason") or "tableIDMissing"
			return result

		rowNumber = cellInfo.get("rowNumber")
		columnNumber = cellInfo.get("columnNumber")
		rowSpan = cellInfo.get("rowSpan")
		columnSpan = cellInfo.get("columnSpan")
		rowCount = cellInfo.get("nRows")
		columnCount = cellInfo.get("nColumns")

		if not isinstance(rowNumber, int) or not isinstance(columnNumber, int):
			result["failReason"] = "rowOrColumnNumberMissing"
			return result

		if not isinstance(rowSpan, int) or not isinstance(columnSpan, int):
			result["failReason"] = "rowOrColumnSpanMissing"
			return result

		try:
			import controlTypes
			import textInfos
		except Exception as e:
			result["failReason"] = "importFailed:%s" % e
			return result

		tableField = textInfos.ControlField()
		tableField["role"] = controlTypes.Role.TABLE
		tableField["table-id"] = tableID
		tableField["_startOfNode"] = True

		if isinstance(rowCount, int):
			tableField["table-rowcount"] = rowCount

		if isinstance(columnCount, int):
			tableField["table-columncount"] = columnCount

		cellField = textInfos.ControlField()
		cellField["role"] = controlTypes.Role.TABLECELL
		cellField["table-id"] = tableID
		cellField["table-rownumber"] = rowNumber
		cellField["table-columnnumber"] = columnNumber
		cellField["table-rowsspanned"] = rowSpan
		cellField["table-columnsspanned"] = columnSpan
		cellField["_startOfNode"] = True

		result.update(
			{
				"ok": True,
				"failReason": "",
				"tableID": tableID,
				"tableField": tableField,
				"cellField": cellField,
				"rowNumber": rowNumber,
				"columnNumber": columnNumber,
				"rowSpan": rowSpan,
				"columnSpan": columnSpan,
				"rowCount": rowCount,
				"columnCount": columnCount,
			},
		)
		return result

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

		return rowIndex <= row < rowIndex + rowSpan and columnIndex <= column < columnIndex + columnSpan

	def _sanitizeSourceCellSpan(
		self,
		context: dict[str, object],
		tableObj: object | None,
		direction: str | None = None,
		timing: dict | None = None,
	) -> tuple[int, int, dict[str, object]]:
		"""Return conservative source row/column spans for movement.

		Only validate the span axis that can affect the requested movement:
		down uses rowSpan, right uses columnSpan, while up and left do not
		use source span when computing the target coordinate.
		"""
		self._markMoveTimingProbe1c(
			timing,
			"sanitizeInternalStartPerf",
		)

		scanStats: dict[str, int] = {
			"foreignLookupCallCount": 0,
			"foreignLookupChildVisitCount": 0,
			"foreignLookupContextOkCount": 0,
			"foreignLookupCoveringCandidateCount": 0,
			"foreignLookupSourceExcludedCount": 0,
			"foreignLookupAcceptedCandidateCount": 0,
		}

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

		def _writeScanStats() -> None:
			for key, value in scanStats.items():
				self._setMoveTimingProbe1cValue(
					timing,
					f"sanitize.{key}",
					value,
				)

		def _finishReturn(
			returnReason: str,
		) -> tuple[int, int, dict[str, object]]:
			details["sourceEffectiveRowSpan"] = effectiveRowSpan
			details["sourceEffectiveColumnSpan"] = effectiveColumnSpan

			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.returnReason",
				returnReason,
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.finalRowSpan",
				effectiveRowSpan,
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.finalColumnSpan",
				effectiveColumnSpan,
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.sourceSpanSanityApplied",
				details.get("sourceSpanSanityApplied"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.sourceRowSpanClamped",
				details.get("sourceRowSpanClamped"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.sourceColumnSpanClamped",
				details.get("sourceColumnSpanClamped"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.sourceSpanSanityFailReason",
				details.get("sourceSpanSanityFailReason", ""),
			)
			_writeScanStats()

			self._markMoveTimingProbe1c(
				timing,
				"sanitizeInternalEndPerf",
			)
			return effectiveRowSpan, effectiveColumnSpan, details

		self._markMoveTimingProbe1c(
			timing,
			"sanitizeBeforeDecisionPerf",
		)

		sourceCoordinateValid = isinstance(rowIndex, int) and isinstance(columnIndex, int)
		tableObjExists = tableObj is not None

		directionUsesRowSpan = direction == "down"
		directionUsesColumnSpan = direction == "right"

		rowClampScanNeededBySpan = effectiveRowSpan > 1
		columnClampScanNeededBySpan = effectiveColumnSpan > 1

		rowScanEnabledForDirection = directionUsesRowSpan and rowClampScanNeededBySpan
		columnScanEnabledForDirection = directionUsesColumnSpan and columnClampScanNeededBySpan

		directionFastPathApplied = (
			sourceCoordinateValid and not rowScanEnabledForDirection and not columnScanEnabledForDirection
		)

		if direction in ("up", "left"):
			directionFastPathReason = f"{direction}DoesNotUseSourceSpan"
		elif direction == "down" and effectiveRowSpan == 1:
			directionFastPathReason = "downRowSpanAlready1"
		elif direction == "right" and effectiveColumnSpan == 1:
			directionFastPathReason = "rightColumnSpanAlready1"
		elif direction not in ("up", "down", "left", "right"):
			directionFastPathReason = "unknownDirection"
		else:
			directionFastPathReason = ""

		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.direction",
			direction,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.sourceRowIndex",
			rowIndex,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.sourceColumnIndex",
			columnIndex,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.nRows",
			nRows,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.nColumns",
			nColumns,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.rawRowSpan",
			rawRowSpan,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.rawColumnSpan",
			rawColumnSpan,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.initialEffectiveRowSpan",
			effectiveRowSpan,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.initialEffectiveColumnSpan",
			effectiveColumnSpan,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.sourceCoordinateValid",
			sourceCoordinateValid,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.tableObjExists",
			tableObjExists,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.directionUsesRowSpan",
			directionUsesRowSpan,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.directionUsesColumnSpan",
			directionUsesColumnSpan,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.rowClampScanNeededBySpan",
			rowClampScanNeededBySpan,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.columnClampScanNeededBySpan",
			columnClampScanNeededBySpan,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.rowScanEnabledForDirection",
			rowScanEnabledForDirection,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.columnScanEnabledForDirection",
			columnScanEnabledForDirection,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.directionFastPathApplied",
			directionFastPathApplied,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.directionFastPathReason",
			directionFastPathReason,
		)

		self._markMoveTimingProbe1c(
			timing,
			"sanitizeAfterDecisionPerf",
		)

		if not sourceCoordinateValid:
			details["sourceSpanSanityFailReason"] = "invalidSourceCoordinate"
			return _finishReturn("invalidSourceCoordinate")

		if directionFastPathApplied:
			return _finishReturn(
				f"directionFastPath:{directionFastPathReason}",
			)

		if tableObj is None:
			details["sourceSpanSanityFailReason"] = "tableObjMissing"
			return _finishReturn("tableObjMissing")

		self._markMoveTimingProbe1c(
			timing,
			"sanitizeBeforeDirectChildrenPerf",
		)
		try:
			directChildren = list(
				getattr(tableObj, "children", None) or [],
			)
		except Exception as e:
			details["sourceSpanSanityFailReason"] = f"childrenAccessFailed: {e!r}"
			self._markMoveTimingProbe1c(
				timing,
				"sanitizeAfterDirectChildrenPerf",
			)
			return _finishReturn("childrenAccessFailed")

		self._markMoveTimingProbe1c(
			timing,
			"sanitizeAfterDirectChildrenPerf",
		)

		details["sourceSpanSanityDirectChildCount"] = len(directChildren)

		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.directChildCount",
			len(directChildren),
		)

		self._markMoveTimingProbe1c(
			timing,
			"sanitizeBeforeSourceIdentityPerf",
		)

		sourceCellObj = context.get("cellObj")
		sourceCellObjIdentity = id(sourceCellObj) if sourceCellObj is not None else None

		try:
			sourceCellIA2UniqueID = getattr(
				sourceCellObj,
				"IA2UniqueID",
				None,
			)
		except Exception:
			sourceCellIA2UniqueID = None

		self._markMoveTimingProbe1c(
			timing,
			"sanitizeAfterSourceIdentityPerf",
		)

		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.sourceCellObjExists",
			sourceCellObj is not None,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"sanitize.sourceCellIA2UniqueID",
			sourceCellIA2UniqueID,
		)

		def isSourceCellObject(
			cellObj: object | None,
			cellContext: dict[str, object],
		) -> bool:
			if cellObj is None:
				return False

			if sourceCellObjIdentity is not None and id(cellObj) == sourceCellObjIdentity:
				return True

			try:
				cellIA2UniqueID = getattr(
					cellObj,
					"IA2UniqueID",
					None,
				)
			except Exception:
				cellIA2UniqueID = None

			if sourceCellIA2UniqueID is not None and cellIA2UniqueID == sourceCellIA2UniqueID:
				return True

			return cellContext.get("rowIndex") == rowIndex and cellContext.get("columnIndex") == columnIndex

		def getForeignCoveringCell(
			targetRow: int,
			targetColumn: int,
		) -> tuple[
			bool,
			object | None,
			dict[str, object] | None,
		]:
			candidates: list[
				tuple[
					int,
					int,
					int,
					object,
					dict[str, object],
				]
			] = []
			scanOrder = 0

			scanStats["foreignLookupCallCount"] += 1

			for child in directChildren:
				scanStats["foreignLookupChildVisitCount"] += 1

				try:
					childContext = self.getContextFromObject(child)
				except Exception:
					continue

				if not childContext or not childContext.get("inTable"):
					continue

				scanStats["foreignLookupContextOkCount"] += 1

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

				scanStats["foreignLookupCoveringCandidateCount"] += 1

				cellObj = childContext.get("cellObj") or child
				if isSourceCellObject(
					cellObj,
					childContext,
				):
					scanStats["foreignLookupSourceExcludedCount"] += 1
					continue

				exactStartPenalty = (
					0
					if (
						childContext.get("rowIndex") == targetRow
						and childContext.get("columnIndex") == targetColumn
					)
					else 1
				)

				spanArea = self._getContextSpanArea(
					childContext,
				)

				candidates.append(
					(
						exactStartPenalty,
						spanArea,
						scanOrder,
						cellObj,
						childContext,
					),
				)

				scanStats["foreignLookupAcceptedCandidateCount"] += 1
				scanOrder += 1

			if not candidates:
				return False, None, None

			candidates.sort(
				key=lambda item: (
					item[0],
					item[1],
					item[2],
				),
			)

			return (
				True,
				candidates[0][3],
				candidates[0][4],
			)

		if rowScanEnabledForDirection:
			self._markMoveTimingProbe1c(
				timing,
				"sanitizeBeforeRowClampScanPerf",
			)

			rowLimit = rowIndex + effectiveRowSpan
			if isinstance(nRows, int):
				rowLimit = min(rowLimit, nRows)

			rowClampCandidateCount = max(
				rowLimit - (rowIndex + 1),
				0,
			)

			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.rowClampCandidateCount",
				rowClampCandidateCount,
			)

			for checkRow in range(
				rowIndex + 1,
				rowLimit,
			):
				exists, blockerObj, blockerContext = getForeignCoveringCell(
					checkRow,
					columnIndex,
				)

				if not exists:
					continue

				effectiveRowSpan = max(
					checkRow - rowIndex,
					1,
				)

				details["sourceSpanSanityApplied"] = True
				details["sourceRowSpanClamped"] = True
				details["sourceRowSpanBlockerRow"] = checkRow

				try:
					details["sourceRowSpanBlockerDescription"] = getattr(
						blockerObj,
						"description",
						None,
					)
				except Exception:
					details["sourceRowSpanBlockerDescription"] = None

				break

			self._markMoveTimingProbe1c(
				timing,
				"sanitizeAfterRowClampScanPerf",
			)
		else:
			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.rowClampCandidateCount",
				0,
			)

		if columnScanEnabledForDirection:
			self._markMoveTimingProbe1c(
				timing,
				"sanitizeBeforeColumnClampScanPerf",
			)

			columnLimit = columnIndex + effectiveColumnSpan
			if isinstance(nColumns, int):
				columnLimit = min(
					columnLimit,
					nColumns,
				)

			columnClampCandidateCount = max(
				columnLimit - (columnIndex + 1),
				0,
			)

			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.columnClampCandidateCount",
				columnClampCandidateCount,
			)

			for checkColumn in range(
				columnIndex + 1,
				columnLimit,
			):
				exists, blockerObj, blockerContext = getForeignCoveringCell(
					rowIndex,
					checkColumn,
				)

				if not exists:
					continue

				effectiveColumnSpan = max(
					checkColumn - columnIndex,
					1,
				)

				details["sourceSpanSanityApplied"] = True
				details["sourceColumnSpanClamped"] = True
				details["sourceColumnSpanBlockerColumn"] = checkColumn

				try:
					details["sourceColumnSpanBlockerDescription"] = getattr(
						blockerObj,
						"description",
						None,
					)
				except Exception:
					details["sourceColumnSpanBlockerDescription"] = None

				break

			self._markMoveTimingProbe1c(
				timing,
				"sanitizeAfterColumnClampScanPerf",
			)
		else:
			self._setMoveTimingProbe1cValue(
				timing,
				"sanitize.columnClampCandidateCount",
				0,
			)

		return _finishReturn("completed")

	def _findAncestorTableObject(self, obj: object | None) -> object | None:
		"""Find the nearest ancestor table object for a Writer IA2 cell."""
		if obj is None:
			return None

		try:
			import controlTypes
		except Exception:
			return None

		current = obj
		for _ in range(10):
			if current is None:
				return None

			try:
				if getattr(current, "role", None) == controlTypes.Role.TABLE:
					return current
			except Exception:
				pass

			try:
				current = getattr(current, "parent", None)
			except Exception:
				return None

		return None

	def _getTableObjectIdentityRawFields(
		self,
		tableObj: object | None,
	) -> dict[str, object]:
		"""Return raw table-object identity materials.

		This helper does not build a formal table-id. It only collects raw
		materials that a later normalized cellInfo layer can use to build a stable
		table identity.
		"""
		fields: dict[str, object] = {
			"tableObj": tableObj,
			"tableObjClass": "",
			"tableObjModule": "",
			"tableObjRole": None,
			"tableObjName": None,
			"tableObjDescription": None,
			"tableObjIA2UniqueID": None,
			"tableObjWindowHandle": None,
			"tableObjProcessID": None,
			"tableObjChildCount": None,
		}

		if tableObj is None:
			return fields

		try:
			fields["tableObjClass"] = tableObj.__class__.__name__
		except Exception:
			fields["tableObjClass"] = ""

		try:
			fields["tableObjModule"] = tableObj.__class__.__module__
		except Exception:
			fields["tableObjModule"] = ""

		try:
			fields["tableObjRole"] = getattr(tableObj, "role", None)
		except Exception:
			fields["tableObjRole"] = None

		try:
			fields["tableObjName"] = getattr(tableObj, "name", None)
		except Exception:
			fields["tableObjName"] = None

		try:
			fields["tableObjDescription"] = getattr(tableObj, "description", None)
		except Exception:
			fields["tableObjDescription"] = None

		try:
			fields["tableObjIA2UniqueID"] = getattr(tableObj, "IA2UniqueID", None)
		except Exception:
			fields["tableObjIA2UniqueID"] = None

		try:
			fields["tableObjWindowHandle"] = getattr(tableObj, "windowHandle", None)
		except Exception:
			fields["tableObjWindowHandle"] = None

		processID = None
		try:
			processID = getattr(tableObj, "processID", None)
		except Exception:
			processID = None

		if processID is None:
			try:
				processID = getattr(getattr(tableObj, "appModule", None), "processID", None)
			except Exception:
				processID = None

		fields["tableObjProcessID"] = processID

		try:
			fields["tableObjChildCount"] = getattr(tableObj, "childCount", None)
		except Exception:
			fields["tableObjChildCount"] = None

		return fields

	def _getWriterIA2TableIdentityDebug(self, cellObj: object | None) -> dict[str, object]:
		"""Return debug information for a Writer IA2 table identity candidate.

		This is diagnostic-only. Do not use this as a formal TextInfo table-id
		until stability and collision probes pass.
		"""
		debug: dict[str, object] = {
			"tableObjExists": False,
			"candidateTableID": "",
			"candidateTableIDSource": "",
			"candidateTableIDFailReason": "",
		}

		if cellObj is None:
			debug["candidateTableIDFailReason"] = "cellObjMissing"
			return debug

		context: dict[str, object] = {}
		try:
			context = self.getContextFromObject(cellObj) or {}
		except Exception:
			context = {}

		tableObj = (
			context.get("tableObj")
			or context.get("tableNVDAObject")
			or context.get("table")
			or self._findAncestorTableObject(cellObj)
		)

		if tableObj is None:
			debug["candidateTableIDFailReason"] = "tableObjMissing"
			return debug

		debug["tableObjExists"] = True
		debug["tableObjClass"] = tableObj.__class__.__name__
		debug["tableObjModule"] = tableObj.__class__.__module__
		debug["tableObjRole"] = getattr(tableObj, "role", None)
		debug["tableObjName"] = getattr(tableObj, "name", None)
		debug["tableObjDescription"] = getattr(tableObj, "description", None)
		debug["tableObjIA2UniqueID"] = getattr(tableObj, "IA2UniqueID", None)
		debug["tableObjWindowHandle"] = getattr(tableObj, "windowHandle", None)
		debug["tableObjChildCount"] = getattr(tableObj, "childCount", None)

		processID = getattr(tableObj, "processID", None)
		if processID is None:
			try:
				processID = getattr(getattr(tableObj, "appModule", None), "processID", None)
			except Exception:
				processID = None

		windowHandle = getattr(tableObj, "windowHandle", None)
		ia2UniqueID = getattr(tableObj, "IA2UniqueID", None)

		debug["tableObjProcessID"] = processID
		debug["tableObjWindowHandle"] = windowHandle
		debug["tableObjIA2UniqueID"] = ia2UniqueID

		try:
			debug["tableObjLocation"] = repr(getattr(tableObj, "location", None))
		except Exception:
			debug["tableObjLocation"] = ""

		rowCount = context.get("nRows")
		columnCount = context.get("nColumns")
		debug["tableNRows"] = rowCount
		debug["tableNColumns"] = columnCount

		if processID is not None and windowHandle is not None and ia2UniqueID is not None:
			debug["candidateTableID"] = "writer-ia2-table:%s:%s:%s" % (
				processID,
				windowHandle,
				ia2UniqueID,
			)
			debug["candidateTableIDSource"] = "processID+windowHandle+tableIA2UniqueID"
			return debug

		if processID is not None and ia2UniqueID is not None:
			debug["candidateTableID"] = "writer-ia2-table:%s:%s" % (
				processID,
				ia2UniqueID,
			)
			debug["candidateTableIDSource"] = "processID+tableIA2UniqueID"
			return debug

		if windowHandle is not None and ia2UniqueID is not None:
			debug["candidateTableID"] = "writer-ia2-table:%s:%s" % (
				windowHandle,
				ia2UniqueID,
			)
			debug["candidateTableIDSource"] = "windowHandle+tableIA2UniqueID"
			return debug

		debug["candidateTableIDFailReason"] = "identityFieldsMissing"
		return debug

	def _buildWriterIA2TableControlFieldCandidate(self, cellObj: object | None) -> dict[str, object]:
		"""Build Writer IA2 table / tableCell ControlField candidates.

		This is a compatibility wrapper for existing callers. The data flow is:

		cellObj
		-> getContextFromObject()
		-> normalizeCellInfo()
		-> getControlFieldProperties()

		Callers should continue to consume tableField and cellField from the
		returned candidate.
		"""
		result: dict[str, object] = {
			"ok": False,
			"failReason": "",
			"tableID": "",
			"tableField": None,
			"cellField": None,
		}

		if cellObj is None:
			result["failReason"] = "cellObjMissing"
			return result

		try:
			context = self.getContextFromObject(cellObj) or {}
		except Exception as e:
			result["failReason"] = "contextFailed:%s" % e
			return result

		if not context.get("inTable"):
			result["failReason"] = context.get("failReason") or "notInTable"
			result["context"] = context
			return result

		try:
			cellInfo = self.normalizeCellInfo(context)
		except Exception as e:
			result["failReason"] = "normalizeCellInfoFailed:%s" % e
			result["context"] = context
			return result

		if not cellInfo.get("inTable"):
			result["failReason"] = cellInfo.get("failReason") or "notInTable"
			result["context"] = context
			result["cellInfo"] = cellInfo
			return result

		try:
			fieldResult = self.getControlFieldProperties(cellInfo)
		except Exception as e:
			result["failReason"] = "getControlFieldPropertiesFailed:%s" % e
			result["context"] = context
			result["cellInfo"] = cellInfo
			return result

		if not fieldResult.get("ok"):
			result["failReason"] = fieldResult.get("failReason") or "controlFieldPropertiesFailed"
			result["context"] = context
			result["cellInfo"] = cellInfo
			result["fieldResult"] = fieldResult
			return result

		identityDebug = {
			"tableObjExists": cellInfo.get("tableObj") is not None,
			"candidateTableID": cellInfo.get("tableID", ""),
			"candidateTableIDSource": cellInfo.get("tableIDSource", ""),
			"candidateTableIDFailReason": cellInfo.get("tableIDFailReason", ""),
			"tableObjClass": cellInfo.get("tableObjClass", ""),
			"tableObjModule": cellInfo.get("tableObjModule", ""),
			"tableObjRole": cellInfo.get("tableObjRole"),
			"tableObjName": cellInfo.get("tableObjName"),
			"tableObjDescription": cellInfo.get("tableObjDescription"),
			"tableObjIA2UniqueID": cellInfo.get("tableObjIA2UniqueID"),
			"tableObjWindowHandle": cellInfo.get("tableObjWindowHandle"),
			"tableObjProcessID": cellInfo.get("tableObjProcessID"),
			"tableObjChildCount": cellInfo.get("tableObjChildCount"),
			"tableNRows": cellInfo.get("nRows"),
			"tableNColumns": cellInfo.get("nColumns"),
		}

		result.update(
			{
				"ok": True,
				"failReason": "",
				"tableID": fieldResult.get("tableID", ""),
				"tableField": fieldResult.get("tableField"),
				"cellField": fieldResult.get("cellField"),
				"rowNumber": fieldResult.get("rowNumber"),
				"columnNumber": fieldResult.get("columnNumber"),
				"rowSpan": fieldResult.get("rowSpan"),
				"columnSpan": fieldResult.get("columnSpan"),
				"rowCount": fieldResult.get("rowCount"),
				"columnCount": fieldResult.get("columnCount"),
				"identityDebug": identityDebug,
				"context": context,
				"cellInfo": cellInfo,
				"fieldResult": fieldResult,
			},
		)
		return result

	def _markMoveTimingProbe1c(
		self,
		timing: dict | None,
		key: str,
	) -> None:
		if not isinstance(timing, dict):
			return

		try:
			import time

			timing[key] = time.perf_counter()
		except Exception:
			pass

	def _setMoveTimingProbe1cValue(
		self,
		timing: dict | None,
		key: str,
		value,
	) -> None:
		if not isinstance(timing, dict):
			return

		try:
			timing[key] = value
		except Exception:
			pass

	def moveToCoordinate(
		self,
		context: dict[str, object],
		targetRow: int,
		targetColumn: int,
		result: dict[str, object],
		allowSourceCell: bool = False,
		timing: dict | None = None,
	) -> dict[str, object]:
		"""Move to a specific table coordinate using the existing target lookup and focus route.

		:param context: Current Writer IA2 table context.
		:param targetRow: Zero-based target row.
		:param targetColumn: Zero-based target column.
		:param result: Existing navigation result dictionary.
		:param allowSourceCell: Whether the current source cell may be accepted as the target.
		:param timing: Optional timing dictionary for move timing probes.
		:return: The updated navigation result dictionary.
		"""
		table2Obj = context.get("table2Obj")
		sourceCellObj = context.get("cellObj")
		tableObj = context.get("tableObj")

		if tableObj is None:
			try:
				tableObj = getattr(sourceCellObj, "parent", None) if sourceCellObj is not None else None
			except Exception:
				tableObj = None

		result["targetRow"] = targetRow
		result["targetColumn"] = targetColumn

		lookupSourceCellObj = None if allowSourceCell else sourceCellObj

		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeTargetLookupPerf",
		)
		targetOk, targetNVDAObject, targetFailReason = self.getTargetNVDAObject(
			table2Obj,
			targetRow,
			targetColumn,
			tableObj=tableObj,
			sourceCellObj=lookupSourceCellObj,
			timing=timing,
		)
		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterTargetLookupPerf",
		)

		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetLookupOk",
			targetOk,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetLookupFailReason",
			targetFailReason,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetObjectExists",
			targetNVDAObject is not None,
		)

		try:
			self._setMoveTimingProbe1cValue(
				timing,
				"navigator.targetObjectClass",
				targetNVDAObject.__class__.__name__ if targetNVDAObject is not None else "<None>",
			)
		except Exception:
			pass

		if not targetOk:
			return self._fail(
				result,
				"getTargetNVDAObject",
				targetFailReason,
			)

		result["targetNVDAObject"] = targetNVDAObject
		result["targetNVDAObjectClass"] = targetNVDAObject.__class__.__name__
		result["targetNVDAObjectModule"] = targetNVDAObject.__class__.__module__
		result["targetNVDAObjectRole"] = getattr(
			targetNVDAObject,
			"role",
			None,
		)

		# Verify the target object before moving focus.
		# In block-merged tables, getTargetNVDAObject may return a merged
		# owner cell that does not actually cover the requested coordinate.
		# Do not call setFocus until this is known to be safe.
		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeTargetVerifyContextPerf",
		)
		targetContext = self.getContextFromObject(
			targetNVDAObject,
		)
		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterTargetVerifyContextPerf",
		)

		targetObjectRowIndex = targetContext.get(
			"rowIndex",
		)
		targetObjectColumnIndex = targetContext.get(
			"columnIndex",
		)
		targetObjectRowSpan = targetContext.get(
			"rowSpan",
		)
		targetObjectColumnSpan = targetContext.get(
			"columnSpan",
		)

		result["targetObjectRowIndex"] = targetObjectRowIndex
		result["targetObjectColumnIndex"] = targetObjectColumnIndex
		result["targetObjectRowSpan"] = targetObjectRowSpan
		result["targetObjectColumnSpan"] = targetObjectColumnSpan

		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeTargetCoordinateVerifyPerf",
		)
		targetObjectMatchesTarget = self._contextContainsCoordinate(
			targetContext,
			targetRow,
			targetColumn,
		)
		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterTargetCoordinateVerifyPerf",
		)

		result["targetObjectMatchesTarget"] = targetObjectMatchesTarget

		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetContextInTable",
			targetContext.get("inTable"),
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetObjectRowIndex",
			targetObjectRowIndex,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetObjectColumnIndex",
			targetObjectColumnIndex,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetObjectRowSpan",
			targetObjectRowSpan,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetObjectColumnSpan",
			targetObjectColumnSpan,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetObjectMatchesTarget",
			targetObjectMatchesTarget,
		)

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

		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeTargetSetFocusPerf",
		)

		try:
			targetNVDAObject.setFocus()
			setFocusOk = True
		except Exception as e:
			setFocusFailReason = repr(e)

		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterTargetSetFocusPerf",
		)

		result["setFocusOk"] = setFocusOk

		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetSetFocusOk",
			setFocusOk,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetSetFocusFailReason",
			setFocusFailReason,
		)

		if not setFocusOk:
			return self._fail(
				result,
				"setFocus",
				setFocusFailReason,
			)

		apiSetFocusObjectOk = False
		apiSetFocusObjectFailReason = ""

		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeApiSetFocusObjectPerf",
		)

		try:
			api.setFocusObject(
				targetNVDAObject,
			)
			apiSetFocusObjectOk = True
		except Exception as e:
			apiSetFocusObjectFailReason = repr(e)

		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterApiSetFocusObjectPerf",
		)

		result["apiSetFocusObjectOk"] = apiSetFocusObjectOk
		result["apiSetFocusObjectFailReason"] = apiSetFocusObjectFailReason

		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.apiSetFocusObjectOk",
			apiSetFocusObjectOk,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.apiSetFocusObjectFailReason",
			apiSetFocusObjectFailReason,
		)

		# Keep legacy after* fields for existing probes.
		# These describe the accepted target object, not necessarily
		# a fresh focus event from NVDA.
		result["afterRowIndex"] = targetObjectRowIndex
		result["afterColumnIndex"] = targetObjectColumnIndex
		result["afterRowSpan"] = targetObjectRowSpan
		result["afterColumnSpan"] = targetObjectColumnSpan

		apiFocusRowIndex = None
		apiFocusColumnIndex = None
		apiFocusRowSpan = None
		apiFocusColumnSpan = None
		apiFocusMatchesTarget = False

		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeApiFocusCheckPerf",
		)

		try:
			apiFocusObj = api.getFocusObject()
			apiFocusContext = self.getContextFromObject(
				apiFocusObj,
			)

			apiFocusRowIndex = apiFocusContext.get(
				"rowIndex",
			)
			apiFocusColumnIndex = apiFocusContext.get(
				"columnIndex",
			)
			apiFocusRowSpan = apiFocusContext.get(
				"rowSpan",
			)
			apiFocusColumnSpan = apiFocusContext.get(
				"columnSpan",
			)

			apiFocusMatchesTarget = self._contextContainsCoordinate(
				apiFocusContext,
				targetRow,
				targetColumn,
			)
		except Exception:
			apiFocusMatchesTarget = False

		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterApiFocusCheckPerf",
		)

		result["apiFocusRowIndex"] = apiFocusRowIndex
		result["apiFocusColumnIndex"] = apiFocusColumnIndex
		result["apiFocusRowSpan"] = apiFocusRowSpan
		result["apiFocusColumnSpan"] = apiFocusColumnSpan
		result["apiFocusMatchesTarget"] = apiFocusMatchesTarget

		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.apiFocusRowIndex",
			apiFocusRowIndex,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.apiFocusColumnIndex",
			apiFocusColumnIndex,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.apiFocusMatchesTarget",
			apiFocusMatchesTarget,
		)

		# Keep this legacy field for existing probes.
		# Here it means the target object matches the requested target cell,
		# not necessarily that api.getFocusObject() has already updated.
		result["landedOnTarget"] = targetObjectMatchesTarget

		result["ok"] = True
		result["moved"] = True

		return result

	def moveToBoundary(
		self,
		obj: object | None,
		movement: str,
		axis: str,
		timing: dict | None = None,
	) -> dict[str, object]:
		"""Move to the first or last table cell on the requested axis.

		:param obj: Starting NVDAObject.
		:param movement: Either first or last.
		:param axis: Either row or column.
		:param timing: Optional timing dictionary for move timing probes.
		:return: A stable navigation result dictionary.
		"""
		if movement not in ("first", "last"):
			result = self._newResult("boundary")
			return self._fail(
				result,
				"validateBoundaryMovement",
				"unsupportedBoundaryMovement",
			)

		if axis not in ("row", "column"):
			result = self._newResult("boundary")
			return self._fail(
				result,
				"validateBoundaryAxis",
				"unsupportedBoundaryAxis",
			)

		operation = f"{movement}{axis[0].upper()}{axis[1:]}"
		result = self._newResult(operation)

		self._markMoveTimingProbe1c(
			timing,
			"navigatorInternalStartPerf",
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.direction",
			operation,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.boundaryMovement",
			movement,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.boundaryAxis",
			axis,
		)

		def _finishReturn(
			moveResult: dict[str, object],
		) -> dict[str, object]:
			self._markMoveTimingProbe1c(
				timing,
				"navigatorInternalEndPerf",
			)
			return moveResult

		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeGetCurrentContextPerf",
		)
		context = self.getContextFromObject(obj)
		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterGetCurrentContextPerf",
		)

		if not context.get("inTable"):
			return _finishReturn(
				self._fail(
					result,
					str(
						context.get(
							"failStage",
							"",
						),
					),
					str(
						context.get(
							"failReason",
							"",
						),
					),
				),
			)

		rowIndex = context.get("rowIndex")
		columnIndex = context.get(
			"columnIndex",
		)
		nRows = context.get("nRows")
		nColumns = context.get("nColumns")

		if not isinstance(rowIndex, int) or not isinstance(columnIndex, int):
			return _finishReturn(
				self._fail(
					result,
					"validateCoordinates",
					"invalidCoordinates",
				),
			)

		if not isinstance(nRows, int) or not isinstance(nColumns, int) or nRows <= 0 or nColumns <= 0:
			return _finishReturn(
				self._fail(
					result,
					"validateTableSize",
					"invalidTableSize",
				),
			)

		result["beforeRowIndex"] = rowIndex
		result["beforeColumnIndex"] = columnIndex
		result["nRows"] = nRows
		result["nColumns"] = nColumns

		targetRow = rowIndex
		targetColumn = columnIndex

		if movement == "first":
			if axis == "row":
				targetRow = 0
			else:
				targetColumn = 0
		else:
			if axis == "row":
				targetRow = nRows - 1
			else:
				targetColumn = nColumns - 1

		result["targetRow"] = targetRow
		result["targetColumn"] = targetColumn

		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetRow",
			targetRow,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetColumn",
			targetColumn,
		)

		return _finishReturn(
			self.moveToCoordinate(
				context,
				targetRow,
				targetColumn,
				result,
				allowSourceCell=True,
				timing=timing,
			),
		)

	def move(
		self,
		obj: object | None,
		direction: str,
		timing: dict | None = None,
	) -> dict[str, object]:
		"""Move one table cell in the requested direction.

		:param obj: Starting NVDAObject.
		:param direction: One of up, down, left, or right.
		:param timing: Optional timing dictionary for move timing probes.
		:return: A stable result dictionary for scripts and probes.
		"""
		self._markMoveTimingProbe1c(
			timing,
			"navigatorInternalStartPerf",
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.direction",
			direction,
		)

		result = self._newResult(direction)

		def _finishReturn(moveResult: dict[str, object]) -> dict[str, object]:
			self._markMoveTimingProbe1c(
				timing,
				"navigatorInternalEndPerf",
			)
			return moveResult

		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeGetCurrentContextPerf",
		)
		context = self.getContextFromObject(obj)
		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterGetCurrentContextPerf",
		)

		try:
			self._setMoveTimingProbe1cValue(
				timing,
				"navigator.contextInTable",
				bool(context.get("inTable")),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"navigator.contextRowIndex",
				context.get("rowIndex"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"navigator.contextColumnIndex",
				context.get("columnIndex"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"navigator.contextRowSpan",
				context.get("rowSpan"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"navigator.contextColumnSpan",
				context.get("columnSpan"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"navigator.contextNRows",
				context.get("nRows"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"navigator.contextNColumns",
				context.get("nColumns"),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"navigator.contextFailStage",
				context.get("failStage", ""),
			)
			self._setMoveTimingProbe1cValue(
				timing,
				"navigator.contextFailReason",
				context.get("failReason", ""),
			)
		except Exception:
			pass

		if not context["inTable"]:
			return _finishReturn(
				self._fail(
					result,
					str(context["failStage"]),
					str(context["failReason"]),
				),
			)

		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeValidateContextPerf",
		)

		rowIndex = context["rowIndex"]
		columnIndex = context["columnIndex"]
		rowSpan = context.get("rowSpan") or 1
		columnSpan = context.get("columnSpan") or 1
		nRows = context["nRows"]
		nColumns = context["nColumns"]
		if not isinstance(rowIndex, int) or not isinstance(columnIndex, int):
			self._markMoveTimingProbe1c(
				timing,
				"navigatorAfterValidateContextPerf",
			)
			return _finishReturn(
				self._fail(result, "validateCoordinates", "invalidCoordinates"),
			)

		try:
			rowSpan = max(int(rowSpan), 1)
		except Exception:
			rowSpan = 1

		try:
			columnSpan = max(int(columnSpan), 1)
		except Exception:
			columnSpan = 1

		if not isinstance(nRows, int) or not isinstance(nColumns, int):
			self._markMoveTimingProbe1c(
				timing,
				"navigatorAfterValidateContextPerf",
			)
			return _finishReturn(
				self._fail(result, "validateTableSize", "invalidTableSize"),
			)

		sourceCellObj = context.get("cellObj")
		tableObj = context.get("tableObj")
		if tableObj is None:
			try:
				tableObj = getattr(sourceCellObj, "parent", None) if sourceCellObj is not None else None
			except Exception:
				tableObj = None

		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterValidateContextPerf",
		)

		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeSanitizeSourceSpanPerf",
		)
		rowSpan, columnSpan, sourceSpanDetails = self._sanitizeSourceCellSpan(
			context,
			tableObj,
			direction=direction,
			timing=timing,
		)
		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterSanitizeSourceSpanPerf",
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

		self._markMoveTimingProbe1c(
			timing,
			"navigatorBeforeTargetCoordinatePerf",
		)
		targetOk, targetRow, targetColumn, targetFailReason = self.computeTargetCell(
			rowIndex,
			columnIndex,
			nRows,
			nColumns,
			direction,
			rowSpan=rowSpan,
			columnSpan=columnSpan,
		)
		self._markMoveTimingProbe1c(
			timing,
			"navigatorAfterTargetCoordinatePerf",
		)

		result["targetRow"] = targetRow
		result["targetColumn"] = targetColumn

		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetRow",
			targetRow,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetColumn",
			targetColumn,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetOk",
			targetOk,
		)
		self._setMoveTimingProbe1cValue(
			timing,
			"navigator.targetFailReason",
			targetFailReason,
		)

		if not targetOk:
			edgeReason = self._getEdgeReason(
				direction,
				targetRow,
				targetColumn,
				nRows,
				nColumns,
			)
			return _finishReturn(
				self._edge(result, edgeReason, targetRow, targetColumn),
			)

		if not isinstance(targetRow, int) or not isinstance(targetColumn, int):
			return _finishReturn(
				self._fail(result, "computeTargetCell", targetFailReason),
			)

		return _finishReturn(
			self.moveToCoordinate(
				context,
				targetRow,
				targetColumn,
				result,
				allowSourceCell=False,
				timing=timing,
			),
		)

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
	try:
		import config

		if not config.conf["documentFormatting"]["reportTableCellCoords"]:
			return ""
	except Exception:
		pass

	targetRow = result.get("targetRow")
	targetColumn = result.get("targetColumn")

	if isinstance(targetRow, int) and isinstance(targetColumn, int):
		# Translators: fallback speech for a Writer table cell location.
		return "%s %s" % (
			_("row %s") % (targetRow + 1),
			_("column %s") % (targetColumn + 1),
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
		# Translators: Reported when a Writer table cell has no text, followed by the cell coordinates.
		return f"{_('blank')}, {coordinateText}"

	# Translators: Reported when a Writer table cell has no text and table coordinates are not reported.
	return _("blank")


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
