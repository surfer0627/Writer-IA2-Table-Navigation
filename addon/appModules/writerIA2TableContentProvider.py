"""Writer IA2 table content provider.

This module is import-time inert.

Layer 3 responsibility:
	table identity + row / column
	→ cell object
	→ cell text
	→ row / column cell sequence

This module must not call ui.message, speech, or braille directly.
"""

from __future__ import annotations


class WriterIA2TableContentProvider:
	"""Provide cell, row, and column text content for Writer IA2 tables."""

	def __init__(
		self,
		module: object | None = None,
		navigator: object | None = None,
	) -> None:
		self._module = module
		self._navigator = navigator

	def buildTableContextFromObject(
		self,
		obj: object,
	) -> dict:
		"""Build a table context from the current focus / cell object."""
		result = {
			"ok": False,
			"failStage": "",
			"failReason": "",
			"context": None,
			"cellInfo": None,
			"tableObj": None,
			"cellObj": None,
			"tableID": "",
			"rowNumber": None,
			"columnNumber": None,
			"rowSpan": 1,
			"columnSpan": 1,
			"rowEndNumber": None,
			"columnEndNumber": None,
			"nRows": None,
			"nColumns": None,
			"cellMap": None,
			"cellMapResult": None,
		}

		module, navigator = self._getModuleAndNavigator()
		if module is None or navigator is None:
			result["failStage"] = "makeNavigator"
			result["failReason"] = "navigatorUnavailable"
			return result

		context = self._getContext(module, navigator, obj)
		if not isinstance(context, dict):
			result["failStage"] = "getContext"
			result["failReason"] = "contextNotDict"
			return result

		if not (context.get("inTable") or context.get("contextInTable") or context.get("ok")):
			result["failStage"] = "getContext"
			result["failReason"] = context.get("failReason", "notInTable")
			return result

		cellObj = self._firstExistingValue(
			context,
			("cellObj", "obj", "focusObj"),
		)
		if cellObj is None:
			cellObj = obj

		cellInfo = self._normalizeCellInfo(
			module,
			navigator,
			context,
			cellObj,
		)
		if not isinstance(cellInfo, dict):
			result["failStage"] = "normalizeCellInfo"
			result["failReason"] = "cellInfoNotDict"
			return result

		tableObj = self._getTableObjFromContext(context)

		result["context"] = context
		result["cellInfo"] = cellInfo
		result["tableObj"] = tableObj
		result["cellObj"] = cellObj

		self._fillCellInfo(result, cellInfo)

		if not result["tableID"]:
			result["failStage"] = "normalizeCellInfo"
			result["failReason"] = "missingTableID"
			return result

		result["ok"] = True
		return result

	def getCellContent(
		self,
		tableContext: dict,
		rowNumber: int,
		columnNumber: int,
	) -> dict:
		"""Return CellContentInfo for one row / column slot."""
		result = self._makeCellContentResult(
			tableContext,
			rowNumber,
			columnNumber,
		)

		cellMapResult = self._ensureCellMap(tableContext)
		if not cellMapResult.get("ok"):
			result["failStage"] = "buildCellMap"
			result["failReason"] = cellMapResult.get("failReason", "")
			return result

		cellMap = cellMapResult.get("cellMap", {})
		lookup = self.lookupCell(
			cellMap,
			rowNumber,
			columnNumber,
		)
		if not lookup.get("ok"):
			result["failStage"] = "lookupCell"
			result["failReason"] = lookup.get("failReason", "")
			return result

		entry = lookup.get("entry", {})
		cellObj = entry.get("cellObj")
		cellInfo = entry.get("cellInfo", {})

		result["ok"] = True
		result["cellObjExists"] = cellObj is not None
		self._fillObjectSummary(result, "cellObj", cellObj)

		result["coveredByMergedCell"] = bool(lookup.get("coveredByMergedCell"))
		result["sourceRowNumber"] = lookup.get("sourceRowNumber")
		result["sourceColumnNumber"] = lookup.get("sourceColumnNumber")

		self._fillCellInfo(result, cellInfo)

		result["rowNumber"] = rowNumber
		result["columnNumber"] = columnNumber

		result["rowHeaderText"] = (
			cellInfo.get("rowHeaderText", "") or cellInfo.get("table-rowheadertext", "") or ""
		)
		result["columnHeaderText"] = (
			cellInfo.get("columnHeaderText", "") or cellInfo.get("table-columnheadertext", "") or ""
		)

		hiddenResult = self._isHiddenOrInvisibleCell(cellObj)
		result["hidden"] = bool(hiddenResult.get("hidden"))
		result["hiddenReason"] = hiddenResult.get("reason", "")

		textResult = self.getCellText(cellObj)
		result["textMakeOk"] = bool(textResult.get("ok"))
		result["text"] = textResult.get("text", "")
		result["textLength"] = len(result["text"])
		result["textSource"] = textResult.get("textSource", "")
		result["textFailReason"] = textResult.get("failReason", "")
		result["empty"] = result["textMakeOk"] and result["text"] == ""

		return result

	def getRowContent(
		self,
		tableContext: dict,
		rowNumber: int | None = None,
	) -> dict:
		"""Return RowContentResult for the requested row."""
		if rowNumber is None:
			rowNumber = tableContext.get("rowNumber")

		result = {
			"ok": False,
			"failStage": "",
			"failReason": "",
			"tableID": tableContext.get("tableID", ""),
			"rowNumber": rowNumber,
			"nColumns": tableContext.get("nColumns"),
			"cells": [],
			"cellCount": 0,
			"texts": [],
			"combinedText": "",
			"cellOrder": "leftToRight",
			"partial": False,
			"missingColumns": "",
			"textExtractionFailureCount": 0,
			"textExtractionFailureCoordinates": "",
		}

		try:
			rowNumber = int(rowNumber)
			nColumns = int(tableContext.get("nColumns"))
		except Exception:
			result["failStage"] = "validate"
			result["failReason"] = "missingRowOrColumnCount"
			return result

		missingColumns = []
		textFailureCoordinates = []

		for columnNumber in range(1, nColumns + 1):
			cell = self.getCellContent(
				tableContext,
				rowNumber,
				columnNumber,
			)
			if not cell.get("ok"):
				missingColumns.append(str(columnNumber))
				continue

			result["cells"].append(cell)
			result["texts"].append(cell.get("text", ""))
			result["cellCount"] += 1

			if not cell.get("textMakeOk"):
				textFailureCoordinates.append(f"{rowNumber},{columnNumber}")

		result["combinedText"] = "\t".join(result["texts"])
		result["missingColumns"] = ",".join(missingColumns)
		result["partial"] = bool(missingColumns)
		result["textExtractionFailureCount"] = len(textFailureCoordinates)
		result["textExtractionFailureCoordinates"] = ";".join(
			textFailureCoordinates,
		)

		result["ok"] = not result["partial"]
		if not result["ok"]:
			result["failStage"] = "buildRow"
			result["failReason"] = "missingColumns"

		return result

	def getColumnContent(
		self,
		tableContext: dict,
		columnNumber: int | None = None,
	) -> dict:
		"""Return ColumnContentResult for the requested column."""
		if columnNumber is None:
			columnNumber = tableContext.get("columnNumber")

		result = {
			"ok": False,
			"failStage": "",
			"failReason": "",
			"tableID": tableContext.get("tableID", ""),
			"columnNumber": columnNumber,
			"nRows": tableContext.get("nRows"),
			"cells": [],
			"cellCount": 0,
			"texts": [],
			"combinedText": "",
			"cellOrder": "topToBottom",
			"partial": False,
			"missingRows": "",
			"textExtractionFailureCount": 0,
			"textExtractionFailureCoordinates": "",
		}

		try:
			columnNumber = int(columnNumber)
			nRows = int(tableContext.get("nRows"))
		except Exception:
			result["failStage"] = "validate"
			result["failReason"] = "missingColumnOrRowCount"
			return result

		missingRows = []
		textFailureCoordinates = []

		for rowNumber in range(1, nRows + 1):
			cell = self.getCellContent(
				tableContext,
				rowNumber,
				columnNumber,
			)
			if not cell.get("ok"):
				missingRows.append(str(rowNumber))
				continue

			result["cells"].append(cell)
			result["texts"].append(cell.get("text", ""))
			result["cellCount"] += 1

			if not cell.get("textMakeOk"):
				textFailureCoordinates.append(f"{rowNumber},{columnNumber}")

		result["combinedText"] = "\t".join(result["texts"])
		result["missingRows"] = ",".join(missingRows)
		result["partial"] = bool(missingRows)
		result["textExtractionFailureCount"] = len(textFailureCoordinates)
		result["textExtractionFailureCoordinates"] = ";".join(
			textFailureCoordinates,
		)

		result["ok"] = not result["partial"]
		if not result["ok"]:
			result["failStage"] = "buildColumn"
			result["failReason"] = "missingRows"

		return result

	def buildCellMap(
		self,
		tableContext: dict,
	) -> dict:
		"""Build a coordinate → cell object map for the current table."""
		module, navigator = self._getModuleAndNavigator()
		if module is None or navigator is None:
			return {
				"ok": False,
				"failReason": "navigatorUnavailable",
				"cellMap": {},
			}

		context = tableContext.get("context")
		cellInfo = tableContext.get("cellInfo")
		currentCellObj = tableContext.get("cellObj")
		tableObj = tableContext.get("tableObj")

		if not isinstance(context, dict) or not isinstance(cellInfo, dict):
			return {
				"ok": False,
				"failReason": "missingTableContext",
				"cellMap": {},
			}

		cellMap = {}
		duplicateCoordinates = []
		candidates = []

		if currentCellObj is not None:
			candidates.append(currentCellObj)

		if tableObj is not None:
			for obj in self._iterObjectTree(tableObj, maxObjects=300, maxDepth=6):
				candidates.append(obj)

		seenIdentities = set()
		uniqueCandidates = []
		for obj in candidates:
			identity = self._getObjectIdentity(obj)
			if identity in seenIdentities:
				continue
			seenIdentities.add(identity)
			uniqueCandidates.append(obj)

		tableID = cellInfo.get("tableID", "")

		for obj in uniqueCandidates:
			objContext = self._getContext(module, navigator, obj)
			if not isinstance(objContext, dict):
				continue

			objCellInfo = self._normalizeCellInfo(
				module,
				navigator,
				objContext,
				obj,
			)
			if not isinstance(objCellInfo, dict):
				continue

			objTableID = objCellInfo.get("tableID", "")
			if tableID and objTableID and objTableID != tableID:
				continue

			try:
				rowNumber = int(objCellInfo.get("rowNumber"))
				columnNumber = int(objCellInfo.get("columnNumber"))
			except Exception:
				continue

			key = (rowNumber, columnNumber)
			if key in cellMap:
				duplicateCoordinates.append(f"{rowNumber},{columnNumber}")
				continue

			objCellInfo = self._normalizeCellInfoSpanValues(objCellInfo)

			cellMap[key] = {
				"cellObj": self._firstExistingValue(
					objContext,
					("cellObj", "obj", "focusObj"),
				)
				or obj,
				"cellInfo": objCellInfo,
			}

		coordinates = sorted(cellMap.keys())
		coordinateText = ";".join(f"{row},{column}" for row, column in coordinates)

		result = {
			"ok": bool(cellMap),
			"failReason": "" if cellMap else "noCellsMapped",
			"candidateCount": len(uniqueCandidates),
			"mappedCellCount": len(cellMap),
			"duplicateCoordinateDetected": bool(duplicateCoordinates),
			"duplicateCoordinates": ";".join(duplicateCoordinates),
			"coordinates": coordinateText,
			"cellMap": cellMap,
		}

		tableContext["cellMap"] = cellMap
		tableContext["cellMapResult"] = result
		return result

	def lookupCell(
		self,
		cellMap: dict,
		rowNumber: int,
		columnNumber: int,
	) -> dict:
		"""Lookup a direct or span-covered cell entry."""
		try:
			rowNumber = int(rowNumber)
			columnNumber = int(columnNumber)
		except Exception:
			return {
				"ok": False,
				"failReason": "invalidRowOrColumn",
			}

		direct = cellMap.get((rowNumber, columnNumber))
		if direct is not None:
			return {
				"ok": True,
				"entry": direct,
				"coveredByMergedCell": False,
				"sourceRowNumber": rowNumber,
				"sourceColumnNumber": columnNumber,
			}

		for entry in cellMap.values():
			info = entry.get("cellInfo", {})
			try:
				startRow = int(info.get("rowNumber"))
				endRow = int(info.get("rowEndNumber") or startRow)
				startColumn = int(info.get("columnNumber"))
				endColumn = int(info.get("columnEndNumber") or startColumn)
			except Exception:
				continue

			if startRow <= rowNumber <= endRow and startColumn <= columnNumber <= endColumn:
				return {
					"ok": True,
					"entry": entry,
					"coveredByMergedCell": True,
					"sourceRowNumber": startRow,
					"sourceColumnNumber": startColumn,
				}

		return {
			"ok": False,
			"failReason": "cellNotFound",
		}

	def getCellText(
		self,
		cellObj: object,
	) -> dict:
		"""Return text from a cell object.

		Observed route:
			SymphonyIATableCell → child → makeTextInfo(POSITION_ALL)
		"""
		textResult = self._getCellTextWithoutChildScan(cellObj)
		if textResult.get("ok"):
			return textResult

		childText = self._getFirstChildText(cellObj)
		if childText.get("ok"):
			return childText

		return textResult

	def _ensureCellMap(
		self,
		tableContext: dict,
	) -> dict:
		existing = tableContext.get("cellMapResult")
		if isinstance(existing, dict) and existing.get("ok"):
			return existing

		return self.buildCellMap(tableContext)

	def _makeCellContentResult(
		self,
		tableContext: dict,
		rowNumber: int,
		columnNumber: int,
	) -> dict:
		return {
			"ok": False,
			"failStage": "",
			"failReason": "",
			"tableID": tableContext.get("tableID", ""),
			"rowNumber": rowNumber,
			"columnNumber": columnNumber,
			"rowSpan": 1,
			"columnSpan": 1,
			"rowEndNumber": rowNumber,
			"columnEndNumber": columnNumber,
			"rowHeaderText": "",
			"columnHeaderText": "",
			"cellObjExists": False,
			"cellObjClass": "",
			"cellObjModule": "",
			"cellObjIA2UniqueID": None,
			"text": "",
			"textLength": 0,
			"textSource": "",
			"textMakeOk": False,
			"textFailReason": "",
			"empty": False,
			"coveredByMergedCell": False,
			"sourceRowNumber": rowNumber,
			"sourceColumnNumber": columnNumber,
			"hidden": False,
			"hiddenReason": "",
		}

	def _getModuleAndNavigator(self) -> tuple[object | None, object | None]:
		if self._module is not None and self._navigator is not None:
			return self._module, self._navigator

		module, navigator = self._makeNavigator()
		self._module = module
		self._navigator = navigator
		return module, navigator

	def _makeNavigator(self) -> tuple[object | None, object | None]:
		import importlib

		moduleNames = (
			"common.writerTableNavCore",
			"writerTableNavCore",
			"appModules.writerTableNavCore",
		)

		for moduleName in moduleNames:
			try:
				module = importlib.import_module(moduleName)
				navigatorClass = getattr(module, "WriterIA2TableNavigator", None)
				if navigatorClass is None:
					continue
				return module, navigatorClass()
			except Exception:
				continue

		return None, None

	def _getContext(
		self,
		module: object,
		navigator: object,
		obj: object,
	) -> dict | None:
		return self._callFirst(
			module,
			navigator,
			(
				"getContextFromObject",
				"getContextFromObj",
				"getContext",
			),
			(obj,),
		)

	def _normalizeCellInfo(
		self,
		module: object,
		navigator: object,
		context: dict,
		cellObj: object,
	) -> dict | None:
		cellInfo = self._callFirst(
			module,
			navigator,
			("normalizeCellInfo",),
			(context,),
		)
		if isinstance(cellInfo, dict):
			return cellInfo

		candidate = self._callFirst(
			module,
			navigator,
			("_buildWriterIA2TableControlFieldCandidate",),
			(cellObj,),
		)
		if isinstance(candidate, dict):
			cellInfo = candidate.get("cellInfo")
			if isinstance(cellInfo, dict):
				return cellInfo

		return None

	def _normalizeCellInfoSpanValues(
		self,
		cellInfo: dict,
	) -> dict:
		if not isinstance(cellInfo, dict):
			return cellInfo

		cellInfo = dict(cellInfo)

		rowNumber = self._asInt(
			cellInfo.get("rowNumber"),
			None,
		)
		columnNumber = self._asInt(
			cellInfo.get("columnNumber"),
			None,
		)
		rowEndNumber = self._asInt(
			cellInfo.get("rowEndNumber"),
			rowNumber,
		)
		columnEndNumber = self._asInt(
			cellInfo.get("columnEndNumber"),
			columnNumber,
		)

		rowSpan = self._asInt(
			cellInfo.get("rowSpan"),
			None,
		)
		columnSpan = self._asInt(
			cellInfo.get("columnSpan"),
			None,
		)

		if rowSpan is None or rowSpan <= 1:
			rowSpan = self._calculateSpan(
				rowNumber,
				rowEndNumber,
			)

		if columnSpan is None or columnSpan <= 1:
			columnSpan = self._calculateSpan(
				columnNumber,
				columnEndNumber,
			)

		cellInfo["rowNumber"] = rowNumber
		cellInfo["columnNumber"] = columnNumber
		cellInfo["rowEndNumber"] = rowEndNumber
		cellInfo["columnEndNumber"] = columnEndNumber
		cellInfo["rowSpan"] = rowSpan
		cellInfo["columnSpan"] = columnSpan

		return cellInfo

	def _getTableObjFromContext(
		self,
		context: dict,
	) -> object | None:
		return self._firstExistingValue(
			context,
			(
				"tableObj",
				"table2Obj",
				"table",
				"tableObject",
				"parentTableObj",
			),
		)

	def _fillCellInfo(
		self,
		result: dict,
		cellInfo: dict,
	) -> None:
		result["tableID"] = (
			cellInfo.get("tableID", "") or cellInfo.get("tableId", "") or result.get("tableID", "")
		)

		rowNumber = self._asInt(
			cellInfo.get("rowNumber", result.get("rowNumber")),
			result.get("rowNumber"),
		)
		columnNumber = self._asInt(
			cellInfo.get("columnNumber", result.get("columnNumber")),
			result.get("columnNumber"),
		)

		rowEndNumber = self._asInt(
			cellInfo.get("rowEndNumber", result.get("rowEndNumber")),
			None,
		)
		columnEndNumber = self._asInt(
			cellInfo.get("columnEndNumber", result.get("columnEndNumber")),
			None,
		)

		if rowEndNumber is None:
			rowEndNumber = rowNumber
		if columnEndNumber is None:
			columnEndNumber = columnNumber

		rowSpan = self._asInt(
			cellInfo.get("rowSpan", result.get("rowSpan")),
			None,
		)
		columnSpan = self._asInt(
			cellInfo.get("columnSpan", result.get("columnSpan")),
			None,
		)

		if rowSpan is None or rowSpan <= 1:
			rowSpan = self._calculateSpan(
				rowNumber,
				rowEndNumber,
			)

		if columnSpan is None or columnSpan <= 1:
			columnSpan = self._calculateSpan(
				columnNumber,
				columnEndNumber,
			)

		result["rowNumber"] = rowNumber
		result["columnNumber"] = columnNumber
		result["rowSpan"] = rowSpan
		result["columnSpan"] = columnSpan
		result["rowEndNumber"] = rowEndNumber
		result["columnEndNumber"] = columnEndNumber

		result["nRows"] = cellInfo.get("nRows", result.get("nRows"))
		result["nColumns"] = cellInfo.get("nColumns", result.get("nColumns"))

	def _calculateSpan(
		self,
		startNumber,
		endNumber,
	) -> int:
		try:
			startNumber = int(startNumber)
			endNumber = int(endNumber)
		except Exception:
			return 1

		if endNumber < startNumber:
			return 1

		return endNumber - startNumber + 1

	def _asInt(
		self,
		value,
		default,
	):
		if value is None:
			return default

		try:
			return int(value)
		except Exception:
			return default

	def _getCellText(
		self,
		cellObj: object,
	) -> dict:
		return self.getCellText(cellObj)

	def _getCellTextWithoutChildScan(
		self,
		cellObj: object,
	) -> dict:
		if cellObj is None:
			return {
				"ok": False,
				"text": "",
				"textSource": "",
				"failReason": "missingCellObj",
			}

		try:
			import textInfos

			info = cellObj.makeTextInfo(textInfos.POSITION_ALL)
			text = info.text
			if text is None:
				text = ""
			return {
				"ok": True,
				"text": text,
				"textSource": "makeTextInfo(POSITION_ALL)",
				"failReason": "",
			}
		except Exception:
			pass

		try:
			text = cellObj.name
			if text is not None:
				return {
					"ok": True,
					"text": text,
					"textSource": "name",
					"failReason": "",
				}
		except Exception:
			pass

		try:
			text = cellObj.value
			if text is not None:
				return {
					"ok": True,
					"text": text,
					"textSource": "value",
					"failReason": "",
				}
		except Exception:
			pass

		return {
			"ok": False,
			"text": "",
			"textSource": "",
			"failReason": "noTextSourceWorked",
		}

	def _getFirstChildText(
		self,
		obj: object,
	) -> dict:
		try:
			childCount = obj.childCount
		except Exception:
			childCount = 0

		try:
			child = obj.firstChild
		except Exception:
			child = None

		index = 0
		while child is not None and index < 20:
			textResult = self._getCellTextWithoutChildScan(child)
			if textResult.get("ok"):
				return {
					"ok": True,
					"text": textResult.get("text", ""),
					"textSource": "child:" + textResult.get("textSource", ""),
					"failReason": "",
				}

			try:
				child = child.next
			except Exception:
				child = None

			index += 1

		return {
			"ok": False,
			"text": "",
			"textSource": "",
			"failReason": f"noChildText:childCount={childCount}",
		}

	def _iterObjectTree(
		self,
		root: object,
		maxObjects: int = 300,
		maxDepth: int = 6,
	):
		visited = set()
		stack = [(root, 0)]
		count = 0

		while stack and count < maxObjects:
			obj, depth = stack.pop()
			if obj is None:
				continue

			identity = self._getObjectIdentity(obj)
			if identity in visited:
				continue
			visited.add(identity)

			yield obj
			count += 1

			if depth >= maxDepth:
				continue

			children = []
			try:
				child = obj.firstChild
			except Exception:
				child = None

			childIndex = 0
			while child is not None and childIndex < 100:
				children.append(child)
				try:
					child = child.next
				except Exception:
					child = None
				childIndex += 1

			for childObj in reversed(children):
				stack.append((childObj, depth + 1))

	def _isHiddenOrInvisibleCell(
		self,
		cellObj: object,
	) -> dict:
		if cellObj is None:
			return {
				"hidden": False,
				"reason": "missingCellObj",
			}

		try:
			location = cellObj.location
			width = getattr(location, "width", None)
			height = getattr(location, "height", None)
			if width == 0 or height == 0:
				return {
					"hidden": True,
					"reason": "zeroSizeLocation",
				}
		except Exception:
			pass

		try:
			states = cellObj.states
			statesText = repr(states).upper()
			if "INVISIBLE" in statesText or "OFFSCREEN" in statesText:
				return {
					"hidden": True,
					"reason": "stateInvisibleOrOffscreen",
				}
		except Exception:
			pass

		return {
			"hidden": False,
			"reason": "",
		}

	def _callFirst(
		self,
		module: object,
		navigator: object,
		methodNames: tuple[str, ...],
		args: tuple,
	):
		for methodName in methodNames:
			for owner in (navigator, module):
				method = getattr(owner, methodName, None)
				if method is None:
					continue
				try:
					return method(*args)
				except Exception:
					continue
		return None

	def _firstExistingValue(
		self,
		source: dict,
		keys: tuple[str, ...],
	) -> object | None:
		for key in keys:
			if key in source and source.get(key) is not None:
				return source.get(key)
		return None

	def _fillObjectSummary(
		self,
		result: dict,
		prefix: str,
		obj: object,
	) -> None:
		if obj is None:
			return

		try:
			result[f"{prefix}Class"] = obj.__class__.__name__
		except Exception:
			pass

		try:
			result[f"{prefix}Module"] = obj.__class__.__module__
		except Exception:
			pass

		try:
			result[f"{prefix}IA2UniqueID"] = obj.IA2UniqueID
		except Exception:
			pass

	def _getObjectIdentity(
		self,
		obj: object,
	) -> tuple:
		if obj is None:
			return ("none",)

		try:
			return ("ia2", obj.windowHandle, obj.IA2UniqueID)
		except Exception:
			pass

		try:
			return ("id", id(obj))
		except Exception:
			return ("repr", repr(obj))
