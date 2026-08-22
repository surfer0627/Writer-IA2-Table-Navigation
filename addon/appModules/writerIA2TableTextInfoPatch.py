# A part of writerIa2TableNavigation add-on.
# This module manages optional TextInfo ControlField injection for Writer IA2 tables.

from __future__ import annotations

from typing import Any


class WriterIA2TableTextInfoPatchManager:
	"""Manage optional Writer IA2 table ControlField injection for TextInfo streams.

	This manager is intentionally inert until installForTextInfoClass is called.
	It should not change Writer behavior by merely being imported.
	"""

	def __init__(self, navigator: Any | None = None):
		if navigator is None:
			try:
				from .writerTableNavCore import WriterIA2TableNavigator
			except Exception:
				try:
					from appModules.writerTableNavCore import WriterIA2TableNavigator
				except Exception:
					from writerTableNavCore import WriterIA2TableNavigator

			navigator = WriterIA2TableNavigator()

		self._navigator = navigator
		self._enabled = False
		self._installed = False
		self._textInfoClass = None
		self._originalGetTextWithFields = None
		self.patchCallCount = 0
		self.lastException = ""

	def setEnabled(self, enabled: bool) -> None:
		self._enabled = bool(enabled)

	def isEnabled(self) -> bool:
		return bool(self._enabled)

	def isInstalled(self) -> bool:
		return bool(self._installed)

	def installForTextInfoClass(self, textInfoClass: object | None) -> dict[str, object]:
		if textInfoClass is None:
			return {
				"ok": False,
				"failReason": "textInfoClassMissing",
			}

		originalGetTextWithFields = getattr(textInfoClass, "getTextWithFields", None)
		if originalGetTextWithFields is None:
			return {
				"ok": False,
				"failReason": "originalGetTextWithFieldsMissing",
			}

		if self._installed:
			if self._textInfoClass is textInfoClass:
				return {
					"ok": True,
					"alreadyInstalled": True,
					"installed": True,
					"failReason": "",
				}
			return {
				"ok": False,
				"failReason": "patchAlreadyInstalledForDifferentTextInfoClass",
			}

		try:
			patchedGetTextWithFields = self._makePatchedGetTextWithFields(
				originalGetTextWithFields,
			)
			setattr(textInfoClass, "getTextWithFields", patchedGetTextWithFields)

			self._textInfoClass = textInfoClass
			self._originalGetTextWithFields = originalGetTextWithFields
			self._installed = True

			return {
				"ok": True,
				"alreadyInstalled": False,
				"installed": True,
				"failReason": "",
			}
		except Exception as e:
			self.lastException = repr(e)
			return {
				"ok": False,
				"failReason": "installException:%r" % e,
			}

	def _makePatchedGetTextWithFields(self, originalGetTextWithFields: object):
		manager = self

		def patchedGetTextWithFields(textInfoSelf, *args, **kwargs):
			manager.patchCallCount += 1
			nativeStream = []
			try:
				fallbackText = manager._getFallbackText(textInfoSelf)
				nativeStream = manager._normalizeStream(
					originalGetTextWithFields(textInfoSelf, *args, **kwargs),
					fallbackText,
				)

				if not manager._enabled:
					return nativeStream

				if manager._shouldSkipAdapterForTextInfo(textInfoSelf):
					return nativeStream

				if manager._hasExistingTableFields(nativeStream):
					return nativeStream

				candidate = manager._getCandidateForTextInfo(textInfoSelf)
				if not candidate.get("ok"):
					return nativeStream

				ok, integratedStream = manager._buildStream(
					candidate.get("tableField"),
					candidate.get("cellField"),
					nativeStream,
				)
				if not ok:
					return nativeStream

				return integratedStream
			except Exception as e:
				manager.lastException = repr(e)
				try:
					from logHandler import log

					log.debugWarning(
						"Writer IA2 table TextInfo patch failed; returning native stream",
						exc_info=True,
					)
				except Exception:
					pass
				return nativeStream

		return patchedGetTextWithFields

	def _getFallbackText(self, textInfo: object) -> str:
		try:
			text = getattr(textInfo, "text", "")
			if isinstance(text, str):
				return text
		except Exception:
			pass
		return ""

	def restore(self) -> dict[str, object]:
		if not self._installed:
			self._textInfoClass = None
			self._originalGetTextWithFields = None
			return {
				"ok": True,
				"alreadyRestored": True,
				"failReason": "",
			}

		textInfoClass = self._textInfoClass
		originalGetTextWithFields = self._originalGetTextWithFields

		if textInfoClass is None or originalGetTextWithFields is None:
			self._installed = False
			self._textInfoClass = None
			self._originalGetTextWithFields = None
			return {
				"ok": False,
				"failReason": "restoreStateMissing",
			}

		try:
			setattr(textInfoClass, "getTextWithFields", originalGetTextWithFields)
			restoredOk = getattr(textInfoClass, "getTextWithFields", None) is originalGetTextWithFields
			self._installed = False
			self._textInfoClass = None
			self._originalGetTextWithFields = None
			return {
				"ok": bool(restoredOk),
				"alreadyRestored": False,
				"failReason": "" if restoredOk else "restoreIdentityMismatch",
			}
		except Exception as e:
			self.lastException = repr(e)
			return {
				"ok": False,
				"alreadyRestored": False,
				"failReason": "restoreException:%r" % e,
			}

	def _normalizeStream(self, stream: object, fallbackText: str = "") -> list[object]:
		if stream is None:
			return [fallbackText] if fallbackText else []
		if isinstance(stream, str):
			return [stream] if stream else []
		try:
			return list(stream)
		except Exception:
			return [fallbackText] if fallbackText else []

	def _cloneField(self, field: object | None) -> object | None:
		if field is None:
			return None
		try:
			import textInfos

			cloned = textInfos.ControlField()
			for key, value in field.items():
				cloned[key] = value
			return cloned
		except Exception:
			return None

	def _isTableStart(self, item: object) -> bool:
		field = getattr(item, "field", None)
		if getattr(item, "command", None) != "controlStart" or field is None:
			return False
		try:
			return bool(
				field.get("table-id")
				and field.get("table-rownumber") is None
				and field.get("table-columnnumber") is None,
			)
		except Exception:
			return False

	def _isCellStart(self, item: object) -> bool:
		field = getattr(item, "field", None)
		if getattr(item, "command", None) != "controlStart" or field is None:
			return False
		try:
			return bool(
				field.get("table-id")
				and field.get("table-rownumber") is not None
				and field.get("table-columnnumber") is not None,
			)
		except Exception:
			return False

	def _countStarts(self, stream: list[object]) -> tuple[int, int]:
		tableCount = 0
		cellCount = 0
		for item in stream:
			if self._isTableStart(item):
				tableCount += 1
			if self._isCellStart(item):
				cellCount += 1
		return tableCount, cellCount

	def _hasExistingTableFields(self, stream: list[object]) -> bool:
		tableCount, cellCount = self._countStarts(stream)
		return bool(tableCount or cellCount)

	def _getCommandAndFieldFromStreamItem(
		self,
		item: object,
	) -> tuple[object | None, object | None]:
		"""Return command and field from a getTextWithFields stream item."""
		command = getattr(item, "command", None)
		field = getattr(item, "field", None)

		if command is not None or field is not None:
			return command, field

		try:
			if isinstance(item, tuple) and len(item) >= 2:
				return item[0], item[1]
		except Exception:
			pass

		return None, None

	def _getFieldValue(
		self,
		field: object | None,
		key: str,
	) -> object:
		if field is None:
			return None

		try:
			return field.get(key)
		except Exception:
			return None

	def _streamHasExistingTableOrCellField(
		self,
		stream: list[object],
	) -> bool:
		"""Return True if the native stream already has table/cell fields.

		The adapter should only fill a missing table field stream.  If the
		underlying TextInfo already provides TABLE / TABLECELL ControlFields, do
		not inject another synthetic writer-ia2-table:* table into the same
		stream.
		"""
		for item in stream:
			command, field = self._getCommandAndFieldFromStreamItem(item)

			if command != "controlStart" or field is None:
				continue

			tableID = self._getFieldValue(field, "table-id")
			rowNumber = self._getFieldValue(field, "table-rownumber")
			columnNumber = self._getFieldValue(field, "table-columnnumber")

			if tableID is not None:
				return True

			if rowNumber is not None or columnNumber is not None:
				return True

			try:
				roleText = repr(field.get("role")).upper()
			except Exception:
				roleText = ""

			if "TABLECELL" in roleText or "TABLE" in roleText:
				return True

		return False

	def _shouldSkipAdapterForTextInfo(
		self,
		textInfo: object,
	) -> bool:
		"""Return True if this TextInfo should keep its native table fields.

		SymphonyDocumentTextInfo already provides table / cell ControlFields.
		If the adapter is also injected into this path, the final stream can
		contain both native tableID=1 fields and writer-ia2-table:* fields.

		The adapter should fill missing table fields, not duplicate native ones.
		"""
		try:
			className = textInfo.__class__.__name__
		except Exception:
			className = ""

		try:
			moduleName = textInfo.__class__.__module__
		except Exception:
			moduleName = ""

		if className == "SymphonyDocumentTextInfo":
			return True

		if className.endswith("DocumentTextInfo") and "soffice" in moduleName:
			return True

		if self._isCalledFromDocumentTextInfo(textInfo):
			return True

		return False

	def _isCalledFromDocumentTextInfo(
		self,
		textInfo: object,
	) -> bool:
		"""Return True if this patched call is inside a document TextInfo path.

		SymphonyDocumentTextInfo can already provide table / cell ControlFields.
		However, its getTextWithFields() path may call into an inner
		SymphonyTextInfo.getTextWithFields(). Since the adapter patches that
		lower TextInfo class, checking only textInfo.__class__ is not enough.

		This helper walks a small number of Python frames and looks for an outer
		DocumentTextInfo instance in the call chain.
		"""
		try:
			import sys

			frame = sys._getframe()
		except Exception:
			return False

		depth = 0
		while frame is not None and depth < 25:
			try:
				localSelf = frame.f_locals.get("self")
			except Exception:
				localSelf = None

			if localSelf is not None and localSelf is not textInfo:
				try:
					className = localSelf.__class__.__name__
				except Exception:
					className = ""

				try:
					moduleName = localSelf.__class__.__module__
				except Exception:
					moduleName = ""

				if className == "SymphonyDocumentTextInfo":
					return True

				if className.endswith("DocumentTextInfo") and "soffice" in moduleName:
					return True

			frame = frame.f_back
			depth += 1

		return False

	def _buildStream(
		self,
		tableField: object | None,
		cellField: object | None,
		nativeStream: list[object],
	) -> tuple[bool, list[object]]:
		try:
			if self._streamHasExistingTableOrCellField(nativeStream):
				return True, nativeStream

			import textInfos

			tableStart = self._cloneField(tableField)
			cellStart = self._cloneField(cellField)
			tableEnd = self._cloneField(tableField)
			cellEnd = self._cloneField(cellField)

			if tableStart is None or cellStart is None or tableEnd is None or cellEnd is None:
				return False, nativeStream

			tableStart["_startOfNode"] = True
			cellStart["_startOfNode"] = True

			tableEnd.pop("_startOfNode", None)
			cellEnd.pop("_startOfNode", None)
			tableEnd["_endOfNode"] = True
			cellEnd["_endOfNode"] = True

			stream = [
				textInfos.FieldCommand("controlStart", tableStart),
				textInfos.FieldCommand("controlStart", cellStart),
			]
			stream.extend(nativeStream)
			stream.append(textInfos.FieldCommand("controlEnd", cellEnd))
			stream.append(textInfos.FieldCommand("controlEnd", tableEnd))
			return True, stream
		except Exception:
			return False, nativeStream

	def _getCandidateForTextInfo(self, textInfo: object) -> dict[str, object]:
		try:
			import api

			objectsToTry: list[object] = []

			textInfoObj = getattr(textInfo, "obj", None)
			if textInfoObj is not None:
				objectsToTry.append(textInfoObj)

			focusObj = api.getFocusObject()
			if focusObj is not None and not any(focusObj is obj for obj in objectsToTry):
				objectsToTry.append(focusObj)

			for obj in objectsToTry:
				context = self._navigator.getContextFromObject(obj) or {}
				if not context.get("inTable"):
					continue

				cellObj = context.get("cellObj")
				if cellObj is None:
					continue

				candidate = self._navigator._buildWriterIA2TableControlFieldCandidate(cellObj)
				if candidate.get("ok"):
					return candidate

			return {
				"ok": False,
				"failReason": "notInTable",
			}
		except Exception as e:
			self.lastException = repr(e)
			return {
				"ok": False,
				"failReason": "candidateException:%r" % e,
			}
