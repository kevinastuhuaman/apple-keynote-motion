-- Export native Keynote renders from a local scratch copy.
--
-- Usage:
--   osascript export_keynote_visuals.applescript <deck.key> <out_dir> [mode]
--
-- mode: images (default), stages, or both
-- The caller must create <out_dir> before running this script.

on pathBasename(posixPath)
	set oldDelimiters to AppleScript's text item delimiters
	set AppleScript's text item delimiters to "/"
	set pathParts to text items of posixPath
	set AppleScript's text item delimiters to oldDelimiters
	return item -1 of pathParts
end pathBasename

on documentForPath(deckPath, expectedName)
	set expectedStem to expectedName
	if expectedName ends with ".key" and (length of expectedName) is greater than 4 then
		set expectedStem to text 1 thru -5 of expectedName
	end if
	using terms from application id "com.apple.Keynote"
		tell application id "com.apple.Keynote"
			repeat with candidate in documents
				try
					if POSIX path of (file of candidate) is deckPath then return candidate
				end try
			try
					if name of candidate is expectedName or name of candidate is expectedStem then return candidate
			end try
			end repeat
		end tell
	end using terms from
	return missing value
end documentForPath

on run argv
	if (count of argv) is less than 2 then
		error "usage: osascript export_keynote_visuals.applescript <deck.key> <out_dir> [images|stages|both]"
	end if

	set deckPath to item 1 of argv
	set outputRoot to item 2 of argv
	set exportMode to "images"
	if (count of argv) is greater than or equal to 3 then set exportMode to item 3 of argv
	if exportMode is not in {"images", "stages", "both"} then error "mode must be images, stages, or both"

	set expectedName to my pathBasename(deckPath)
	set slideImagesDir to outputRoot & "/slide-images"
	set allStagesPdf to outputRoot & "/all-stages.pdf"

	set docRef to my documentForPath(deckPath, expectedName)
	set openedHere to false

	using terms from application id "com.apple.Keynote"
		tell application id "com.apple.Keynote"
			with timeout of 3600 seconds
				if docRef is missing value then
					open (POSIX file deckPath)
					set openedHere to true
				end if

				set waitCount to 0
				repeat while docRef is missing value and waitCount is less than 1800
					set docRef to my documentForPath(deckPath, expectedName)
					if docRef is missing value then delay 1
					set waitCount to waitCount + 1
				end repeat
				if docRef is missing value then error "Keynote opened no document matching the requested path after 30 minutes: " & deckPath

				if exportMode is in {"images", "both"} then
					export docRef to (POSIX file slideImagesDir) as slide images with properties {image format:PNG, skipped slides:true}
				end if
				if exportMode is in {"stages", "both"} then
					export docRef to (POSIX file allStagesPdf) as PDF with properties {export style:IndividualSlides, all stages:true, skipped slides:true, PDF image quality:Best}
				end if

				if openedHere then close docRef saving no
			end timeout
		end tell
	end using terms from
end run
