"""Writer IA2 table row / column commands.

This module is import-time inert.

Layer 4 responsibility:
	table content provider result
	→ command result
	→ user-facing message text

This module must not call ui.message, speech, or braille directly.
The app module script layer is responsible for presentation.
"""

from __future__ import annotations

from typing import Any


class WriterIA2TableCommandHandler:
	"""Build command-level results for Writer IA2 table row / column reading."""

	def __init__(
		self,
		provider: object | None = None,
	) -> None:
		self._provider = provider

	def readCurrentRow(
		self,
		focusObj: object,
	) -> dict:
		"""Return a command result for reading the current table row."""
		result = self._makeCommandResult("readCurrentRow")

		provider = self._getProvider()
		if provider is None:
			result["failStage"] = "makeProvider"
			result["failReason"] = "providerUnavailable"
			result["message"] = "Unable to read row"
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

		rowResult = provider.getRowContent(tableContext)
		result["sequenceResultOk"] = bool(rowResult.get("ok"))
		result["sequenceFailStage"] = rowResult.get("failStage", "")
		result["sequenceFailReason"] = rowResult.get("failReason", "")
		result["partial"] = bool(rowResult.get("partial"))

		self._fillSequenceSummary(result, rowResult, axis="row")

		message = self._buildSequenceMessage(rowResult)
		result["message"] = message
		result["messageLength"] = len(message)

		if not rowResult.get("ok") and not message:
			result["failStage"] = "getRowContent"
			result["failReason"] = rowResult.get("failReason", "rowContentFailed")
			result["message"] = "Unable to read row"
			result["messageLength"] = len(result["message"])
			return result

		if not message:
			result["failStage"] = "buildMessage"
			result["failReason"] = "emptyMessage"
			result["message"] = "Unable to read row"
			result["messageLength"] = len(result["message"])
			return result

		result["ok"] = True
		return result

	def readCurrentColumn(
		self,
		focusObj: object,
	) -> dict:
		"""Return a command result for reading the current table column."""
		result = self._makeCommandResult("readCurrentColumn")

		provider = self._getProvider()
		if provider is None:
			result["failStage"] = "makeProvider"
			result["failReason"] = "providerUnavailable"
			result["message"] = "Unable to read column"
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

		columnResult = provider.getColumnContent(tableContext)
		result["sequenceResultOk"] = bool(columnResult.get("ok"))
		result["sequenceFailStage"] = columnResult.get("failStage", "")
		result["sequenceFailReason"] = columnResult.get("failReason", "")
		result["partial"] = bool(columnResult.get("partial"))

		self._fillSequenceSummary(result, columnResult, axis="column")

		message = self._buildSequenceMessage(columnResult)
		result["message"] = message
		result["messageLength"] = len(message)

		if not columnResult.get("ok") and not message:
			result["failStage"] = "getColumnContent"
			result["failReason"] = columnResult.get("failReason", "columnContentFailed")
			result["message"] = "Unable to read column"
			result["messageLength"] = len(result["message"])
			return result

		if not message:
			result["failStage"] = "buildMessage"
			result["failReason"] = "emptyMessage"
			result["message"] = "Unable to read column"
			result["messageLength"] = len(result["message"])
			return result

		result["ok"] = True
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

	def _makeCommandResult(
		self,
		command: str,
	) -> dict:
		return {
			"ok": False,
			"command": command,
			"failStage": "",
			"failReason": "",

			"message": "",
			"messageLength": 0,

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

			"sequenceResultOk": False,
			"sequenceFailStage": "",
			"sequenceFailReason": "",
			"partial": False,

			"cellCount": 0,
			"expectedCellCount": None,
			"texts": [],
			"combinedText": "",
			"skippedCellCount": 0,
			"textExtractionFailureCount": 0,
			"textExtractionFailureCoordinates": "",
			"hiddenCellCount": 0,
			"coveredCellCount": 0,
			"emptyCellCount": 0,
			"blankPlaceholderCount": 0,
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

	def _fillSequenceSummary(
		self,
		result: dict,
		sequenceResult: dict,
		axis: str,
	) -> None:
		cells = sequenceResult.get("cells", [])
		result["cellCount"] = sequenceResult.get("cellCount", len(cells))
		result["texts"] = sequenceResult.get("texts", [])
		result["combinedText"] = sequenceResult.get("combinedText", "")

		if axis == "row":
			result["expectedCellCount"] = sequenceResult.get("nColumns")
			result["missingCells"] = sequenceResult.get("missingColumns", "")
		else:
			result["expectedCellCount"] = sequenceResult.get("nRows")
			result["missingCells"] = sequenceResult.get("missingRows", "")

		result["textExtractionFailureCount"] = sequenceResult.get(
			"textExtractionFailureCount",
			0,
		)
		result["textExtractionFailureCoordinates"] = sequenceResult.get(
			"textExtractionFailureCoordinates",
			"",
		)

		hiddenCellCount = 0
		coveredCellCount = 0
		emptyCellCount = 0
		skippedCellCount = 0

		for cell in cells:
			if cell.get("hidden"):
				hiddenCellCount += 1
			if cell.get("coveredByMergedCell"):
				coveredCellCount += 1
			if cell.get("empty"):
				emptyCellCount += 1
			if not cell.get("textMakeOk"):
				skippedCellCount += 1

		result["hiddenCellCount"] = hiddenCellCount
		result["coveredCellCount"] = coveredCellCount
		result["emptyCellCount"] = emptyCellCount
		result["skippedCellCount"] = skippedCellCount

	def _buildSequenceMessage(
		self,
		sequenceResult: dict,
	) -> str:
		cells = sequenceResult.get("cells", [])
		parts = []
		blankPlaceholderCount = 0

		for cell in cells:
			part = self._cellToMessagePart(cell)
			if part == "":
				continue
			if part == "blank":
				blankPlaceholderCount += 1
			parts.append(part)

		if not parts:
			return ""

		return ", ".join(parts)

	def _cellToMessagePart(
		self,
		cell: dict,
	) -> str:
		if not cell.get("ok"):
			return ""

		if not cell.get("textMakeOk"):
			return ""

		text = cell.get("text", "")
		if text == "":
			return "blank"

		return self._cleanCellText(text)

	def _cleanCellText(
		self,
		text: str,
	) -> str:
		text = str(text)
		text = text.replace("\r\n", " ")
		text = text.replace("\n", " ")
		text = text.replace("\r", " ")
		text = text.replace("\t", " ")

		while "  " in text:
			text = text.replace("  ", " ")

		return text.strip()

	def _messageForTableContextFailure(
		self,
		tableContext: dict,
	) -> str:
		failReason = tableContext.get("failReason", "")
		if failReason in {"notInTable", "missingCellObj", "contextNotDict"}:
			return "Not in a table cell"

		failStage = tableContext.get("failStage", "")
		if failStage == "getContext":
			return "Not in a table cell"

		return "Not in a table cell"
