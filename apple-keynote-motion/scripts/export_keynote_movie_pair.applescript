on run argv
	if (count of argv) is not 4 then error "Usage: export_keynote_movie_pair.applescript deck.key output.m4v first_slide last_slide"

	set sourcePath to item 1 of argv
	set outputPath to item 2 of argv
	set firstSlide to (item 3 of argv) as integer
	set lastSlide to (item 4 of argv) as integer

	if sourcePath is outputPath then error "Source and output paths must differ."
	if firstSlide < 1 or lastSlide < firstSlide then error "Invalid slide range."

	tell application "System Events"
		if not (exists disk item sourcePath) then error "Source deck not found: " & sourcePath
		if exists disk item outputPath then error "Refusing to overwrite existing output: " & outputPath
	end tell

	tell application id "com.apple.Keynote"
		with timeout of 1800 seconds
			activate
			set sourceFile to (my POSIX file sourcePath)
			set outputFile to (my POSIX file outputPath)
			set referenceDocument to open sourceFile
			try
				set slideCount to count of slides of referenceDocument
				if lastSlide > slideCount then error "Slide range exceeds document count of " & slideCount
				repeat with slideIndex from 1 to slideCount
					set skipped of slide slideIndex of referenceDocument to (slideIndex < firstSlide or slideIndex > lastSlide)
				end repeat
				export referenceDocument to outputFile as QuickTime movie with properties {movie format:format1080p, movie codec:h264, movie framerate:FPS60}
				close referenceDocument saving no
			on error errorMessage number errorNumber
				try
					close referenceDocument saving no
				end try
				error errorMessage number errorNumber
			end try
		end timeout
	end tell

	return outputPath
end run
