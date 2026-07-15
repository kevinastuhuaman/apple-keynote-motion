-- Dump slide-level transition settings from an explicit or front Keynote document.
--
-- Usage:
--   osascript dump_slide_transition_settings.applescript [deck.key]

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

on pathBasename(posixPath)
	set oldDelimiters to AppleScript's text item delimiters
	set AppleScript's text item delimiters to "/"
	set pathParts to text items of posixPath
	set AppleScript's text item delimiters to oldDelimiters
	return item -1 of pathParts
end pathBasename

on documentForPath(deckPath, expectedName)
	using terms from application id "com.apple.Keynote"
		tell application id "com.apple.Keynote"
			repeat with candidate in documents
				try
					if POSIX path of (file of candidate) is deckPath then return candidate
				end try
				try
					if name of candidate is expectedName then return candidate
				end try
			end repeat
		end tell
	end using terms from
	return missing value
end documentForPath

on run argv
	set outputText to my emitLine({"slide_number", "skipped", "transition_effect", "transition_duration", "transition_delay", "automatic_transition"})
	set deckPath to ""
	if (count of argv) is greater than or equal to 1 then set deckPath to item 1 of argv
	set openedHere to false
	using terms from application id "com.apple.Keynote"
		tell application id "com.apple.Keynote"
			with timeout of 600 seconds
				if deckPath is "" then
					set docRef to front document
				else
					set expectedName to my pathBasename(deckPath)
					set docRef to my documentForPath(deckPath, expectedName)
					if docRef is missing value then
						open (POSIX file deckPath)
						set openedHere to true
					end if
					set waitCount to 0
					repeat while docRef is missing value and waitCount is less than 600
						set docRef to my documentForPath(deckPath, expectedName)
						if docRef is missing value then delay 1
						set waitCount to waitCount + 1
					end repeat
					if docRef is missing value then error "Could not bind requested Keynote document: " & deckPath
				end if
				set slideCount to count slides of docRef
				repeat with slideIndex from 1 to slideCount
					set slideRef to slide slideIndex of docRef
					set skippedText to skipped of slideRef
					set transitionRef to transition properties of slideRef
					set outputText to outputText & my emitLine({slideIndex, skippedText, transition effect of transitionRef, transition duration of transitionRef, transition delay of transitionRef, automatic transition of transitionRef})
				end repeat
				if openedHere then close docRef saving no
			end timeout
		end tell
	end using terms from
	return outputText
end run
