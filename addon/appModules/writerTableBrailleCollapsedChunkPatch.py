# -*- coding: UTF-8 -*-
from __future__ import annotations


class WriterTableBrailleCollapsedChunkPatchManager:
	"""Writer-only workaround plus passive TextInfoRegion live tracing."""

	_TRACE_UPDATE_LIMIT = 20

	def __init__(self):
		self._enabled = False
		self._installed = False
		self._targetClass = None
		self._originalMethod = None
		self._patchedMethod = None
		self._originalUpdate = None
		self._patchedUpdate = None

		self.patchCallCount = 0
		self.targetCollapsedCallCount = 0
		self.skipStateRestoreCount = 0
		self.lastException = ""

		self._traceUpdateCounter = 0
		self._traceUpdates = []
		self._activeUpdateRecord = None

	def setEnabled(self, enabled: bool) -> None:
		self._enabled = bool(enabled)

	def isEnabled(self) -> bool:
		return self._enabled

	def isInstalled(self) -> bool:
		return self._installed

	def clearTrace(self) -> None:
		self._traceUpdates = []

	def getTraceSnapshot(self) -> list[dict[str, object]]:
		result = []

		for updateRecord in self._traceUpdates:
			copied = dict(updateRecord)

			copied["calls"] = [
				dict(call)
				for call in updateRecord.get(
					"calls",
					[],
				)
			]

			result.append(copied)

		return result

	def _appendTraceUpdate(
		self,
		updateRecord: dict[str, object],
	) -> None:
		self._traceUpdates.append(
			updateRecord,
		)

		if len(self._traceUpdates) > self._TRACE_UPDATE_LIMIT:
			del self._traceUpdates[: -self._TRACE_UPDATE_LIMIT]

	def _getTextInfoRegionClass(self):
		import braille

		textInfoRegionClass = getattr(
			braille,
			"TextInfoRegion",
			None,
		)

		if textInfoRegionClass is not None:
			return textInfoRegionClass

		from braille.regions.textInfo import (
			TextInfoRegion,
		)

		return TextInfoRegion

	def _isWriterSymphonyDocumentTextInfo(
		self,
		info,
	) -> bool:
		if info is None:
			return False

		try:
			infoClass = info.__class__

			return bool(
				infoClass.__name__ == "SymphonyDocumentTextInfo"
				and infoClass.__module__.endswith(
					"appModules.soffice",
				),
			)
		except Exception:
			return False

	def _safeText(
		self,
		info,
	) -> str:
		try:
			return str(
				info.text,
			)
		except Exception as e:
			return f"<error:{e!r}>"

	def install(self) -> dict[str, object]:
		result = {
			"ok": False,
			"installed": self._installed,
			"alreadyInstalled": False,
			"enabled": self._enabled,
			"failReason": "",
		}

		if self._installed:
			result.update(
				{
					"ok": True,
					"installed": True,
					"alreadyInstalled": True,
				},
			)
			return result

		try:
			targetClass = self._getTextInfoRegionClass()

			originalMethod = getattr(
				targetClass,
				"_addTextWithFields",
				None,
			)

			originalUpdate = getattr(
				targetClass,
				"update",
				None,
			)

			if not callable(
				originalMethod,
			):
				result["failReason"] = "addTextWithFieldsMissing"
				return result

			if not callable(
				originalUpdate,
			):
				result["failReason"] = "updateMissing"
				return result

			if getattr(
				originalMethod,
				"_writerTableBrailleCollapsedChunkPatch",
				False,
			):
				result["failReason"] = "patchAlreadyInstalledByAnotherManager"
				return result

			if getattr(
				originalUpdate,
				"_writerTableBrailleLiveTracePatch",
				False,
			):
				result["failReason"] = "updatePatchAlreadyInstalledByAnotherManager"
				return result

			manager = self

			def patchedAddTextWithFields(
				region,
				info,
				formatConfig,
				isSelection=False,
			):
				manager.patchCallCount += 1

				isWriterInfo = manager._isWriterSymphonyDocumentTextInfo(
					info,
				)

				active = manager._activeUpdateRecord

				callRecord = None

				if isWriterInfo and active is not None:
					active["writerDetected"] = True

					try:
						collapsed = bool(
							info.isCollapsed,
						)
					except Exception:
						collapsed = False

					callRecord = {
						"callInUpdate": (
							len(
								active["calls"],
							)
							+ 1
						),
						"collapsed": collapsed,
						"text": (
							manager._safeText(
								info,
							)
						),
						"isSelection": bool(
							isSelection,
						),
						"skipBefore": bool(
							getattr(
								region,
								"_skipFieldsNotAtStartOfNode",
								False,
							),
						),
						"rawTextBefore": str(
							getattr(
								region,
								"rawText",
								"",
							),
						),
						"skipAfterOriginal": None,
						"skipRestored": False,
						"skipAfterFinal": None,
						"rawTextAfter": "",
						"exception": "",
					}

					active["calls"].append(
						callRecord,
					)

				try:
					collapsed = bool(
						info.isCollapsed,
					)
				except Exception:
					collapsed = False

				if not isWriterInfo or not manager._enabled or not collapsed:
					try:
						return originalMethod(
							region,
							info,
							formatConfig,
							isSelection=isSelection,
						)
					finally:
						if callRecord is not None:
							try:
								callRecord["skipAfterOriginal"] = bool(
									getattr(
										region,
										"_skipFieldsNotAtStartOfNode",
										False,
									),
								)

								callRecord["skipAfterFinal"] = callRecord["skipAfterOriginal"]

								callRecord["rawTextAfter"] = str(
									getattr(
										region,
										"rawText",
										"",
									),
								)
							except Exception as e:
								callRecord["exception"] = f"traceFinalize:{e!r}"

				manager.targetCollapsedCallCount += 1

				skipBefore = bool(
					getattr(
						region,
						"_skipFieldsNotAtStartOfNode",
						False,
					),
				)

				try:
					return originalMethod(
						region,
						info,
						formatConfig,
						isSelection=isSelection,
					)

				finally:
					try:
						skipAfterOriginal = bool(
							getattr(
								region,
								"_skipFieldsNotAtStartOfNode",
								False,
							),
						)

						skipRestored = skipAfterOriginal != skipBefore

						if skipRestored:
							region._skipFieldsNotAtStartOfNode = skipBefore

							manager.skipStateRestoreCount += 1

						if callRecord is not None:
							callRecord["skipAfterOriginal"] = skipAfterOriginal

							callRecord["skipRestored"] = skipRestored

							callRecord["skipAfterFinal"] = bool(
								getattr(
									region,
									"_skipFieldsNotAtStartOfNode",
									skipBefore,
								),
							)

							callRecord["rawTextAfter"] = str(
								getattr(
									region,
									"rawText",
									"",
								),
							)

					except Exception as e:
						manager.lastException = repr(e)

						if callRecord is not None:
							callRecord["exception"] = f"collapsedFinalize:{e!r}"

			def patchedUpdate(
				region,
			):
				manager._traceUpdateCounter += 1

				previousActive = manager._activeUpdateRecord

				updateRecord = {
					"updateId": (manager._traceUpdateCounter),
					"regionId": hex(
						id(region),
					),
					"writerDetected": False,
					"rawTextBefore": str(
						getattr(
							region,
							"rawText",
							"",
						),
					),
					"rawTextAfter": "",
					"skipBefore": bool(
						getattr(
							region,
							"_skipFieldsNotAtStartOfNode",
							False,
						),
					),
					"skipAfter": None,
					"cursorPosAfter": None,
					"readingInfoClassAfter": "",
					"readingInfoModuleAfter": "",
					"calls": [],
					"exception": "",
				}

				manager._activeUpdateRecord = updateRecord

				try:
					return originalUpdate(
						region,
					)

				except Exception as e:
					updateRecord["exception"] = repr(e)
					raise

				finally:
					try:
						updateRecord["rawTextAfter"] = str(
							getattr(
								region,
								"rawText",
								"",
							),
						)

						updateRecord["skipAfter"] = bool(
							getattr(
								region,
								"_skipFieldsNotAtStartOfNode",
								False,
							),
						)

						updateRecord["cursorPosAfter"] = getattr(
							region,
							"cursorPos",
							None,
						)

						readingInfo = getattr(
							region,
							"_readingInfo",
							None,
						)

						if readingInfo is not None:
							updateRecord["readingInfoClassAfter"] = readingInfo.__class__.__name__

							updateRecord["readingInfoModuleAfter"] = readingInfo.__class__.__module__

						if updateRecord["writerDetected"]:
							manager._appendTraceUpdate(
								updateRecord,
							)

					except Exception as e:
						manager.lastException = repr(e)

					finally:
						manager._activeUpdateRecord = previousActive

			patchedAddTextWithFields._writerTableBrailleCollapsedChunkPatch = True

			patchedUpdate._writerTableBrailleLiveTracePatch = True

			setattr(
				targetClass,
				"_addTextWithFields",
				patchedAddTextWithFields,
			)

			setattr(
				targetClass,
				"update",
				patchedUpdate,
			)

			self._targetClass = targetClass

			self._originalMethod = originalMethod

			self._patchedMethod = patchedAddTextWithFields

			self._originalUpdate = originalUpdate

			self._patchedUpdate = patchedUpdate

			self._installed = True

			result.update(
				{
					"ok": True,
					"installed": True,
				},
			)

			return result

		except Exception as e:
			self.lastException = repr(e)

			result["failReason"] = f"installException:{e!r}"

			return result

	def restore(self) -> dict[str, object]:
		result = {
			"ok": False,
			"alreadyRestored": False,
			"failReason": "",
		}

		if not self._installed:
			result.update(
				{
					"ok": True,
					"alreadyRestored": True,
				},
			)
			return result

		try:
			if (
				getattr(
					self._targetClass,
					"_addTextWithFields",
					None,
				)
				is not self._patchedMethod
			):
				result["failReason"] = "patchedAddTextWithFieldsChanged"
				return result

			if (
				getattr(
					self._targetClass,
					"update",
					None,
				)
				is not self._patchedUpdate
			):
				result["failReason"] = "patchedUpdateChanged"
				return result

			setattr(
				self._targetClass,
				"_addTextWithFields",
				self._originalMethod,
			)

			setattr(
				self._targetClass,
				"update",
				self._originalUpdate,
			)

			self._enabled = False
			self._installed = False
			self._targetClass = None
			self._originalMethod = None
			self._patchedMethod = None
			self._originalUpdate = None
			self._patchedUpdate = None
			self._activeUpdateRecord = None

			result["ok"] = True

			return result

		except Exception as e:
			self.lastException = repr(e)

			result["failReason"] = f"restoreException:{e!r}"

			return result
