"""Writer IA2 table SayAll commands.

This module is import-time inert.

Responsibility:
	Writer IA2 table content provider
	→ TextInfo sequence
	→ sayAll.SayAllHandler.readText(CURSOR.TABLE, ...)

This module does not call ui.message directly.
The app module script layer is responsible for user-facing error messages.
"""

from __future__ import annotations

DEBUG_ENABLE_WRITER_SAYALL_LANDING_FALLBACK = False


class WriterIA2SayAllTableTextInfoWrapper:
	"""TextInfo wrapper that injects Writer IA2 table fields for SayAll.

	The inner TextInfo remains responsible for object lifetime, bookmark,
	text, caret movement and selection behavior.

	This wrapper only adds table / cell control fields to getTextWithFields().
	"""

	def __init__(
		self,
		innerInfo: object,
		tableContext: dict,
		entry: dict,
	):
		self._innerInfo = innerInfo
		self._tableContext = dict(tableContext or {})
		self._entry = dict(entry or {})

	def __getattr__(
		self,
		name: str,
	):
		return getattr(
			self._innerInfo,
			name,
		)

	def __repr__(
		self,
	) -> str:
		return (
			f"{self.__class__.__name__}("
			f"inner={self._innerInfo!r}, "
			f"row={self._entry.get('rowNumber')!r}, "
			f"column={self._entry.get('columnNumber')!r})"
		)

	@property
	def obj(
		self,
	):
		return self._innerInfo.obj

	@property
	def bookmark(
		self,
	):
		return self._innerInfo.bookmark

	@property
	def text(
		self,
	):
		return self._innerInfo.text

	@property
	def isCollapsed(
		self,
	):
		return self._innerInfo.isCollapsed

	def copy(
		self,
	):
		return self.__class__(
			self._innerInfo.copy(),
			self._tableContext,
			self._entry,
		)

	def getTextWithFields(
		self,
		*args,
		**kwargs,
	):
		from .writerIA2TableFields import WriterIA2TableFieldBuilder

		fieldStream = list(
			self._innerInfo.getTextWithFields(
				*args,
				**kwargs,
			),
		)

		return WriterIA2TableFieldBuilder().injectTableFieldsIntoFieldStream(
			fieldStream,
			self._tableContext,
			self._entry,
		)

	def updateCaret(
		self,
	):
		return self._innerInfo.updateCaret()

	def updateSelection(
		self,
	):
		return self._innerInfo.updateSelection()

	def collapse(
		self,
		*args,
		**kwargs,
	):
		return self._innerInfo.collapse(
			*args,
			**kwargs,
		)

	def expand(
		self,
		*args,
		**kwargs,
	):
		return self._innerInfo.expand(
			*args,
			**kwargs,
		)

	def move(
		self,
		*args,
		**kwargs,
	):
		return self._innerInfo.move(
			*args,
			**kwargs,
		)

	def setEndPoint(
		self,
		other,
		which,
	):
		if isinstance(other, self.__class__):
			other = other._innerInfo

		return self._innerInfo.setEndPoint(
			other,
			which,
		)

	def compareEndPoints(
		self,
		other,
		which,
	):
		if isinstance(other, self.__class__):
			other = other._innerInfo

		return self._innerInfo.compareEndPoints(
			other,
			which,
		)


class WriterIA2EmptyCellSayAllTextInfo:
	"""Minimal empty TextInfo used by Writer table SayAll.

	This object represents a table cell for which Writer / IA2 did not expose a
	usable cell text. It intentionally returns empty text, but still injects table
	and cell control fields so SayAll can announce coordinates and continue to the
	next entry.
	"""

	def __init__(
		self,
		anchorInfo: object | None,
		tableContext: dict,
		entry: dict,
		cellObj: object | None = None,
	):
		self._anchorInfo = anchorInfo
		self._tableContext = dict(tableContext or {})
		self._entry = dict(entry or {})
		self._cellObj = cellObj
		self._writerIA2SayAllEmptyCell = True
		self._writerIA2SayAllEntryCoordinate = (
			self._entry.get("rowNumber"),
			self._entry.get("columnNumber"),
		)

	def __repr__(
		self,
	) -> str:
		return (
			f"{self.__class__.__name__}("
			f"row={self._entry.get('rowNumber')!r}, "
			f"column={self._entry.get('columnNumber')!r})"
		)

	def __getattr__(
		self,
		name: str,
	):
		if self._anchorInfo is None:
			raise AttributeError(name)
		return getattr(
			self._anchorInfo,
			name,
		)

	@property
	def obj(
		self,
	):
		if self._anchorInfo is None:
			return None

		try:
			return self._anchorInfo.obj
		except Exception:
			return None

	@property
	def bookmark(
		self,
	):
		if self._anchorInfo is None:
			return None

		try:
			return self._anchorInfo.bookmark
		except Exception:
			return None

	@property
	def text(
		self,
	):
		return ""

	@property
	def isCollapsed(
		self,
	):
		return False

	def copy(
		self,
	):
		return self.__class__(
			self._anchorInfo,
			self._tableContext,
			self._entry,
			self._cellObj,
		)

	def getTextWithFields(
		self,
		*args,
		**kwargs,
	):
		from .writerIA2TableFields import WriterIA2TableFieldBuilder

		return WriterIA2TableFieldBuilder().injectTableFieldsIntoFieldStream(
			[""],
			self._tableContext,
			self._entry,
		)

	def getControlFieldSpeech(
		self,
		*args,
		**kwargs,
	):
		if self._anchorInfo is not None:
			try:
				return self._anchorInfo.getControlFieldSpeech(
					*args,
					**kwargs,
				)
			except AttributeError:
				pass
		return []

	def getFormatFieldSpeech(
		self,
		*args,
		**kwargs,
	):
		if self._anchorInfo is not None:
			try:
				return self._anchorInfo.getFormatFieldSpeech(
					*args,
					**kwargs,
				)
			except AttributeError:
				pass
		return []

	def updateCaret(
		self,
	):
		return None

	def updateSelection(
		self,
	):
		return None

	def collapse(
		self,
		*args,
		**kwargs,
	):
		return None

	def expand(
		self,
		*args,
		**kwargs,
	):
		return None

	def move(
		self,
		*args,
		**kwargs,
	):
		return 0

	def setEndPoint(
		self,
		other,
		which,
	):
		return None

	def compareEndPoints(
		self,
		other,
		which,
	):
		return 0


class WriterIA2MultiChildCellTextInfo:
	"""TextInfo wrapper for a Writer table cell with multiple paragraph children.

	The table cell itself may not expose IAccessibleTextObject, while each
	paragraph child exposes its own TextInfo. This wrapper represents those child
	TextInfos as one cell TextInfo so table SayAll reads the whole cell without
	treating each paragraph as a separate table position.
	"""

	def __init__(
		self,
		childInfos: list,
	):
		self._childInfos = [info for info in childInfos if info is not None]

	def __repr__(self):
		return f"<WriterIA2MultiChildCellTextInfo childCount={len(self._childInfos)}>"

	def __getattr__(self, name: str):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			raise AttributeError(name)
		return getattr(firstInfo, name)

	def _getFirstInfo(self):
		if not self._childInfos:
			return None
		return self._childInfos[0]

	@property
	def obj(self):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return None
		return getattr(firstInfo, "obj", None)

	@property
	def bookmark(self):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return None
		return getattr(firstInfo, "bookmark", None)

	@property
	def text(self):
		parts = []
		for info in self._childInfos:
			try:
				text = info.text
			except Exception:
				text = ""
			if text:
				parts.append(text)
		return "\n".join(parts)

	@property
	def isCollapsed(self):
		return False

	def copy(self):
		childInfos = []
		for info in self._childInfos:
			try:
				childInfos.append(info.copy())
			except Exception:
				childInfos.append(info)
		return self.__class__(childInfos)

	def getTextWithFields(self, *args, **kwargs):
		fields = []
		for index, info in enumerate(self._childInfos):
			if index:
				fields.append("\n")

			try:
				childFields = info.getTextWithFields(*args, **kwargs)
			except Exception:
				try:
					text = info.text
				except Exception:
					text = ""
				childFields = [text]

			fields.extend(childFields)

		return fields

	def getControlFieldSpeech(
		self,
		*args,
		**kwargs,
	):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return []
		try:
			return firstInfo.getControlFieldSpeech(*args, **kwargs)
		except AttributeError:
			return []

	def getFormatFieldSpeech(
		self,
		*args,
		**kwargs,
	):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return []
		try:
			return firstInfo.getFormatFieldSpeech(*args, **kwargs)
		except AttributeError:
			return []

	def updateCaret(self, *args, **kwargs):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return
		return firstInfo.updateCaret(*args, **kwargs)

	def updateSelection(self, *args, **kwargs):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return
		return firstInfo.updateSelection(*args, **kwargs)

	def collapse(self, *args, **kwargs):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return
		return firstInfo.collapse(*args, **kwargs)

	def expand(self, *args, **kwargs):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return
		return firstInfo.expand(*args, **kwargs)

	def move(self, *args, **kwargs):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return 0
		return firstInfo.move(*args, **kwargs)

	def setEndPoint(self, *args, **kwargs):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return
		return firstInfo.setEndPoint(*args, **kwargs)

	def compareEndPoints(self, *args, **kwargs):
		firstInfo = self._getFirstInfo()
		if firstInfo is None:
			return 0
		return firstInfo.compareEndPoints(*args, **kwargs)


class WriterIA2TableSayAllHandler:
	"""Run SayAll row / column for Writer IA2 tables."""

	def __init__(
		self,
		provider: object | None = None,
		updateCaret: bool = False,
	) -> None:
		self._provider = provider
		self._updateCaret = updateCaret

	def sayAllRow(
		self,
		focusObj: object,
	) -> dict:
		"""Say all from the current cell rightwards to the last cell in the row."""
		return self._sayAll(
			focusObj,
			command="sayAllRow",
			direction="row",
		)

	def sayAllColumn(
		self,
		focusObj: object,
	) -> dict:
		"""Say all from the current cell downwards to the last cell in the column."""
		return self._sayAll(
			focusObj,
			command="sayAllColumn",
			direction="column",
		)

	def _sayAll(
		self,
		focusObj: object,
		command: str,
		direction: str,
	) -> dict:
		result = self._makeResult(command, direction)

		provider = self._getProvider()
		if provider is None:
			result["failStage"] = "makeProvider"
			result["failReason"] = "providerUnavailable"
			result["message"] = self._messageForFailure(result)
			return result

		tableContext = provider.buildTableContextFromObject(focusObj)
		result["tableContextMakeOk"] = bool(tableContext.get("ok"))
		result["tableContextFailStage"] = tableContext.get("failStage", "")
		result["tableContextFailReason"] = tableContext.get("failReason", "")

		if not tableContext.get("ok"):
			result["failStage"] = "buildTableContext"
			result["failReason"] = tableContext.get("failReason", "notInTable")
			result["message"] = self._messageForTableContextFailure(tableContext)
			return result

		self._fillTableContext(result, tableContext)

		cellMapResult = provider.buildCellMap(tableContext)
		result["cellMapBuildOk"] = bool(cellMapResult.get("ok"))
		result["cellMapFailReason"] = cellMapResult.get("failReason", "")
		result["cellMapCandidateCount"] = cellMapResult.get("candidateCount", 0)
		result["cellMapMappedCellCount"] = cellMapResult.get("mappedCellCount", 0)
		result["cellMapDuplicateCoordinateDetected"] = bool(
			cellMapResult.get("duplicateCoordinateDetected"),
		)
		result["cellMapDuplicateCoordinates"] = cellMapResult.get(
			"duplicateCoordinates",
			"",
		)

		if not cellMapResult.get("ok"):
			result["failStage"] = "buildCellMap"
			result["failReason"] = cellMapResult.get("failReason", "cellMapBuildFailed")
			result["message"] = self._messageForFailure(result)
			return result

		cellMap = cellMapResult.get("cellMap", {})

		if direction == "row":
			sequence = self._buildSayAllRowSequence(
				provider,
				tableContext,
				cellMap,
			)
		elif direction == "column":
			sequence = self._buildSayAllColumnSequence(
				provider,
				tableContext,
				cellMap,
			)
		else:
			result["failStage"] = "validate"
			result["failReason"] = f"unknownDirection:{direction}"
			result["message"] = self._messageForFailure(result)
			return result

		self._fillSequenceResult(result, sequence)

		if not sequence.get("ok"):
			result["failStage"] = "buildSequence"
			result["failReason"] = sequence.get("failReason", "sequenceFailed")
			result["message"] = self._messageForFailure(result)
			return result

		entries = sequence.get("entries", [])
		if not entries:
			result["failStage"] = "buildSequence"
			result["failReason"] = "emptySequence"
			result["message"] = self._messageForFailure(result)
			return result

		sayAllResult = self._callSayAllHandler(
			provider,
			tableContext,
			cellMap,
			entries,
		)
		self._fillSayAllResult(result, sayAllResult)

		if not sayAllResult.get("ok"):
			result["failStage"] = "callSayAll"
			result["failReason"] = sayAllResult.get("failReason", "sayAllFailed")
			result["message"] = self._messageForFailure(result)
			return result

		result["ok"] = True
		result["message"] = ""
		return result

	def _getProvider(
		self,
	) -> object | None:
		if self._provider is not None:
			return self._provider

		try:
			from .writerIA2TableContentProvider import WriterIA2TableContentProvider
		except Exception:
			return None

		self._provider = WriterIA2TableContentProvider()
		return self._provider

	def _makeResult(
		self,
		command: str,
		direction: str,
	) -> dict:
		return {
			"ok": False,
			"command": command,
			"direction": direction,
			"failStage": "",
			"failReason": "",
			"message": "",
			"tableContextMakeOk": False,
			"tableContextFailStage": "",
			"tableContextFailReason": "",
			"tableID": "",
			"tableIDExists": False,
			"rowNumber": None,
			"columnNumber": None,
			"rowSpan": None,
			"columnSpan": None,
			"rowEndNumber": None,
			"columnEndNumber": None,
			"nRows": None,
			"nColumns": None,
			"cellMapBuildOk": False,
			"cellMapFailReason": "",
			"cellMapCandidateCount": 0,
			"cellMapMappedCellCount": 0,
			"cellMapDuplicateCoordinateDetected": False,
			"cellMapDuplicateCoordinates": "",
			"sequenceOk": False,
			"sequenceFailReason": "",
			"startRow": None,
			"startColumn": None,
			"endRow": None,
			"endColumn": None,
			"slotCount": 0,
			"entryCount": 0,
			"coordinates": "",
			"sourceCoordinates": "",
			"texts": "",
			"textInfoSources": "",
			"textInfoFailureCount": 0,
			"textInfoFailureCoordinates": "",
			"skippedCoveredSlotCount": 0,
			"skippedCoveredSlotCoordinates": "",
			"hiddenCellCount": 0,
			"coveredCellCount": 0,
			"startIsCurrentCell": False,
			"sayAllImportOk": False,
			"sayAllImportException": "",
			"sayAllCursorTableExists": False,
			"sayAllHandlerExists": False,
			"sayAllReadTextExists": False,
			"sayAllCalled": False,
			"sayAllCursorIsTable": False,
			"startPosMakeOk": False,
			"startText": "",
			"startTextInfoClass": "",
			"startTextInfoModule": "",
			"nextLineFuncProvided": False,
			"shouldUpdateCaret": self._updateCaret,
			"startedFromScript": True,
			"sayAllException": "",
		}

	def _fillTableContext(
		self,
		result: dict,
		tableContext: dict,
	) -> None:
		result["tableID"] = tableContext.get("tableID", "")
		result["tableIDExists"] = bool(result["tableID"])

		result["rowNumber"] = tableContext.get("rowNumber")
		result["columnNumber"] = tableContext.get("columnNumber")
		result["rowSpan"] = tableContext.get("rowSpan")
		result["columnSpan"] = tableContext.get("columnSpan")
		result["rowEndNumber"] = tableContext.get("rowEndNumber")
		result["columnEndNumber"] = tableContext.get("columnEndNumber")
		result["nRows"] = tableContext.get("nRows")
		result["nColumns"] = tableContext.get("nColumns")

	def _buildSayAllRowSequence(
		self,
		provider: object,
		tableContext: dict,
		cellMap: dict,
	) -> dict:
		try:
			rowNumber = int(tableContext.get("rowNumber"))
			startColumn = int(tableContext.get("columnNumber"))
			nColumns = int(tableContext.get("nColumns"))
		except Exception:
			return {
				"ok": False,
				"failReason": "missingRowOrColumnCount",
				"entries": [],
			}

		currentSource = self._getCurrentSourceCoordinate(
			provider,
			cellMap,
			rowNumber,
			startColumn,
		)

		entries = []
		seenSources = set()
		textInfoFailures = []
		skippedCoveredSlots = []
		hiddenCellCount = 0
		coveredCellCount = 0
		slotCount = 0

		for columnNumber in range(startColumn, nColumns + 1):
			slotCount += 1

			rawEntry = self._makeSequenceCellEntry(
				provider,
				cellMap,
				rowNumber,
				columnNumber,
			)

			source = rawEntry.get("sourceCoordinate")
			if source in seenSources:
				skippedCoveredSlots.append(f"{rowNumber},{columnNumber}")
				continue

			if source is not None:
				seenSources.add(source)

			if rawEntry.get("coveredByMergedCell"):
				coveredCellCount += 1
			if rawEntry.get("hidden"):
				hiddenCellCount += 1

			if not rawEntry.get("ok"):
				textInfoFailures.append(f"{rowNumber},{columnNumber}")
				continue

			entries.append(
				self._makeSayAllCoordinateEntry(
					rawEntry,
					rowNumber,
					columnNumber,
				),
			)

		startIsCurrent = (
			bool(entries)
			and currentSource is not None
			and entries[0].get("sourceCoordinate") == currentSource
		)

		return {
			"ok": bool(entries) and startIsCurrent,
			"failReason": "" if bool(entries) and startIsCurrent else "missingStartPos",
			"entries": entries,
			"startRow": rowNumber,
			"startColumn": startColumn,
			"endRow": rowNumber,
			"endColumn": nColumns,
			"slotCount": slotCount,
			"entryCount": len(entries),
			"startIsCurrentCell": startIsCurrent,
			"textInfoFailureCount": len(textInfoFailures),
			"textInfoFailureCoordinates": ";".join(textInfoFailures),
			"skippedCoveredSlotCount": len(skippedCoveredSlots),
			"skippedCoveredSlotCoordinates": ";".join(skippedCoveredSlots),
			"hiddenCellCount": hiddenCellCount,
			"coveredCellCount": coveredCellCount,
		}

	def _buildSayAllColumnSequence(
		self,
		provider: object,
		tableContext: dict,
		cellMap: dict,
	) -> dict:
		try:
			startRow = int(tableContext.get("rowNumber"))
			columnNumber = int(tableContext.get("columnNumber"))
			nRows = int(tableContext.get("nRows"))
		except Exception:
			return {
				"ok": False,
				"failReason": "missingColumnOrRowCount",
				"entries": [],
			}

		currentSource = self._getCurrentSourceCoordinate(
			provider,
			cellMap,
			startRow,
			columnNumber,
		)

		entries = []
		seenSources = set()
		textInfoFailures = []
		skippedCoveredSlots = []
		hiddenCellCount = 0
		coveredCellCount = 0
		slotCount = 0

		for rowNumber in range(startRow, nRows + 1):
			slotCount += 1

			rawEntry = self._makeSequenceCellEntry(
				provider,
				cellMap,
				rowNumber,
				columnNumber,
			)

			source = rawEntry.get("sourceCoordinate")
			if source in seenSources:
				skippedCoveredSlots.append(f"{rowNumber},{columnNumber}")
				continue

			if source is not None:
				seenSources.add(source)

			if rawEntry.get("coveredByMergedCell"):
				coveredCellCount += 1
			if rawEntry.get("hidden"):
				hiddenCellCount += 1

			if not rawEntry.get("ok"):
				textInfoFailures.append(f"{rowNumber},{columnNumber}")
				continue

			entries.append(
				self._makeSayAllCoordinateEntry(
					rawEntry,
					rowNumber,
					columnNumber,
				),
			)

		startIsCurrent = (
			bool(entries)
			and currentSource is not None
			and entries[0].get("sourceCoordinate") == currentSource
		)

		return {
			"ok": bool(entries) and startIsCurrent,
			"failReason": "" if bool(entries) and startIsCurrent else "missingStartPos",
			"entries": entries,
			"startRow": startRow,
			"startColumn": columnNumber,
			"endRow": nRows,
			"endColumn": columnNumber,
			"slotCount": slotCount,
			"entryCount": len(entries),
			"startIsCurrentCell": startIsCurrent,
			"textInfoFailureCount": len(textInfoFailures),
			"textInfoFailureCoordinates": ";".join(textInfoFailures),
			"skippedCoveredSlotCount": len(skippedCoveredSlots),
			"skippedCoveredSlotCoordinates": ";".join(skippedCoveredSlots),
			"hiddenCellCount": hiddenCellCount,
			"coveredCellCount": coveredCellCount,
		}

	def _makeSayAllCoordinateEntry(
		self,
		entry: dict,
		rowNumber: int,
		columnNumber: int,
	) -> dict:
		"""Return a coordinate-only SayAll entry.

		SayAll must not keep or return the TextInfo created while building the
		sequence. TextInfo for startPos and nextLineFunc is created fresh later.
		"""
		return {
			"ok": True,
			"rowNumber": entry.get("rowNumber", rowNumber),
			"columnNumber": entry.get("columnNumber", columnNumber),
			"rowSpan": entry.get("rowSpan", 1),
			"columnSpan": entry.get("columnSpan", 1),
			"rowEndNumber": entry.get("rowEndNumber"),
			"columnEndNumber": entry.get("columnEndNumber"),
			"sourceCoordinate": entry.get("sourceCoordinate"),
			"coveredByMergedCell": bool(entry.get("coveredByMergedCell")),
			"hidden": bool(entry.get("hidden")),
			"text": entry.get("text", ""),
			"textInfoSource": entry.get("textInfoSource", ""),
			"legacyTextInfoIgnored": "info" in entry,
		}

	def _makeSequenceCellEntry(
		self,
		provider: object,
		cellMap: dict,
		rowNumber: int,
		columnNumber: int,
	) -> dict:
		entry = {
			"ok": False,
			"rowNumber": rowNumber,
			"columnNumber": columnNumber,
			"sourceRowNumber": None,
			"sourceColumnNumber": None,
			"sourceCoordinate": None,
			"lookupOk": False,
			"lookupFailReason": "",
			"coveredByMergedCell": False,
			"hidden": False,
			"hiddenReason": "",
			"info": None,
			"textInfoMakeOk": False,
			"textInfoFailReason": "",
			"textInfoSource": "",
			"textInfoClass": "",
			"textInfoModule": "",
			"text": "",
			"textLength": 0,
		}

		lookup = provider.lookupCell(cellMap, rowNumber, columnNumber)
		entry["lookupOk"] = bool(lookup.get("ok"))
		entry["lookupFailReason"] = lookup.get("failReason", "")
		entry["coveredByMergedCell"] = bool(lookup.get("coveredByMergedCell"))
		entry["sourceRowNumber"] = lookup.get("sourceRowNumber")
		entry["sourceColumnNumber"] = lookup.get("sourceColumnNumber")

		if entry["sourceRowNumber"] is not None and entry["sourceColumnNumber"] is not None:
			entry["sourceCoordinate"] = (
				int(entry["sourceRowNumber"]),
				int(entry["sourceColumnNumber"]),
			)

		if not lookup.get("ok"):
			entry["textInfoFailReason"] = lookup.get("failReason", "lookupFailed")
			return entry

		cellEntry = lookup.get("entry", {})
		cellObj = cellEntry.get("cellObj")
		cellInfo = cellEntry.get("cellInfo", {})

		entry["rowNumber"] = cellInfo.get(
			"rowNumber",
			entry.get("sourceRowNumber") or rowNumber,
		)
		entry["columnNumber"] = cellInfo.get(
			"columnNumber",
			entry.get("sourceColumnNumber") or columnNumber,
		)
		entry["rowSpan"] = cellInfo.get("rowSpan", 1)
		entry["columnSpan"] = cellInfo.get("columnSpan", 1)
		entry["rowEndNumber"] = cellInfo.get("rowEndNumber")
		entry["columnEndNumber"] = cellInfo.get("columnEndNumber")

		hidden = self._isHiddenOrInvisibleCell(cellObj)
		entry["hidden"] = bool(hidden.get("hidden"))
		entry["hiddenReason"] = hidden.get("reason", "")

		textInfoResult = self._makeCellTextInfo(cellObj)
		entry["textInfoMakeOk"] = bool(textInfoResult.get("ok"))
		entry["textInfoFailReason"] = textInfoResult.get("failReason", "")
		entry["textInfoSource"] = textInfoResult.get("textInfoSource", "")
		entry["info"] = textInfoResult.get("info")

		info = entry["info"]
		if info is not None:
			try:
				entry["textInfoClass"] = info.__class__.__name__
			except Exception:
				pass

			try:
				entry["textInfoModule"] = info.__class__.__module__
			except Exception:
				pass

			try:
				text = info.text
				if text is None:
					text = ""
				entry["text"] = text
				entry["textLength"] = len(text)
			except Exception:
				entry["text"] = ""
				entry["textLength"] = 0

		# Sequence building should only require a valid table cell lookup.
		# TextInfo created here is diagnostic / preview data only. The actual
		# SayAll startPos and nextLineFunc return values are created fresh later.
		entry["ok"] = entry["lookupOk"]
		entry["textInfoDiagnosticOk"] = entry["textInfoMakeOk"]
		return entry

	def _landingBeforeReadTextInfoHasText(
		self,
		textInfoResult: dict | None,
	) -> bool:
		"""Return True only when the cached result text is non-empty.

		Direct info.text can become non-empty later while the cached result text
		is still empty, and that late value may contain only a partial first
		character. Treat an empty cached result as unreliable and use the
		landing fallback when it is enabled.
		"""
		textInfoResult = textInfoResult or {}
		try:
			text = textInfoResult.get("text", "")
		except Exception:
			text = ""

		return bool(text)

	def _tryLandingBeforeReadFocus(
		self,
		label: str,
		obj,
	) -> None:
		if obj is None:
			return

		try:
			obj.setFocus()
		except Exception:
			pass

		try:
			import api

			api.setFocusObject(obj)
		except Exception:
			pass

	def _makeEmptyCellSayAllTextInfoResult(
		self,
		tableContext: dict,
		entry: dict,
		anchorInfo: object | None = None,
		cellObj: object | None = None,
		fallbackReason: str = "",
	) -> dict:
		info = WriterIA2EmptyCellSayAllTextInfo(
			anchorInfo,
			tableContext,
			entry,
			cellObj,
		)
		return {
			"ok": True,
			"failStage": "",
			"failReason": "",
			"info": info,
			"text": "",
			"textInfoSource": "emptyCellFallback:emptyOrNoUsableText",
			"fallbackReason": fallbackReason or "emptyOrNoUsableText",
			"wrappedTextInfo": True,
			"wrapperClass": info.__class__.__name__,
			"innerTextInfoClass": "",
			"innerTextInfoModule": "",
		}

	def _makeSayAllTextInfoOrEmptyFallbackForEntry(
		self,
		tableContext: dict,
		cellMap: dict,
		entry: dict,
		beforeTextInfoResult: dict | None = None,
		fallbackAnchorInfo: object | None = None,
	) -> dict:
		entry = entry or {}

		original = beforeTextInfoResult or self._makeSayAllTextInfo(
			tableContext,
			cellMap,
			entry,
		)

		if self._landingBeforeReadTextInfoHasText(original):
			return original

		cellLookup = self._lookupCellObjFromCellMap(
			cellMap,
			entry.get("rowNumber"),
			entry.get("columnNumber"),
		)
		cellObj = cellLookup.get("cellObj")

		if DEBUG_ENABLE_WRITER_SAYALL_LANDING_FALLBACK:
			landingResult = self._makeLandingBeforeReadTextInfoForEntry(
				tableContext,
				cellMap,
				entry,
				beforeTextInfoResult=original,
			)
			if landingResult.get("ok"):
				return landingResult

		fallbackReason = "emptyOrNoUsableText"
		if not original.get("ok"):
			fallbackReason = "makeTextInfoFailed"
		elif not original.get("text"):
			fallbackReason = "textInfoTextEmpty"

		anchorInfo = original.get("info")
		if not self._isSayAllRuntimeTextInfoUsable(anchorInfo):
			anchorInfo = fallbackAnchorInfo

		if not self._isSayAllRuntimeTextInfoUsable(anchorInfo):
			return {
				"ok": False,
				"failStage": "makeTextInfo",
				"failReason": "emptyFallbackAnchorUnavailable",
				"info": None,
				"text": "",
				"textInfoSource": "",
				"fallbackReason": fallbackReason,
			}

		return self._makeEmptyCellSayAllTextInfoResult(
			tableContext,
			entry,
			anchorInfo=anchorInfo,
			cellObj=cellObj,
			fallbackReason=fallbackReason,
		)

	def _makeLandingBeforeReadTextInfoForEntry(
		self,
		tableContext: dict,
		cellMap: dict,
		entry: dict,
		beforeTextInfoResult: dict | None = None,
	) -> dict:
		entry = entry or {}
		for name in (
			"rowNumber",
			"columnNumber",
			"rowSpan",
			"columnSpan",
			"sourceCoordinate",
			"text",
			"textInfoSource",
		):
			pass

		original = beforeTextInfoResult or self._makeSayAllTextInfo(
			tableContext,
			cellMap,
			entry,
		)

		if self._landingBeforeReadTextInfoHasText(original):
			return original

		cellLookup = self._lookupCellObjFromCellMap(
			cellMap,
			entry.get("rowNumber"),
			entry.get("columnNumber"),
		)

		cellObj = cellLookup.get("cellObj")
		self._tryLandingBeforeReadFocus(
			"cellObjLanding",
			cellObj,
		)
		afterCellLanding = self._makeSayAllTextInfo(
			tableContext,
			cellMap,
			entry,
		)

		if afterCellLanding.get("ok") and self._landingBeforeReadTextInfoHasText(afterCellLanding):
			return afterCellLanding

		try:
			childObj = self._getFirstChild(cellObj)
		except Exception:
			childObj = None

		self._tryLandingBeforeReadFocus(
			"childLanding",
			childObj,
		)
		afterChildLanding = self._makeSayAllTextInfo(
			tableContext,
			cellMap,
			entry,
		)

		if afterChildLanding.get("ok") and self._landingBeforeReadTextInfoHasText(afterChildLanding):
			return afterChildLanding

		fallbackReason = "emptyOrNoUsableText"

		if not original.get("ok") and not afterCellLanding.get("ok") and not afterChildLanding.get("ok"):
			fallbackReason = "makeTextInfoFailed"
		elif (
			not original.get("text")
			and not afterCellLanding.get("text")
			and not afterChildLanding.get("text")
		):
			fallbackReason = "textInfoTextEmptyAfterLanding"

		emptyFallback = self._makeEmptyCellSayAllTextInfoResult(
			tableContext,
			entry,
			anchorInfo=original.get("info"),
			cellObj=cellObj,
			fallbackReason=fallbackReason,
		)
		return emptyFallback

	def _callSayAllHandler(
		self,
		provider: object,
		tableContext: dict,
		cellMap: dict,
		entries: list,
	) -> dict:
		result = {
			"ok": False,
			"failStage": "",
			"failReason": "",
			"message": "",
			"readTextCalled": False,
			"sayAllCalled": False,
			"startFreshTextInfoOk": False,
			"startFreshTextInfoFailReason": "",
			"nextLineFuncProvided": False,
			"runtimeTextInfoContractOk": False,
			"runtimeTextInfoFailureCount": 0,
			"runtimeTextInfoFailureCoordinates": "",
			"runtimeTextInfoFailureReasons": "",
		}

		if not entries:
			result["failStage"] = "callSayAll"
			result["failReason"] = "emptyEntries"
			result["message"] = "Unable to read row"
			return result

		startEntry = entries[0]
		startInfoResult = self._makeSayAllTextInfo(
			tableContext,
			cellMap,
			startEntry,
		)

		if not startInfoResult.get("ok"):
			result["failStage"] = "callSayAll"
			result["failReason"] = (
				"startTextInfoUnavailable:"
				+ startInfoResult.get("failStage", "")
				+ ":"
				+ startInfoResult.get("failReason", "")
			)
			result["startFreshTextInfoFailReason"] = result["failReason"]
			result["message"] = "Unable to read row"
			return result

		startPos = startInfoResult.get("info")
		result["startFreshTextInfoOk"] = True

		runtimeCheck = self._validateSayAllRuntimeTextInfos(
			[
				{
					"rowNumber": startEntry.get("rowNumber"),
					"columnNumber": startEntry.get("columnNumber"),
					"info": startPos,
				},
			],
		)

		result["runtimeTextInfoContractOk"] = bool(runtimeCheck.get("ok"))
		result["runtimeTextInfoFailureCount"] = runtimeCheck.get(
			"failureCount",
			0,
		)
		result["runtimeTextInfoFailureCoordinates"] = runtimeCheck.get(
			"failureCoordinates",
			"",
		)
		result["runtimeTextInfoFailureReasons"] = runtimeCheck.get(
			"failureReasons",
			"",
		)

		if not runtimeCheck.get("ok"):
			result["failStage"] = "callSayAll"
			result["failReason"] = "startTextInfoRuntimeUnavailable"
			result["message"] = "Unable to read row"
			return result

		nextLineFunc = self._makeNextLineFunc(
			tableContext,
			cellMap,
			entries,
		)
		result["nextLineFuncProvided"] = True

		try:
			import speech.sayAll as sayAll
		except Exception as e:
			result["failStage"] = "callSayAll"
			result["failReason"] = f"sayAllImportFailed:{repr(e)}"
			result["message"] = "Unable to read row"
			return result

		try:
			sayAll.SayAllHandler.readText(
				sayAll.CURSOR.TABLE,
				startPos,
				nextLineFunc,
				self._updateCaret,
				startedFromScript=True,
			)
		except Exception as e:
			result["failStage"] = "callSayAll"
			result["failReason"] = f"readTextFailed:{repr(e)}"
			result["message"] = "Unable to read row"
			return result

		result["ok"] = True
		result["readTextCalled"] = True
		result["sayAllCalled"] = True
		return result

	def _makeFreshTextInfoForEntry(
		self,
		cellMap: dict,
		entry: dict,
	) -> dict:
		rowNumber = entry.get("rowNumber")
		columnNumber = entry.get("columnNumber")

		result = {
			"ok": False,
			"failStage": "",
			"failReason": "",
			"info": None,
			"text": "",
			"textInfoSource": "",
		}

		cellLookup = self._lookupCellObjFromCellMap(
			cellMap,
			rowNumber,
			columnNumber,
		)
		if not cellLookup.get("ok"):
			result["failStage"] = "cellLookup"
			result["failReason"] = cellLookup.get("failReason", "")
			return result

		cellObj = cellLookup.get("cellObj")
		textInfoResult = self._makeFreshTextInfoFromCellObj(cellObj)

		if not textInfoResult.get("ok"):
			result["failStage"] = textInfoResult.get("failStage", "makeTextInfo")
			result["failReason"] = textInfoResult.get("failReason", "")
			return result

		info = textInfoResult.get("info")
		if not self._isSayAllRuntimeTextInfoUsable(info):
			result["failStage"] = "runtime"
			result["failReason"] = "textInfoRuntimeUnavailable"
			return result

		result["ok"] = True
		result["info"] = info
		result["textInfoSource"] = textInfoResult.get("textInfoSource", "")

		try:
			text = info.text
			if text is None:
				text = ""
			result["text"] = text
		except Exception:
			result["text"] = ""

		return result

	def _makeSayAllTextInfo(
		self,
		tableContext: dict,
		cellMap: dict,
		entry: dict,
	) -> dict:
		"""Create a fresh TextInfo and wrap it with SayAll table fields."""

		result = self._makeFreshTextInfoForEntry(
			cellMap,
			entry,
		)

		if not result.get("ok"):
			return result

		innerInfo = result.get("info")
		if innerInfo is None:
			result["ok"] = False
			result["failStage"] = "wrapSayAllTextInfo"
			result["failReason"] = "missingInnerTextInfo"
			return result

		wrappedInfo = WriterIA2SayAllTableTextInfoWrapper(
			innerInfo,
			tableContext,
			entry,
		)

		if not self._isSayAllRuntimeTextInfoUsable(wrappedInfo):
			result["ok"] = False
			result["failStage"] = "wrapSayAllTextInfo"
			result["failReason"] = "wrappedTextInfoRuntimeUnavailable"
			return result

		result["info"] = wrappedInfo
		result["wrappedTextInfo"] = True
		result["wrapperClass"] = wrappedInfo.__class__.__name__

		try:
			result["innerTextInfoClass"] = innerInfo.__class__.__name__
		except Exception:
			result["innerTextInfoClass"] = ""

		try:
			result["innerTextInfoModule"] = innerInfo.__class__.__module__
		except Exception:
			result["innerTextInfoModule"] = ""

		return result

	def _lookupCellObjFromCellMap(
		self,
		cellMap: dict,
		rowNumber,
		columnNumber,
	) -> dict:
		keys = [
			(rowNumber, columnNumber),
			(f"{rowNumber},{columnNumber}"),
			(str((rowNumber, columnNumber))),
		]

		for key in keys:
			try:
				value = cellMap.get(key)
			except Exception:
				value = None

			cellObj = self._extractCellObj(value)
			if cellObj is not None:
				return {
					"ok": True,
					"cellObj": cellObj,
					"failReason": "",
				}

		try:
			values = list(cellMap.values())
		except Exception:
			values = []

		for value in values:
			if not self._valueMatchesCoordinate(
				value,
				rowNumber,
				columnNumber,
			):
				continue

			cellObj = self._extractCellObj(value)
			if cellObj is not None:
				return {
					"ok": True,
					"cellObj": cellObj,
					"failReason": "",
				}

		return {
			"ok": False,
			"cellObj": None,
			"failReason": "cellObjNotFound",
		}

	def _extractCellObj(
		self,
		value,
	):
		if value is None:
			return None

		if isinstance(value, dict):
			for key in (
				"cellObj",
				"obj",
				"ia2CellObj",
				"candidateObj",
				"sourceObj",
			):
				cellObj = value.get(key)
				if cellObj is not None:
					return cellObj

		return value

	def _valueMatchesCoordinate(
		self,
		value,
		rowNumber,
		columnNumber,
	) -> bool:
		if not isinstance(value, dict):
			return False

		rowKeys = (
			"rowNumber",
			"row",
			"rowIndex",
			"table-rownumber",
		)
		columnKeys = (
			"columnNumber",
			"column",
			"columnIndex",
			"col",
			"table-columnnumber",
		)

		rowValue = None
		columnValue = None

		for key in rowKeys:
			if key in value:
				rowValue = value.get(key)
				break

		for key in columnKeys:
			if key in value:
				columnValue = value.get(key)
				break

		return rowValue == rowNumber and columnValue == columnNumber

	def _makeFreshTextInfoFromCellObj(
		self,
		cellObj,
	) -> dict:
		result = {
			"ok": False,
			"failStage": "",
			"failReason": "",
			"info": None,
			"textInfoSource": "",
		}

		if cellObj is None:
			result["failStage"] = "cellObj"
			result["failReason"] = "missingCellObj"
			return result

		direct = self._tryMakeTextInfo(cellObj)
		if direct.get("ok"):
			direct["textInfoSource"] = "cellObj.makeTextInfo(POSITION_ALL)"
			return direct

		childResult = self._tryMakeTextInfoFromChildren(cellObj)
		if childResult.get("ok"):
			return childResult

		result["failStage"] = "makeTextInfo"
		result["failReason"] = (
			direct.get("failReason", "") or childResult.get("failReason", "") or "makeTextInfoFailed"
		)
		return result

	def _tryMakeTextInfo(
		self,
		obj,
	) -> dict:
		result = {
			"ok": False,
			"failStage": "",
			"failReason": "",
			"info": None,
			"textInfoSource": "",
		}

		try:
			import textInfos

			info = obj.makeTextInfo(textInfos.POSITION_ALL)
		except Exception as e:
			result["failStage"] = "makeTextInfo"
			result["failReason"] = repr(e)
			return result

		if info is None:
			result["failStage"] = "makeTextInfo"
			result["failReason"] = "textInfoNone"
			return result

		result["ok"] = True
		result["info"] = info
		return result

	def _getChildObjectForTextInfo(
		self,
		obj,
		childIndex: int,
	):
		"""Return a child object for TextInfo creation.

		childIndex is 1-based to match IA2 child indexing.
		"""
		if obj is None:
			return None

		try:
			children = getattr(obj, "children", None)
			if children and len(children) >= childIndex:
				return children[childIndex - 1]
		except Exception:
			pass

		for index in (
			childIndex - 1,
			childIndex,
		):
			try:
				childObj = obj.getChild(index)
				if childObj is not None:
					return childObj
			except Exception:
				pass

		return None

	def _tryMakeTextInfoFromChildren(
		self,
		cellObj,
	) -> dict:
		result = {
			"ok": False,
			"failStage": "makeTextInfo",
			"failReason": "",
			"info": None,
			"textInfoSource": "",
		}

		if cellObj is None:
			result["failReason"] = "missingCellObj"
			return result

		childCount = getattr(cellObj, "childCount", None)
		try:
			childCount = int(childCount or 0)
		except Exception:
			childCount = 0

		if childCount <= 0:
			result["failReason"] = "missingChildren"
			return result

		childInfos = []
		childSources = []
		lastFailReason = ""

		for childIndex in range(1, childCount + 1):
			childObj = self._getChildObjectForTextInfo(
				cellObj,
				childIndex,
			)
			if childObj is None:
				continue

			childTextInfoResult = self._tryMakeTextInfo(childObj)
			if not childTextInfoResult.get("ok"):
				lastFailReason = childTextInfoResult.get("failReason", "")
				continue

			info = childTextInfoResult.get("info")
			if not self._isSayAllRuntimeTextInfoUsable(info):
				lastFailReason = "textInfoRuntimeUnavailable"
				continue

			try:
				text = info.text
			except Exception:
				text = ""

			if text is None:
				text = ""

			# Keep empty child TextInfos out of the multi-child wrapper. Empty
			# cells are handled later by emptyCellFallback.
			if not text:
				continue

			childInfos.append(info)
			childSources.append(f"child[{childIndex}].makeTextInfo(POSITION_ALL)")

		if not childInfos:
			result["failReason"] = lastFailReason or "makeTextInfoFromChildrenFailed"
			return result

		if len(childInfos) == 1:
			result["ok"] = True
			result["failStage"] = ""
			result["failReason"] = ""
			result["info"] = childInfos[0]
			result["textInfoSource"] = childSources[0]
			return result

		result["ok"] = True
		result["failStage"] = ""
		result["failReason"] = ""
		result["info"] = WriterIA2MultiChildCellTextInfo(childInfos)
		result["textInfoSource"] = "multiChildCellTextInfo:" + ",".join(childSources)
		return result

	def _getFirstChild(
		self,
		obj,
	):
		for attr in ("simpleFirstChild", "firstChild"):
			try:
				child = getattr(obj, attr)
			except Exception:
				child = None

			if child is not None:
				return child

		return None

	def _getNextSibling(
		self,
		obj,
	):
		for attr in ("simpleNext", "next"):
			try:
				nextObj = getattr(obj, attr)
			except Exception:
				nextObj = None

			if nextObj is not None:
				return nextObj

		return None

	def _isSayAllRuntimeTextInfoUsable(
		self,
		info: object,
	) -> bool:
		if info is None:
			return False

		if getattr(info, "_writerIA2SayAllEmptyCell", False):
			return True

		try:
			obj = info.obj
		except Exception:
			return False

		if obj is None:
			return False

		if not hasattr(obj, "makeTextInfo"):
			return False

		try:
			bookmark = info.bookmark
		except Exception:
			return False

		try:
			updater = obj.makeTextInfo(bookmark)
		except Exception:
			return False

		if updater is None:
			return False

		try:
			return updater.obj is not None
		except Exception:
			return False

	def _validateSayAllRuntimeTextInfos(
		self,
		entries: list,
	) -> dict:
		failures = []

		for entry in entries:
			coordinate = self._entryCoordinateFromEntry(entry)
			info = entry.get("info")

			check = self._checkSayAllRuntimeTextInfo(
				info,
			)

			if not check.get("ok"):
				failures.append(
					{
						"coordinate": coordinate,
						"failStage": check.get("failStage", ""),
						"failReason": check.get("failReason", ""),
					},
				)

		if failures:
			return {
				"ok": False,
				"failureCount": len(failures),
				"failureCoordinates": ";".join(failure.get("coordinate", "") for failure in failures),
				"failureReasons": ";".join(
					(
						f"{failure.get('coordinate', '')}:"
						f"{failure.get('failStage', '')}:"
						f"{failure.get('failReason', '')}"
					)
					for failure in failures
				),
			}

		return {
			"ok": True,
			"failureCount": 0,
			"failureCoordinates": "",
			"failureReasons": "",
		}

	def _checkSayAllRuntimeTextInfo(
		self,
		info: object,
	) -> dict:
		if info is None:
			return {
				"ok": False,
				"failStage": "textInfo",
				"failReason": "missingTextInfo",
			}

		if getattr(info, "_writerIA2SayAllEmptyCell", False):
			return {
				"ok": True,
			}

		try:
			obj = info.obj
		except Exception as e:
			return {
				"ok": False,
				"failStage": "obj",
				"failReason": repr(e),
			}

		if obj is None:
			return {
				"ok": False,
				"failStage": "obj",
				"failReason": "objNone",
			}

		if not hasattr(obj, "makeTextInfo"):
			return {
				"ok": False,
				"failStage": "obj",
				"failReason": "objHasNoMakeTextInfo",
			}

		try:
			bookmark = info.bookmark
		except Exception as e:
			return {
				"ok": False,
				"failStage": "bookmark",
				"failReason": repr(e),
			}

		try:
			updater = obj.makeTextInfo(bookmark)
		except Exception as e:
			return {
				"ok": False,
				"failStage": "roundTrip",
				"failReason": repr(e),
			}

		if updater is None:
			return {
				"ok": False,
				"failStage": "roundTrip",
				"failReason": "updaterNone",
			}

		try:
			if updater.obj is None:
				return {
					"ok": False,
					"failStage": "roundTrip",
					"failReason": "updaterObjNone",
				}
		except Exception as e:
			return {
				"ok": False,
				"failStage": "roundTrip",
				"failReason": repr(e),
			}

		return {
			"ok": True,
			"failStage": "",
			"failReason": "",
		}

	def _entryCoordinateFromEntry(
		self,
		entry: dict,
	) -> str:
		if not entry:
			return ""

		return f"{entry.get('rowNumber')},{entry.get('columnNumber')}"

	def _resolveEntryIndexFromTextInfo(
		self,
		cellMap: dict,
		entries: list,
		info,
	) -> dict:
		if info is None:
			return {
				"ok": False,
				"index": -1,
				"failReason": "missingInfo",
			}

		directCoordinate = getattr(
			info,
			"_writerIA2SayAllEntryCoordinate",
			None,
		)
		if directCoordinate:
			for index, entry in enumerate(entries):
				if directCoordinate == (
					entry.get("rowNumber"),
					entry.get("columnNumber"),
				):
					return {
						"ok": True,
						"index": index,
						"failReason": "",
					}

		queryKeyGroups = self._makeTextInfoKeyGroups(info)
		priorities = (
			"objBookmark",
			"objText",
			"objOnly",
		)

		for priority in priorities:
			queryKeys = queryKeyGroups.get(priority, set())
			if not queryKeys:
				continue

			matches = []

			for index, entry in enumerate(entries):
				fresh = self._makeFreshTextInfoForEntry(
					cellMap,
					entry,
				)
				if not fresh.get("ok"):
					continue

				freshInfo = fresh.get("info")
				freshKeyGroups = self._makeTextInfoKeyGroups(freshInfo)
				freshKeys = freshKeyGroups.get(priority, set())

				if queryKeys.intersection(freshKeys):
					matches.append(index)

			if len(matches) == 1:
				return {
					"ok": True,
					"index": matches[0],
					"failReason": "",
				}

			if len(matches) > 1:
				return {
					"ok": False,
					"index": -1,
					"failReason": "ambiguousCurrentInfo",
				}

		return {
			"ok": False,
			"index": -1,
			"failReason": "currentInfoNotResolvable",
		}

	def _makeTextInfoKeyGroups(
		self,
		info,
	) -> dict:
		groups = {
			"objBookmark": set(),
			"objText": set(),
			"objOnly": set(),
		}

		if info is None:
			return groups

		objIdentity = None
		try:
			objIdentity = self._makeObjectIdentity(info.obj)
		except Exception:
			objIdentity = None

		bookmarkRepr = ""
		try:
			bookmarkRepr = repr(info.bookmark)
		except Exception:
			bookmarkRepr = ""

		text = ""
		try:
			text = info.text
			if text is None:
				text = ""
		except Exception:
			text = ""

		if objIdentity and bookmarkRepr:
			groups["objBookmark"].add((objIdentity, bookmarkRepr))

		if objIdentity and text:
			groups["objText"].add((objIdentity, text))

		if objIdentity:
			groups["objOnly"].add(objIdentity)

		return groups

	def _makeObjectIdentity(
		self,
		obj,
	):
		if obj is None:
			return None

		parts = []

		try:
			parts.append(("class", obj.__class__.__name__))
		except Exception:
			pass

		try:
			parts.append(("module", obj.__class__.__module__))
		except Exception:
			pass

		try:
			parts.append(("IA2UniqueID", obj.IA2UniqueID))
		except Exception:
			pass

		try:
			parts.append(("windowHandle", obj.windowHandle))
		except Exception:
			pass

		try:
			parts.append(("role", repr(obj.role)))
		except Exception:
			pass

		if not parts:
			try:
				parts.append(("id", id(obj)))
			except Exception:
				return None

		return tuple(parts)

	def _makeNextLineFunc(
		self,
		tableContext: dict,
		cellMap: dict,
		entries: list,
	):
		def nextLineFunc(currentInfo):
			resolve = self._resolveEntryIndexFromTextInfo(
				cellMap,
				entries,
				currentInfo,
			)

			if not resolve.get("ok"):
				raise StopIteration

			currentIndex = resolve.get("index", -1)
			nextIndex = currentIndex + 1

			if nextIndex >= len(entries):
				raise StopIteration

			nextEntry = entries[nextIndex]
			nextInfoResult = self._makeSayAllTextInfo(
				tableContext,
				cellMap,
				nextEntry,
			)

			nextInfoResult = self._makeSayAllTextInfoOrEmptyFallbackForEntry(
				tableContext,
				cellMap,
				nextEntry,
				beforeTextInfoResult=nextInfoResult,
				fallbackAnchorInfo=currentInfo,
			)

			if not nextInfoResult.get("ok"):
				raise StopIteration

			nextInfo = nextInfoResult.get("info")
			if not self._isSayAllRuntimeTextInfoUsable(nextInfo):
				raise StopIteration

			return nextInfo

		return nextLineFunc

	def _fillSequenceResult(
		self,
		result: dict,
		sequence: dict,
	) -> None:
		result["sequenceOk"] = bool(sequence.get("ok"))
		result["sequenceFailReason"] = sequence.get("failReason", "")
		result["startRow"] = sequence.get("startRow")
		result["startColumn"] = sequence.get("startColumn")
		result["endRow"] = sequence.get("endRow")
		result["endColumn"] = sequence.get("endColumn")
		result["slotCount"] = sequence.get("slotCount", 0)
		result["entryCount"] = sequence.get("entryCount", 0)
		result["startIsCurrentCell"] = bool(sequence.get("startIsCurrentCell"))

		entries = sequence.get("entries", [])
		coordinates = []
		sourceCoordinates = []
		texts = []
		sources = []

		for entry in entries:
			coordinates.append(
				f"{entry.get('rowNumber')},{entry.get('columnNumber')}",
			)
			sourceCoordinates.append(
				f"{entry.get('sourceRowNumber')},{entry.get('sourceColumnNumber')}",
			)
			texts.append(entry.get("text", ""))
			sources.append(entry.get("textInfoSource", ""))

		result["coordinates"] = ";".join(coordinates)
		result["sourceCoordinates"] = ";".join(sourceCoordinates)
		result["texts"] = " | ".join(texts)
		result["textInfoSources"] = " | ".join(sources)

		result["textInfoFailureCount"] = sequence.get(
			"textInfoFailureCount",
			0,
		)
		result["textInfoFailureCoordinates"] = sequence.get(
			"textInfoFailureCoordinates",
			"",
		)
		result["skippedCoveredSlotCount"] = sequence.get(
			"skippedCoveredSlotCount",
			0,
		)
		result["skippedCoveredSlotCoordinates"] = sequence.get(
			"skippedCoveredSlotCoordinates",
			"",
		)
		result["hiddenCellCount"] = sequence.get("hiddenCellCount", 0)
		result["coveredCellCount"] = sequence.get("coveredCellCount", 0)

	def _fillSayAllResult(
		self,
		result: dict,
		sayAllResult: dict,
	) -> None:
		result["sayAllImportOk"] = bool(sayAllResult.get("sayAllImportOk"))
		result["sayAllImportException"] = sayAllResult.get("sayAllImportException", "")
		result["sayAllCursorTableExists"] = bool(
			sayAllResult.get("sayAllCursorTableExists"),
		)
		result["sayAllHandlerExists"] = bool(sayAllResult.get("sayAllHandlerExists"))
		result["sayAllReadTextExists"] = bool(
			sayAllResult.get("sayAllReadTextExists"),
		)
		result["sayAllCalled"] = bool(sayAllResult.get("sayAllCalled"))
		result["sayAllCursorIsTable"] = bool(sayAllResult.get("sayAllCursorIsTable"))
		result["startPosMakeOk"] = bool(sayAllResult.get("startPosMakeOk"))
		result["startText"] = sayAllResult.get("startText", "")
		result["startTextInfoClass"] = sayAllResult.get("startTextInfoClass", "")
		result["startTextInfoModule"] = sayAllResult.get("startTextInfoModule", "")
		result["nextLineFuncProvided"] = bool(
			sayAllResult.get("nextLineFuncProvided"),
		)
		result["shouldUpdateCaret"] = sayAllResult.get("shouldUpdateCaret")
		result["startedFromScript"] = bool(sayAllResult.get("startedFromScript"))
		result["sayAllException"] = sayAllResult.get("sayAllException", "")

	def _getCurrentSourceCoordinate(
		self,
		provider: object,
		cellMap: dict,
		rowNumber: int,
		columnNumber: int,
	):
		lookup = provider.lookupCell(cellMap, rowNumber, columnNumber)
		if not lookup.get("ok"):
			return None

		sourceRow = lookup.get("sourceRowNumber")
		sourceColumn = lookup.get("sourceColumnNumber")
		if sourceRow is None or sourceColumn is None:
			return None

		try:
			return (int(sourceRow), int(sourceColumn))
		except Exception:
			return None

	def _makeCellTextInfo(
		self,
		cellObj: object,
	) -> dict:
		textInfoResult = self._makeTextInfoWithoutChildScan(cellObj)
		if textInfoResult.get("ok"):
			return textInfoResult

		childTextInfo = self._getFirstChildTextInfo(cellObj)
		if childTextInfo.get("ok"):
			return childTextInfo

		return textInfoResult

	def _makeTextInfoWithoutChildScan(
		self,
		obj: object,
	) -> dict:
		if obj is None:
			return {
				"ok": False,
				"info": None,
				"textInfoSource": "",
				"failReason": "missingObject",
			}

		try:
			import textInfos

			info = obj.makeTextInfo(textInfos.POSITION_ALL)
			return {
				"ok": True,
				"info": info,
				"textInfoSource": "makeTextInfo(POSITION_ALL)",
				"failReason": "",
			}
		except Exception as e:
			return {
				"ok": False,
				"info": None,
				"textInfoSource": "",
				"failReason": repr(e),
			}

	def _getFirstChildTextInfo(
		self,
		obj: object,
	) -> dict:
		if obj is None:
			return {
				"ok": False,
				"info": None,
				"textInfoSource": "",
				"failReason": "missingObject",
			}

		try:
			childCount = obj.childCount
		except Exception:
			childCount = 0

		try:
			child = obj.firstChild
		except Exception:
			child = None

		index = 0
		lastFailReason = ""
		while child is not None and index < 20:
			textInfoResult = self._makeTextInfoWithoutChildScan(child)
			if textInfoResult.get("ok"):
				textInfoResult["textInfoSource"] = "child:" + textInfoResult.get("textInfoSource", "")
				return textInfoResult

			lastFailReason = textInfoResult.get("failReason", "")

			try:
				child = child.next
			except Exception:
				child = None

			index += 1

		return {
			"ok": False,
			"info": None,
			"textInfoSource": "",
			"failReason": f"noChildTextInfo:childCount={childCount};last={lastFailReason}",
		}

	def _fillStartPosSummary(
		self,
		result: dict,
		startPos: object,
	) -> None:
		try:
			result["startTextInfoClass"] = startPos.__class__.__name__
		except Exception:
			pass

		try:
			result["startTextInfoModule"] = startPos.__class__.__module__
		except Exception:
			pass

		try:
			startText = startPos.text
			if startText is None:
				startText = ""
			result["startText"] = startText
		except Exception:
			result["startText"] = ""

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

	def _messageForTableContextFailure(
		self,
		tableContext: dict,
	) -> str:
		failReason = tableContext.get("failReason", "")
		if failReason in {
			"notInTable",
			"missingCellObj",
			"contextNotDict",
			"nearestTableCellNotFound",
		}:
			return "Not in a table cell"

		failStage = tableContext.get("failStage", "")
		if failStage == "getContext":
			return "Not in a table cell"

		return "Not in a table cell"

	def _messageForFailure(
		self,
		result: dict,
	) -> str:
		if result.get("command") == "sayAllRow":
			return "Unable to read row"

		if result.get("command") == "sayAllColumn":
			return "Unable to read column"

		return "Unable to read table"
