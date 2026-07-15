-- Bulk dump slide transition settings and object geometry from an explicit or front Keynote document.
--
-- Usage:
--   osascript dump_keynote_native_state_bulk.applescript [deck.key] [start_slide] [end_slide]

on replaceText(theText, searchString, replacementString)
	set oldDelimiters to AppleScript's text item delimiters
	set AppleScript's text item delimiters to searchString
	set textParts to text items of theText
	set AppleScript's text item delimiters to replacementString
	set joinedText to textParts as text
	set AppleScript's text item delimiters to oldDelimiters
	return joinedText
end replaceText

on cleanValue(theValue)
	if theValue is missing value then return ""
	set theText to theValue as text
	set theText to my replaceText(theText, tab, " ")
	set theText to my replaceText(theText, return, " ")
	set theText to my replaceText(theText, linefeed, " ")
	return theText
end cleanValue

on joinFields(fieldList)
	set oldDelimiters to AppleScript's text item delimiters
	set AppleScript's text item delimiters to tab
	set cleanedFields to {}
	repeat with fieldValue in fieldList
		set end of cleanedFields to my cleanValue(fieldValue)
	end repeat
	set joinedText to cleanedFields as text
	set AppleScript's text item delimiters to oldDelimiters
	return joinedText
end joinFields

on emitLine(fieldList)
	return (my joinFields(fieldList) & linefeed)
end emitLine

on listValue(valueList, valueIndex)
	try
		return item valueIndex of valueList
	on error
		return ""
	end try
end listValue

on pointX(pointList, valueIndex)
	try
		return item 1 of item valueIndex of pointList
	on error
		return ""
	end try
end pointX

on pointY(pointList, valueIndex)
	try
		return item 2 of item valueIndex of pointList
	on error
		return ""
	end try
end pointY

on emitBulkObjects(slideIndex, kindText, objectCount, nameList, identityList, positionList, widthList, heightList, rotationList, opacityList, lockedList, extraList)
	set outputText to ""
	repeat with objectIndex from 1 to objectCount
		set outputText to outputText & (my emitLine({"object", slideIndex, kindText, objectIndex, my listValue(nameList, objectIndex), my listValue(identityList, objectIndex), my pointX(positionList, objectIndex), my pointY(positionList, objectIndex), my listValue(widthList, objectIndex), my listValue(heightList, objectIndex), my listValue(rotationList, objectIndex), my listValue(opacityList, objectIndex), my listValue(lockedList, objectIndex), my listValue(extraList, objectIndex)}))
	end repeat
	return outputText
end emitBulkObjects

on documentForPath(deckPath)
	using terms from application id "com.apple.Keynote"
		tell application id "com.apple.Keynote"
			repeat with candidate in documents
				try
					if POSIX path of (file of candidate) is deckPath then return candidate
				end try
			end repeat
		end tell
	end using terms from
	return missing value
end documentForPath

on run argv
	set outputText to ""
	set deckPath to ""
	set argumentOffset to 0
	if (count of argv) is greater than or equal to 1 then
		set firstArgument to item 1 of argv as text
		if firstArgument ends with ".key" then
			set deckPath to firstArgument
			set argumentOffset to 1
		end if
	end if
	set requestedStart to 1
	set requestedEnd to 0
	if (count of argv) is greater than or equal to (argumentOffset + 1) then set requestedStart to (item (argumentOffset + 1) of argv) as integer
	if (count of argv) is greater than or equal to (argumentOffset + 2) then set requestedEnd to (item (argumentOffset + 2) of argv) as integer

	set outputText to outputText & (my emitLine({"record", "slide_number", "object_type", "object_index", "object_name", "identity_text", "x", "y", "width", "height", "rotation", "opacity", "locked", "extra"}))

	using terms from application id "com.apple.Keynote"
		tell application id "com.apple.Keynote"
			with timeout of 3600 seconds
				set openedHere to false
				if deckPath is "" then
					set docRef to front document
				else
					set docRef to my documentForPath(deckPath)
					if docRef is missing value then
						open (POSIX file deckPath)
						set openedHere to true
					end if
					set waitCount to 0
					repeat while docRef is missing value and waitCount is less than 1800
						set docRef to my documentForPath(deckPath)
						if docRef is missing value then delay 1
						set waitCount to waitCount + 1
					end repeat
					if docRef is missing value then error "Could not bind requested Keynote document: " & deckPath
				end if
				set slideCount to count slides of docRef
				set documentWidth to ""
				set documentHeight to ""
				set keynoteVersion to ""
				try
					set documentWidth to width of docRef
					set documentHeight to height of docRef
					set keynoteVersion to version
				end try
				set outputText to outputText & (my emitLine({"document", "", "", "", "", "", "", "", documentWidth, documentHeight, "", "", "", "keynote_version=" & (keynoteVersion as text) & "; slide_count=" & (slideCount as text)}))
				if requestedEnd is 0 or requestedEnd is greater than slideCount then set requestedEnd to slideCount

				repeat with slideIndex from requestedStart to requestedEnd
					set slideRef to slide slideIndex of docRef
					set transitionEffectText to ""
					set transitionDurationText to ""
					set transitionDelayText to ""
					set automaticTransitionText to ""
					try
						set transitionRef to transition properties of slideRef
						set transitionEffectText to transition effect of transitionRef
						set transitionDurationText to transition duration of transitionRef
						set transitionDelayText to transition delay of transitionRef
						set automaticTransitionText to automatic transition of transitionRef
					end try
					set skippedText to ""
					set baseLayoutText to ""
					try
						set skippedText to skipped of slideRef
					end try
					try
						set baseLayoutText to name of base layout of slideRef
					end try
					set outputText to outputText & (my emitLine({"slide", slideIndex, "", "", "", "", "", "", "", "", "", "", skippedText, "effect=" & (transitionEffectText as text) & "; duration=" & (transitionDurationText as text) & "; delay=" & (transitionDelayText as text) & "; automatic=" & (automaticTransitionText as text) & "; base_layout=" & (baseLayoutText as text)}))

					set objectCount to count images of slideRef
					if objectCount is greater than 0 then
						set outputText to outputText & (my emitBulkObjects(slideIndex, "image", objectCount, {}, file name of every image of slideRef, position of every image of slideRef, width of every image of slideRef, height of every image of slideRef, rotation of every image of slideRef, opacity of every image of slideRef, locked of every image of slideRef, {}))
					end if

					set objectCount to count text items of slideRef
					if objectCount is greater than 0 then
						set outputText to outputText & (my emitBulkObjects(slideIndex, "text item", objectCount, {}, object text of every text item of slideRef, position of every text item of slideRef, width of every text item of slideRef, height of every text item of slideRef, rotation of every text item of slideRef, opacity of every text item of slideRef, locked of every text item of slideRef, {}))
					end if

					set objectCount to count shapes of slideRef
					if objectCount is greater than 0 then
						set outputText to outputText & (my emitBulkObjects(slideIndex, "shape", objectCount, {}, object text of every shape of slideRef, position of every shape of slideRef, width of every shape of slideRef, height of every shape of slideRef, rotation of every shape of slideRef, opacity of every shape of slideRef, locked of every shape of slideRef, background fill type of every shape of slideRef))
					end if

					set objectCount to count groups of slideRef
					if objectCount is greater than 0 then
						set outputText to outputText & (my emitBulkObjects(slideIndex, "group", objectCount, {}, {}, position of every group of slideRef, width of every group of slideRef, height of every group of slideRef, rotation of every group of slideRef, {}, {}, {}))
					end if

					set objectCount to count movies of slideRef
					if objectCount is greater than 0 then
						set outputText to outputText & (my emitBulkObjects(slideIndex, "movie", objectCount, {}, file name of every movie of slideRef, position of every movie of slideRef, width of every movie of slideRef, height of every movie of slideRef, rotation of every movie of slideRef, opacity of every movie of slideRef, locked of every movie of slideRef, {}))
					end if

					set objectCount to count lines of slideRef
					if objectCount is greater than 0 then
						set outputText to outputText & (my emitBulkObjects(slideIndex, "line", objectCount, {}, {}, start point of every line of slideRef, {}, {}, rotation of every line of slideRef, {}, locked of every line of slideRef, end point of every line of slideRef))
					end if

					set objectCount to count tables of slideRef
					if objectCount is greater than 0 then
						set outputText to outputText & (my emitBulkObjects(slideIndex, "table", objectCount, {}, {}, position of every table of slideRef, width of every table of slideRef, height of every table of slideRef, {}, {}, locked of every table of slideRef, {}))
					end if

					set objectCount to count charts of slideRef
					if objectCount is greater than 0 then
						set outputText to outputText & (my emitBulkObjects(slideIndex, "chart", objectCount, {}, {}, position of every chart of slideRef, width of every chart of slideRef, height of every chart of slideRef, rotation of every chart of slideRef, {}, locked of every chart of slideRef, {}))
					end if

					set objectCount to count audio clips of slideRef
					if objectCount is greater than 0 then
						set outputText to outputText & (my emitBulkObjects(slideIndex, "audio clip", objectCount, {}, file name of every audio clip of slideRef, position of every audio clip of slideRef, width of every audio clip of slideRef, height of every audio clip of slideRef, rotation of every audio clip of slideRef, {}, locked of every audio clip of slideRef, clip volume of every audio clip of slideRef))
					end if
				end repeat
				if openedHere then close docRef saving no
			end timeout
		end tell
	end using terms from
	return outputText
end run
