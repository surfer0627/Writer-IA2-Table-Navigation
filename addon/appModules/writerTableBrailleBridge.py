"""Braille bridge helpers for Writer IA2 table navigation.

This module bridges a Writer IA2 table field sequence to NVDA's native
TextInfoRegion pipeline. It intentionally does not update the real braille
handler. Callers should build the TABLE / TABLECELL field sequence elsewhere
and pass it into these wrappers.
"""

from __future__ import annotations

from typing import Any

import textInfos


def normalizeTextForTextInfoRegion(text: str | None) -> tuple[str, bool]:
	"""Return text safe for TextInfoRegion.

	TextInfoRegion may treat an empty text range as collapsed and skip
	getTextWithFields. For an empty table cell, use a single space so the
	range remains non-collapsed while the TABLE / TABLECELL fields can still be
	processed by NVDA's native braille formatter.

	Returns:
		(text, usedPlaceholder)
	"""
	if text:
		return text, False
	return " ", True


def _makeOffsetsBookmark(startOffset: int, endOffset: int) -> object | None:
	offsetsType = getattr(textInfos, "Offsets", None)
	if offsetsType is None:
		return None

	try:
		return offsetsType(startOffset=startOffset, endOffset=endOffset)
	except Exception:
		try:
			return offsetsType(startOffset, endOffset)
		except Exception:
			return None


class WriterTableFieldSequenceObjectWrapper:
	"""Temporary NVDAObject-like wrapper for TextInfoRegion.

	This wrapper is intentionally small. It delegates object properties to the
	real focused object, but returns WriterTableFieldSequenceTextInfo from
	makeTextInfo so TextInfoRegion can consume a prepared field sequence.
	"""

	def __init__(
		self,
		baseObj: object,
		baseInfo: object | None,
		fieldSequence: list[object],
		text: str,
	) -> None:
		self._baseObj = baseObj
		self._baseInfo = baseInfo
		self._fieldSequence = fieldSequence
		self._text = text
		self.isTextSelectionAnchoredAtStart = False

	def __getattr__(self, name: str) -> object:
		return getattr(self._baseObj, name)

	@property
	def role(self):
		return getattr(self._baseObj, "role", None)

	@property
	def states(self):
		return getattr(self._baseObj, "states", set())

	def makeTextInfo(self, position):
		if position == textInfos.POSITION_ALL:
			return WriterTableFieldSequenceTextInfo(
				self,
				self._baseInfo,
				list(self._fieldSequence),
				self._text,
				0,
				len(self._text),
			)

		if position == textInfos.POSITION_FIRST:
			return WriterTableFieldSequenceTextInfo(
				self,
				self._baseInfo,
				list(self._fieldSequence),
				self._text,
				0,
				0,
			)

		if position == textInfos.POSITION_LAST:
			return WriterTableFieldSequenceTextInfo(
				self,
				self._baseInfo,
				list(self._fieldSequence),
				self._text,
				len(self._text),
				len(self._text),
			)

		# TextInfoRegion first asks POSITION_SELECTION. Return a collapsed
		# cursor at the start so update() can expand the readingInfo later.
		return WriterTableFieldSequenceTextInfo(
			self,
			self._baseInfo,
			list(self._fieldSequence),
			self._text,
			0,
			0,
		)


class WriterTableFieldSequenceTextInfo:
	"""Synthetic TextInfo-like wrapper for Writer table field sequences."""

	def __init__(
		self,
		obj: object,
		baseInfo: object | None,
		fieldSequence: list[object],
		text: str,
		startOffset: int,
		endOffset: int,
	) -> None:
		self.obj = obj
		self._baseInfo = baseInfo
		self._fieldSequence = fieldSequence
		self._text = text
		self._startOffset = max(0, min(startOffset, len(text)))
		self._endOffset = max(0, min(endOffset, len(text)))

		try:
			self.bookmark = baseInfo.bookmark if baseInfo is not None else None
		except Exception:
			self.bookmark = None

		if self.bookmark is None:
			self.bookmark = _makeOffsetsBookmark(self._startOffset, self._endOffset)

	def __getattr__(self, name: str) -> object:
		if self._baseInfo is not None:
			return getattr(self._baseInfo, name)
		raise AttributeError(name)

	def copy(self):
		return WriterTableFieldSequenceTextInfo(
			self.obj,
			self._baseInfo,
			list(self._fieldSequence),
			self._text,
			self._startOffset,
			self._endOffset,
		)

	@property
	def text(self) -> str:
		return self._text[self._startOffset:self._endOffset]

	@property
	def isCollapsed(self) -> bool:
		return self._startOffset == self._endOffset

	def collapse(self, end: bool = False) -> None:
		if end:
			self._startOffset = self._endOffset
		else:
			self._endOffset = self._startOffset

	def expand(self, unit) -> None:
		self._startOffset = 0
		self._endOffset = len(self._text)
		self.bookmark = _makeOffsetsBookmark(self._startOffset, self._endOffset)

	def setEndPoint(self, other, relation: str) -> None:
		otherStart = getattr(other, "_startOffset", 0)
		otherEnd = getattr(other, "_endOffset", otherStart)

		if relation == "endToStart":
			self._endOffset = otherStart
		elif relation == "startToStart":
			self._startOffset = otherStart
		elif relation == "endToEnd":
			self._endOffset = otherEnd
		elif relation == "startToEnd":
			self._startOffset = otherEnd

		if self._startOffset > self._endOffset:
			self._startOffset = self._endOffset

		self.bookmark = _makeOffsetsBookmark(self._startOffset, self._endOffset)

	def compareEndPoints(self, other, relation: str) -> int:
		otherStart = getattr(other, "_startOffset", 0)
		otherEnd = getattr(other, "_endOffset", otherStart)

		if relation == "startToStart":
			left = self._startOffset
			right = otherStart
		elif relation == "endToEnd":
			left = self._endOffset
			right = otherEnd
		elif relation == "startToEnd":
			left = self._startOffset
			right = otherEnd
		elif relation == "endToStart":
			left = self._endOffset
			right = otherStart
		else:
			left = self._startOffset
			right = otherStart

		if left < right:
			return -1
		if left > right:
			return 1
		return 0

	def move(self, unit, direction: int, endPoint=None) -> int:
		return 0

	def updateCaret(self) -> None:
		if self._baseInfo is None:
			return

		try:
			self._baseInfo.updateCaret()
		except Exception:
			pass

	def getControlFieldBraille(self, field, ancestors, reportStart, formatConfig):
		return textInfos.TextInfo.getControlFieldBraille(
			self,
			field,
			ancestors,
			reportStart,
			formatConfig,
		)

	def getTextWithFields(self, *args, **kwargs):
		if self.isCollapsed:
			return []

		if self._startOffset == 0 and self._endOffset == len(self._text):
			return list(self._fieldSequence)

		text = self.text
		if not text:
			return []
		return [text]


def createTextInfoRegionObject(
	baseObj: object,
	baseInfo: object | None,
	fieldSequence: list[object],
	text: str | None,
) -> tuple[WriterTableFieldSequenceObjectWrapper, str, bool]:
	"""Create a TextInfoRegion-ready object wrapper.

	Returns:
		(wrapperObj, bridgeText, usedPlaceholder)
	"""
	bridgeText, usedPlaceholder = normalizeTextForTextInfoRegion(text)
	wrapperObj = WriterTableFieldSequenceObjectWrapper(
		baseObj,
		baseInfo,
		fieldSequence,
		bridgeText,
	)
	return wrapperObj, bridgeText, usedPlaceholder

