# TestStripper.py
import argparse, os, re, time
from pathlib import Path
from colorama import Fore, init
import pyperclip

'''
This program strips the speaker labels and timecodes from a text file produced by Adobe Premiere Pro's
"Export to Text File" for transcribed video sequences. It can optionally replace speaker labels with proper names.
'''


# Regex matching timecodes, e.g. 00:01:22:08 - 00:01:38:09
TIMECODE_PATTERN = "^[0-9]{2}:[0-9]{2}:[0-9]{2}:[0-9]{2} - [0-9]{2}:[0-9]{2}:[0-9]{2}:[0-9]{2}"
DEFAULT_EXT = ".txt"  # Default filename extension
DEFAULT_LABEL = "Speaker"  # Default speaker label to match in transcripts.
SEPARATOR = "-"  # Used when appending several transcripts to a single output file, to delineate transcript names.
DEFAULT_OUTPUT_FILENAME = f"output{DEFAULT_EXT}"

# Error codes for ParseFileException
PFE_NONEXISTANT = 1
PFE_FILE_ERROR = 2
PFE_SPEAKER_ERROR = 3


class ParseFileException(Exception):
	"""Exception thrown when the processFile function can't process a transcript file.
	Wrapper around several file i/o exceptions"""

	def __init__(self, message: str, code: int, line_num=0, line=""):
		super().__init__(message)
		self.code = code
		self.line_num = line_num
		self.line = line


def prompt_yn(question, default="yes"):
	"""Ask a y/n question via input() and return their answer as a boolean."""
	valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}

	if default is None:
		prompt = " [y/n] "
	elif default == "yes":
		prompt = " [Y/n] "
	elif default == "no":
		prompt = " [y/N] "
	else:
		raise ValueError(f"Invalid default answer: '{default}'")

	while True:
		print(question + prompt)
		choice = input().lower().strip()

		# Handle the 'Enter' key (default)
		if default is not None and choice == "":
			return valid[default]
		# Handle explicit answers
		elif choice in valid:
			return valid[choice]
		else:
			print("Please respond with 'yes' or 'no' (or 'y' or 'n').")


def get_unique_filename(test_filename: Path) -> Path:
	"""Takes a path. If something already exists there, append '_1' to the end of the file name.
	Keep incrementing that last number and checking until a unique filename is found.
	:returns: Path to the unique filename"""
	counter = 1
	# Grab "file" from "file_1" or just "file" from "file"
	base_stem = re.split(r"_(\d+)$", test_filename.stem, maxsplit=1)[0]
	new_path = test_filename

	# If it already had a number, start our counter one higher
	split = re.split(r"_(\d+)$", test_filename.stem, maxsplit=1)
	if len(split) > 1:
		counter = int(split[1]) + 1

	# Test if file with the name exists, and increment the trailing number till a unique file is found.
	while new_path.exists():
		new_path = test_filename.parent / f"{base_stem}_{counter}{test_filename.suffix}"
		counter += 1

	return new_path


def get_filename_header(filename: str) -> str:
	header = SEPARATOR * len(filename) + "\n"
	header += filename + "\n"
	header += SEPARATOR * len(filename) + "\n"
	return header

def get_pathstring_with_parent(path: Path) -> str:
	"""Returns the name of a path's parent dir along with its own name, e.g. 'files/file.txt'.
	Used to provide the user with a hint as to file locations, instead of just file names.
	:param path: Path object
	:returns: Path string: parent dir and file name
	"""
	if path == path.parent: return path.name  # Check if we're at the root of the filesystem.
	return path.parent.name + os.sep + path.name


speaker_arg_counter = 0  # Incremented with each new speaker in arguments


def speaker_pair(arg_string: str):
	"""Converts cmd line arguments '-s 1=NameA 2=NameB' or '-s NameA NameB' into a ('Label', 'Name') tuple."""
	global speaker_arg_counter
	speaker_arg_counter += 1
	arg_string = arg_string.strip()

	if re.search(r"(\d+)=", arg_string):  # Find pattern, e.g. '1=John'
		parts = arg_string.split('=', 1)  # Split along the =
		if len(parts) != 2: raise argparse.ArgumentTypeError(f"'{arg_string}' must be 'XXX=Name' or just 'Name'.")
		label = f"{DEFAULT_LABEL} " + parts[0]  # Use our default label
		return label, parts[1]
	else:
		return f"{DEFAULT_LABEL} {speaker_arg_counter}", arg_string


def is_transcript(path: Path) -> bool:
	"""Verify that a file is a valid transcript by checking if the first line is a timecode.
	:param path: Path object"""
	if path.is_file():
		try:  # Read the first line and try to match it to the timecode pattern
			with open(path.resolve(), 'r', encoding='utf-8') as file:
				line = file.readline()
				return bool(re.search(TIMECODE_PATTERN, line))

		except FileNotFoundError:
			raise ParseFileException(f"File doesn't exist: '{get_pathstring_with_parent(path)}'",
									 PFE_NONEXISTANT)
		except (PermissionError, OSError, UnicodeDecodeError) as e:
			raise ParseFileException(f"{e}",
									 PFE_FILE_ERROR)
	return False


def parse_transcript(path: Path, speaker_map: dict, keep_timecodes=False, speaker_label=DEFAULT_LABEL) \
		-> tuple[dict, str]:
	"""
	Reads through a transcript file, replaces speaker labels with proper names, and,
	optionally, strips timecodes. Writes the processed transcript to a file.
	:param path: Path to the transcript file to read from.
	:param keep_timecodes: True if timecodes should be preserved in the output
	:param speaker_map: Mapping from speaker labels to speaker names.
	:param speaker_label: Label to match speaker names against.
	:return: Tuple[dict, str]: dict(Label, Name) representing the speakers found in the transcript, and
	a string containing the processed text.
	:raises ProcessFileException: If processing fails.
	"""
	found_speakers = dict()  # Keep a ledger of label/speaker pairs found in this transcript.
	try:

		with open(path.resolve(), 'r', encoding='utf-8') as file:
			output = ""  # Buffer for the processed text

			for line_num, line in enumerate(file, start=1):
				line = line.strip()

				# Check if the line is a timecode
				if re.search(TIMECODE_PATTERN, line):
					if keep_timecodes: output += line + "\n"  # If we're keeping timecodes, append to output.
					continue

				# Check if line is a speaker label
				if re.match(rf"^{speaker_label} (\d+)", line):
					if line in speaker_map:  # Speaker label found in speaker_map
						if not line in found_speakers: found_speakers[line] = speaker_map[line]
						output += speaker_map[line] + "\n"
						continue
					else:  # We've encountered an unidentified speaker.
						raise ParseFileException(f"Improper speaker label '{line}'",
												 code=PFE_SPEAKER_ERROR, line_num=line_num, line=line)

				# Line isn't a speaker label or timecode, so just append it to the output.
				output += line + "\n"

			return found_speakers, output

	except FileNotFoundError as e:
		raise ParseFileException(f"File doesn't exist: '{e.filename}'", PFE_NONEXISTANT)

	except (PermissionError, OSError, UnicodeDecodeError) as e:
		raise ParseFileException(f"Read error for '{e.filename}'", PFE_NONEXISTANT)


def get_args():
	"""Parses command line arguments."""
	parser = argparse.ArgumentParser(description=f'Removes timecodes from a text file produced by '
												 'Adobe Premiere Pro\'s "Export to Text File" for transcribed '
												 'video sequences. Can optionally replace speaker labels '
												 f'(e.g. \'{DEFAULT_LABEL} 1\') with proper names, and consolidate '
												 f'multiple transcripts into one output file.')
	parser.add_argument("path", type=str,
						help="path to transcript file or directory containing transcript files. Supports"
							 "wildcard '*' matching.")
	parser.add_argument("-e", "--extension", type=str, default=DEFAULT_EXT,
						help=f"filename extension for directory processing, default is '{DEFAULT_EXT}'")
	parser.add_argument("-i", "--interactive", default=False, action="store_true",
						help="prompt for user input")
	parser.add_argument("-o", "--output", type=str,
						help="output filename or directory. Can be relative to input directory.")
	parser.add_argument("-r", "--recursive", default=False, action="store_true",
						help="search subdirectories recursively for transcript files.")
	parser.add_argument("-w", "--wildcard", default=False, action="store_true",
						help="Wildcard matching ('*') in input filename.")
	parser.add_argument("-s", "--speakers", default=[], type=speaker_pair, action="append",
						nargs='+', help="speaker label and name, e.g. '1=John' or just 'John' "
										"(with automatic numbering).")
	parser.add_argument("-t", "--timecodes", default=False, action="store_true",
						help="preserve timecodes")
	parser.add_argument("-v", "--verbose", default=False, action="store_true",
						help="display results and errors for each file processed")
	parser.add_argument("-x", "--overwrite", default=False, action="store_true",
						help="overwrite existing files")
	parser.add_argument("-l", "--label", type=str, default=DEFAULT_LABEL,
						help=f"speaker label (to match in transcripts). Default is '{DEFAULT_LABEL}'")
	parser.add_argument("-ex", "--extra", default=[], type=str, action="append",
						nargs='+', help="Extra speaker names for missing speakers.")
	return parser.parse_args()


def main(args):
	# Get arguments from argparse into local variables
	arg_ext = args.extension
	arg_keep_timecodes = args.timecodes
	arg_overwrite = args.overwrite
	arg_verbose = args.verbose
	arg_interactive = args.interactive
	arg_recursive = args.recursive
	arg_label = args.label
	arg_inpath = Path(args.path)
	arg_wildcard = args.wildcard
	arg_extra = args.extra

	init(autoreset=True)  # Set up colorama text colors

	#----------------------------------
	#HANDLE SPEAKERS
	# ----------------------------------
	# Create speaker_map, populate with args or use a default entry.
	speaker_map = {}
	if args.speakers:
		for item in args.speakers:
			if isinstance(item, list):
				speaker_map.update(dict(item))  # Handles the action="append" list-of-lists
			else:
				speaker_map.update([item])  # Handles a simple list of tuples
	else:
		speaker_map = {f"{arg_label} 1": f"{arg_label} 1"}  # e.g. 'Speaker 1: Speaker 1'

	# If we've supplied a label argument, update all the labels in speaker_map
	if arg_label != DEFAULT_LABEL:
		arg_label = args.label.strip()
		new_map = dict()
		for key, value in speaker_map.items():
			new_map[f"{arg_label} {key.split(' ', 1)[1]}"] = value
		speaker_map = new_map

	# ----------------------------------
	#HANDLE INPUT PATH
	# ----------------------------------
	# Check that the input path argument can be resolved on the filesystem.
	try:
		if arg_wildcard:  # If we're wildcard matching the filenames, just check the parent dir.
			arg_inpath.parent.resolve(strict=True)  # Strict checking. Input path must exist on the filesystem.

		else:
			arg_inpath.resolve(strict=True)

		# If input path can't be resolved, exit or prompt to revise and recheck.
	except (OSError, RuntimeError, FileNotFoundError) as e:
		print(Fore.RED + f"Input path is invalid: '{arg_inpath}'")
		if arg_verbose: print(Fore.RED + f"Error: {e}")
		exit(1)

	# ----------------------------------
	# HANDLE OUTPUT PATH
	# ----------------------------------
	arg_outpath = Path(args.output) if args.output else arg_inpath
	try:
		# If out_path is relative, make it relative to input path
		if not arg_outpath.is_absolute():
			arg_outpath = arg_inpath / arg_outpath if arg_inpath.is_dir() else arg_inpath.parent / arg_outpath
		arg_outpath.resolve()
	except (OSError, RuntimeError) as e:
		print(Fore.RED + f"Output path is invalid: '{arg_outpath}'")
		if arg_verbose: print(Fore.RED + f"Error: {e}")
		exit(1)
	if not arg_outpath.suffix == args.extension: # if outpath is a dir, make sure it exists
		arg_outpath.mkdir(parents=True, exist_ok=True)

	# Set up some stats collection.
	success_list = list()  # Dict containing successfully processed file input and output pairs.
	fail_list: list[Path] = []  # List of input files that failed to process.
	start_time = time.perf_counter()  # Track time to complete processing.

	# ----------------------------------
	# CORRELATE INPUT AND OUTPUT FILES
	# ----------------------------------
	# Build a list of input files to process.
	in_paths = list()
	is_clipping = False
	if arg_wildcard:
		if arg_recursive:
			in_paths = list(arg_inpath.parent.rglob(arg_inpath.name))
		else:
			in_paths = list(arg_inpath.parent.glob(arg_inpath.name))
	else:
		if arg_inpath.is_dir():
			in_paths = list(arg_inpath.rglob("*" + arg_ext)) if arg_recursive else list(arg_inpath.glob("*" + arg_ext))
		else:
			is_clipping = True
			in_paths = [arg_inpath]

	# Build a list of valid input and output file pairs.
	in_out_paths = []
	for path in in_paths:
		try:
			if not is_transcript(path): continue # First, check if we're looking at a valid transcript file.

			if arg_outpath.is_dir():
				if arg_inpath.is_dir():
					in_out_paths.append((path, arg_outpath / path.relative_to(arg_inpath)))
				else:
					in_out_paths.append((path, arg_outpath / path.relative_to(arg_inpath.parent)))
			else:
				in_out_paths.append((path, arg_outpath))
		except ParseFileException as e:  # This exception wraps together several  i/o exceptions.
			print(Fore.RED + f"Error reading {get_pathstring_with_parent(path)}.")
			if arg_verbose: print(Fore.RED + f"\t{str(e)}\n")
			fail_list.append(path)
			continue

	if len(in_out_paths) == 0: # Double-check to make sure we've identified some transcripts.
		print(Fore.RED + f"No transcript files found.")
		exit(0)

	# ----------------------------------
	# PROCESS EACH INPUT/OUTPUT PAIR
	# ----------------------------------
	# Now, parse each file pair
	for in_file, out_file in in_out_paths:

		max_extra_speaker = 0
		if arg_verbose: print(f"{get_pathstring_with_parent(in_file)}:")

		# Handle the overwrite argument. Create a unique filename for out_file if needed.
		if out_file.exists():
			if arg_overwrite:
				if arg_verbose: print(Fore.RED + f"\tOverwriting '{get_pathstring_with_parent(out_file)}'.")
			else:
				if arg_outpath.is_dir():
					out_file = get_unique_filename(out_file)  # Create a unique filename for out_file.
					if arg_verbose: print(Fore.RED + f"\tFile already exists, writing instead to: "
													 f"'{get_pathstring_with_parent(out_file)}'.")

		# Try processing the transcript. This loop is here to handle unidentified speakers. If a speaker can't be
		# identified, ParseFileException is raised. Prompt for speaker name or use the default speaker, and reprocess.
		# New added speaker names will be used in subsequent processing.
		success = False
		while not success:
			try:
				found_speakers, out_string = parse_transcript(in_file, speaker_map, keep_timecodes=arg_keep_timecodes,
															  speaker_label=arg_label)
				lines = len(out_string.splitlines())

				# Write to separate files or append to one file, depending on arg_outpath.
				out_file.parent.mkdir(parents=True, exist_ok=True)
				if arg_outpath.is_dir():
					with open(out_file, 'w', encoding='utf-8') as file:
						file.write(out_string)
				else: #arg_outpath doesn't point to a dir, so every intput file writes to the same output. Append.
					with open(out_file, 'a', encoding='utf-8') as file:
						if len(success_list) == 0: file.truncate(0)  # Clear out_file if this is first file.
						# Add header text for each new input transcript.
						if len(in_out_paths) > 1: file.write(get_filename_header(in_file.stem))
						else: file.write(out_string) #Else there's just one input file, so don't use

						if is_clipping: pyperclip.copy(out_string) #Add to system clipboard.

				# Successfully processed and wrote transcript!
				success = True  # Exit the while loop
				success_list.append((in_file, out_file))  # Add to ledger of successfully processed files.
				if arg_verbose:  # Print a little report for this transcript.
					print(f"\tSuccessfully processed '{get_pathstring_with_parent(in_file)}'")
					names = [found_speakers[k] for k in sorted(found_speakers)]
					total_speakers = len(found_speakers)
					if total_speakers > 0:
						print(
							f"\tFound {total_speakers} speaker{"" if total_speakers == 1 else "s"}: {", ".join(names)}")
					print(f"\tWrote {lines} lines to '{get_pathstring_with_parent(out_file)}'\n")
					if is_clipping: print("Copied to clipboard.")

			except ParseFileException as e:
				if e.code == PFE_SPEAKER_ERROR:  # We've found a missing speaker. Add an entry to speaker_map
					name = e.line
					if arg_verbose: print(Fore.RED + f"\tMissing speaker '{e.line}' at line {e.line_num}.")
					if arg_extra:
						test_speaker_num = 0
						while arg_label + " " + str(test_speaker_num) in speaker_map:
							test_speaker_num += 1
						name = arg_extra[max_extra_speaker]
						max_extra_speaker += 1
					elif arg_interactive: name = input(f"\tName for {e.line}: ")

					speaker_map[e.line] = name  # Create a new entry in speaker_map
				# Now return to while loop and re-process file with new speaker_map

				else:  # Handle other errors.
					print(Fore.RED + f"Error while processing file: '{get_pathstring_with_parent(in_file)}'"
									 f"\n\t{str(e)}\n")
					fail_list.append(in_file)
					continue

			# ParseFileException wraps file i/o errors for the input file, so these are only raised when writing.
			except FileNotFoundError as e:
				print(Fore.RED + f"Output file doesn't exist: '{get_pathstring_with_parent(out_file)}'"
								 f"\n\t{str(e)}\n")
				fail_list.append(in_file)
				continue
			except PermissionError as e:
				print(Fore.RED + f"Improper permissions for output file: '{get_pathstring_with_parent(out_file)}'"
								 f"\n\t{str(e)}\n")
				fail_list.append(in_file)
				continue
			except OSError as e:
				print(Fore.RED + f"Filesystem Error for output file: {e}")
				fail_list.append(in_file)
				continue

	# Calculate time taken to process files.
	end_time = time.perf_counter()

	# Finished processing all files, print results.
	if arg_verbose:
		print(Fore.CYAN + "----- REPORT -----")
		print(f"Total processing time: {(end_time - start_time):.3f} seconds.\n")

	print(f"Successfully processed {len(success_list)} {"files" if len(success_list) != 1 else "file"}"
		  f"{":" if arg_verbose and len(success_list) != 0 else "."}")

	if arg_verbose:
		for pair in success_list: print(f"\t{get_pathstring_with_parent(pair[0])}" + Fore.CYAN + " ---> " +
												Fore.RESET + f"{get_pathstring_with_parent(pair[1])}")

	if len(fail_list) > 0:
		print(Fore.RED + f"Failed to process {len(fail_list)} {"files" if len(fail_list) != 1 else "file"}"
						 f"{":" if arg_verbose else "."}")
		if arg_verbose:
			for path in fail_list: print(f"\t{get_pathstring_with_parent(path)}")

# ------------------- MAIN -------------------
if __name__ == "__main__":
	try:
		main(get_args())
	except KeyboardInterrupt:
		print(Fore.RED + "Operation cancelled by user.")
		exit(1)