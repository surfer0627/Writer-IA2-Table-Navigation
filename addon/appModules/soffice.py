import api
import braille
import config
import core
import textInfos
import ui

import addonHandler
addonHandler.initTranslation()

from .writerTableNavCore import WriterIA2TableNavigator
from nvdaBuiltin.appModules import soffice as builtinSoffice

_TABLE_SPEECH_ORDER = "contentThenCell"
_TABLE_SPEECH_DELAY_MS = 200

class AppModule(builtinSoffice.AppModule):
	"""Minimal LibreOffice Writer alpha AppModule entry."""

	def _syncWriterIA2TableAfterMove(self, result: dict[str, object]) -> dict[str, object]:
		"""Synchronize NVDA focus, Symphony, speech, and braille after IA2 table movement."""
		syncResult = {
			"attempted": False,
			"ok": False,
			"reason": "",
			"moved": bool(result.get("moved")),
			"apiFocusMatchesTargetBefore": result.get("apiFocusMatchesTarget"),
			"apiFocusMatchesTargetAfter": False,
			"targetObjectExists": result.get("targetNVDAObject") is not None,
			"targetObjectClass": "",
			"targetObjectModule": "",
			"symphonyDocumentDetected": False,
			"focusSetOk": False,
			"gainFocusQueued": False,
			"speechOk": False,
			"brailleGainFocusOk": False,
			"brailleCaretMoveOk": False,
			"failReason": "",
		}

		if not result.get("moved"):
			syncResult["reason"] = "notMoved"
			self._lastWriterIA2TableSyncResult = syncResult
			return syncResult

		syncResult["attempted"] = True
		syncResult = self._syncWriterIA2TableSymphonyAndBraille(result, syncResult)
		self._lastWriterIA2TableSyncResult = syncResult
		return syncResult

	def _syncWriterIA2TableSymphonyAndBraille(
		self,
		result: dict[str, object],
		syncResult: dict[str, object] | None = None,
	) -> dict[str, object]:
		"""Sync target table cell with Symphony focus events, speech, and braille."""
		if syncResult is None:
			syncResult = {
				"attempted": True,
				"ok": False,
				"reason": "",
				"apiFocusMatchesTargetAfter": False,
				"failReason": "",
			}

		targetObj = result.get("targetNVDAObject")
		if targetObj is None:
			syncResult["reason"] = "targetObjectMissing"
			syncResult["failReason"] = "targetNVDAObject missing from move result"
			return syncResult

		try:
			syncResult["targetObjectClass"] = targetObj.__class__.__name__
			syncResult["targetObjectModule"] = targetObj.__class__.__module__
		except Exception:
			pass

		try:
			treeInterceptor = getattr(targetObj, "treeInterceptor", None)
			syncResult["symphonyDocumentDetected"] = (
				treeInterceptor is not None
				and treeInterceptor.__class__.__name__ == "SymphonyDocument"
			)
		except Exception:
			treeInterceptor = None

		try:
			api.setFocusObject(targetObj)
			syncResult["focusSetOk"] = True
		except Exception as e:
			syncResult["failReason"] = f"api.setFocusObject failed: {e!r}"

		syncResult["gainFocusQueued"] = False
		syncResult["gainFocusQueueSkipped"] = True
		syncResult["gainFocusQueueSkipReason"] = "doNotQueueGainFocusOnSymphonyIATableCell"

		try:
			cellName = getattr(targetObj, "name", None) or ""

			if not cellName:
				try:
					cellName = targetObj.IAccessibleObject.accName(0) or ""
				except Exception:
					cellName = ""

			syncResult["speechOk"] = True
			syncResult["speechMode"] = "deferredContentThenCell"
			syncResult["cellSpeechName"] = str(cellName)
		except Exception as e:
			if not syncResult.get("failReason"):
				syncResult["failReason"] = f"speech preparation failed: {e!r}"


		syncResult["brailleGainFocusOk"] = False
		syncResult["brailleGainFocusSkipped"] = True
		syncResult["brailleGainFocusSkipReason"] = "waitForNaturalParagraphFocus"

		syncResult["brailleCaretMoveOk"] = False
		syncResult["brailleCaretMoveSkipped"] = True
		syncResult["brailleCaretMoveSkipReason"] = "targetCellIsNotTextObject"

		try:
			apiFocusObj = api.getFocusObject()
			apiFocusMatchesTarget = apiFocusObj is targetObj
			apiFocusRowIndex = None
			apiFocusColumnIndex = None
			if not apiFocusMatchesTarget:
				navigator = WriterIA2TableNavigator()
				apiFocusContext = navigator.getContextFromObject(apiFocusObj)
				apiFocusRowIndex = apiFocusContext.get("rowIndex")
				apiFocusColumnIndex = apiFocusContext.get("columnIndex")
				apiFocusMatchesTarget = (
					apiFocusRowIndex == result.get("targetRow")
					and apiFocusColumnIndex == result.get("targetColumn")
				)
		except Exception:
			apiFocusMatchesTarget = False
			apiFocusRowIndex = None
			apiFocusColumnIndex = None

		syncResult["apiFocusMatchesTargetAfter"] = apiFocusMatchesTarget
		syncResult["apiFocusRowIndexAfter"] = apiFocusRowIndex
		syncResult["apiFocusColumnIndexAfter"] = apiFocusColumnIndex
		result["apiFocusMatchesTarget"] = apiFocusMatchesTarget
		result["apiFocusRowIndex"] = apiFocusRowIndex
		result["apiFocusColumnIndex"] = apiFocusColumnIndex

		syncResult["ok"] = bool(
			syncResult.get("focusSetOk")
			and syncResult.get("speechOk")
		)
		if syncResult["ok"]:
			syncResult["reason"] = "synced"
		elif not syncResult.get("reason"):
			syncResult["reason"] = "partialSync"

		try:
			core.callLater(
				_TABLE_SPEECH_DELAY_MS,
				self._finishWriterIA2TableSymphonySpeech,
				result.copy(),
				syncResult.copy(),
			)
			syncResult["delayedSpeechScheduled"] = True
		except Exception as e:
			syncResult["delayedSpeechScheduled"] = False
			syncResult["delayedSpeechError"] = repr(e)

		return syncResult

	def _getWriterIA2TableFocusedContentText(self, focusObj) -> str:
		"""Return text from the naturally focused Symphony paragraph."""
		if focusObj is None:
			return ""

		contentText = ""

		try:
			value = getattr(focusObj, "value", None)
			if value:
				contentText = str(value)
		except Exception:
			pass

		if not contentText:
			try:
				contentText = str(focusObj.IAccessibleObject.accValue(0) or "")
			except Exception:
				contentText = ""

		if not contentText:
			try:
				ti = focusObj.makeTextInfo(textInfos.POSITION_ALL)
				contentText = getattr(ti, "text", "") or ""
			except Exception:
				contentText = ""

		return contentText.strip()

	def _shouldReportWriterIA2TableCellCoords(self) -> bool:
		"""Return whether NVDA is configured to report table cell coordinates."""
		try:
			return bool(config.conf["documentFormatting"]["reportTableCellCoords"])
		except Exception:
			return True

	def _getWriterIA2TableCellCoordsSpeechText(
		self,
		result: dict[str, object],
	) -> str:
		"""Return table cell coordinate speech using NVDA's native table coordinate strings."""
		try:
			import speech
		except Exception:
			return ""

		targetRow = result.get("targetRow")
		targetColumn = result.get("targetColumn")

		if not isinstance(targetRow, int) and not isinstance(targetColumn, int):
			return ""

		props = {
			"includeTableCellCoords": True,
		}

		if isinstance(targetRow, int):
			props["rowNumber"] = targetRow + 1

		if isinstance(targetColumn, int):
			props["columnNumber"] = targetColumn + 1

		try:
			sequence = speech.getPropertiesSpeech(**props)
		except Exception:
			return ""

		return " ".join(item for item in sequence if isinstance(item, str)).strip()

	def _getWriterIA2TableBrailleCoordsText(
		self,
		brailleProperties: dict[str, object],
	) -> str:
		"""Return NVDA core braille text for table-cell coordinates.

		The caller is responsible for converting Writer IA2 table context into
		NVDA-style row/column/span properties through WriterIA2TableNavigator.
		This helper only delegates formatting to NVDA core.
		"""
		if not brailleProperties:
			return ""

		try:
			import braille
		except Exception:
			return ""

		getPropertiesBraille = getattr(braille, "getPropertiesBraille", None)
		if not callable(getPropertiesBraille):
			return ""

		try:
			return getPropertiesBraille(**brailleProperties)
		except Exception:
			return ""

	def _formatWriterIA2TableSpeech(
		self,
		contentText: str,
		cellName: str,
		result: dict[str, object],
	) -> str:
		"""Format table navigation speech from focused content and target coordinates."""
		contentText = (contentText or "").strip()
		cellName = (cellName or "").strip()

		reportCoords = self._shouldReportWriterIA2TableCellCoords()

		coordinateText = ""
		if reportCoords:
			coordinateText = self._getWriterIA2TableCellCoordsSpeechText(result)

		if reportCoords and not coordinateText and cellName:
			coordinateText = cellName

		# Translators: Fallback speech when a Writer table cell has no text or coordinates.
		fallbackText = _("table cell")

		if _TABLE_SPEECH_ORDER == "contentOnly":
			return contentText or coordinateText or fallbackText

		if _TABLE_SPEECH_ORDER == "cellThenContent":
			if coordinateText and contentText:
				return f"{coordinateText}, {contentText}"
			return coordinateText or contentText or fallbackText

		# Default: contentThenCell.
		if contentText and coordinateText:
			return f"{contentText}, {coordinateText}"

		return contentText or coordinateText or fallbackText


	def _getWriterIA2TableBraillePresentation(
		self,
		focusObj: object | None,
		reportTableCellCoords: bool,
		delayedResult: dict[str, object],
	) -> str:
		"""Return braille coordinate text through the Writer IA2 cell-info adapter."""
		focusContext: dict[str, object] = {}
		cellInfo: dict[str, object] = {}
		brailleProperties: dict[str, object] = {}
		brailleCoordsText = ""

		try:
			from .writerTableNavCore import WriterIA2TableNavigator
		except Exception:
			try:
				from writerTableNavCore import WriterIA2TableNavigator
			except Exception:
				WriterIA2TableNavigator = None

		if WriterIA2TableNavigator is None or focusObj is None:
			delayedResult["brailleCoordsFailReason"] = (
				"WriterIA2TableNavigatorUnavailableOrFocusMissing"
			)
			return ""

		try:
			navigator = WriterIA2TableNavigator()
			focusContext = navigator.getContextFromObject(focusObj)

			delayedResult["brailleContextInTable"] = focusContext.get("inTable")
			delayedResult["brailleContextRowIndex"] = focusContext.get("rowIndex")
			delayedResult["brailleContextColumnIndex"] = focusContext.get("columnIndex")
			delayedResult["brailleContextRowSpan"] = focusContext.get("rowSpan")
			delayedResult["brailleContextColumnSpan"] = focusContext.get("columnSpan")
			delayedResult["brailleContextNRows"] = focusContext.get("nRows")
			delayedResult["brailleContextNColumns"] = focusContext.get("nColumns")

			cellInfo = navigator.normalizeCellInfo(
				focusContext,
				includeTableCellCoords=reportTableCellCoords,
			)

			delayedResult["brailleCellInfoInTable"] = cellInfo.get("inTable")
			delayedResult["brailleCellInfoRowIndex"] = cellInfo.get("rowIndex")
			delayedResult["brailleCellInfoColumnIndex"] = cellInfo.get("columnIndex")
			delayedResult["brailleCellInfoRowSpan"] = cellInfo.get("rowSpan")
			delayedResult["brailleCellInfoColumnSpan"] = cellInfo.get("columnSpan")
			delayedResult["brailleCellInfoRowNumber"] = cellInfo.get("rowNumber")
			delayedResult["brailleCellInfoColumnNumber"] = cellInfo.get("columnNumber")
			delayedResult["brailleCellInfoRowEndNumber"] = cellInfo.get("rowEndNumber")
			delayedResult["brailleCellInfoColumnEndNumber"] = cellInfo.get("columnEndNumber")
			delayedResult["brailleCellInfoIncludeTableCellCoords"] = cellInfo.get(
				"includeTableCellCoords",
			)

			brailleProperties = navigator.getBrailleProperties(cellInfo)

			delayedResult["braillePropertiesExists"] = bool(brailleProperties)
			delayedResult["braillePropertiesRowNumber"] = brailleProperties.get("rowNumber")
			delayedResult["braillePropertiesColumnNumber"] = brailleProperties.get("columnNumber")
			delayedResult["braillePropertiesRowSpan"] = brailleProperties.get("rowSpan")
			delayedResult["braillePropertiesColumnSpan"] = brailleProperties.get("columnSpan")
			delayedResult["braillePropertiesIncludeTableCellCoords"] = brailleProperties.get(
				"includeTableCellCoords",
			)

			if reportTableCellCoords:
				brailleCoordsText = self._getWriterIA2TableBrailleCoordsText(
					brailleProperties,
				)
			else:
				delayedResult["brailleCoordsSkippedReason"] = (
					"reportTableCellCoordsDisabled"
				)

		except Exception as e:
			delayedResult["brailleCoordsError"] = repr(e)

		return brailleCoordsText

	def _buildWriterIA2TableCombinedBrailleText(
		self,
		brailleCoordsText: str,
		brailleContentText: str,
		reportTableCellCoords: bool,
	) -> str:
		"""Return one combined braille message for table coordinates and content.

		This is an interim bridge. NVDA's native table-cell braille should
		eventually come from TextInfo/control-field properties. Until Writer
		table-cell coordinates are exposed that way, keep coordinates and content
		in one message so the coordinates are not overwritten by a later
		content-only braille message.
		"""
		if reportTableCellCoords and brailleCoordsText and brailleContentText:
			return f"{brailleCoordsText} {brailleContentText}"

		return brailleContentText

	def _finishWriterIA2TableSymphonySpeech(
		self,
		result: dict[str, object],
		syncResult: dict[str, object],
	) -> None:
		"""Speak target cell content after natural Symphony paragraph focus settles."""
		delayedResult = dict(syncResult)
		delayedResult["delayedSpeechRan"] = True

		try:
			focusObj = api.getFocusObject()
		except Exception as e:
			focusObj = None
			delayedResult["afterFocusError"] = repr(e)

		delayedResult["afterFocusExists"] = focusObj is not None

		if focusObj is not None:
			try:
				delayedResult["afterFocusClass"] = focusObj.__class__.__name__
				delayedResult["afterFocusModule"] = focusObj.__class__.__module__
				delayedResult["afterFocusRole"] = getattr(focusObj, "role", None)
				delayedResult["afterFocusIA2UniqueID"] = getattr(focusObj, "IA2UniqueID", None)
			except Exception:
				pass

		contentText = self._getWriterIA2TableFocusedContentText(focusObj)
		cellName = str(syncResult.get("cellSpeechName") or "")

		contentIsBlank = not contentText
		if contentIsBlank:
			contentText = _("blank")

		delayedResult["afterFocusContentIsBlank"] = contentIsBlank

		reportTableCellCoords = self._shouldReportWriterIA2TableCellCoords()
		delayedResult["reportTableCellCoords"] = reportTableCellCoords

		brailleCoordsText = self._getWriterIA2TableBraillePresentation(
			focusObj=focusObj,
			reportTableCellCoords=reportTableCellCoords,
			delayedResult=delayedResult,
		)

		speechText = self._formatWriterIA2TableSpeech(
			contentText=contentText,
			cellName=cellName,
			result=result,
		)

		brailleContentText = contentText or speechText
		brailleText = self._buildWriterIA2TableCombinedBrailleText(
			brailleCoordsText=brailleCoordsText,
			brailleContentText=brailleContentText,
			reportTableCellCoords=reportTableCellCoords,
		)

		delayedResult["afterFocusContentText"] = contentText
		delayedResult["cellSpeechName"] = cellName
		delayedResult["speechText"] = speechText
		delayedResult["speechOrder"] = _TABLE_SPEECH_ORDER
		delayedResult["brailleCoordsText"] = brailleCoordsText
		delayedResult["brailleContentText"] = brailleContentText
		delayedResult["brailleText"] = brailleText
		delayedResult["brailleOrder"] = "coordsThenContentCombined"

		try:
			ui.message(speechText)
			delayedResult["delayedSpeechOk"] = True
		except Exception as e:
			delayedResult["delayedSpeechOk"] = False
			delayedResult["delayedSpeechError"] = repr(e)

		try:
			handler = getattr(braille, "handler", None)
			message = getattr(handler, "message", None) if handler is not None else None

			if callable(message) and brailleText:
				message(brailleText)
				delayedResult["brailleMessageOk"] = True
			else:
				delayedResult["brailleMessageOk"] = False
				delayedResult["brailleMessageFailReason"] = "brailleHandlerMessageNotAvailable"
		except Exception as e:
			delayedResult["brailleMessageOk"] = False
			delayedResult["brailleMessageError"] = repr(e)

		try:
			handler = getattr(braille, "handler", None)
			buffer = getattr(handler, "buffer", None) if handler is not None else None
			delayedResult["brailleBufferExistsAfterDelay"] = buffer is not None
			delayedResult["brailleRawTextAfterDelay"] = (
				getattr(buffer, "rawText", "")
				if buffer is not None else ""
			)
		except Exception as e:
			delayedResult["brailleAfterDelayError"] = repr(e)

		try:
			self._lastWriterIA2TableSymphonyDelayedSpeechResult = delayedResult
		except Exception:
			pass

	def _moveWriterIA2TableCell(self, direction: str) -> None:
		"""Move to a nearby Writer table cell through IA2."""
		navigator = WriterIA2TableNavigator()
		result = navigator.move(api.getFocusObject(), direction)

		if result.get("moved"):
			self._syncWriterIA2TableAfterMove(result)
			return

		if result.get("edge"):
			self._lastWriterIA2TableSyncResult = {
				"ok": False,
				"edge": True,
				"edgeReason": result.get("edgeReason", ""),
				"failStage": result.get("failStage", ""),
				"failReason": result.get("failReason", ""),
			}
			# Translators: Reported when a table navigation command cannot move further
			# because the cursor is at the edge of the table.
			ui.message(_("Edge of table"))
			return

		self._lastWriterIA2TableSyncResult = {
			"ok": False,
			"edge": False,
			"failStage": result.get("failStage", ""),
			"failReason": result.get("failReason", ""),
		}
		# Translators: Reported when a table navigation command is used
		# but the cursor is not inside a table cell.
		ui.message(_("Not in a table cell"))

	def script_writerIA2TableMoveUp(self, gesture) -> None:
		"""Move to the Writer table cell above."""
		self._moveWriterIA2TableCell("up")

	def script_writerIA2TableMoveDown(self, gesture) -> None:
		"""Move to the Writer table cell below."""
		self._moveWriterIA2TableCell("down")

	def script_writerIA2TableMoveLeft(self, gesture) -> None:
		"""Move to the previous Writer table cell."""
		self._moveWriterIA2TableCell("left")

	def script_writerIA2TableMoveRight(self, gesture) -> None:
		"""Move to the next Writer table cell."""
		self._moveWriterIA2TableCell("right")



	__gestures = {
		"kb:control+alt+upArrow": "writerIA2TableMoveUp",
		"kb:control+alt+downArrow": "writerIA2TableMoveDown",
		"kb:control+alt+leftArrow": "writerIA2TableMoveLeft",
		"kb:control+alt+rightArrow": "writerIA2TableMoveRight",
	}

