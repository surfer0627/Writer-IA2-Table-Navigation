import addonHandler
import builtins
import api
import config
import core
import scriptHandler
import speech
import textInfos
import ui

from .writerTableNavCore import WriterIA2TableNavigator
from nvdaBuiltin.appModules import soffice as builtinSoffice

_nvdaCoreGettext = builtins._
addonHandler.initTranslation()

_TABLE_SPEECH_ORDER = "contentThenCell"
_TABLE_SPEECH_DELAY_MS = 200

# Translators: command category for the add-on.
SCRCAT_WRITER_IA2_TABLE = _("Writer IA2 Table Navigation")


class AppModule(builtinSoffice.AppModule):
	"""Minimal LibreOffice Writer alpha AppModule entry."""

	_writerIA2TableTextInfoPatchEnabled = False
	_writerTableBrailleCollapsedChunkPatchEnabled = True

	def event_NVDAObject_init(
		self,
		obj,
	) -> None:
		"""Use table-enabled SymphonyDocument for Writer documents."""
		super().event_NVDAObject_init(
			obj,
		)

		try:
			treeInterceptorClass = obj.treeInterceptorClass
		except (AttributeError, NotImplementedError):
			return

		# Let builtin soffice decide whether this object is a Writer
		# document. Only replace the exact SymphonyDocument selected by
		# the builtin AppModule.
		if treeInterceptorClass is not builtinSoffice.SymphonyDocument:
			return

		from .writerDocumentTableNavigation import (
			WriterTableNavigationSymphonyDocument,
		)

		obj.treeInterceptorClass = WriterTableNavigationSymphonyDocument

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
		"""Sync target table cell with Symphony focus and deferred speech."""
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
				treeInterceptor is not None and treeInterceptor.__class__.__name__ == "SymphonyDocument"
			)
		except Exception:
			syncResult["symphonyDocumentDetected"] = False

		try:
			api.setFocusObject(targetObj)
			syncResult["focusSetOk"] = True
		except Exception as e:
			syncResult["focusSetOk"] = False
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
			syncResult["speechOk"] = False
			if not syncResult.get("failReason"):
				syncResult["failReason"] = f"speech preparation failed: {e!r}"

		# Native Symphony paragraph focus owns braille presentation.
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
				navigator = self._getWriterIA2TableNavigator()
				apiFocusContext = navigator.getContextFromObject(apiFocusObj)
				apiFocusRowIndex = apiFocusContext.get("rowIndex")
				apiFocusColumnIndex = apiFocusContext.get("columnIndex")
				apiFocusMatchesTarget = apiFocusRowIndex == result.get(
					"targetRow",
				) and apiFocusColumnIndex == result.get("targetColumn")
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
			syncResult.get("focusSetOk") and syncResult.get("speechOk"),
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
			syncResult["failReason"] = repr(e)

		return syncResult

	def _getWriterIA2TableObjectContentText(self, obj) -> str:
		if obj is None:
			return ""

		contentText = ""

		try:
			value = getattr(obj, "value", None)
			if value:
				contentText = str(value)
		except Exception:
			pass

		if not contentText:
			try:
				contentText = str(obj.IAccessibleObject.accValue(0) or "")
			except Exception:
				contentText = ""

		if not contentText:
			try:
				displayText = getattr(obj, "displayText", "") or ""
				if displayText:
					contentText = str(displayText)
			except Exception:
				contentText = ""

		if not contentText:
			try:
				ti = obj.makeTextInfo(textInfos.POSITION_ALL)
				contentText = getattr(ti, "text", "") or ""
			except Exception:
				contentText = ""

		return contentText.strip()

	def _getWriterIA2TableChildContentText(self, obj) -> str:
		if obj is None:
			return ""

		try:
			childCount = int(getattr(obj, "childCount", 0) or 0)
		except Exception:
			childCount = 0

		if childCount <= 0:
			return ""

		parts = []
		for index in range(childCount):
			try:
				child = obj.getChild(index)
			except Exception:
				child = None

			if child is None:
				continue

			text = self._getWriterIA2TableObjectContentText(child)
			if text:
				parts.append(text)

		return "\n".join(parts).strip()

	def _getWriterIA2TableFocusedContentText(self, focusObj) -> str:
		"""Return text from the focused Writer IA2 table object or its text children."""
		text = self._getWriterIA2TableObjectContentText(focusObj)
		if text:
			return text

		return self._getWriterIA2TableChildContentText(focusObj)

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

	def _finishWriterIA2TableSymphonySpeech(
		self,
		result: dict[str, object],
		syncResult: dict[str, object],
	) -> None:
		"""Speak target cell content after natural Symphony paragraph focus settles."""
		delayedResult = dict(syncResult or {})
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
			contentText = _nvdaCoreGettext("blank")

		delayedResult["afterFocusContentIsBlank"] = contentIsBlank
		delayedResult["afterFocusContentText"] = contentText
		delayedResult["cellSpeechName"] = cellName
		delayedResult["reportTableCellCoords"] = self._shouldReportWriterIA2TableCellCoords()

		speechText = self._formatWriterIA2TableSpeech(
			contentText=contentText,
			cellName=cellName,
			result=result,
		)
		delayedResult["speechText"] = speechText
		delayedResult["speechOrder"] = _TABLE_SPEECH_ORDER

		try:
			speech.speakMessage(speechText)
			delayedResult["delayedSpeechOk"] = True
		except Exception as e:
			delayedResult["delayedSpeechOk"] = False
			delayedResult["delayedSpeechError"] = repr(e)

		try:
			self._lastWriterIA2TableSymphonyDelayedSpeechResult = delayedResult
		except Exception:
			pass

	def _getWriterIA2TableNavigator(self) -> WriterIA2TableNavigator:
		"""Return the persistent Writer IA2 table navigator for this AppModule."""
		navigator = getattr(
			self,
			"_writerIA2TableNavigator",
			None,
		)

		if navigator is None:
			navigator = WriterIA2TableNavigator()
			self._writerIA2TableNavigator = navigator

		return navigator

	def _moveWriterIA2TableCell(self, direction: str) -> None:
		"""Move to a nearby Writer table cell through IA2."""
		try:
			beforeFocus = api.getFocusObject()
		except Exception:
			beforeFocus = None

		navigator = self._getWriterIA2TableNavigator()
		result = navigator.move(
			beforeFocus,
			direction,
		)

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
			ui.message(_nvdaCoreGettext("Edge of table"))
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

	def _moveWriterIA2TableBoundary(
		self,
		movement: str,
		axis: str,
	) -> None:
		"""Move to the first or last Writer table cell on the requested axis."""
		navigator = self._getWriterIA2TableNavigator()
		result = navigator.moveToBoundary(
			api.getFocusObject(),
			movement,
			axis,
		)

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
			ui.message(
				_nvdaCoreGettext("Edge of table"),
			)
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

	def _ensureWriterIA2TableTextInfoPatchForFocus(
		self,
		focusObj: object | None = None,
		enabled: bool | None = None,
	) -> dict[str, object]:
		"""Lazy-install the Writer IA2 table TextInfo patch for the focused object.

		This is the mainline call-site helper. With the feature flag left off, the
		patch can be installed and exercised without injecting table ControlFields.
		"""
		result = {
			"called": True,
			"ok": False,
			"canProceed": False,
			"enabled": False,
			"focusObjExists": False,
			"focusObjClass": "",
			"focusObjModule": "",
			"textInfoMakeOk": False,
			"textInfoClass": "",
			"installed": False,
			"alreadyInstalled": False,
			"failReason": "",
		}

		if enabled is None:
			enabled = bool(getattr(self, "_writerIA2TableTextInfoPatchEnabled", False))
		result["enabled"] = bool(enabled)

		if focusObj is None:
			try:
				focusObj = api.getFocusObject()
			except Exception as e:
				result["failReason"] = "getFocusObjectException:%r" % e
				return result

		result["focusObjExists"] = focusObj is not None
		if focusObj is None:
			result["failReason"] = "focusObjMissing"
			return result

		try:
			result["focusObjClass"] = focusObj.__class__.__name__
			result["focusObjModule"] = focusObj.__class__.__module__
		except Exception:
			pass

		try:
			makeTextInfo = getattr(focusObj, "makeTextInfo", None)
			if not callable(makeTextInfo):
				result["failReason"] = "makeTextInfoMissing"
				return result

			textInfo = makeTextInfo(textInfos.POSITION_ALL)
			result["textInfoMakeOk"] = textInfo is not None
			if textInfo is None:
				result["failReason"] = "textInfoMissing"
				return result

			result["textInfoClass"] = textInfo.__class__.__name__
		except Exception as e:
			result["failReason"] = "makeTextInfoException:%r" % e
			return result

		installResult = self._lazyInstallWriterIA2TableTextInfoPatchManagerForTextInfo(
			textInfo,
			enabled=enabled,
		)
		result.update(
			{
				"ok": bool(installResult.get("ok")),
				"alreadyInstalled": bool(installResult.get("alreadyInstalled", False)),
				"installed": bool(installResult.get("installed", False)),
				"enabled": bool(installResult.get("enabled", False)),
				"failReason": installResult.get("failReason", ""),
			},
		)
		result["canProceed"] = bool(
			result.get("textInfoMakeOk") and result.get("installed") and not result.get("failReason"),
		)
		return result

	def _getWriterTableBrailleCollapsedChunkPatchManager(self):
		manager = getattr(
			self,
			"_writerTableBrailleCollapsedChunkPatchManager",
			None,
		)

		if manager is not None:
			return manager

		from .writerTableBrailleCollapsedChunkPatch import (
			WriterTableBrailleCollapsedChunkPatchManager,
		)

		manager = WriterTableBrailleCollapsedChunkPatchManager()

		self._writerTableBrailleCollapsedChunkPatchManager = manager

		return manager

	def _ensureWriterTableBrailleCollapsedChunkPatch(
		self,
	) -> dict[str, object]:
		enabled = bool(
			getattr(
				self,
				"_writerTableBrailleCollapsedChunkPatchEnabled",
				False,
			),
		)

		if not enabled:
			return {
				"ok": True,
				"installed": False,
				"enabled": False,
				"failReason": "",
			}

		manager = self._getWriterTableBrailleCollapsedChunkPatchManager()

		manager.setEnabled(True)

		result = manager.install()

		return {
			"ok": bool(result.get("ok")),
			"installed": bool(
				result.get("installed"),
			),
			"alreadyInstalled": bool(
				result.get(
					"alreadyInstalled",
					False,
				),
			),
			"enabled": manager.isEnabled(),
			"failReason": result.get(
				"failReason",
				"",
			),
		}

	def _restoreWriterTableBrailleCollapsedChunkPatchManager(
		self,
	) -> dict[str, object]:
		manager = getattr(
			self,
			"_writerTableBrailleCollapsedChunkPatchManager",
			None,
		)

		if manager is None:
			return {
				"ok": True,
				"alreadyRestored": True,
				"released": True,
				"failReason": "",
			}

		result = manager.restore()

		if not result.get("ok"):
			return {
				"ok": False,
				"alreadyRestored": False,
				"released": False,
				"failReason": result.get(
					"failReason",
					"",
				),
			}

		try:
			del self._writerTableBrailleCollapsedChunkPatchManager
			released = not hasattr(
				self,
				"_writerTableBrailleCollapsedChunkPatchManager",
			)
		except Exception:
			released = False

		return {
			"ok": True,
			"alreadyRestored": bool(
				result.get(
					"alreadyRestored",
					False,
				),
			),
			"released": released,
			"failReason": "",
		}

	def event_gainFocus(self, obj, nextHandler):
		"""Install Writer-specific lazy patches before native focus handling."""
		try:
			self._lastWriterIA2TableTextInfoPatchMainlineCallSiteResult = (
				self._ensureWriterIA2TableTextInfoPatchForFocus(obj)
			)
		except Exception as e:
			self._lastWriterIA2TableTextInfoPatchMainlineCallSiteResult = {
				"called": True,
				"ok": False,
				"canProceed": False,
				"failReason": "mainlineCallSiteException:%r" % e,
			}

		try:
			self._lastWriterTableBrailleCollapsedChunkPatchResult = (
				self._ensureWriterTableBrailleCollapsedChunkPatch()
			)
		except Exception as e:
			self._lastWriterTableBrailleCollapsedChunkPatchResult = {
				"ok": False,
				"installed": False,
				"enabled": False,
				"failReason": "mainlineCallSiteException:%r" % e,
			}

		finally:
			if callable(nextHandler):
				nextHandler()

	def _getWriterIA2TableTextInfoPatchManager(self):
		manager = getattr(self, "_writerIA2TableTextInfoPatchManager", None)
		if manager is not None:
			return manager

		try:
			from .writerIA2TableTextInfoPatch import WriterIA2TableTextInfoPatchManager
		except Exception:
			try:
				from appModules.writerIA2TableTextInfoPatch import WriterIA2TableTextInfoPatchManager
			except Exception:
				from writerIA2TableTextInfoPatch import WriterIA2TableTextInfoPatchManager

		manager = WriterIA2TableTextInfoPatchManager()
		manager.setEnabled(False)
		self._writerIA2TableTextInfoPatchManager = manager
		return manager

	def _installWriterIA2TableTextInfoPatchManagerForTextInfoClass(
		self,
		textInfoClass,
		enabled=None,
	) -> dict[str, object]:
		"""Install the Writer IA2 table TextInfo patch through AppModule lifecycle.

		By default the feature flag is off. Installing the patch should not
		inject table fields until the flag is explicitly enabled.
		"""
		manager = self._getWriterIA2TableTextInfoPatchManager()

		if enabled is None:
			enabled = bool(getattr(self, "_writerIA2TableTextInfoPatchEnabled", False))

		manager.setEnabled(enabled)
		result = manager.installForTextInfoClass(textInfoClass)

		if result.get("failReason") == "patchAlreadyInstalledForDifferentTextInfoClass":
			restoreResult = manager.restore()
			if restoreResult.get("ok"):
				result = manager.installForTextInfoClass(textInfoClass)
			else:
				return {
					"ok": False,
					"alreadyInstalled": False,
					"installed": manager.isInstalled(),
					"enabled": manager.isEnabled(),
					"failReason": "restoreBeforeReinstallFailed:%s" % restoreResult.get("failReason", ""),
				}

		return {
			"ok": bool(result.get("ok")),
			"alreadyInstalled": bool(result.get("alreadyInstalled", False)),
			"installed": manager.isInstalled(),
			"enabled": manager.isEnabled(),
			"failReason": result.get("failReason", ""),
		}

	def _lazyInstallWriterIA2TableTextInfoPatchManagerForTextInfo(
		self,
		textInfo,
		enabled=None,
	) -> dict[str, object]:
		"""Install the Writer IA2 table TextInfo patch only after a TextInfo exists.

		This keeps import/init paths inert. The default feature flag remains off
		unless enabled=True is explicitly passed or an AppModule flag enables it.
		"""
		if textInfo is None:
			return {
				"ok": False,
				"alreadyInstalled": False,
				"installed": False,
				"enabled": False,
				"textInfoClass": "",
				"failReason": "textInfoMissing",
			}

		textInfoClass = textInfo.__class__
		result = self._installWriterIA2TableTextInfoPatchManagerForTextInfoClass(
			textInfoClass,
			enabled=enabled,
		)

		return {
			"ok": bool(result.get("ok")),
			"alreadyInstalled": bool(result.get("alreadyInstalled", False)),
			"installed": bool(result.get("installed", False)),
			"enabled": bool(result.get("enabled", False)),
			"textInfoClass": textInfoClass.__name__,
			"failReason": result.get("failReason", ""),
		}

	def _restoreWriterIA2TableTextInfoPatchManager(self) -> dict[str, object]:
		"""Restore and release the Writer IA2 table TextInfo patch manager.

		This helper is safe to call more than once. AppModule.terminate() uses it
		so the TextInfo class patch does not survive reload.
		"""
		manager = getattr(self, "_writerIA2TableTextInfoPatchManager", None)
		if manager is None:
			return {
				"ok": True,
				"alreadyRestored": True,
				"released": True,
				"failReason": "",
			}

		try:
			result = manager.restore()
		except Exception as e:
			return {
				"ok": False,
				"alreadyRestored": False,
				"released": False,
				"failReason": "restoreException:%r" % e,
			}

		try:
			del self._writerIA2TableTextInfoPatchManager
			released = not hasattr(self, "_writerIA2TableTextInfoPatchManager")
		except Exception:
			released = False

		return {
			"ok": bool(result.get("ok")),
			"alreadyRestored": bool(result.get("alreadyRestored", False)),
			"released": released,
			"failReason": result.get("failReason", ""),
		}

	def terminate(self):
		"""Restore Writer-specific patches before AppModule shutdown."""
		try:
			textInfoRestoreResult = self._restoreWriterIA2TableTextInfoPatchManager()

			if not textInfoRestoreResult.get("ok"):
				try:
					from logHandler import log

					log.debugWarning(
						"Failed to restore Writer IA2 table TextInfo patch manager: %s"
						% textInfoRestoreResult.get(
							"failReason",
							"",
						),
					)
				except Exception:
					pass

		finally:
			try:
				brailleRestoreResult = self._restoreWriterTableBrailleCollapsedChunkPatchManager()

				if not brailleRestoreResult.get("ok"):
					try:
						from logHandler import log

						log.debugWarning(
							"Failed to restore Writer table braille collapsed chunk patch: %s"
							% brailleRestoreResult.get(
								"failReason",
								"",
							),
						)
					except Exception:
						pass

			finally:
				try:
					super().terminate()
				except AttributeError:
					pass

	@scriptHandler.script(
		# Translators: Input help mode message for moving to the previous row in a Writer table.
		description=_nvdaCoreGettext("moves to the previous table row"),
		category=SCRCAT_WRITER_IA2_TABLE,
		# gesture="kb:control+alt+upArrow",
	)
	def script_writerIA2TableMoveUp(self, gesture) -> None:
		self._moveWriterIA2TableCell("up")

	@scriptHandler.script(
		# Translators: Input help mode message for moving to the next row in a Writer table.
		description=_nvdaCoreGettext("moves to the next table row"),
		category=SCRCAT_WRITER_IA2_TABLE,
		# gesture="kb:control+alt+downArrow",
	)
	def script_writerIA2TableMoveDown(self, gesture) -> None:
		self._moveWriterIA2TableCell("down")

	@scriptHandler.script(
		# Translators: Input help mode message for moving to the previous column in a Writer table.
		description=_nvdaCoreGettext("moves to the previous table column"),
		category=SCRCAT_WRITER_IA2_TABLE,
		# gesture="kb:control+alt+leftArrow",
	)
	def script_writerIA2TableMoveLeft(self, gesture) -> None:
		self._moveWriterIA2TableCell("left")

	@scriptHandler.script(
		# Translators: Input help mode message for moving to the next column in a Writer table.
		description=_nvdaCoreGettext("moves to the next table column"),
		category=SCRCAT_WRITER_IA2_TABLE,
		# gesture="kb:control+alt+rightArrow",
	)
	def script_writerIA2TableMoveRight(self, gesture) -> None:
		self._moveWriterIA2TableCell("right")

	@scriptHandler.script(
		# Translators: Input help mode message for moving to the first row in a Writer table.
		description=_nvdaCoreGettext("moves to the first table row"),
		category=SCRCAT_WRITER_IA2_TABLE,
		# gesture="kb:control+alt+pageUp",
	)
	def script_writerIA2TableFirstRow(self, gesture) -> None:
		self._moveWriterIA2TableBoundary(
			"first",
			"row",
		)

	@scriptHandler.script(
		# Translators: Input help mode message for moving to the last row in a Writer table.
		description=_nvdaCoreGettext("moves to the last table row"),
		category=SCRCAT_WRITER_IA2_TABLE,
		# gesture="kb:control+alt+pageDown",
	)
	def script_writerIA2TableLastRow(self, gesture) -> None:
		self._moveWriterIA2TableBoundary(
			"last",
			"row",
		)

	@scriptHandler.script(
		# Translators: Input help mode message for moving to the first column in a Writer table.
		description=_nvdaCoreGettext("moves to the first table column"),
		category=SCRCAT_WRITER_IA2_TABLE,
		# gesture="kb:control+alt+home",
	)
	def script_writerIA2TableFirstColumn(self, gesture) -> None:
		self._moveWriterIA2TableBoundary(
			"first",
			"column",
		)

	@scriptHandler.script(
		# Translators: Input help mode message for moving to the last column in a Writer table.
		description=_nvdaCoreGettext("moves to the last table column"),
		category=SCRCAT_WRITER_IA2_TABLE,
		# gesture="kb:control+alt+end",
	)
	def script_writerIA2TableLastColumn(self, gesture) -> None:
		self._moveWriterIA2TableBoundary(
			"last",
			"column",
		)

	@scriptHandler.script(
		description=_nvdaCoreGettext(
			"Reads the row horizontally from the current cell rightwards to the last cell in the row.",
		),
		category=SCRCAT_WRITER_IA2_TABLE,
		gesture="kb:NVDA+control+alt+downArrow",
		speakOnDemand=True,
	)
	def script_sayAllWriterTableRow(self, gesture):
		import ui
		import api
		from .writerIA2TableSayAll import WriterIA2TableSayAllHandler

		result = WriterIA2TableSayAllHandler(updateCaret=True).sayAllRow(
			api.getFocusObject(),
		)

		if result.get("ok"):
			return

		message = result.get("message") or "Unable to read row"
		if message == "Not in a table cell":
			ui.message(_("Not in a table cell"))
			return

		ui.message(message)

	@scriptHandler.script(
		description=_nvdaCoreGettext(
			"Reads the column vertically from the current cell downwards to the last cell in the column.",
		),
		category=SCRCAT_WRITER_IA2_TABLE,
		gesture="kb:NVDA+control+alt+rightArrow",
		speakOnDemand=True,
	)
	def script_sayAllWriterTableColumn(self, gesture):
		import ui
		import api
		from .writerIA2TableSayAll import WriterIA2TableSayAllHandler

		result = WriterIA2TableSayAllHandler(updateCaret=True).sayAllColumn(
			api.getFocusObject(),
		)

		if result.get("ok"):
			return

		message = result.get("message") or "Unable to read column"
		if message == "Not in a table cell":
			ui.message(_("Not in a table cell"))
			return

		ui.message(message)

	@scriptHandler.script(
		description=_nvdaCoreGettext(
			"Reads the current row horizontally from left to right without moving the system caret.",
		),
		category=SCRCAT_WRITER_IA2_TABLE,
		gesture="kb:NVDA+control+alt+leftArrow",
		speakOnDemand=True,
	)
	def script_readCurrentWriterTableRow(self, gesture):
		import ui
		from .writerIA2TableSayAll import WriterIA2TableSayAllHandler

		result = WriterIA2TableSayAllHandler(
			updateCaret=False,
		).speakRow(
			api.getFocusObject(),
		)

		if result.get("ok"):
			return

		message = result.get("message", "")
		if message == "Not in a table cell":
			# Translators: The message reported when a user attempts to use a table movement command
			# when the cursor is not within a table.
			ui.message(_("Not in a table cell"))
			return

		ui.message(message or "Unable to read row")

	@scriptHandler.script(
		description=_nvdaCoreGettext(
			"Reads the current column vertically from top to bottom without moving the system caret.",
		),
		category=SCRCAT_WRITER_IA2_TABLE,
		gesture="kb:NVDA+control+alt+upArrow",
		speakOnDemand=True,
	)
	def script_readCurrentWriterTableColumn(self, gesture):
		import ui
		from .writerIA2TableSayAll import WriterIA2TableSayAllHandler

		result = WriterIA2TableSayAllHandler(
			updateCaret=False,
		).speakColumn(
			api.getFocusObject(),
		)

		if result.get("ok"):
			return

		message = result.get("message", "")
		if message == "Not in a table cell":
			# Translators: The message reported when a user attempts to use a table movement command
			# when the cursor is not within a table.
			ui.message(_("Not in a table cell"))
			return

		ui.message(message or "Unable to read column")

	__gestures = {
		"kb:control+alt+r": "sayAllWriterTableRow",
		"kb:control+alt+c": "sayAllWriterTableColumn",
	}
